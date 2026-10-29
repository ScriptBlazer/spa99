#!/usr/bin/env bash
# Spa 99 live: Telegram alerts, one message when a check turns bad and one when it recovers.
# Cron runs it every 5 minutes. `alert.sh --test` sends one test message.
set -euo pipefail

SERVER_NAME="Spa 99 live"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ALERT_ENV_FILE:-$SCRIPT_DIR/.alert.env}"
STATE_FILE="${ALERT_STATE_FILE:-$SCRIPT_DIR/.alert_state}"
APP_DIR="${APP_DIR:-$HOME/spa99}"
DOMAIN="${DOMAIN:-spa99.uk}"

DISK_LIMIT=75        # percent used on /
RAM_AVAIL_MIN=12     # percent available
SWAP_LIMIT=50        # percent used
CERT_DAYS_MIN=14

[ -f "$ENV_FILE" ] || { echo "alert.sh: $ENV_FILE not found" >&2; exit 0; }
# shellcheck disable=SC1090
. "$ENV_FILE"
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_ADMIN_CHAT_ID="${TELEGRAM_ADMIN_CHAT_ID:-}"
if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_ADMIN_CHAT_ID" ]; then
  echo "alert.sh: Telegram token or chat id is empty in $ENV_FILE; nothing sent" >&2
  exit 0
fi

send() {
  # -K - keeps the token out of the process list; --data-urlencode escapes the text.
  # Returns non-zero (and says why) when Telegram refuses, e.g. "chat not found".
  local reply
  reply="$(printf 'url = "https://api.telegram.org/bot%s/sendMessage"\n' "$TELEGRAM_BOT_TOKEN" |
    curl -sS -m 20 -K - \
      --data-urlencode "chat_id=$TELEGRAM_ADMIN_CHAT_ID" \
      --data-urlencode "text=$1" --data-urlencode "disable_web_page_preview=true" 2>&1)" || { echo "alert.sh: Telegram send failed: $reply" >&2; return 1; }
  if ! printf '%s' "$reply" | jq -e '.ok == true' >/dev/null 2>&1; then
    echo "alert.sh: Telegram refused: $(printf '%s' "$reply" | jq -r '.description // "unknown reply"' 2>/dev/null)" >&2
    return 1
  fi
}

if [ "${1:-}" = "--test" ]; then
  if send "✅ $SERVER_NAME: test message from alert.sh ($(date -u '+%Y-%m-%d %H:%M UTC'))"; then
    echo "Test message sent (check Telegram)."
    exit 0
  fi
  echo "Test message NOT delivered (see the reason above)."
  exit 1
fi

touch "$STATE_FILE"
chmod 600 "$STATE_FILE"

get_state() { grep "^$1=" "$STATE_FILE" 2>/dev/null | tail -n1 | cut -d= -f2 || true; }
set_state() {
  local tmp
  tmp="$(mktemp)"
  { grep -v "^$1=" "$STATE_FILE" || true; echo "$1=$2"; } > "$tmp"
  cat "$tmp" > "$STATE_FILE"
  rm -f "$tmp"
}

# check KEY STATUS(OK|ALERT) "problem text" "recovery text"
check() {
  local key="$1" status="$2" bad="$3" good="$4" prev
  prev="$(get_state "$key")"
  if [ "$status" = "ALERT" ] && [ "$prev" != "ALERT" ]; then
    send "🚨 $SERVER_NAME: $bad"
  elif [ "$status" = "OK" ] && [ "$prev" = "ALERT" ]; then
    send "✅ $SERVER_NAME recovered: $good"
  fi
  set_state "$key" "$status"
}

# Disk
disk_pct="$(df -P / | awk 'NR==2 {gsub("%","",$5); print $5}')"
if [ "$disk_pct" -ge "$DISK_LIMIT" ]; then s=ALERT; else s=OK; fi
check DISK "$s" "disk / is ${disk_pct}% full (limit ${DISK_LIMIT}%)" "disk / is ${disk_pct}% full"

# RAM
ram_pct="$(free | awk '/^Mem:/ {printf "%d", $7*100/$2}')"
if [ "$ram_pct" -le "$RAM_AVAIL_MIN" ]; then s=ALERT; else s=OK; fi
check RAM "$s" "only ${ram_pct}% RAM available (limit ${RAM_AVAIL_MIN}%)" "${ram_pct}% RAM available"

# Swap
swap_pct="$(free | awk '/^Swap:/ {if ($2>0) printf "%d", $3*100/$2; else print 0}')"
if [ "$swap_pct" -ge "$SWAP_LIMIT" ]; then s=ALERT; else s=OK; fi
check SWAP "$s" "swap ${swap_pct}% used (limit ${SWAP_LIMIT}%)" "swap ${swap_pct}% used"

# Site down: 3 tries, 10 s apart, to avoid flapping
code=000
for i in 1 2 3; do
  code="$(curl -s -o /dev/null -m 10 -w '%{http_code}' "https://$DOMAIN/health/" || true)"
  [ "$code" = "200" ] && break
  [ "$i" -lt 3 ] && sleep 10
done
if [ "$code" != "200" ]; then s=ALERT; else s=OK; fi
check SITE "$s" "https://$DOMAIN/health/ answered ${code} (not 200)" "https://$DOMAIN/health/ answers 200"

# Containers
bad_list=""
if [ -d "$APP_DIR" ]; then
  out="$(cd "$APP_DIR" && docker compose ps -a --format json 2>/dev/null || true)"
  if [ -n "$out" ]; then
    # Newer compose prints one JSON object per line, older prints an array; jq -s handles both.
    bad_list="$(printf '%s\n' "$out" | jq -rs 'flatten | .[] | select(.State != "running" or ((.Health // "") != "" and .Health != "healthy")) | "\(.Service)=\(.State)\(if (.Health // "") != "" then "/" + .Health else "" end)"' | tr '\n' ' ')"
  else
    bad_list="no containers found "
  fi
else
  bad_list="$APP_DIR missing "
fi
if [ -n "$bad_list" ]; then s=ALERT; else s=OK; fi
check CONTAINERS "$s" "container problem: ${bad_list}" "all containers running and healthy"

# Certificate
end="$(echo | openssl s_client -servername "$DOMAIN" -connect "127.0.0.1:443" 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2 || true)"
if [ -n "$end" ]; then
  days=$(( ( $(date -d "$end" +%s) - $(date +%s) ) / 86400 ))
  if [ "$days" -lt "$CERT_DAYS_MIN" ]; then s=ALERT; else s=OK; fi
  check CERT "$s" "certificate for $DOMAIN expires in ${days} days (limit ${CERT_DAYS_MIN})" "certificate for $DOMAIN has ${days} days left"
else
  check CERT ALERT "could not read the certificate for $DOMAIN" "certificate readable again"
fi

# Reboot required: alert once, recover when the reboot is done
if [ -f /var/run/reboot-required ]; then s=ALERT; else s=OK; fi
check REBOOT "$s" "reboot required (security updates installed)" "reboot done"
