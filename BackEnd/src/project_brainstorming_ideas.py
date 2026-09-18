from fastapi import Query, Depends, HTTPException
from typing import List
import sqlite3
import json
from datetime import datetime
from db_manager import get_db_connection
from brainstorm_models import SaveBrainstormIdeasRequest, SaveBrainstormIdeasResponse

def ensure_query_history_table_exists():
    """Create query_history table if it doesn't exist"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS query_history (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            item_id TEXT,
            channel_id TEXT,
            prompt_id TEXT,
            content TEXT,
            fields TEXT,
            llm TEXT,
            prompt_template TEXT,
            query TEXT,
            response TEXT,
            panel_fractions TEXT,
            rag_on_off BOOLEAN,
            raw_output TEXT,
            query_datetime TEXT
        )
        """
    )
    
    conn.commit()
    conn.close()

def save_project_brainstorm_idea(project_id: str, idea_id: str, idea_data: dict):
    """
    Save brainstorm idea to the project_brainstorm_ideas table.
    
    Parameters:
        project_id (str): The project ID
        idea_id (str): Unique ID for the brainstorm idea
        idea_data (dict): The brainstorm idea data
    """
    current_datetime = datetime.now().isoformat()
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS project_brainstorm_ideas (
                project_id TEXT NOT NULL,
                id TEXT NOT NULL,
                idea_data TEXT NOT NULL,
                create_datetime TEXT NOT NULL,
                PRIMARY KEY (project_id, id)
            )
        """)
        
        # Ensure query_history table exists
        ensure_query_history_table_exists()
        
        # Insert the brainstorm idea
        cursor.execute("""
            INSERT OR REPLACE INTO project_brainstorm_ideas 
            (project_id, id, idea_data, create_datetime)
            VALUES (?, ?, ?, ?)
        """, (project_id, idea_id, json.dumps(idea_data), current_datetime))
        
        conn.commit()
        print(f"Saved brainstorm idea {idea_id} for project {project_id}")
        
    except sqlite3.Error as e:
        print(f"Error saving brainstorm idea: {e}")
    except Exception as e:
        print(f"Unexpected error saving brainstorm idea: {e}")
    finally:
        if conn:
            conn.close()

def get_project_brainstorm_ideas(project_id: str) -> List[dict]:
    """
    Retrieve all brainstorm ideas for a project.
    
    Parameters:
        project_id (str): The project ID
        
    Returns:
        List[dict]: List of brainstorm ideas
    """
    conn = None
    try:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Create table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS project_brainstorm_ideas (
                project_id TEXT NOT NULL,
                id TEXT NOT NULL,
                idea_data TEXT NOT NULL,
                create_datetime TEXT NOT NULL,
                PRIMARY KEY (project_id, id)
            )
        """)
        
        # Ensure query_history table exists
        ensure_query_history_table_exists()
        
        # Generation order, so the sidebar nav and the idea cards on the Campaign
        # Projects page agree. The rowid tiebreaker matters because
        # save_project_brainstorm_ideas() stamps every row of a batch with one
        # shared create_datetime - once that has run, create_datetime alone no
        # longer orders anything, and rowid reproduces the order the client sent.
        cursor.execute("""
            SELECT * FROM project_brainstorm_ideas
            WHERE project_id = ?
            ORDER BY create_datetime ASC, rowid ASC
        """, (project_id,))
        
        rows = cursor.fetchall()
        ideas = []
        
        for row in rows:
            idea_dict = dict(row)
            # Parse JSON idea data
            if idea_dict["idea_data"]:
                try:
                    idea_dict["idea_data"] = json.loads(idea_dict["idea_data"])
                except json.JSONDecodeError:
                    idea_dict["idea_data"] = {}
            else:
                idea_dict["idea_data"] = {}
            
            # Check query_history for the latest entry with raw_output for this idea
            item_id = idea_dict.get("id")
            if item_id:
                cursor.execute("""
                    SELECT raw_output FROM query_history 
                    WHERE project_id = ? AND item_id = ? AND raw_output IS NOT NULL AND raw_output != ''
                    ORDER BY query_datetime DESC 
                    LIMIT 1
                """, (project_id, item_id))
                
                history_row = cursor.fetchone()
                if history_row and history_row["raw_output"]:
                    # Add the raw_output as generated_content in idea_data
                    idea_dict["idea_data"]["generated_content"] = history_row["raw_output"]
            
            ideas.append(idea_dict)
        
        print(f"Retrieved {len(ideas)} brainstorm ideas for project {project_id}")
        return ideas
        
    except sqlite3.Error as e:
        print(f"Error retrieving brainstorm ideas: {e}")
        return []
    except Exception as e:
        print(f"Unexpected error retrieving brainstorm ideas: {e}")
        return []
    finally:
        if conn:
            conn.close()

def save_project_brainstorm_ideas(project_id: str, brainstorm_ideas: list):
    """
    Save multiple brainstorm ideas to the project_brainstorm_ideas table.
    This will replace all existing ideas for the project.
    
    Parameters:
        project_id (str): The project ID
        brainstorm_ideas (list): List of brainstorm idea objects
    """
    current_datetime = datetime.now().isoformat()
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS project_brainstorm_ideas (
                project_id TEXT NOT NULL,
                id TEXT NOT NULL,
                idea_data TEXT NOT NULL,
                create_datetime TEXT NOT NULL,
                PRIMARY KEY (project_id, id)
            )
        """)
        
        # Ensure query_history table exists
        ensure_query_history_table_exists()
        
        # Delete existing ideas for this project
        cursor.execute("""
            DELETE FROM project_brainstorm_ideas WHERE project_id = ?
        """, (project_id,))
        
        # Insert new ideas
        for idea in brainstorm_ideas:
            # Use existing id if present, otherwise generate new one
            idea_id = idea.get('id', str(__import__('uuid').uuid4()))
            if 'id' not in idea:
                idea['id'] = idea_id
                
            cursor.execute("""
                INSERT INTO project_brainstorm_ideas 
                (project_id, id, idea_data, create_datetime)
                VALUES (?, ?, ?, ?)
            """, (project_id, idea_id, json.dumps(idea), current_datetime))
        
        conn.commit()
        print(f"Saved {len(brainstorm_ideas)} brainstorm ideas for project {project_id}")
        
    except sqlite3.Error as e:
        print(f"Error saving brainstorm ideas: {e}")
        raise e
    except Exception as e:
        print(f"Unexpected error saving brainstorm ideas: {e}")
        raise e
    finally:
        if conn:
            conn.close()

async def get_project_brainstorming_ideas_endpoint(project_id: str = Query(..., description="Project ID"), user_id: str = None):
    """Get brainstorming ideas for a project"""
    try:
        ideas = get_project_brainstorm_ideas(project_id)
        # Extract just the idea_data from each result
        idea_data_list = [idea['idea_data'] for idea in ideas]
        return idea_data_list
    except Exception as e:
        return {"status": "error", "message": str(e)}

async def save_project_brainstorming_ideas_endpoint(request: SaveBrainstormIdeasRequest, user_id: str = None):
    """Save/update brainstorming ideas for a project"""
    try:
        # Convert Pydantic models to dict for database storage
        ideas_list = [idea.dict() for idea in request.brainstorm_ideas]
        save_project_brainstorm_ideas(request.project_id, ideas_list)
        return SaveBrainstormIdeasResponse(
            success=True,
            message=f"Successfully saved {len(ideas_list)} brainstorm ideas for project {request.project_id}"
        )
    except Exception as e:
        return SaveBrainstormIdeasResponse(
            success=False,
            message="Failed to save brainstorm ideas",
            error=str(e)
        )