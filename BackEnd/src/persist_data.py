import sqlite3
import json
from datetime import datetime
from typing import List,Optional
from models import DropDownItem
from db_manager import get_db_connection
from sql_identifiers import quote_identifier

def replace_dropdown_values(table_name, records: List[DropDownItem],parent: Optional[str] = None):
    """
    Replace multiple items in the SQLite table with a replace datetime.

    Parameters:
        db_path (str): Path to the SQLite database file.
        table_name (str): Name of the table to replace items.
        items (List[Item]): List of Pydantic Item objects.
    """
    # Validate table name to prevent SQL injection
    quoted_table = quote_identifier(table_name)

    current_datetime = datetime.now().isoformat()
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Create table if it doesn't exist
        _create_table_if_not_exists(cursor, table_name)

        if parent is not None:
            # delete all records with this parent first
            cursor.execute(
                f"""
                DELETE FROM {quoted_table} WHERE parent = ?
                """,
                (
                    parent,
                ),
            )
        else:
            # clear the table
            cursor.execute(
                f"""
                DELETE FROM {quoted_table}
                """
            )

    # Insert or replace records
        for record in records:
            cursor.execute(
                f"""
                REPLACE INTO {quoted_table} (id, name, parent, create_datetime, replace_datetime)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.name,
                    record.parent,
                    record.create_datetime.isoformat() if record.create_datetime else current_datetime,
                    current_datetime
                ),
            )
    except sqlite3.Error as e:
        print(f"Error: {e}")
    finally:
        if conn:
            conn.commit()
            conn.close()


def _create_table_if_not_exists(cursor, table_name):
    """
    Create table if it doesn't exist based on the table name.
    Uses standard dropdown format for generic tables (projects, items, etc).

    channels/llms are deliberately NOT created here: they're seeded with default
    data during user database initialization (db_manager.init_user_database /
    ensure_user_defaults_seeded), which always runs before any authenticated
    request reaches this code. Creating an empty placeholder here would
    permanently short-circuit that seeding logic (it only seeds a table the
    first time it's created), silently leaving the user with no defaults.
    """
    if table_name in ("channels", "llms"):
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        if not cursor.fetchone():
            raise RuntimeError(
                f"Table '{table_name}' is missing but should have been seeded during "
                f"user database initialization. Refusing to silently create an empty one."
            )
    else:
        # For projects, items, and any other table, use the standard dropdown format
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {quote_identifier(table_name)} (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                parent TEXT,
                create_datetime TEXT,
                replace_datetime TEXT
            )
        """)


def retrieve_dropdown_values(table_name,parent=None):
    """
    Retrieve all items from the SQLite table.

    Parameters:
        db_path (str): Path to the SQLite database file.
        table_name (str): Name of the table to retrieve items from.

    Returns:
        list of tuples: Each tuple represents a row in the table.

    Example:
        items = retrieve_all_items('database.db', 'items')
        for item in items:
            print(item)
    """
    # Validate table name to prevent SQL injection
    quoted_table = quote_identifier(table_name)

    try:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Create table if it doesn't exist
        _create_table_if_not_exists(cursor, table_name)

        # Use parameterized query to prevent SQL injection
        # Order by create_datetime to maintain insertion order
        if parent is None:
            query = f"SELECT * FROM {quoted_table} ORDER BY create_datetime ASC"
            cursor.execute(query)
        else:
            query = f"SELECT * FROM {quoted_table} WHERE parent = ? ORDER BY create_datetime ASC"
            cursor.execute(query, (parent,))
        rows = cursor.fetchall()
        records = [dict(row) for row in rows]
        print(f"Retrieved {len(rows)} rows from table '{table_name}'.")
        return records
    except sqlite3.Error as e:
        print(f"Error: {e}")
        return []
    finally:
        if conn:
            conn.close()

def retrieve_llm_dropdown_values(table_name,parent=None):
    """
    Special Retrieval for LLM -- do not return API info, including keys to front end.
    Note: Table is pre-created and loaded during user database initialization in db_manager.py
    """
    # Validate table name to prevent SQL injection
    quoted_table = quote_identifier(table_name)

    try:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = f"SELECT id,name,model FROM {quoted_table} ORDER BY create_datetime ASC"
        cursor.execute(query)
        rows = cursor.fetchall()
        records = [dict(row) for row in rows]
        print(f"Retrieved {len(rows)} rows from table '{table_name}'.")
        return records
    except sqlite3.Error as e:
        print(f"Error: {e}")
        return []
    finally:
        if conn:
            conn.close()

def save_project_data(project_id: str, survey_type: str, survey_data: dict, question_set: str = None):
    """
    Save survey data for a specific project.

    Parameters:
        project_id (str): The ID of the project
        survey_type (str): Type of survey (e.g., "project_survey", "business_survey")
        survey_data (dict): The survey response data
        question_set (str, optional): The question set name for the project

    Returns:
        dict: Success status and message
    """
    current_datetime = datetime.now().isoformat()
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create projects table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS project_data (
                id TEXT PRIMARY KEY,
                survey_type TEXT,
                survey_data TEXT,
                question_set TEXT,
                create_datetime TEXT,
                update_datetime TEXT
            )
        """)
        
        # Insert or update project data
        cursor.execute("""
            INSERT OR REPLACE INTO project_data
            (id, survey_type, survey_data, question_set, update_datetime, create_datetime)
            VALUES (?, ?, ?, ?, ?,
                COALESCE((SELECT create_datetime FROM project_data WHERE id = ?), ?))
        """, (
            project_id,
            survey_type,
            json.dumps(survey_data),
            question_set,
            current_datetime,
            project_id,
            current_datetime
        ))
        
        conn.commit()
        print(f"Saved project data for project_id: {project_id}, survey_type: {survey_type}")
        return {"success": True, "message": "Project data saved successfully"}
        
    except sqlite3.Error as e:
        print(f"Error saving project data: {e}")
        return {"success": False, "message": f"Database error: {e}"}
    except Exception as e:
        print(f"Unexpected error saving project data: {e}")
        return {"success": False, "message": f"Unexpected error: {e}"}
    finally:
        if conn:
            conn.close()

def get_project_data(project_id: str):
    """
    Retrieve survey data for a specific project.
    
    Parameters:
        project_id (str): The ID of the project to retrieve
    
    Returns:
        dict: Project data including survey responses, or empty dict if not found
    """
    try:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, survey_type, survey_data, question_set, create_datetime, update_datetime
            FROM project_data
            WHERE id = ?
        """, (project_id,))
        
        row = cursor.fetchone()
        if row:
            project_data = dict(row)
            # Parse JSON survey data
            if project_data["survey_data"]:
                try:
                    project_data["survey_data"] = json.loads(project_data["survey_data"])
                except json.JSONDecodeError:
                    project_data["survey_data"] = {}
            else:
                project_data["survey_data"] = {}
            
            print(f"Retrieved project data for project_id: {project_id}")
            return project_data
        else:
            print(f"No project found with id: {project_id}")
            return {}
            
    except sqlite3.Error as e:
        print(f"Error retrieving project data: {e}")
        return {}
    except Exception as e:
        print(f"Unexpected error retrieving project data: {e}")
        return {}
    finally:
        if conn:
            conn.close()


def check_item_for_llm_channel(item_id: str):
    """
    Check what LLM and channel combinations are available for a specific item
    by querying the query_history table.

    Parameters:
        item_id (str): The item ID to check

    Returns:
        list: List of dictionaries containing unique llm and channel_id combinations
    """
    conn = None
    try:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Query distinct llm and channel_id combinations for the item
        cursor.execute("""
            SELECT DISTINCT llm, channel_id
            FROM query_history
            WHERE item_id = ?
            ORDER BY llm, channel_id
        """, (item_id,))

        rows = cursor.fetchall()
        combinations = [dict(row) for row in rows]

        print(f"Found {len(combinations)} LLM-channel combinations for item {item_id}")
        return combinations

    except sqlite3.Error as e:
        print(f"Error checking LLM-channel combinations: {e}")
        return []
    except Exception as e:
        print(f"Unexpected error checking LLM-channel combinations: {e}")
        return []
    finally:
        if conn:
            conn.close()
