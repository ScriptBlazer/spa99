# Server setup (live)

Scripts for the live EC2 server (Ubuntu, user `ubuntu`, reached with `ssh spa99`). Run from your Mac, in the repo.

| File | What it does |
|---|---|
| `bootstrap.sh` | Prepares a fresh server. Idempotent: safe to run again. Prints each step. |
| `server-health.sh` | One-page health report (like the home server's). |
| `alert.sh` | Telegram alerts, run by cron every 5 minutes. One message on a problem, one on recovery. |

## First time

1. Copy and run:
   ```
   scp -r scripts/server spa99:~/server-setup
   ssh spa99 'sudo bash ~/server-setup/bootstrap.sh'
   ```
2. Log out and back in (the docker group only applies to new sessions).
3. Telegram:
   - In Telegram, message **@BotFather**, send `/newbot`, pick a name, and copy the token it gives you.
   - Open a chat with your new bot and press Start (a bot cannot message you first).
   - Get your chat id: open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser after sending the bot a message, and copy `"chat":{"id":...}`. (Or message @userinfobot.)
   - On the server: `nano ~/scripts/.alert.env` and fill in `TELEGRAM_BOT_TOKEN=` and `TELEGRAM_ADMIN_CHAT_ID=`. The file is mode 600 and never goes in git.
4. Test: `~/scripts/alert.sh --test`. A message should arrive.
5. Run `~/scripts/server-health.sh`.

Until the token is filled in, `alert.sh` writes one line to stderr and exits quietly.

## What bootstrap does

- `apt update && upgrade`; installs unattended-upgrades (security only), fail2ban (sshd jail), curl, jq, htop, ncdu.
- Keeps the timezone on UTC.
- 2 GB swapfile if there is no swap (in fstab, `vm.swappiness=10`).
- Docker Engine and compose plugin from Docker's apt repo if it supports this Ubuntu codename (checked with curl). Otherwise the newest older LTS codename Docker lists, otherwise Ubuntu's `docker.io` and `docker-compose-v2`. It prints which one it used.
- `/etc/docker/daemon.json`: json-file logs 10m x 5, `live-restore` (merged with anything already there).
- SSH drop-in `/etc/ssh/sshd_config.d/99-spa99.conf`: no root login, no passwords. Skipped if `~/.ssh/authorized_keys` is empty; checked with `sshd -t` before reload. Your open session stays connected.
- `~/spa99` and `~/scripts`, the two scripts, `~/scripts/.alert.env`.
- Cron for `ubuntu`: alert every 5 minutes; Sunday 04:30 UTC `docker image prune -af --filter "until=168h"` (images used by running containers are always kept; the previous release's image is kept only while a container uses it, so roll back by pulling the tag again).

## Alerts

Checks: disk `/` at 75% or more, RAM available 12% or less, swap 50% or more, site down (`https://spa99.uk/health/` not 200 after 3 tries 10 s apart), a container not running or unhealthy, certificate under 14 days, reboot required.

State is in `~/scripts/.alert_state` (`KEY=OK|ALERT`). Log: `~/scripts/alert.log`. To use another domain set `DOMAIN=` in `.alert.env`.

Caddy redirects plain http to https, so every check uses https.
