#!/usr/bin/env bash
# Share this Mac's dev site on temporary public https links (Cloudflare quick tunnels, free, no account).
# Gives two links: the website and the Office. Ctrl+C stops the links and the server. Links change every run.
# Needs: brew install cloudflared. Stop any other runserver on the same port first.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v cloudflared >/dev/null || { echo "Install it first:  brew install cloudflared"; exit 1; }
PORT="${PORT:-8000}"
LOGS="$(mktemp -d)"
trap 'kill $(jobs -p) 2>/dev/null || true' EXIT INT TERM

for name in site office; do
  cloudflared tunnel --no-autoupdate --url "http://localhost:$PORT" >"$LOGS/$name.log" 2>&1 &
done

link() {
  for _ in $(seq 60); do
    u=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOGS/$1.log" | head -1 || true)
    [ -n "$u" ] && { echo "$u"; return 0; }
    sleep 1
  done
  echo "The $1 link did not start. Details: $LOGS/$1.log" >&2
  exit 1
}
SITE=$(link site)
OFFICE=$(link office)

export DOMAIN="${SITE#https://}" OFFICE_DOMAIN="${OFFICE#https://}" SITE_URL="$SITE" OFFICE_URL="$OFFICE"
export ALLOWED_HOSTS="$DOMAIN,$OFFICE_DOMAIN" CSRF_TRUSTED_ORIGINS="$SITE,$OFFICE" DEV_BEHIND_TUNNEL=1

echo
echo "  Website: $SITE"
echo "  Office:  $OFFICE"
echo
echo "  Anyone with these links can open them while this runs. Ctrl+C to stop."
echo
PY=".venv/bin/python"; [ -x "$PY" ] || PY="python"
"$PY" manage.py runserver "$PORT"
