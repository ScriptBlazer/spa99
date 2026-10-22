"""Live server. Refuses to start without a real SECRET_KEY and DATABASE_URL."""
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import DEV_SECRET_KEY, DOMAIN, ENV, PRIVATE_DIR, SECRET_KEY, build_startup_report
from common.settings_helpers import build_databases, build_media_storage, describe_database

_weak_secret_markers = ("insecure", "change-me", "changeme", "dummy")
if not SECRET_KEY or SECRET_KEY == DEV_SECRET_KEY or any(m in SECRET_KEY.lower() for m in _weak_secret_markers):
    raise ImproperlyConfigured("SECRET_KEY must be set to a real secret in production.")
if not ENV.get("DATABASE_URL"):
    raise ImproperlyConfigured("DATABASE_URL must be set in production (managed PostgreSQL).")

DEBUG = False
CONTROL_HOST = ENV.get("CONTROL_DOMAIN", "control.spa99.uk")
ALLOWED_HOSTS = ENV.list("ALLOWED_HOSTS", [DOMAIN, CONTROL_HOST, "localhost", "127.0.0.1"])  # localhost: health check

DATABASES = build_databases(ENV.get("DATABASE_URL"), None, require_ssl=True)

# Media: S3 prod/ folder. Credentials come from the EC2 instance role (no AWS keys in the server .env).
MEDIA_STORAGE, MEDIA_DESCRIPTION = build_media_storage(
    ENV, location_prefix="prod/", local_media_dir=PRIVATE_DIR.subdir("media"), require_credentials=False
)
STORAGES = {**STORAGES, "default": MEDIA_STORAGE}  # noqa: F405
if MEDIA_STORAGE["BACKEND"].endswith("FileSystemStorage"):
    MEDIA_DESCRIPTION += " (WARNING: S3 not configured, files are lost when the container is replaced)"

# HTTPS behind Caddy (RULES.md section 9). HSTS stays off until the site has run on HTTPS without problems.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^health/$"]  # the container health check speaks plain http
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = [f"https://{DOMAIN}", f"https://{CONTROL_HOST}"]
SECURE_HSTS_SECONDS = 0
TRUST_FORWARDED_FOR = True  # Caddy sets X-Forwarded-For to the real client IP

_sentry_dsn = ENV.get("SENTRY_DSN")
if _sentry_dsn:
    import sentry_sdk

    sentry_sdk.init(dsn=_sentry_dsn, send_default_pii=False, traces_sample_rate=0)

STARTUP_REPORT = build_startup_report("config.settings.prod")
STARTUP_REPORT["database"] = describe_database(DATABASES)
STARTUP_REPORT["media"] = MEDIA_DESCRIPTION
