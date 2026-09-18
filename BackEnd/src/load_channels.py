import sqlite3
import yaml
import os
from db_manager import get_db_connection
from safe_paths import list_yaml_files
from sql_identifiers import quote_identifier

def load_yaml_files(directory):
    """Load and merge data from all YAML files in a directory, including multi-document YAML files."""
    all_data = []
    for file_path in list_yaml_files(directory):
        with open(file_path, "r", encoding="utf-8") as file:
            documents = yaml.safe_load_all(file)  # Load multiple documents
            for doc in documents:
                if isinstance(doc, dict):
                    all_data.append(doc)  # Single object
                elif isinstance(doc, list):
                    all_data.extend(doc)  # List of objects
    return all_data

def sync_channel_table(db_path, yaml_dir):
    """
    Syncs the 'channel' table and its related 'channel_tags' table in SQLite with data from multiple YAML files.
    - Updates existing records
    - Inserts new records
    - Deletes obsolete records
    - Updates/deletes related tags in 'channel_tags'

    :param db_path: Path to the SQLite database file (ignored, uses user-specific db)
    :param yaml_dir: Directory containing YAML files
    """
    if not os.path.isdir(yaml_dir):
        print(f"Channels config directory not found, skipping sync: {yaml_dir}")
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    # Pre-quoted through the shared whitelist so every f-string below interpolates
    # a validated identifier rather than a bare string.
    table_name = quote_identifier("channels")
    tag_table_name = quote_identifier("channel_tags")

    # Load new records from all YAML files
    new_data = load_yaml_files(yaml_dir)

    # Get existing records (id) from the database
    cursor.execute(f"SELECT id FROM {table_name}")
    existing_ids = {row[0] for row in cursor.fetchall()}  # Set of existing channel IDs

    # Extract ids from new dataset
    new_ids = {record['id'] for record in new_data}

    # Identify records to be removed (present in DB but not in new data)
    ids_to_remove = existing_ids - new_ids

    # Insert or update records
    for record in new_data:
        record_id = record['id']
        name = record.get('name', None)  # Required field
        tags = record.get('tags', [])  # Get tags list (default to empty list)

        if record_id in existing_ids:
            # Update existing record using id
            update_query = f"""
            UPDATE {table_name} 
            SET name = ?
            WHERE id = ?;
            """
            cursor.execute(update_query, (name, record_id))

            # Delete existing tags before inserting new ones
            cursor.execute(f"DELETE FROM {tag_table_name} WHERE channel_id = ?", (record_id,))
        else:
            # Insert new record
            insert_query = f"""
            INSERT INTO {table_name} (id, name)
            VALUES (?, ?);
            """
            cursor.execute(insert_query, (record_id, name))

        # Insert tags into channel_tags table
        for tag in tags:
            tag_insert_query = f"""
            INSERT INTO {tag_table_name} (channel_id, tag)
            VALUES (?, ?);
            """
            cursor.execute(tag_insert_query, (record_id, tag))

    # Automatically delete obsolete records and their tags
    if ids_to_remove:
        cursor.execute(f"DELETE FROM {table_name} WHERE id IN ({','.join(['?']*len(ids_to_remove))})", list(ids_to_remove))
        cursor.execute(f"DELETE FROM {tag_table_name} WHERE channel_id IN ({','.join(['?']*len(ids_to_remove))})", list(ids_to_remove))
        print(f"Deleted {len(ids_to_remove)} outdated records and related tags.")

    # Commit changes and close connection
    conn.commit()
    conn.close()


# Main function
def main():
    from config_manager import get_channels_path
    folder_path = get_channels_path()
    db_path = "./db/persistent_data.sqlite"
    sync_channel_table(db_path, folder_path)
    result = "Channel data has been successfully loaded into the SQLite database."
    print(result)
    return result

if __name__ == '__main__':
    main()
