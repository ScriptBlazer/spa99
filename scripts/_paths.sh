#!/usr/bin/env bash
# Shared by backup_db.sh and restore_db.sh. Source it; do not run it.
# Sets: PROJECT_DIR, PRIVATE_DIR, BACKUP_DIR, DB_FILE, PYTHON

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_PRIVATE_DIR="/Users/moishe/Library/CloudStorage/OneDrive-Personal/BML/Spa 99/Software Files"
PRIVATE_DIR="${SPA99_PRIVATE_DIR:-$DEFAULT_PRIVATE_DIR}"

# Use the private folder only if it exists and we can write to it; otherwise the git-ignored .private/.
if [ ! -d "$PRIVATE_DIR" ] || [ ! -w "$PRIVATE_DIR" ]; then
    PRIVATE_DIR="$PROJECT_DIR/.private"
fi
BACKUP_DIR="$PRIVATE_DIR/db-backups"
mkdir -p "$BACKUP_DIR"

# The working database always lives in the project's .private/, never in OneDrive.
DB_FILE="${SPA99_DB_FILE:-$PROJECT_DIR/.private/db.sqlite3}"

if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
    PYTHON="$PROJECT_DIR/.venv/bin/python"
else
    PYTHON="python3"
fi
