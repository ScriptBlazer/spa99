#!/usr/bin/env bash
# Download the DB-IP "IP to Country Lite" file (CC BY 4.0, no account) for local use: .private/geoip/dbip-country-lite.mmdb.
# This month's file, else last month's. DB-IP publishes a new one on the first of each month. Live gets it in the Docker build.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_paths.sh"

DEST="${GEOIP_DB_PATH:-$PROJECT_DIR/.private/geoip/dbip-country-lite.mmdb}"
cd "$PROJECT_DIR"
"$PYTHON" -m common.geoip_fetch "$DEST"
