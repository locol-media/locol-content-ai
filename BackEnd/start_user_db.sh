#!/bin/bash

# Script to start sqlite_web for a specific user's database
# Usage: ./start_user_db.sh <username>

# Check if username is provided
if [ $# -eq 0 ]; then
    echo "Usage: $0 <username>"
    echo "Example: $0 john_doe"
    exit 1
fi

USERNAME="$1"
PERSISTENT_DB="/app/BackEnd/db/persistent_data.sqlite"
USER_DB_DIR="/app/BackEnd/db/users"
# Set in the image's ENV; the fallback keeps this correct when the script is run
# outside the container, where that ENV doesn't apply.
USER_DB_PORT="${LOCOL_USER_DB_PORT:-8081}"

# Check if persistent database exists
if [ ! -f "$PERSISTENT_DB" ]; then
    echo "Error: Persistent database not found at $PERSISTENT_DB"
    exit 1
fi

# Check if sqlite3 is available
if ! command -v sqlite3 &> /dev/null; then
    echo "Error: sqlite3 command not found. Please install sqlite3."
    exit 1
fi

# Look up user ID by username
echo "Looking up user ID for username: $USERNAME"
USER_ID=$(sqlite3 "$PERSISTENT_DB" "SELECT id FROM users WHERE username='$USERNAME' AND is_active=1;" 2>/dev/null)

# Check if user was found
if [ -z "$USER_ID" ]; then
    echo "Error: User '$USERNAME' not found or inactive in the database."
    echo "Available active users:"
    sqlite3 "$PERSISTENT_DB" "SELECT username FROM users WHERE is_active=1;" 2>/dev/null
    exit 1
fi

echo "Found user ID: $USER_ID"

# Construct path to user's database
USER_DB_PATH="$USER_DB_DIR/$USER_ID.sqlite"

# Check if user's database exists
if [ ! -f "$USER_DB_PATH" ]; then
    echo "Error: User database not found at $USER_DB_PATH"
    echo "Available user databases:"
    ls -la "$USER_DB_DIR"/*.sqlite 2>/dev/null || echo "No user databases found"
    exit 1
fi

# Check for existing processes using the port and kill them
echo "Checking for existing processes on port $USER_DB_PORT..."
PID=$(lsof -ti:"$USER_DB_PORT" 2>/dev/null)
if [ ! -z "$PID" ]; then
    echo "Found process $PID using port $USER_DB_PORT. Killing it..."
    kill -9 $PID 2>/dev/null
    sleep 1
    echo "Process killed."
else
    echo "No existing process found on port $USER_DB_PORT."
fi

echo "Starting sqlite_web for user '$USERNAME' (ID: $USER_ID)"
echo "Database path: $USER_DB_PATH"
echo "Access at: http://0.0.0.0:$USER_DB_PORT"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""
cd /app/sqlite-web
# Start sqlite_web pointing to the user's database. Runs the module directly rather
# than `-m sqlite_web`, whose __main__.py shim is broken upstream in 0.8.0 (see the
# pin in the Dockerfile); this form works on every version.
exec /usr/local/bin/python3 -m sqlite_web.sqlite_web "$USER_DB_PATH" --host 0.0.0.0 --port "$USER_DB_PORT"