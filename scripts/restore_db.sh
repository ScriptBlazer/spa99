#!/usr/bin/env bash
# Restore the local SQLite database from a backup. Lists backups, asks you to pick one,
# then asks you to type RESTORE. The current database is kept as a safety copy first.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_paths.sh"

BACKUPS=()
while IFS= read -r FILE; do
    BACKUPS+=("$FILE")
done < <(ls -1t "$BACKUP_DIR"/db-*.sqlite3 2>/dev/null || true)

if [ "${#BACKUPS[@]}" -eq 0 ]; then
    echo "No backups found in: $BACKUP_DIR" >&2
    exit 1
fi

echo "Backups in $BACKUP_DIR (newest first):"
for INDEX in "${!BACKUPS[@]}"; do
    echo "  $((INDEX + 1)). $(basename "${BACKUPS[$INDEX]}")"
done

read -r -p "Number to restore (or Enter to cancel): " CHOICE
if [ -z "$CHOICE" ]; then echo "Cancelled."; exit 0; fi
if ! [[ "$CHOICE" =~ ^[0-9]+$ ]] || [ "$CHOICE" -lt 1 ] || [ "$CHOICE" -gt "${#BACKUPS[@]}" ]; then
    echo "Not a valid number." >&2
    exit 1
fi
SELECTED="${BACKUPS[$((CHOICE - 1))]}"

echo
echo "This REPLACES the current database:"
echo "  $DB_FILE"
echo "with:"
echo "  $SELECTED"
echo "Stop runserver and the worker first. The current database is saved next to it as a safety copy."
read -r -p "Type RESTORE to continue: " CONFIRM
if [ "$CONFIRM" != "RESTORE" ]; then echo "Cancelled."; exit 0; fi

mkdir -p "$(dirname "$DB_FILE")"
if [ -f "$DB_FILE" ]; then
    SAFETY="$DB_FILE.before-restore-$(date +%Y-%m-%d_%H-%M-%S)"
    cp -- "$DB_FILE" "$SAFETY"
    echo "Safety copy: $SAFETY"
fi
rm -f -- "$DB_FILE-wal" "$DB_FILE-shm"
cp -- "$SELECTED" "$DB_FILE"
echo "Restored."
