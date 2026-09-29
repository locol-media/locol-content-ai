# set up the LLM, right now pointing to the local LLM


from llm import LLM, DEFAULT_SYSTEM_PROMPT
from prompt import prompt_rag, prompt
from voice_manager import get_voice_prompt, compose_system_prompt
from models import LLMQuery, LLMResponse
from persist_history import insert_query_history
from quill_html_to_delta import html_to_delta, extract_html
from quill_op import delta_to_plain_text
import json
import logging
import os

# Configure logging
logger = logging.getLogger(__name__)

# Debug mode flag
DEBUG = os.environ.get("DEBUG", "").lower() in ("true", "1", "yes")

# Placeholder standing in for the retrieved context in prompt_rag(). There is no
# retriever wired up - the Chroma/embedding scaffolding that would have supplied one
# was never connected and has been removed - so the RAG branch below sends this instead.
# Kept as-is rather than dropped because rag_on_off is still live: the editor persists
# it to query_history and generate_project_items sets it True.
NO_RETRIEVED_CONTEXT = "x"

def content_agent_create(llm_name="default", voice_prompt=None):
    """
    Build a content generation agent for the calling request.

    The result is request-scoped and deliberately not cached anywhere. This process
    serves every user from one interpreter, and LLM configurations - including API
    keys - live in per-user databases resolved through a ContextVar. An agent held
    past the end of a request would carry one user's key and model into the next
    user's generation.

    Args:
        llm_name: The LLM configuration ID to use (default: "default")
        voice_prompt: Saved writing-style prompt to write in, or None for the
            neutral house style

    Returns:
        A new LLM instance

    Raises:
        HTTPException: 404 if no LLM is configured under that id
        Exception: If LLM initialization fails
    """
    try:
        print(f"[RAG] Creating content agent with LLM: {llm_name}"
              f"{' (voice applied)' if voice_prompt else ''}")
        logger.info(f"Creating content agent with LLM: {llm_name}")
        # Default system prompt (digital marketing expert), with the selected voice
        # layered on top when the request carried one.
        if voice_prompt:
            agent = LLM(llm_name, compose_system_prompt(DEFAULT_SYSTEM_PROMPT, voice_prompt))
        else:
            agent = LLM(llm_name)
        print(f"[RAG] Content agent created successfully: {agent.llm_selected.get('name')}")
        logger.info(f"Content agent created successfully: {agent.llm_selected.get('name')}")
        return agent
    except Exception as e:
        print(f"[RAG] ERROR: Failed to create content agent with LLM {llm_name}: {str(e)}")
        logger.error(f"Failed to create content agent with LLM {llm_name}: {str(e)}", exc_info=DEBUG)
        raise


async def invoke(query: LLMQuery, response_model=LLMResponse):
    """
    Invoke the content generation agent with RAG support.

    Args:
        query: LLM query containing context, prompts, and configuration
        response_model: Response model type (default: LLMResponse)

    Returns:
        LLMResponse with generated content and metadata

    Raises:
        HTTPException: 404 if query.llm names an LLM that no longer exists
        Exception: If content agent initialization fails
    """
    # Build the agent for the model this request actually asked for. The editor sends
    # an empty llm whenever nothing is selected in its dropdown, hence the fallback.
    # A voice_id naming a voice that has since been deleted resolves to None here, so
    # generation falls back to the house style rather than failing.
    agent = content_agent_create(
        query.llm if query.llm else "default",
        get_voice_prompt(query.voice_id) if query.voice_id else None
    )
    # Record the id that actually served the request, not the one the client sent -
    # they differ when the editor had no LLM selected and the fallback applied.
    llm_id = agent.llm_selected.get("id") or query.llm

    # Prepare messages based on RAG setting
    if query.rag_on_off:
        messages = prompt_rag(query.query, NO_RETRIEVED_CONTEXT)
    else:
        messages = prompt(query.query)

    # Invoke the LLM with retry logic
    try:
        res = await agent.invoke(messages)
    except Exception as e:
        logger.error(f"Error invoking content agent: {str(e)}")
        raise

    # Process response. Strip any preamble/code fence once, here, so raw_output (what
    # Web shows as generated_content) is as clean as the Delta the editor gets.
    output = extract_html(res.output)
    content = json.dumps(html_to_delta(output))
    response = LLMResponse(
        content=content,
        timestamp=insert_query_history(
            query.project_id, query.item_id, query.channel_id, query.prompt_id,
            query.content, query.fields, llm_id, query.prompt_template, query.query,
            content, query.panel_fractions, query.rag_on_off, output
        ),
        output=output
    )
    return response


async def save_content(query: LLMQuery, response_model=LLMResponse):
    """
    Save content to query history without invoking the LLM.

    Args:
        query: LLM query containing content and metadata to save
        response_model: Response model type (default: LLMResponse)

    Returns:
        LLMResponse with saved content and timestamp
    """
    try:
        print(f"[RAG] Saving content to history without LLM invocation")
        logger.info("Saving content to history without LLM invocation")

        # query.content is already the editor's Delta JSON (not HTML), so use it as-is
        content = query.content

        # Save to query history with content as both query and response.
        # raw_output is the plain-text extraction of the Delta, since
        # get_project_brainstorm_ideas() overlays generated_content from the
        # latest query_history row with a non-empty raw_output - an empty
        # raw_output here would make manual edits invisible to that lookup.
        raw_output = delta_to_plain_text(query.content)
        timestamp = insert_query_history(
            query.project_id, query.item_id, query.channel_id, query.prompt_id,
            query.content, query.fields, query.llm, query.prompt_template,
            query.query if query.query else "Content saved manually",
            content, query.panel_fractions, query.rag_on_off, raw_output
        )

        print(f"[RAG] Content saved successfully at {timestamp}")
        logger.info(f"Content saved successfully at {timestamp}")

        response = LLMResponse(
            content=content,
            timestamp=timestamp,
            output=query.content
        )
        return response

    except Exception as e:
        print(f"[RAG] ERROR saving content: {str(e)}")
        logger.error(f"Error saving content: {str(e)}", exc_info=DEBUG)
        raise