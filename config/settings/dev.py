"""Local development."""
from .base import *  # noqa: F401,F403
from .base import ENV, build_startup_report

DEBUG = ENV.bool("DEBUG", True)
# Dev-only mail defaults (emails print to the console; .invalid can never deliver).
DEFAULT_FROM_EMAIL = ENV.get("DEFAULT_FROM_EMAIL", "Spa 99 <dev@spa99.invalid>")
SERVER_EMAIL = ENV.get("SERVER_EMAIL", DEFAULT_FROM_EMAIL)
ALLOWED_HOSTS = ALLOWED_HOSTS + ["control.localhost", "office.localhost", "system.localhost", "testserver"]  # noqa: F405
SITE_URL = ENV.get("SITE_URL", "http://localhost:8000").rstrip("/")
CONTROL_URL = ENV.get("CONTROL_URL", "http://control.localhost:8000").rstrip("/")
OFFICE_URL = ENV.get("OFFICE_URL", "http://office.localhost:8000").rstrip("/")
SYSTEM_URL = ENV.get("SYSTEM_URL", "http://system.localhost:8000").rstrip("/")

# Serve static files straight from the source folders; no collectstatic needed locally.
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True

STARTUP_REPORT = build_startup_report("config.settings.dev")

# Background jobs run inline on Moishe's Mac (no worker to start): emails print straight to the runserver terminal.
# Set Q_SYNC=0 in .env to test the real queue with `manage.py qcluster`.
Q_CLUSTER = {**Q_CLUSTER, "sync": ENV.get("Q_SYNC", "1") != "0"}  # noqa: F405
