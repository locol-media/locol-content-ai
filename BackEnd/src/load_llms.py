import sqlite3
import yaml
import os
from db_manager import get_db_connection
from config_manager import get_llms_path
from bifrost_manager import VK_PREFIX
from db_crypto import encrypt_value, decrypt_or_none
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

def sync_table(db_path, table_name, yaml_dir):
    """
    Syncs an SQLite table with data from multiple YAML files in a directory.
    - Updates existing records
    - Inserts new records
    - Deletes obsolete records

    :param db_path: Path to the SQLite database file (ignored, uses user-specific db)
    :param table_name: Name of the table to sync
    :param yaml_dir: Directory containing YAML files
    """
    if not os.path.isdir(yaml_dir):
        print(f"{table_name} config directory not found, skipping sync: {yaml_dir}")
        return

    quoted_table = quote_identifier(table_name)

    conn = get_db_connection()
    cursor = conn.cursor()

    # Load new records from all YAML files
    new_data = load_yaml_files(yaml_dir)

    # Get existing records (id) from the database
    cursor.execute(f"SELECT id, APIkey FROM {quoted_table}")
    existing_rows = cursor.fetchall()
    existing_ids = {row[0] for row in existing_rows}  # Set of existing IDs

    # Rows holding a Bifrost virtual key were provisioned for this user specifically
    # (see bifrost_manager.py); the YAML only knows the shared seed values, so syncing
    # them back over would revert the routing and strand the key in Bifrost. A key that
    # won't decrypt can't be confirmed as one of ours, so the row is resynced from the
    # YAML like any other - it holds nothing usable to preserve.
    provisioned_ids = {
        row[0] for row in existing_rows
        if (decrypt_or_none(row[1]) or "").startswith(VK_PREFIX)
    }

    # Extract ids from new dataset
    new_ids = {record['id'] for record in new_data}

    # Identify records to be removed (present in DB but not in new data)
    ids_to_remove = existing_ids - new_ids

    # Insert or update records
    for record in new_data:
        record_id = record['id']
        name = record.get('name', "")  # Required field
        APIstyle = record.get('APIstyle', "")  # Required field
        APIkey = encrypt_value(record.get('APIkey', ""))  # Optional field, defaults to NULL; encrypted at rest
        APIurl = record.get('APIurl', "")  # Optional field, defaults to NULL
        model = record.get('model', "")  # Optional field, defaults to NULL

        if record_id in provisioned_ids:
            # Keep the Bifrost-provisioned connection details; the display name is the
            # only field the YAML is still authoritative for.
            cursor.execute(f"UPDATE {quoted_table} SET name = ? WHERE id = ?;", (name, record_id))
        elif record_id in existing_ids:
            # Update existing record using id
            update_query = f"""
            UPDATE {quoted_table}
            SET name = ?, APIstyle = ?, APIkey = ?, APIurl = ?, model = ?
            WHERE id = ?;
            """
            cursor.execute(update_query, (name, APIstyle, APIkey, APIurl, model, record_id))
        else:
            # Insert new record
            insert_query = f"""
            INSERT INTO {quoted_table} (id, name, APIstyle, APIkey, APIurl, model)
            VALUES (?, ?, ?, ?, ?, ?);
            """
            cursor.execute(insert_query, (record_id, name, APIstyle, APIkey, APIurl, model))

    # Automatically delete obsolete records
    if ids_to_remove:
        cursor.execute(f"DELETE FROM {quoted_table} WHERE id IN ({','.join(['?']*len(ids_to_remove))})", list(ids_to_remove))
        print(f"Deleted {len(ids_to_remove)} outdated records.")

    # Commit changes and close connection
    conn.commit()
    conn.close()


# Main function
def main():
    folder_path = get_llms_path()
    db_path = "./db/persistent_data.sqlite"
    table = "llms"
    sync_table(db_path, table, folder_path)
    result = "LLM data has been successfully loaded into the SQLite database."
    print(result)
    return result

if __name__ == '__main__':
    main()
