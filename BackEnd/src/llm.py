import os
import sqlite3
from sqlite3 import Error
import json
import asyncio
import logging
from typing import Any, Callable, TypeVar
from datetime import datetime
from email.utils import parsedate_to_datetime
from fastapi import HTTPException
from pydantic_ai import Agent, RunContext
from db_manager import get_db_connection
from db_crypto import decrypt_value, UndecryptableValue

# Configure logging
logger = logging.getLogger(__name__)

# Debug mode flag
DEBUG = os.environ.get("DEBUG", "").lower() in ("true", "1", "yes")

# Type variable for return type
T = TypeVar('T')

# System prompt every agent falls back to when the caller doesn't supply one. Exposed
# as a constant so callers that need to layer something on top - voice_manager's
# compose_system_prompt() - build on the exact text used here rather than a copy of it.
DEFAULT_SYSTEM_PROMPT = (
    'You are a professional digital marketing expert. '
    'Generate output in HTML format using only p, b,i,em,u,a,ul,ol,br,h1,h2 elements.'
)

# Retry configuration
MAX_RETRIES = 5
INITIAL_BACKOFF = 1.0  # seconds
MAX_BACKOFF = 60.0  # seconds

# Provider tokens pydantic-ai accepts as a "<provider>:<model>" prefix. Stored model
# names carry one (the shipped default is "google-gla:gemini-2.0-flash") because they
# used to be handed to infer_model() as a bare string. The explicit model classes take
# the model name on its own, so the prefix has to come off - but only when it really is
# a provider token, never at the first colon of an arbitrary name.
_PROVIDER_PREFIXES = frozenset({
    "openai", "openai-chat", "gemini", "google-gla", "anthropic", "claude",
})


def strip_model_prefix(model_name: str) -> str:
    """Drop a leading "<provider>:" from a stored model name, if present."""
    if not model_name:
        return model_name
    prefix, separator, remainder = model_name.partition(":")
    if separator and prefix in _PROVIDER_PREFIXES:
        return remainder
    return model_name


def mask_api_key(api_key: str) -> str:
    """
    Mask an API key for safe logging, showing only first 4 and last 4 characters.

    Args:
        api_key: The API key to mask

    Returns:
        Masked API key string (e.g., "sk-a***************xyz")
    """
    if not api_key or len(api_key) < 8:
        return "****"

    return f"{api_key[:4]}{'*' * (len(api_key) - 8)}{api_key[-4:]}"


def extract_retry_delay(exception: Exception) -> float | None:
    """
    Extract retry delay from exception headers or response body.

    Checks in order:
    1. Retry-After header (number of seconds or HTTP date)
    2. retryDelay/retry_delay in response body (JSON)
    3. retryAfter in response body (JSON)

    Args:
        exception: The exception that may contain response headers/body

    Returns:
        Number of seconds to wait, or None if not found
    """
    response = None
    headers = None

    # Try to get response from various exception types
    if hasattr(exception, 'response') and exception.response is not None:
        response = exception.response
        if hasattr(response, 'headers'):
            headers = response.headers
    elif hasattr(exception, '__cause__') and exception.__cause__:
        if hasattr(exception.__cause__, 'response'):
            response = exception.__cause__.response
            if hasattr(response, 'headers'):
                headers = response.headers
        elif hasattr(exception.__cause__, 'headers'):
            headers = exception.__cause__.headers

    # First, try Retry-After header
    if headers is not None:
        retry_after_value = None
        if hasattr(headers, 'get'):
            # Dict-like interface
            retry_after_value = headers.get('Retry-After') or headers.get('retry-after')
        else:
            # Try to iterate if it's a different structure
            try:
                for key, value in headers.items():
                    if key.lower() == 'retry-after':
                        retry_after_value = value
                        break
            except (AttributeError, TypeError):
                pass

        if retry_after_value:
            # Parse the Retry-After value
            try:
                # Try parsing as integer (seconds)
                return float(retry_after_value)
            except (ValueError, TypeError):
                pass

            # Try parsing as HTTP date
            try:
                retry_datetime = parsedate_to_datetime(str(retry_after_value))
                now = datetime.now(retry_datetime.tzinfo)
                delta = (retry_datetime - now).total_seconds()
                return max(0, delta)  # Don't return negative values
            except (ValueError, TypeError):
                pass

    # Second, try to extract from response body
    if response is not None:
        try:
            # Get response body/content
            response_body = None
            if hasattr(response, 'json'):
                # Try to get JSON response (httpx/requests style)
                try:
                    response_body = response.json() if callable(response.json) else response.json
                except:
                    pass
            elif hasattr(response, 'text'):
                # Try to parse text as JSON
                try:
                    response_text = response.text() if callable(response.text) else response.text
                    response_body = json.loads(response_text)
                except:
                    pass
            elif hasattr(response, 'content'):
                # Try to parse content as JSON
                try:
                    response_content = response.content() if callable(response.content) else response.content
                    if isinstance(response_content, bytes):
                        response_content = response_content.decode('utf-8')
                    response_body = json.loads(response_content)
                except:
                    pass

            # Look for retry delay in response body
            if response_body and isinstance(response_body, dict):
                # Check various field names (case-insensitive)
                for key in ['retryDelay', 'retry_delay', 'retryAfter', 'retry_after', 'retryIn', 'retry_in']:
                    if key in response_body:
                        try:
                            return float(response_body[key])
                        except (ValueError, TypeError):
                            pass
                    # Also check lowercase version
                    key_lower = key.lower()
                    if key_lower in response_body:
                        try:
                            return float(response_body[key_lower])
                        except (ValueError, TypeError):
                            pass
        except Exception:
            # Silently ignore errors when trying to parse response body
            pass

    return None


async def retry_with_exponential_backoff(
    func: Callable[..., Any],
    *args,
    max_retries: int = MAX_RETRIES,
    initial_backoff: float = INITIAL_BACKOFF,
    max_backoff: float = MAX_BACKOFF,
    **kwargs
) -> Any:
    """
    Retry an async function with exponential backoff on HTTP 429 errors.

    Args:
        func: The async function to retry
        max_retries: Maximum number of retry attempts
        initial_backoff: Initial backoff time in seconds
        max_backoff: Maximum backoff time in seconds
        *args, **kwargs: Arguments to pass to the function

    Returns:
        The result of the function call

    Raises:
        The last exception if all retries are exhausted
    """
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            result = await func(*args, **kwargs)

            # Log success
            if attempt == 0:
                logger.info("LLM request completed successfully on first attempt")
            else:
                logger.info(f"LLM request completed successfully after {attempt} retry(ies)")

            return result
        except Exception as e:
            last_exception = e

            # Check if this is a rate limit error (429)
            is_rate_limit = False
            error_message = str(e).lower()

            # Check for HTTP 429 in various exception types
            if hasattr(e, 'status_code') and e.status_code == 429:
                is_rate_limit = True
            elif hasattr(e, 'status') and e.status == 429:
                is_rate_limit = True
            elif '429' in error_message or 'rate limit' in error_message or 'too many requests' in error_message:
                is_rate_limit = True
            elif hasattr(e, '__cause__') and e.__cause__:
                cause_message = str(e.__cause__).lower()
                if '429' in cause_message or 'rate limit' in cause_message:
                    is_rate_limit = True

            # If not a rate limit error, raise immediately
            if not is_rate_limit:
                raise

            # If we've exhausted retries, raise the last exception
            if attempt == max_retries:
                logger.error(f"Max retries ({max_retries}) exceeded for rate limit error")
                raise

            # Check for retry delay from headers or response body
            retry_delay = extract_retry_delay(e)

            if retry_delay is not None:
                # Use the provided retry delay, but cap it at max_backoff
                backoff_time = min(retry_delay, max_backoff)
                logger.warning(
                    f"Rate limit error (429) encountered. "
                    f"Server specified retry delay: {retry_delay:.2f}s. "
                    f"Retry {attempt + 1}/{max_retries} after {backoff_time:.2f}s. "
                    f"Error: {str(e)}"
                )
            else:
                # Calculate backoff time with exponential growth
                backoff_time = min(initial_backoff * (2 ** attempt), max_backoff)
                logger.warning(
                    f"Rate limit error (429) encountered. "
                    f"No retry delay specified by server. "
                    f"Retry {attempt + 1}/{max_retries} after {backoff_time:.2f}s (exponential backoff). "
                    f"Error: {str(e)}"
                )

            # Wait before retrying
            await asyncio.sleep(backoff_time)

    # This should never be reached, but just in case
    if last_exception:
        raise last_exception


class LLM:
    def __init__(self, llm_name, system_prompt=None, tools=None):
        # Configure basic logging if not already configured
        if not logger.handlers:
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )

        self.llm_selected = get_llm(llm_name)

        print(f"[LLM] Initializing LLM: {self.llm_selected.get('name')} "
              f"(id: {self.llm_selected.get('id')}, "
              f"model: {self.llm_selected.get('model')}, "
              f"APIstyle: {self.llm_selected.get('APIstyle')})")
        logger.info(
            f"Initializing LLM: {self.llm_selected.get('name')} "
            f"(id: {self.llm_selected.get('id')}, "
            f"model: {self.llm_selected.get('model')}, "
            f"APIstyle: {self.llm_selected.get('APIstyle')})"
        )

        if system_prompt is None:
            system_prompt = DEFAULT_SYSTEM_PROMPT

        model = self._build_model()

        if tools is None:
            tools = []
        try:
            self.llm_agent = Agent(
                model,
                deps_type=list,
                output_type=str,
                system_prompt=system_prompt,
                tools=tools
            )
            print(f"[LLM] Agent created successfully for {self.llm_selected.get('name')}")
            logger.info(f"LLM Agent created successfully for {self.llm_selected.get('name')}")
        except Exception as e:
            print(f"[LLM] ERROR creating Agent: {str(e)}")
            logger.error(f"Error creating Agent for {self.llm_selected.get('name')}: {str(e)}", exc_info=DEBUG)
            raise

    def _build_model(self):
        """
        Build the pydantic-ai model for this configuration, passing the API key
        straight to the provider.

        The key is deliberately never written to os.environ. Agents are built per
        request from the requesting user's own llms row, and this process serves
        every user - a key parked in the environment would be a key any other
        user's request could pick up.

        Returns:
            A pydantic-ai model instance, or the bare model-name string for an
            APIstyle we don't construct explicitly (infer_model() then resolves it
            from the ambient environment, which is what google-vertex/ADC needs).
        """
        api_style = self.llm_selected.get("APIstyle")
        api_url = self.llm_selected.get("APIurl")
        api_key = self.llm_selected.get("APIkey")
        model_name = strip_model_prefix(self.llm_selected.get("model"))
        masked_key = mask_api_key(api_key) if api_key else "None"

        print(f"[LLM] Building model for APIstyle: {api_style} (key: {masked_key})")

        try:
            match api_style:
                case "openai":
                    from pydantic_ai.models.openai import OpenAIChatModel
                    from pydantic_ai.providers.openai import OpenAIProvider
                    if api_url:
                        # Local / self-hosted OpenAI-compatible server: it may not
                        # want a key at all, but the provider insists on a value.
                        provider = OpenAIProvider(base_url=api_url, api_key=api_key or "no-key-required")
                        print(f"[LLM] OpenAIChatModel: model={model_name}, base_url={api_url}")
                    else:
                        provider = OpenAIProvider(api_key=api_key)
                        print(f"[LLM] OpenAIChatModel: model={model_name}")
                    return OpenAIChatModel(model_name or "local-model", provider=provider)
                case "gemini":
                    from pydantic_ai.models.google import GoogleModel
                    from pydantic_ai.providers.google import GoogleProvider
                    print(f"[LLM] GoogleModel: model={model_name}")
                    return GoogleModel(model_name, provider=GoogleProvider(api_key=api_key))
                case "claude":
                    from pydantic_ai.models.anthropic import AnthropicModel
                    from pydantic_ai.providers.anthropic import AnthropicProvider
                    print(f"[LLM] AnthropicModel: model={model_name}")
                    return AnthropicModel(model_name, provider=AnthropicProvider(api_key=api_key))
        except ImportError as e:
            print(f"[LLM] WARNING: provider SDK for APIstyle '{api_style}' is not installed ({e}); "
                  f"falling back to model-name inference")
            logger.warning(
                f"Provider SDK for APIstyle '{api_style}' unavailable ({e}); "
                f"falling back to model-name inference"
            )
            return self.llm_selected.get("model")

        # Unrecognised APIstyle (e.g. google-vertex): hand pydantic-ai the raw model
        # string, prefix included, and let it resolve credentials however it normally
        # would. The configured APIkey is not used on this path.
        print(f"[LLM] Unknown APIstyle '{api_style}'; inferring model from name: {self.llm_selected.get('model')}")
        logger.warning(f"Unknown APIstyle '{api_style}'; configured APIkey will not be used")
        return self.llm_selected.get("model")

    async def invoke(self, messages):
        """
        Invoke the LLM with retry logic for HTTP 429 responses.

        Args:
            messages: The messages to send to the LLM

        Returns:
            The LLM response result

        Raises:
            Exception: If all retries are exhausted or a non-429 error occurs
        """
        print(f"[LLM] Sending message ({len(str(messages))} chars):\n{str(messages)[:500]}{'...' if len(str(messages)) > 500 else ''}")
        logger.info(f"Sending message to LLM ({len(str(messages))} chars)")

        result = await retry_with_exponential_backoff(
            self.llm_agent.run,
            messages
        )

        print(f"[LLM] Raw output: {repr(result.output)[:500]}")
        logger.info(f"LLM output received ({len(str(result.output or ''))} chars)")
        if DEBUG:
            for i, msg in enumerate(result.all_messages()):
                print(f"[LLM] Message[{i}]: {repr(msg)[:300]}")

        return result


def get_llm(llm):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Check if llms table exists
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='llms'")
    table_exists = cur.fetchone()
    
    if not table_exists:
        # Table doesn't exist, create it and load data
        from persist_data import _create_table_if_not_exists
        _create_table_if_not_exists(cur, "llms")
        conn.commit()
        conn.close()
        
        # Load data from YAML files
        from load_llms import main as load_llms_main
        load_llms_main()
        
        # Reconnect after loading data
        conn = get_db_connection()
        cur = conn.cursor()
    
    # Now perform the actual query
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    sql = f'''
        SELECT  id,name,APIstyle,APIkey,APIurl,model FROM llms WHERE id=?;
    '''
    cur.execute(sql,[llm])
    rows = cur.fetchall()
    if not rows:
        # Agents are resolved per request now, so an id the client still holds after
        # the LLM was deleted in Config Manager reaches here. Say so, rather than
        # raising IndexError - and never silently substitute a different model, which
        # is what made query_history.llm untrustworthy in the first place.
        conn.close()
        raise HTTPException(status_code=404, detail=f"No LLM configured with id '{llm}'")
    result = dict(rows[0])

    try:
        result["APIkey"] = decrypt_value(result["APIkey"])
    except UndecryptableValue:
        # Never guess here: without the real key there is nothing to send the provider,
        # and the stored value is left exactly as it is rather than rewritten.
        conn.close()
        raise HTTPException(
            status_code=500,
            detail=f"The stored API key for LLM '{llm}' could not be decrypted; "
                   f"the database encryption key may have changed"
        )

    conn.close()
    return result