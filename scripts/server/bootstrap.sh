#!/usr/bin/env bash
# Prepares a fresh Ubuntu server for Spa 99. Safe to re-run. Run with: sudo bash bootstrap.sh
set -euo pipefail

APP_USER="${APP_USER:-ubuntu}"
APP_HOME="/home/${APP_USER}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a   # restart services automatically instead of the purple prompt

step() { printf '\n==> %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this with sudo: sudo bash $0" >&2
  exit 1
fi
id "$APP_USER" >/dev/null 2>&1 || { echo "User $APP_USER does not exist" >&2; exit 1; }

DOCKER_SOURCE=""

step "1. Update packages"
apt-get update
apt-get -y upgrade

step "2. Install base packages"
apt-get install -y unattended-upgrades fail2ban curl jq htop ncdu ca-certificates gnupg

step "3. Automatic security updates (security only)"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
CONF
# Ubuntu's default 50unattended-upgrades only enables the -security origins; make sure nothing else is on.
if [ -f /etc/apt/apt.conf.d/50unattended-upgrades ]; then
  if grep -Eq '^[[:space:]]*"\$\{distro_id\}:\$\{distro_codename\}-(updates|proposed|backports)"' /etc/apt/apt.conf.d/50unattended-upgrades; then
    note "WARNING: non-security origins are enabled in 50unattended-upgrades; review it."
  fi
fi
systemctl enable --now unattended-upgrades

step "4. fail2ban (sshd jail on)"
cat > /etc/fail2ban/jail.d/spa99-sshd.local <<'CONF'
[sshd]
enabled = true
CONF
systemctl enable fail2ban
systemctl restart fail2ban

step "5. Timezone"
note "Keeping the server on UTC (current: $(timedatectl show -p Timezone --value 2>/dev/null || echo unknown)). Cron times in the docs are UTC."

step "6. Swap (2 GB)"
if swapon --show --noheadings | grep -q .; then
  note "Swap already active, leaving it alone:"
  swapon --show | sed 's/^/    /'
else
  if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
  fi
  swapon /swapfile
  note "Swapfile /swapfile enabled"
fi
if ! grep -Eq '^[^#]*[[:space:]]swap[[:space:]]' /etc/fstab; then
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
  note "Added swap to /etc/fstab"
fi
echo 'vm.swappiness=10' > /etc/sysctl.d/99-spa99-swap.conf
sysctl -q -p /etc/sysctl.d/99-spa99-swap.conf
note "vm.swappiness=10"

step "7. Docker Engine and compose plugin"
codename="$(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")"
arch="$(dpkg --print-architecture)"
docker_ok() { curl -fsSI -m 15 "https://download.docker.com/linux/ubuntu/dists/$1/Release" >/dev/null 2>&1; }

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  DOCKER_SOURCE="already installed ($(docker --version))"
  note "$DOCKER_SOURCE"
else
  repo_codename=""
  # This Ubuntu first, then the newest older LTS Docker lists as a fallback.
  for c in "$codename" noble jammy; do
    if docker_ok "$c"; then repo_codename="$c"; break; fi
  done
  if [ -n "$repo_codename" ]; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=${arch} signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${repo_codename} stable" > /etc/apt/sources.list.d/docker.list
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    DOCKER_SOURCE="Docker official apt repo (codename ${repo_codename}; this server is ${codename})"
  else
    apt-get install -y docker.io docker-compose-v2
    DOCKER_SOURCE="Ubuntu packages docker.io + docker-compose-v2 (Docker's repo had nothing for ${codename})"
  fi
  note "Installed from: $DOCKER_SOURCE"
fi
systemctl enable docker
usermod -aG docker "$APP_USER"

step "8. Docker daemon.json (capped logs, live-restore)"
install -d /etc/docker
daemon=/etc/docker/daemon.json
tmp="$(mktemp)"
if [ -s "$daemon" ]; then base="$(cat "$daemon")"; else base='{}'; fi
printf '%s' "$base" | jq '. + {"log-driver":"json-file","log-opts":((.["log-opts"] // {}) + {"max-size":"10m","max-file":"5"}),"live-restore":true}' > "$tmp"
if ! cmp -s "$tmp" "$daemon" 2>/dev/null; then
  install -m 0644 "$tmp" "$daemon"
  systemctl restart docker
  note "Written and Docker restarted"
else
  note "Already correct"
fi
rm -f "$tmp"

step "9. SSH hardening"
key_file="$APP_HOME/.ssh/authorized_keys"
if [ ! -s "$key_file" ]; then
  note "SKIPPED: $key_file is missing or empty, so turning passwords off could lock you out."
else
  install -d /etc/ssh/sshd_config.d
  cat > /etc/ssh/sshd_config.d/99-spa99.conf <<'CONF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
CONF
  install -d -m 0755 /run/sshd   # sshd -t needs it; Ubuntu 24.04+ starts ssh on demand, so it may not exist yet
  if sshd -t; then
    if systemctl cat ssh.service >/dev/null 2>&1; then ssh_unit=ssh; else ssh_unit=sshd; fi
    # Socket-activated ssh may be inactive: then the drop-in applies to the next connection anyway. Never abort here.
    if systemctl is-active --quiet "$ssh_unit"; then
      systemctl reload "$ssh_unit" || note "WARNING: reload of '$ssh_unit' failed; the setting applies on the next ssh start."
    else
      note "'$ssh_unit' is socket-activated/inactive; the new settings apply to the next connection."
    fi
    note "sshd config valid. Your current session stays open. Test with a NEW terminal: ssh spa99"
    effective="$(sshd -T 2>/dev/null | grep -E '^(permitrootlogin|passwordauthentication) ' | tr '\n' ' ')"
    note "Effective: $effective"
  else
    rm -f /etc/ssh/sshd_config.d/99-spa99.conf
    note "ERROR: sshd -t failed; the drop-in was removed and SSH is unchanged."
  fi
fi

step "10. Folders"
install -d -o "$APP_USER" -g "$APP_USER" "$APP_HOME/spa99" "$APP_HOME/scripts"

step "11. Scripts"
for f in server-health.sh alert.sh; do
  if [ -f "$SRC_DIR/$f" ]; then
    install -m 0755 -o "$APP_USER" -g "$APP_USER" "$SRC_DIR/$f" "$APP_HOME/scripts/$f"
    note "Installed $APP_HOME/scripts/$f"
  else
    note "WARNING: $f not found next to bootstrap.sh"
  fi
done
env_file="$APP_HOME/scripts/.alert.env"
if [ ! -f "$env_file" ]; then
  cat > "$env_file" <<'CONF'
# Telegram alerts. Get a bot token from @BotFather and your chat id (see README). Never commit this file.
TELEGRAM_BOT_TOKEN=
TELEGRAM_ADMIN_CHAT_ID=
CONF
  chown "$APP_USER:$APP_USER" "$env_file"
  chmod 600 "$env_file"
  note "Created $env_file (empty, mode 600): fill it in"
else
  chmod 600 "$env_file"
  note "$env_file already exists, kept"
fi

step "12. Cron jobs for $APP_USER"
cron_alert="*/5 * * * * $APP_HOME/scripts/alert.sh >> $APP_HOME/scripts/alert.log 2>&1 # spa99-alert"
cron_prune="30 4 * * 0 docker image prune -af --filter \"until=168h\" >> $APP_HOME/scripts/prune.log 2>&1 # spa99-prune (images in use are kept)"
current="$(crontab -u "$APP_USER" -l 2>/dev/null || true)"
new="$(printf '%s\n' "$current" | grep -v '# spa99-' || true)"
printf '%s\n%s\n%s\n' "$new" "$cron_alert" "$cron_prune" | sed '/^$/d' | crontab -u "$APP_USER" -
note "Alert every 5 minutes; image prune Sundays 04:30 UTC (images used by running containers are never removed)."
cat > /etc/logrotate.d/spa99-scripts <<CONF
$APP_HOME/scripts/*.log {
  weekly
  rotate 4
  size 1M
  missingok
  notifempty
  copytruncate
}
CONF

step "Summary"
note "Docker:    $DOCKER_SOURCE"
note "Swap:      $(swapon --show --noheadings | awk '{print $1" "$3}' | tr '\n' ';')"
note "Timezone:  UTC kept"
note "SSH:       key-only, no root login (drop-in 99-spa99.conf)"
note "Updates:   unattended security upgrades on; fail2ban sshd on"
note "Crontab:"
crontab -u "$APP_USER" -l | sed 's/^/      /'
[ -f /var/run/reboot-required ] && note "A reboot is required (kernel or libc update). Reboot when convenient."
echo
echo "NEXT: log out and back in so the docker group applies to $APP_USER."
echo "Then fill in $env_file and run: ~/scripts/alert.sh --test"
