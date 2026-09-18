"""
Business survey data management functions
"""
import sqlite3
import json
import uuid
from sqlite3 import Error
from datetime import datetime
from typing import Optional, Dict, Any, List
from business_models import SaveBusinessSurveyRequest, SaveBusinessSurveyResponse, GetBusinessSurveyResponse, extract_survey_values
from db_manager import get_db_connection


def create_connection(db_file: str = None):
    """Create a database connection to user-specific SQLite database"""
    try:
        if db_file:
            # Legacy support for specific db file
            conn = sqlite3.connect(db_file)
        else:
            conn = get_db_connection()
        return conn
    except Error as e:
        print(f"Database connection error: {e}")
    return None


def create_business_survey_table():
    """Create the business_survey_data table if it doesn't exist, migrating old schema if needed"""
    conn = create_connection()
    if conn is None:
        return False

    try:
        cursor = conn.cursor()

        # Migrate old schema: if table exists without 'data' column, drop and recreate
        cursor.execute("PRAGMA table_info(business_survey_data)")
        cols = {row[1] for row in cursor.fetchall()}
        if cols and 'data' not in cols:
            cursor.execute("DROP TABLE business_survey_data")

        create_table_sql = """
        CREATE TABLE IF NOT EXISTS business_survey_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            survey_id TEXT UNIQUE NOT NULL,
            data TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        cursor.execute(create_table_sql)
        conn.commit()
        return True
    except Error as e:
        print(f"Error creating table: {e}")
        return False
    finally:
        conn.close()


def save_business_survey_data(request: SaveBusinessSurveyRequest) -> SaveBusinessSurveyResponse:
    """Save business survey data to the database, keeping only the latest version"""

    print("DEBUG: Starting save_business_survey_data")

    table_created = create_business_survey_table()
    print(f"DEBUG: Table creation result: {table_created}")
    if not table_created:
        return SaveBusinessSurveyResponse(
            success=False,
            message="Failed to initialize database table"
        )

    conn = create_connection()
    if conn is None:
        return SaveBusinessSurveyResponse(
            success=False,
            message="Database connection failed"
        )

    try:
        survey_dict = extract_survey_values(request.survey_data) if isinstance(request.survey_data, dict) else dict(request.survey_data)
        data_json = json.dumps(survey_dict)

        print(f"DEBUG: Saving survey data keys: {list(survey_dict.keys())}")

        survey_id = str(uuid.uuid4())
        cursor = conn.cursor()

        cursor.execute("DELETE FROM business_survey_data")
        print(f"DEBUG: Deleted {cursor.rowcount} existing records")

        cursor.execute(
            "INSERT INTO business_survey_data (survey_id, data) VALUES (?, ?)",
            (survey_id, data_json)
        )
        print(f"DEBUG: Inserted {cursor.rowcount} new record")

        conn.commit()
        print("DEBUG: Transaction committed")

        return SaveBusinessSurveyResponse(
            success=True,
            message="Business survey data saved successfully",
            survey_id=survey_id,
            timestamp=datetime.now().isoformat()
        )

    except Error as e:
        print(f"DEBUG: Database error: {e}")
        return SaveBusinessSurveyResponse(
            success=False,
            message=f"Database error: {str(e)}"
        )
    except Exception as e:
        print(f"DEBUG: Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return SaveBusinessSurveyResponse(
            success=False,
            message=f"Unexpected error: {str(e)}"
        )
    finally:
        conn.close()


def get_business_survey_data() -> GetBusinessSurveyResponse:
    """Retrieve the single business survey data"""

    conn = create_connection()
    if conn is None:
        return GetBusinessSurveyResponse(
            success=False,
            survey_data=None
        )

    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM business_survey_data")
        count = cursor.fetchone()[0]
        print(f"DEBUG: Found {count} records in business_survey_data table")

        cursor.execute("SELECT * FROM business_survey_data ORDER BY updated_at DESC LIMIT 1")
        row = cursor.fetchone()

        if row is None:
            print("DEBUG: No row found in database")
            return GetBusinessSurveyResponse(
                success=False,
                survey_data=None
            )

        row_dict = dict(row)
        survey_dict = json.loads(row_dict['data'])

        return GetBusinessSurveyResponse(
            success=True,
            survey_data=survey_dict,
            last_updated=row_dict.get('updated_at'),
            survey_id=row_dict.get('survey_id')
        )

    except Error as e:
        return GetBusinessSurveyResponse(
            success=False,
            survey_data=None
        )
    except Exception as e:
        return GetBusinessSurveyResponse(
            success=False,
            survey_data=None
        )
    finally:
        conn.close()


def get_all_business_surveys() -> List[Dict[str, Any]]:
    """Get all business surveys with basic info"""

    conn = create_connection()
    if conn is None:
        return []

    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
        SELECT survey_id, created_at, updated_at
        FROM business_survey_data
        ORDER BY created_at DESC
        """)
        rows = cursor.fetchall()

        return [dict(row) for row in rows]

    except Error as e:
        print(f"Error retrieving surveys: {e}")
        return []
    finally:
        conn.close()


def update_business_survey_data(survey_id: str, request: SaveBusinessSurveyRequest) -> SaveBusinessSurveyResponse:
    """Update existing business survey data"""

    conn = create_connection()
    if conn is None:
        return SaveBusinessSurveyResponse(
            success=False,
            message="Database connection failed"
        )

    try:
        survey_dict = extract_survey_values(request.survey_data) if isinstance(request.survey_data, dict) else dict(request.survey_data)
        data_json = json.dumps(survey_dict)

        cursor = conn.cursor()
        cursor.execute(
            "UPDATE business_survey_data SET data = ?, updated_at = CURRENT_TIMESTAMP WHERE survey_id = ?",
            (data_json, survey_id)
        )

        if cursor.rowcount == 0:
            return SaveBusinessSurveyResponse(
                success=False,
                message="Survey ID not found"
            )

        conn.commit()

        return SaveBusinessSurveyResponse(
            success=True,
            message="Business survey data updated successfully",
            survey_id=survey_id,
            timestamp=datetime.now().isoformat()
        )

    except Error as e:
        return SaveBusinessSurveyResponse(
            success=False,
            message=f"Database error: {str(e)}"
        )
    except Exception as e:
        return SaveBusinessSurveyResponse(
            success=False,
            message=f"Unexpected error: {str(e)}"
        )
    finally:
        conn.close()


def delete_business_survey_data(survey_id: str) -> SaveBusinessSurveyResponse:
    """Delete business survey data by survey ID"""

    conn = create_connection()
    if conn is None:
        return SaveBusinessSurveyResponse(
            success=False,
            message="Database connection failed"
        )

    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM business_survey_data WHERE survey_id = ?", (survey_id,))

        if cursor.rowcount == 0:
            return SaveBusinessSurveyResponse(
                success=False,
                message="Survey ID not found"
            )

        conn.commit()

        return SaveBusinessSurveyResponse(
            success=True,
            message="Business survey data deleted successfully",
            survey_id=survey_id,
            timestamp=datetime.now().isoformat()
        )

    except Error as e:
        return SaveBusinessSurveyResponse(
            success=False,
            message=f"Database error: {str(e)}"
        )
    finally:
        conn.close()
