#!/usr/bin/env bash
# Spa 99 live: one-page server health report. Run: ~/scripts/server-health.sh
set -uo pipefail

APP_DIR="${APP_DIR:-$HOME/spa99}"
DOMAIN="${DOMAIN:-spa99.uk}"

section() { printf '\n===== %s =====\n' "$*"; }

section "Uptime"; uptime
section "Memory"; free -h
section "Disk"; df -h
section "Inodes"; df -ih
section "Docker containers"; docker ps
section "Docker stats"; docker stats --no-stream
section "Docker disk use"; docker system df
section "Listening ports"; ss -tulpn
section "Top CPU"; ps -eo pid,ppid,%cpu,%mem,comm --sort=-%cpu | head -n 8
section "Top memory"; ps -eo pid,ppid,%cpu,%mem,comm --sort=-%mem | head -n 8
section "Failed services"; systemctl --failed --no-pager

section "Spa 99 compose"
if [ -d "$APP_DIR" ]; then (cd "$APP_DIR" && docker compose ps); else echo "$APP_DIR not found"; fi

# Caddy redirects plain http to https, so check https. --resolve tests this server itself, whatever DNS/Cloudflare say.
section "/health/ (this server, https)"
curl -sS -o /dev/null -m 10 -w "HTTP %{http_code} in %{time_total}s\n" \
  --resolve "$DOMAIN:443:127.0.0.1" "https://$DOMAIN/health/" || echo "FAILED"
section "/health/ (public URL)"
curl -sS -o /dev/null -m 10 -w "HTTP %{http_code} in %{time_total}s\n" "https://$DOMAIN/health/" || echo "FAILED"

section "TLS certificate ($DOMAIN)"
end="$(echo | openssl s_client -servername "$DOMAIN" -connect "127.0.0.1:443" 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2 || true)"
if [ -n "${end:-}" ]; then
  end_ts="$(date -d "$end" +%s)"
  echo "Expires: $end ($(( (end_ts - $(date +%s)) / 86400 )) days left)"
else
  echo "Could not read the certificate"
fi

section "Web log (last 20 lines)"
if [ -d "$APP_DIR" ]; then (cd "$APP_DIR" && docker compose logs --tail 20 web 2>&1); fi

section "Unattended upgrades (last run)"
if [ -f /var/log/unattended-upgrades/unattended-upgrades.log ]; then
  tail -n 5 /var/log/unattended-upgrades/unattended-upgrades.log
else
  echo "No log yet"
fi
ls -l --time-style=long-iso /var/lib/apt/periodic/unattended-upgrades-stamp 2>/dev/null || true

section "Reboot required"
if [ -f /var/run/reboot-required ]; then echo "YES"; cat /var/run/reboot-required.pkgs 2>/dev/null || true; else echo "No"; fi
