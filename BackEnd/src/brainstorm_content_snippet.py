from llm import LLM
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import uuid
import sqlite3
from sqlite3 import Error
from db_manager import get_db_connection
from voice_manager import get_voice_prompt, compose_system_prompt


class IdeaBrainstormRequest(BaseModel):
    idea_id: str
    prompt: str
    title: Optional[str] = ""
    description: Optional[str] = ""
    content_type: Optional[str] = ""
    platform: Optional[str] = ""
    goal: Optional[str] = ""
    voice_id: Optional[str] = None


def create_brainstorm_content_snippets_table():
    """Create the brainstorm_content_snippets table if it doesn't exist."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS brainstorm_content_snippets (
                id TEXT PRIMARY KEY,
                idea_id TEXT NOT NULL,
                prompt TEXT NOT NULL,
                response TEXT NOT NULL,
                create_datetime TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    except Error as e:
        print(f"Error creating brainstorm_content_snippets table: {e}")
    finally:
        conn.close()


def save_brainstorm_content_snippet(idea_id: str, prompt: str, response: str) -> None:
    """Persist a prompt/response pair for a given idea_id."""
    create_brainstorm_content_snippets_table()
    conn = get_db_connection()
    try:
        snippet_id = str(uuid.uuid4())
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO brainstorm_content_snippets (id, idea_id, prompt, response) VALUES (?, ?, ?, ?)",
            (snippet_id, idea_id, prompt, response)
        )
        conn.commit()
    except Error as e:
        print(f"Error saving brainstorm content snippet: {e}")
    finally:
        conn.close()


def get_brainstorm_content_snippets(idea_id: str) -> List[Dict[str, Any]]:
    """Return all content snippets for a given idea_id, newest first."""
    create_brainstorm_content_snippets_table()
    conn = get_db_connection()
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT create_datetime, prompt, response FROM brainstorm_content_snippets WHERE idea_id = ? ORDER BY create_datetime DESC",
            (idea_id,)
        )
        return [dict(row) for row in cursor.fetchall()]
    except Error as e:
        print(f"Error retrieving brainstorm content snippets: {e}")
        return []
    finally:
        conn.close()


async def idea_brainstorm_invoke(request: IdeaBrainstormRequest) -> dict:
    """Brainstorm on a campaign idea using a user-provided prompt."""
    system_prompt = (
        "You are a creative marketing strategist helping brainstorm and develop campaign ideas. "
        "You will be given details about a campaign idea and a user prompt. "
        "Provide thoughtful, actionable, and creative brainstorming output."
    )
    # A voice deleted since it was selected resolves to None and is simply skipped.
    voice_prompt = get_voice_prompt(request.voice_id) if request.voice_id else None
    if voice_prompt:
        system_prompt = compose_system_prompt(system_prompt, voice_prompt)

    idea_context = (
        f"Campaign Idea:\n"
        f"  Title: {request.title}\n"
        f"  Description: {request.description}\n"
        f"  Content Type: {request.content_type}\n"
        f"  Platform: {request.platform}\n"
        f"  Goal: {request.goal}\n\n"
    )
    user_prompt = idea_context + request.prompt

    llm = LLM("default", system_prompt)
    result = await llm.invoke(user_prompt)
    response_text = result.output if hasattr(result, "output") else str(result)

    save_brainstorm_content_snippet(request.idea_id, request.prompt, response_text)

    return {"response": response_text}
