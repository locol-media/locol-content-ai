#!/usr/bin/env python3
"""Create the main BackEnd database (users table) for a fresh environment.

Usage:
    uv run --project BackEnd python scripts/create_user_database.py [--db-path PATH] [--force]

Reuses BackEnd/src/user_management.py::init_users_table() so the schema has a
single source of truth. Only bootstraps the shared `users` table - per-user
config databases (channels/llms/prompts) are created separately, on demand,
by BackEnd/src/db_manager.py::init_user_database() during registration.
"""

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_SRC = os.path.join(REPO_ROOT, "BackEnd", "src")
DEFAULT_DB_PATH = os.path.join(REPO_ROOT, "BackEnd", "db", "persistent_data.sqlite")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH, help="Path to create/init (default: %(default)s)")
    parser.add_argument("--force", action="store_true", help="Run even if the db file already exists (init_users_table() only CREATEs IF NOT EXISTS, so existing data is untouched)")
    args = parser.parse_args()

    if os.path.exists(args.db_path) and not args.force:
        raise SystemExit(f"{args.db_path} already exists. Pass --force to run anyway.")

    os.makedirs(os.path.dirname(args.db_path), exist_ok=True)

    sys.path.insert(0, BACKEND_SRC)
    import user_management
    user_management.DATABASE_PATH = args.db_path
    user_management.init_users_table()

    print(f"Initialized users table in {args.db_path}")


if __name__ == "__main__":
    main()
