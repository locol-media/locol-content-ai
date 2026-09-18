import os
import sqlite3
from fastapi import HTTPException
from db_manager import get_db_connection
from db_crypto import encrypt_value, decrypt_or_none
from models import LLMConfig, LLMConfigUpdate, ChannelConfig, ChannelConfigUpdate, PromptConfig, PromptConfigUpdate

def get_config_root():
    """
    Returns the root path for configuration files.
    Default location is config/default relative to the BackEnd directory.
    """
    LOCOL_CONFIG_LOCATION = os.environ.get('LOCOL_CONFIG_LOCATION', './config')
    config_root = os.path.join(LOCOL_CONFIG_LOCATION, "default")
    return config_root

# Convenience constant
CONFIG_ROOT = get_config_root()

def get_channels_path():
    """Returns the path to the channels configuration directory."""
    return os.path.join(CONFIG_ROOT, "channels")

def get_llms_path():
    """Returns the path to the LLMs configuration directory."""
    return os.path.join(CONFIG_ROOT, "llms")

def get_prompt_templates_path():
    """Returns the path to the prompt templates directory."""
    return os.path.join(CONFIG_ROOT, "promptTemplates")

# =============================================================================
# LLM CRUD Operations
# =============================================================================

# Shown in place of a key that won't decrypt. Deliberately not blank, which would read
# as "no key set" - the key is there, it just can't be read under the current key.
UNREADABLE_KEY_PLACEHOLDER = "(unreadable - re-enter this key)"

def _mask_api_key(api_key):
    """Mask an API key so only the last 4 characters are visible."""
    if not api_key:
        return api_key
    if len(api_key) <= 4:
        return "•" * len(api_key)
    return "•" * (len(api_key) - 4) + api_key[-4:]

def get_all_llms():
    """
    Get all LLM configurations.

    APIkey is decrypted, then masked; the real value is never sent to clients. A row
    whose key won't decrypt is reported with UNREADABLE_KEY_PLACEHOLDER rather than
    failing the whole list, and is left untouched in the database.
    """
    conn = get_db_connection()
    conn.row_factory = lambda cursor, row: {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, APIstyle, APIkey, APIurl, model FROM llms ORDER BY name ASC")
    rows = cursor.fetchall()
    for row in rows:
        plaintext = decrypt_or_none(row["APIkey"])
        if plaintext is None:
            # stdout, not just a logger: no handlers are configured here, so a
            # logger-only warning is invisible in container logs. Never log the value.
            print(f"[config] APIkey for LLM '{row['id']}' could not be decrypted; "
                  f"the database encryption key may have changed")
            row["APIkey"] = UNREADABLE_KEY_PLACEHOLDER
        else:
            row["APIkey"] = _mask_api_key(plaintext)
    conn.close()
    return rows

def create_llm(config: LLMConfig):
    """Create a new LLM configuration"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO llms (id, name, APIstyle, APIkey, APIurl, model) VALUES (?, ?, ?, ?, ?, ?)",
            (config.id, config.name, config.APIstyle, encrypt_value(config.APIkey), config.APIurl, config.model)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=409, detail=f"An LLM with id '{config.id}' already exists")
    conn.close()
    return {"success": True, "id": config.id}

def update_llm(llm_id: str, config: LLMConfigUpdate):
    """Update an LLM configuration"""
    conn = get_db_connection()
    cursor = conn.cursor()
    updates = []
    values = []
    if config.name is not None:
        updates.append("name = ?")
        values.append(config.name)
    if config.APIstyle is not None:
        updates.append("APIstyle = ?")
        values.append(config.APIstyle)
    if config.APIkey is not None:
        updates.append("APIkey = ?")
        values.append(encrypt_value(config.APIkey))
    if config.APIurl is not None:
        updates.append("APIurl = ?")
        values.append(config.APIurl)
    if config.model is not None:
        updates.append("model = ?")
        values.append(config.model)

    if updates:
        values.append(llm_id)
        cursor.execute(f"UPDATE llms SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
    conn.close()
    return {"success": True, "id": llm_id}

def delete_llm(llm_id: str):
    """Delete an LLM configuration"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM llms WHERE id = ?", (llm_id,))
    conn.commit()
    conn.close()
    return {"success": True, "id": llm_id}

# =============================================================================
# Channel CRUD Operations
# =============================================================================

def get_all_channels():
    """Get all channel configurations"""
    conn = get_db_connection()
    conn.row_factory = lambda cursor, row: {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM channels ORDER BY name ASC")
    rows = cursor.fetchall()
    conn.close()
    return rows

def create_channel(config: ChannelConfig):
    """Create a new channel configuration"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO channels (id, name, parent) VALUES (?, ?, ?)",
            (config.id, config.name, config.parent)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=409, detail=f"A channel with id '{config.id}' already exists")
    conn.close()
    return {"success": True, "id": config.id}

def update_channel(channel_id: str, config: ChannelConfigUpdate):
    """Update a channel configuration"""
    conn = get_db_connection()
    cursor = conn.cursor()
    updates = []
    values = []
    if config.name is not None:
        updates.append("name = ?")
        values.append(config.name)
    if config.parent is not None:
        updates.append("parent = ?")
        values.append(config.parent)

    if updates:
        values.append(channel_id)
        cursor.execute(f"UPDATE channels SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
    conn.close()
    return {"success": True, "id": channel_id}

def delete_channel(channel_id: str):
    """Delete a channel configuration"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
    cursor.execute("DELETE FROM channel_tags WHERE channel_id = ?", (channel_id,))
    conn.commit()
    conn.close()
    return {"success": True, "id": channel_id}

# =============================================================================
# Prompt CRUD Operations
# =============================================================================

def get_all_prompts():
    """Get all prompt configurations with tags"""
    conn = get_db_connection()
    conn.row_factory = lambda cursor, row: {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, template FROM prompts ORDER BY name ASC")
    prompts = cursor.fetchall()

    # Get tags for each prompt
    for prompt in prompts:
        cursor.execute("SELECT tag FROM prompt_tags WHERE prompt_id = ?", (prompt['id'],))
        tags = [row['tag'] for row in cursor.fetchall()]
        prompt['tags'] = tags

    conn.close()
    return prompts

def create_prompt(config: PromptConfig):
    """Create a new prompt configuration"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO prompts (id, name, template) VALUES (?, ?, ?)",
            (config.id, config.name, config.template)
        )

        # Insert tags
        if config.tags:
            for tag in config.tags:
                cursor.execute(
                    "INSERT INTO prompt_tags (prompt_id, tag) VALUES (?, ?)",
                    (config.id, tag)
                )

        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=409, detail=f"A prompt with id '{config.id}' already exists")
    conn.close()
    return {"success": True, "id": config.id}

def update_prompt(prompt_id: str, config: PromptConfigUpdate):
    """Update a prompt configuration"""
    conn = get_db_connection()
    cursor = conn.cursor()
    updates = []
    values = []
    if config.name is not None:
        updates.append("name = ?")
        values.append(config.name)
    if config.template is not None:
        updates.append("template = ?")
        values.append(config.template)

    if updates:
        values.append(prompt_id)
        cursor.execute(f"UPDATE prompts SET {', '.join(updates)} WHERE id = ?", values)

    # Update tags if provided
    if config.tags is not None:
        cursor.execute("DELETE FROM prompt_tags WHERE prompt_id = ?", (prompt_id,))
        for tag in config.tags:
            cursor.execute(
                "INSERT INTO prompt_tags (prompt_id, tag) VALUES (?, ?)",
                (prompt_id, tag)
            )

    conn.commit()
    conn.close()
    return {"success": True, "id": prompt_id}

def delete_prompt(prompt_id: str):
    """Delete a prompt configuration"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM prompts WHERE id = ?", (prompt_id,))
    cursor.execute("DELETE FROM prompt_tags WHERE prompt_id = ?", (prompt_id,))
    conn.commit()
    conn.close()
    return {"success": True, "id": prompt_id}
