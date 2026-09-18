import asyncio
import json
import logging
import os
import urllib.request

from llm import LLM
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Reddit now gates the public content this feature depends on: logged-out requests to
# www.reddit.com/user/<name>/*.json return 403 and old.reddit.com redirects to a login
# page (see the note in scripts/fetch-reddit-user.ps1), and the Google index this reads
# through Serper has thinned out with it. The search-and-analyse path below is left
# intact - Reddit's posture keeps shifting - but it is off unless deliberately switched
# back on, so users get a straight answer instead of an empty analysis.
# Web mirrors this variable to disable the analyse form; keep the two in step.
FIND_YOUR_VOICE_ENABLED = os.environ.get("LOCOL_FIND_YOUR_VOICE_ENABLED", "").lower() in ("true", "1", "yes")

UNAVAILABLE_MESSAGE = (
    "Reddit writing-style analysis is currently unavailable - Reddit blocks the "
    "automated access this feature relies on. Create a voice by hand instead."
)


class FindYourVoiceRequest(BaseModel):
    reddit_username: str


def _search_reddit_user_sync(username: str) -> str:
    """Search Google via Serper for a Reddit user's posts and comments."""
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        raise ValueError("SERPER_API_KEY environment variable is not set")

    queries = [
        f'site:reddit.com "u/{username}"',
        f'reddit "u/{username}" comments',
    ]

    lines = []
    seen: set[str] = set()

    for query in queries:
        payload = json.dumps({"q": query, "num": 10}).encode()
        req = urllib.request.Request(
            "https://google.serper.dev/search",
            data=payload,
            headers={
                "X-API-KEY": api_key,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            for r in data.get("organic", []):
                snippet = (r.get("snippet") or "").strip()
                title = (r.get("title") or "").strip()
                if snippet and snippet not in seen:
                    seen.add(snippet)
                    lines.append(f"[{title}]\n{snippet}")
        except Exception as e:
            logger.warning(f"Serper search failed for query '{query}': {e}")

    return "\n\n".join(lines)


async def find_your_voice_invoke(request: FindYourVoiceRequest) -> dict:
    """Search for a Reddit user's public writing and return a recommended voice prompt."""
    if not FIND_YOUR_VOICE_ENABLED:
        return {"error": UNAVAILABLE_MESSAGE}

    username = request.reddit_username.strip()

    print(f"[FindYourVoice] Searching for u/{username} via Serper/Google...")
    try:
        content = await asyncio.to_thread(_search_reddit_user_sync, username)
    except ValueError as e:
        return {"error": str(e)}

    if not content:
        return {"error": f"No public Reddit content found for u/{username}."}

    print(f"[FindYourVoice] Got {len(content)} chars of content. Sending to LLM.")
    logger.info(f"Search content for u/{username}:\n{content[:1000]}")

    system_prompt = (
        "You are an expert writing style analyst. Your task is to analyze a Reddit user's "
        "posts and comments, identify their unique voice, tone, vocabulary, and writing patterns, "
        "then craft a system prompt that will allow an LLM to generate content in that person's "
        "authentic voice. Return only the recommended system prompt text, ready to use."
    )

    user_prompt = (
        f"Below are Google search results showing recent posts and comments by Reddit user u/{username}. "
        f"Analyze their writing style based on this content:\n\n"
        f"{content}\n\n"
        f"Analyze their writing style:\n"
        f"- Are their sentences short and punchy, or long and complex? Do they use fragments, run-ons, or lists?\n"
        f"- Is the user generally serious, sarcastic, earnest, detached, passionate, or neutral?\n"
        f"- Do they try to be funny? If so, how — dry wit, self-deprecating jokes, absurdist humour, puns?\n"
        f"- Does their writing feel like it comes from a younger or older person? What specific cues point to this?\n"
        f"- Do they use slang, jargon, or technical terms? Is their vocabulary broad or simple?\n"
        f"- Do they use caps for emphasis, ellipses, excessive punctuation, or emojis?\n"
        f"- Based on their writing alone, what kind of person do they come across as?\n\n"
        f"Based on this analysis, write a system prompt that an LLM can use to generate new "
        f"content that authentically matches u/{username}'s voice and style. "
        f"The prompt should be specific, actionable, and capture the nuances of their writing."
    )

    llm = LLM("default", system_prompt, tools=[])
    result = await llm.invoke(user_prompt)
    voice_prompt = result.output if hasattr(result, "output") else str(result)
    return {"voice_prompt": voice_prompt}
