"""
Story ideas database persistence
"""
import json
import uuid
from sqlite3 import Error
from datetime import datetime
from typing import Dict, Any, List
from db_manager import get_db_connection


def _get_conn():
    try:
        return get_db_connection()
    except Error as e:
        print(f"Database connection error: {e}")
        return None


def _ensure_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS story_ideas (
            id TEXT PRIMARY KEY,
            idea_data TEXT NOT NULL,
            create_datetime TEXT NOT NULL
        )
    """)


def save_story_idea(idea_id: str, idea_data: Dict[str, Any]) -> bool:
    conn = _get_conn()
    if conn is None:
        return False
    try:
        cursor = conn.cursor()
        _ensure_table(cursor)
        cursor.execute(
            "INSERT OR REPLACE INTO story_ideas (id, idea_data, create_datetime) VALUES (?, ?, ?)",
            (idea_id, json.dumps(idea_data), datetime.now().isoformat())
        )
        conn.commit()
        return True
    except Error as e:
        print(f"Error saving story idea: {e}")
        return False
    finally:
        conn.close()


def get_story_ideas() -> List[Dict[str, Any]]:
    conn = _get_conn()
    if conn is None:
        return []
    try:
        cursor = conn.cursor()
        _ensure_table(cursor)
        cursor.execute("SELECT idea_data FROM story_ideas ORDER BY create_datetime DESC")
        return [json.loads(row[0]) for row in cursor.fetchall()]
    except Error as e:
        print(f"Error retrieving story ideas: {e}")
        return []
    finally:
        conn.close()


def delete_story_ideas() -> bool:
    conn = _get_conn()
    if conn is None:
        return False
    try:
        cursor = conn.cursor()
        _ensure_table(cursor)
        cursor.execute("DELETE FROM story_ideas")
        conn.commit()
        return True
    except Error as e:
        print(f"Error deleting story ideas: {e}")
        return False
    finally:
        conn.close()
