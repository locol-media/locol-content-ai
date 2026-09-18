import sqlite3
from datetime import datetime
import uuid
from models import HistoryQuery
from db_manager import get_db_connection

def create_table():
    # Connect to the SQLite database (or create it if it doesn't exist)
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create the table if it doesn't exist
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

    # Commit and close the connection
    conn.commit()
    conn.close()

def insert_query_history(project_id, item_id, channel_id, prompt_id, content, fields, llm, prompt_template, query, response,panel_fractions,rag_on_off,raw_output):
    # Connect to the SQLite database
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get the current datetime
    current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    id = str(uuid.uuid4())

    # Insert data into the table
    cursor.execute(
        """
        INSERT INTO query_history (id, project_id, item_id, channel_id, prompt_id, content, fields, llm, prompt_template, query, response, panel_fractions, rag_on_off, raw_output, query_datetime)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (id, project_id, item_id, channel_id, prompt_id, content, fields, llm, prompt_template, query, response, panel_fractions, rag_on_off, raw_output, current_datetime)
    )

    # Commit and close the connection
    conn.commit()
    conn.close()
    return current_datetime

def retrieve_query_history(query: HistoryQuery):
    # Connect to the SQLite database
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row 
    cursor = conn.cursor()

    # Retrieve data from the table
    cursor.execute("SELECT * FROM query_history WHERE project_id = ? and item_id = ? and channel_id = ? ORDER BY query_datetime DESC",
                   (query.project_id,query.item_id,query.channel_id)
                   )
    rows = cursor.fetchall()
    records = [dict(row) for row in rows]
    # Close the connection
    conn.close()

    return records
