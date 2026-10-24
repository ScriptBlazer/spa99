#!/usr/bin/env bash
# One command, whole site: a real browser (Playwright) walks the nine user journeys against a THROWAWAY copy of the site.
#
#   scripts/e2e.sh                     run everything, write the report, delete the workspace
#   scripts/e2e.sh --keep              keep the workspace (.private/e2e: database, emails, media, server log) to look around
#   scripts/e2e.sh --headed            show the browser window
#   scripts/e2e.sh --only gold_approved,6   run some walk-throughs (names or numbers; --list shows them)
#
# Never touches your dev database or OneDrive: see docs/features/e2e.md. Exit code is non-zero if any step failed.
set -u -o pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 2

KEEP=0
RUN_ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --keep) KEEP=1 ;;
    --headed) RUN_ARGS+=("--headed") ;;
    --only) shift; RUN_ARGS+=("--only" "${1:-}") ;;
    --only=*) RUN_ARGS+=("--only" "${1#--only=}") ;;
    --list) PY_LIST=1 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1 (see --help)"; exit 2 ;;
  esac
  shift
done

PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"
if [ "${PY_LIST:-0}" = "1" ]; then exec "$PY" -m e2e.run --list; fi
if ! "$PY" -c "import playwright" 2>/dev/null; then
  echo "Playwright is not installed. Once:"
  echo "  \"$ROOT/.venv/bin/pip\" install -r requirements-dev.txt"
  echo "  \"$ROOT/.venv/bin/python\" -m playwright install chromium"
  exit 2
fi

WS="$ROOT/.private/e2e"                  # throwaway workspace (git-ignored)
REPORT="$ROOT/.private/e2e-report"       # the report is kept (git-ignored)
SERVER_PID=""

cleanup() {
  if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null
    wait "$SERVER_PID" 2>/dev/null
  fi
  if [ -f "$WS/server.log" ]; then cp "$WS/server.log" "$REPORT/server.log" 2>/dev/null; fi
  if [ "$KEEP" = "1" ]; then
    echo "Workspace kept: $WS"
  else
    rm -rf "$WS"
  fi
}
trap cleanup EXIT
trap 'exit 130' INT TERM

rm -rf "$WS" "$REPORT"
mkdir -p "$WS/mail" "$WS/media" "$WS/private" "$REPORT"

# A free port, starting at 8765.
PORT="$("$PY" - <<'PYEOF'
import socket
for port in range(8765, 8800):
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", port)) != 0:
            print(port)
            break
PYEOF
)"
[ -n "$PORT" ] || { echo "No free port between 8765 and 8799."; exit 2; }

# ---- isolation: everything the site reads comes from here, never from your real .env or database ----
export E2E_WORKSPACE="$WS"
export E2E_PORT="$PORT"
export E2E_REPORT_DIR="$REPORT"
export DJANGO_SETTINGS_MODULE="e2e.settings"          # refuses to start unless the database is inside $WS
export SPA99_SKIP_ENV_FILES=1                         # environment variables only (no OneDrive .env, no project .env)
export SPA99_PRIVATE_DIR="$WS/private"
export DATABASE_URL="sqlite:///$WS/db.sqlite3"        # sqlite:/// + absolute path: the throwaway file
export SECRET_KEY="e2e-only-secret-key-not-used-anywhere-else-0123456789"
export SENTRY_DSN=""
export Q_SYNC=1                                       # background jobs (emails) run inline
export SYSTEM_UNLOCK_CODE="482916"
export DEBUG=true
export DOMAIN="localhost" OFFICE_DOMAIN="office.localhost" CONTROL_DOMAIN="control.localhost" SYSTEM_DOMAIN="system.localhost"
export SITE_URL="http://localhost:$PORT" OFFICE_URL="http://office.localhost:$PORT" CONTROL_URL="http://control.localhost:$PORT" SYSTEM_URL="http://system.localhost:$PORT"
export ADMIN_PATH="e2e-admin/" DEFAULT_FROM_EMAIL="Spa 99 <e2e@example.com>"
unset AWS_STORAGE_BUCKET_NAME AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY EMAIL_HOST EMAIL_HOST_USER EMAIL_HOST_PASSWORD

echo "Workspace: $WS (database, emails and media live only there)"
echo "Setting up the throwaway site ..."
{
  "$PY" manage.py migrate --noinput &&
  "$PY" manage.py setup_roles &&
  "$PY" manage.py seed_phase1 &&
  "$PY" manage.py register_schedules
} > "$WS/setup.log" 2>&1 || { echo "Setup failed. Last lines:"; tail -n 25 "$WS/setup.log"; cp "$WS/setup.log" "$REPORT/" 2>/dev/null; exit 2; }
cp "$WS/setup.log" "$REPORT/setup.log"

echo "Starting the server on 127.0.0.1:$PORT (localhost, office., control., system.localhost) ..."
"$PY" manage.py runserver "127.0.0.1:$PORT" --noreload > "$WS/server.log" 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:$PORT/health/" >/dev/null 2>&1; then break; fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then echo "The server stopped. Log:"; tail -n 25 "$WS/server.log"; exit 2; fi
  sleep 0.5
done
curl -fsS "http://127.0.0.1:$PORT/health/" >/dev/null 2>&1 || { echo "The server never answered /health/."; tail -n 25 "$WS/server.log"; exit 2; }

"$PY" -m e2e.run "${RUN_ARGS[@]+"${RUN_ARGS[@]}"}"
STATUS=$?
exit "$STATUS"
