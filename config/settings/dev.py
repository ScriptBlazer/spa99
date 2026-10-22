"""Local development."""
from .base import *  # noqa: F401,F403
from .base import ENV, build_startup_report

DEBUG = ENV.bool("DEBUG", True)
ALLOWED_HOSTS = ALLOWED_HOSTS + ["control.localhost", "testserver"]  # noqa: F405
SITE_URL = ENV.get("SITE_URL", "http://localhost:8000").rstrip("/")
CONTROL_URL = ENV.get("CONTROL_URL", "http://control.localhost:8000").rstrip("/")

# Serve static files straight from the source folders; no collectstatic needed locally.
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True

STARTUP_REPORT = build_startup_report("config.settings.dev")
