"""
Voice management functions - save, retrieve, update, delete user voices,
and the per-project selection of which voice content is generated in.
"""
import sqlite3
import uuid
from datetime import datetime
from sqlite3 import Error
from typing import List, Dict, Any, Optional

from pydantic import BaseModel
from db_manager import get_db_connection


class SaveVoiceRequest(BaseModel):
    name: str
    voice_prompt: str


class UpdateVoiceRequest(BaseModel):
    name: str
    voice_prompt: str


class SetProjectVoiceRequest(BaseModel):
    voice_id: Optional[str] = None


def create_voices_table():
    """Create the voices table if it doesn't exist."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS voices (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                voice_prompt TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        return True
    except Error as e:
        print(f"Error creating voices table: {e}")
        return False
    finally:
        conn.close()


def save_voice(request: SaveVoiceRequest) -> Dict[str, Any]:
    """Insert a new voice record."""
    create_voices_table()
    conn = get_db_connection()
    try:
        voice_id = str(uuid.uuid4())
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO voices (id, name, voice_prompt) VALUES (?, ?, ?)",
            (voice_id, request.name, request.voice_prompt)
        )
        conn.commit()
        return {"success": True, "id": voice_id, "message": "Voice saved successfully"}
    except Error as e:
        return {"success": False, "message": f"Database error: {str(e)}"}
    finally:
        conn.close()


def get_voices() -> List[Dict[str, Any]]:
    """Return all voices for the current user, newest first."""
    create_voices_table()
    conn = get_db_connection()
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, voice_prompt, created_at, updated_at FROM voices ORDER BY updated_at DESC")
        return [dict(row) for row in cursor.fetchall()]
    except Error as e:
        print(f"Error retrieving voices: {e}")
        return []
    finally:
        conn.close()


def get_voice_prompt(voice_id: str) -> Optional[str]:
    """Return one voice's prompt text, or None if there is no such voice.

    Callers use this to steer generation, so a voice deleted after it was selected
    has to degrade to "no voice" rather than fail the generation it was attached to.
    """
    if not voice_id:
        return None
    create_voices_table()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT voice_prompt FROM voices WHERE id = ?", (voice_id,))
        row = cursor.fetchone()
        return row[0] if row else None
    except Error as e:
        print(f"Error retrieving voice {voice_id}: {e}")
        return None
    finally:
        conn.close()


def compose_system_prompt(base_prompt: str, voice_prompt: str) -> str:
    """Layer a saved voice on top of an agent's own system prompt.

    The voice describes how the text should sound, nothing more. It is appended
    rather than substituted, and told explicitly not to override the task or the
    output format, because the base prompts here carry hard contracts the rest of
    the app depends on - the content agent's restricted-HTML instruction being the
    one that breaks visibly (quill_html_to_delta() renders whatever survives it).
    """
    if not voice_prompt or not voice_prompt.strip():
        return base_prompt
    return (
        f"{base_prompt}\n\n"
        "Write in the following voice. It describes how the text should sound - "
        "tone, rhythm, vocabulary, habits of punctuation. It does not change the "
        "task you were given, and it never overrides the required output format:\n\n"
        f"{voice_prompt.strip()}"
    )


def update_voice(voice_id: str, request: UpdateVoiceRequest) -> Dict[str, Any]:
    """Update an existing voice record."""
    create_voices_table()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE voices SET name = ?, voice_prompt = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (request.name, request.voice_prompt, voice_id)
        )
        if cursor.rowcount == 0:
            return {"success": False, "message": "Voice not found"}
        conn.commit()
        return {"success": True, "message": "Voice updated successfully"}
    except Error as e:
        return {"success": False, "message": f"Database error: {str(e)}"}
    finally:
        conn.close()


def delete_voice(voice_id: str) -> Dict[str, Any]:
    """Delete a voice record by ID, and any project selections pointing at it."""
    create_voices_table()
    create_project_voices_table()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM voices WHERE id = ?", (voice_id,))
        if cursor.rowcount == 0:
            return {"success": False, "message": "Voice not found"}
        # Projects still pointing at it would otherwise keep a dangling selection that
        # silently resolves to no voice on every generation.
        cursor.execute("DELETE FROM project_voices WHERE voice_id = ?", (voice_id,))
        conn.commit()
        return {"success": True, "message": "Voice deleted successfully"}
    except Error as e:
        return {"success": False, "message": f"Database error: {str(e)}"}
    finally:
        conn.close()


def create_project_voices_table():
    """Create the project_voices table if it doesn't exist."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS project_voices (
                project_id TEXT PRIMARY KEY,
                voice_id TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        return True
    except Error as e:
        print(f"Error creating project_voices table: {e}")
        return False
    finally:
        conn.close()


def get_project_voice(project_id: str) -> Dict[str, Any]:
    """Return the voice selected for a project, or {} if none is selected.

    Joins through to voices so a selection left behind by a deleted voice reads as
    no selection at all.
    """
    create_voices_table()
    create_project_voices_table()
    conn = get_db_connection()
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT v.id AS voice_id, v.name, v.voice_prompt
              FROM project_voices pv
              JOIN voices v ON v.id = pv.voice_id
             WHERE pv.project_id = ?
        """, (project_id,))
        row = cursor.fetchone()
        return dict(row) if row else {}
    except Error as e:
        print(f"Error retrieving project voice for {project_id}: {e}")
        return {}
    finally:
        conn.close()


def set_project_voice(project_id: str, request: SetProjectVoiceRequest) -> Dict[str, Any]:
    """Set (or clear, with an empty voice_id) the voice a project generates in."""
    create_voices_table()
    create_project_voices_table()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        voice_id = (request.voice_id or "").strip()
        if not voice_id:
            cursor.execute("DELETE FROM project_voices WHERE project_id = ?", (project_id,))
            conn.commit()
            return {"success": True, "message": "Project voice cleared"}

        cursor.execute("SELECT 1 FROM voices WHERE id = ?", (voice_id,))
        if not cursor.fetchone():
            return {"success": False, "message": "Voice not found"}

        cursor.execute("""
            INSERT OR REPLACE INTO project_voices (project_id, voice_id, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (project_id, voice_id))
        conn.commit()
        return {"success": True, "message": "Project voice saved"}
    except Error as e:
        return {"success": False, "message": f"Database error: {str(e)}"}
    finally:
        conn.close()
