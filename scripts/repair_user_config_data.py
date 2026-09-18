#!/usr/bin/env python3
"""Backfill channels/llms/prompts config data for existing per-user databases
left incomplete by the config_manager.py path bug (fixed alongside this script).

Usage:
    uv run --project BackEnd python scripts/repair_user_config_data.py [--dry-run]

For every account in the main users table, ensures its per-user database has
channels/llms/prompts tables (via db_manager.init_user_database(), itself
schema-idempotent), then INSERTS any seed records missing from those tables.
Strictly additive: never updates or deletes an existing row, so it's safe to
run against accounts that already have data - including user-created records
beyond the seed set - it only fills in gaps.
"""

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(REPO_ROOT, "BackEnd")
BACKEND_SRC = os.path.join(BACKEND_DIR, "src")


def _backfill_channels(conn, yaml_dir):
    from load_channels import load_yaml_files
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM channels")
    existing = {row[0] for row in cursor.fetchall()}
    added = 0
    for record in load_yaml_files(yaml_dir):
        if record["id"] in existing:
            continue
        cursor.execute("INSERT INTO channels (id, name) VALUES (?, ?)", (record["id"], record.get("name")))
        for tag in record.get("tags", []):
            cursor.execute("INSERT INTO channel_tags (channel_id, tag) VALUES (?, ?)", (record["id"], tag))
        added += 1
    conn.commit()
    return added


def _backfill_llms(conn, yaml_dir):
    from load_llms import load_yaml_files
    from db_crypto import encrypt_value
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM llms")
    existing = {row[0] for row in cursor.fetchall()}
    added = 0
    for record in load_yaml_files(yaml_dir):
        if record["id"] in existing:
            continue
        cursor.execute(
            "INSERT INTO llms (id, name, APIstyle, APIkey, APIurl, model) VALUES (?, ?, ?, ?, ?, ?)",
            (
                record["id"],
                record.get("name", ""),
                record.get("APIstyle", ""),
                encrypt_value(record.get("APIkey", "")),
                record.get("APIurl", ""),
                record.get("model", ""),
            ),
        )
        added += 1
    conn.commit()
    return added


def _backfill_prompts(conn, yaml_dir):
    from load_prompts import load_yaml_files
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM prompts")
    existing = {row[0] for row in cursor.fetchall()}
    added = 0
    for record in load_yaml_files(yaml_dir):
        if record["id"] in existing:
            continue
        cursor.execute(
            "INSERT INTO prompts (id, name, template) VALUES (?, ?, ?)",
            (record["id"], record.get("name"), record.get("template")),
        )
        for tag in record.get("tags", []):
            cursor.execute("INSERT INTO prompt_tags (prompt_id, tag) VALUES (?, ?)", (record["id"], tag))
        added += 1
    conn.commit()
    return added


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="List affected accounts without writing anything")
    args = parser.parse_args()

    os.chdir(BACKEND_DIR)
    sys.path.insert(0, BACKEND_SRC)

    import sqlite3
    from db_manager import init_user_database, set_current_user, get_user_db_path, MAIN_DB_PATH
    from config_manager import get_channels_path, get_llms_path, get_prompt_templates_path

    conn = sqlite3.connect(MAIN_DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, username FROM users")
    users = cursor.fetchall()
    conn.close()

    print(f"Found {len(users)} account(s) in {MAIN_DB_PATH}")
    for user_id, username in users:
        if args.dry_run:
            print(f"[dry-run] would backfill {username} ({user_id})")
            continue

        set_current_user(user_id)
        init_user_database(user_id)  # ensures tables exist; idempotent

        user_conn = sqlite3.connect(get_user_db_path(user_id))
        added_channels = _backfill_channels(user_conn, get_channels_path())
        added_llms = _backfill_llms(user_conn, get_llms_path())
        added_prompts = _backfill_prompts(user_conn, get_prompt_templates_path())
        user_conn.close()

        print(f"Backfilled {username} ({user_id}): +{added_channels} channels, +{added_llms} llms, +{added_prompts} prompts")

    print("Done.")


if __name__ == "__main__":
    main()
