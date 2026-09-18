import sqlite3
import os
from typing import Optional
from contextvars import ContextVar

from sql_identifiers import quote_identifier

# Context variable for current user context (works with async/await)
_current_user_id: ContextVar[Optional[str]] = ContextVar('current_user_id', default=None)

# Global database paths  
MAIN_DB_PATH = "./db/persistent_data.sqlite"
USER_DB_DIR = "./db/users"

def get_user_db_path(user_id: str) -> str:
    """Get the database path for a specific user"""
    if not user_id:
        raise ValueError("User ID cannot be empty")

    # Sanitize user_id to prevent path traversal attacks
    # Remove any directory separators and parent directory references
    sanitized_user_id = user_id.replace('/', '').replace('\\', '').replace('..', '').replace('\0', '')

    # Validate that the user_id is a valid UUID or alphanumeric string
    if not sanitized_user_id or sanitized_user_id != user_id:
        raise ValueError(f"Invalid user ID format. User ID cannot contain path separators or special characters.")

    # Additional check: ensure user_id is alphanumeric with hyphens only (UUID format)
    import re
    if not re.match(r'^[a-zA-Z0-9_-]+$', user_id):
        raise ValueError(f"Invalid user ID format. Must contain only alphanumeric characters, hyphens, and underscores.")

    # Ensure user db directory exists
    os.makedirs(USER_DB_DIR, exist_ok=True)

    return f"{USER_DB_DIR}/{user_id}.sqlite"

def set_current_user(user_id: str):
    """Set the current user context for database operations"""
    _current_user_id.set(user_id)

def get_current_user() -> Optional[str]:
    """Get the current user ID from context"""
    return _current_user_id.get()

def get_current_user_db_path() -> str:
    """Get the current user's database path"""
    user_id = get_current_user()
    if not user_id:
        raise ValueError("No current user set. Call set_current_user() first.")
    return get_user_db_path(user_id)

def get_db_connection(user_specific: bool = True) -> sqlite3.Connection:
    """
    Get a database connection
    
    Args:
        user_specific: If True, connect to current user's db. If False, connect to main db.
    """
    if user_specific:
        db_path = get_current_user_db_path()
    else:
        db_path = MAIN_DB_PATH
    
    return sqlite3.connect(db_path)

def init_user_database(user_id: str):
    """Initialize a new user database with all required tables and data"""
    user_db_path = get_user_db_path(user_id)

    # Set current user context
    set_current_user(user_id)

    # Create the database file
    conn = sqlite3.connect(user_db_path)
    cursor = conn.cursor()

    # Import config manager for paths
    from config_manager import get_channels_path, get_llms_path, get_prompt_templates_path

    # Create channels table and related tags table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='channels'")
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                parent TEXT,
                create_datetime TEXT,
                replace_datetime TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS channel_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                FOREIGN KEY (channel_id) REFERENCES channels(id)
            )
        """)
        conn.commit()
        # Load channels data
        from load_channels import sync_channel_table
        sync_channel_table("", get_channels_path())

    # Create llms table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='llms'")
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS llms (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                APIstyle TEXT NOT NULL,
                APIkey TEXT,
                APIurl TEXT,
                model TEXT,
                parent TEXT,
                create_datetime TEXT,
                replace_datetime TEXT
            )
        """)
        conn.commit()
        # Load llms data
        from load_llms import sync_table
        sync_table("", "llms", get_llms_path())

    # Create prompts table and related tags table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='prompts'")
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prompts (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                template TEXT NOT NULL,
                parent TEXT,
                create_datetime TEXT,
                replace_datetime TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prompt_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                FOREIGN KEY (prompt_id) REFERENCES prompts(id)
            )
        """)
        conn.commit()
        # Load prompts data
        from load_prompts import sync_prompts_table
        sync_prompts_table("", get_prompt_templates_path())

    conn.close()

    print(f"Initialized database with tables for user: {user_id}")


def ensure_user_defaults_seeded(user_id: str):
    """
    Idempotently repair a user's channels/llms/prompts tables if missing or empty.

    init_user_database() only seeds a table the first time it's created, so a user
    whose seed step failed partway (e.g. a transient config-directory issue) can be
    left with a table that exists but has zero rows, with nothing to ever retry it.
    This re-checks row counts and re-syncs any empty table.
    """
    # Create any tables that don't exist yet (no-op for tables that already exist)
    init_user_database(user_id)

    user_db_path = get_user_db_path(user_id)
    conn = sqlite3.connect(user_db_path)
    cursor = conn.cursor()

    def _is_empty(table_name: str) -> bool:
        cursor.execute(f"SELECT COUNT(*) FROM {quote_identifier(table_name)}")
        return cursor.fetchone()[0] == 0

    from config_manager import get_channels_path, get_llms_path, get_prompt_templates_path

    if _is_empty("channels"):
        from load_channels import sync_channel_table
        sync_channel_table("", get_channels_path())

    if _is_empty("llms"):
        from load_llms import sync_table
        sync_table("", "llms", get_llms_path())

    if _is_empty("prompts"):
        from load_prompts import sync_prompts_table
        sync_prompts_table("", get_prompt_templates_path())

    conn.close()

    # Give the default LLM its Bifrost virtual key if it hasn't got one - including
    # for users who registered before Bifrost was configured, or whose row was reset
    # by a config resync. No-op once the row holds a key, and it never raises.
    from bifrost_manager import provision_default_llm
    provision_default_llm(user_id)


def clear_current_user():
    """Clear the current user context"""
    _current_user_id.set(None)