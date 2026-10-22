#!/usr/bin/env bash
# Back up the local SQLite database to <private folder>/db-backups/ (fallback: .private/db-backups/).
# Safe while the app is running (uses SQLite's online backup, not a plain file copy). Keeps the last 30.
# Live uses managed PostgreSQL: take an RDS snapshot instead.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_paths.sh"

if [ ! -f "$DB_FILE" ]; then
    echo "No database found at: $DB_FILE" >&2
    exit 1
fi

STAMP="$(date +%Y-%m-%d_%H-%M-%S)"
DEST="$BACKUP_DIR/db-$STAMP.sqlite3"

"$PYTHON" - "$DB_FILE" "$DEST" <<'PY'
import sqlite3, sys
source, destination = sys.argv[1], sys.argv[2]
with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
    src.backup(dst)
PY
echo "Backed up to: $DEST"

# Keep the newest 30, delete the rest.
COUNT=0
while IFS= read -r OLD; do
    COUNT=$((COUNT + 1))
    if [ "$COUNT" -gt 30 ]; then
        rm -f -- "$OLD"
        echo "Removed old backup: $OLD"
    fi
done < <(ls -1t "$BACKUP_DIR"/db-*.sqlite3)
