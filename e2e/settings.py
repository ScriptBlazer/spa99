"""Django settings for the end-to-end run ONLY (scripts/e2e.sh sets DJANGO_SETTINGS_MODULE=e2e.settings).

Dev settings, made safe and quiet for a robot:
- reads environment variables only (never the OneDrive .env or the project .env), so no real secret or bucket is reachable;
- refuses to start unless the database is a SQLite file inside the throwaway workspace (E2E_WORKSPACE), so the dev database
  can never be touched, whatever the environment says;
- media and email go to folders in that workspace (emails are written as files the run reads back);
- no rate limits (one robot IP signs in many times) and background jobs run inline.
"""
import os
from pathlib import Path

os.environ["SPA99_SKIP_ENV_FILES"] = "1"  # before base.py loads the environment: environment variables only
os.environ.pop("SENTRY_DSN", None)

from django.core.exceptions import ImproperlyConfigured  # noqa: E402

from config.settings.dev import *  # noqa: E402,F401,F403
from config.settings.dev import DATABASES, Q_CLUSTER  # noqa: E402

_workspace = os.environ.get("E2E_WORKSPACE", "")
if not _workspace:
    raise ImproperlyConfigured("e2e.settings is only for scripts/e2e.sh (E2E_WORKSPACE is not set).")
WORKSPACE = Path(_workspace).resolve()

_db = DATABASES["default"]
if not _db["ENGINE"].endswith("sqlite3") or WORKSPACE not in Path(str(_db["NAME"])).resolve().parents:
    raise ImproperlyConfigured(f"e2e refuses to run: the database must be a SQLite file inside {WORKSPACE} (DATABASE_URL), not {_db['NAME']}.")

EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
EMAIL_FILE_PATH = str(WORKSPACE / "mail")
DEFAULT_FROM_EMAIL = "Spa 99 <e2e@example.com>"
SERVER_EMAIL = DEFAULT_FROM_EMAIL

STORAGES = {
    **STORAGES,  # noqa: F405 (staticfiles as dev)
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage", "OPTIONS": {"location": str(WORKSPACE / "media"), "base_url": "/media/"}},
}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}  # rate limits off
Q_CLUSTER = {**Q_CLUSTER, "sync": True}
