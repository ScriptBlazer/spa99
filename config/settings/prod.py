"""Live server. Refuses to start without a real SECRET_KEY and DATABASE_URL."""
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import ADMIN_PATH, DEFAULT_ADMIN_PATH, DEV_SECRET_KEY, DOMAIN, ENV, finish_media_description, PRIVATE_DIR, SECRET_KEY, SYSTEM_UNLOCK_CODE, build_startup_report
from common.settings_helpers import build_databases, build_media_storage, describe_database

_weak_secret_markers = ("insecure", "change-me", "changeme", "dummy")
if not SECRET_KEY or SECRET_KEY == DEV_SECRET_KEY or any(m in SECRET_KEY.lower() for m in _weak_secret_markers):
    raise ImproperlyConfigured("SECRET_KEY must be set to a real secret in production.")
if not ENV.get("DEFAULT_FROM_EMAIL"):
    raise ImproperlyConfigured("DEFAULT_FROM_EMAIL must be set in production (the From address of every email).")
if not SYSTEM_UNLOCK_CODE:  # missing or not 6 to 12 digits
    raise ImproperlyConfigured("SYSTEM_UNLOCK_CODE must be set in production: digits only, 6 to 12 (asked with the password to unlock System).")
if not ENV.get("DATABASE_URL"):
    raise ImproperlyConfigured("DATABASE_URL must be set in production (managed PostgreSQL).")

if not ENV.get("ADMIN_PATH") or ADMIN_PATH.strip("/") == DEFAULT_ADMIN_PATH.strip("/"):
    raise ImproperlyConfigured("ADMIN_PATH must be set to your own non-default value in production.")

DEBUG = False
CONTROL_HOST = ENV.get("CONTROL_DOMAIN", "control.spa99.uk")
OFFICE_HOST = ENV.get("OFFICE_DOMAIN", "office.spa99.uk")
SYSTEM_HOST = ENV.get("SYSTEM_DOMAIN", "system.spa99.uk")
SYSTEM_ENV_LABEL = ENV.get("SYSTEM_ENV_LABEL", "LIVE").upper()
# ALLOWED_HOSTS in the environment ADDS to these. localhost / 127.0.0.1: the container health check.
ALLOWED_HOSTS = [DOMAIN, CONTROL_HOST, OFFICE_HOST, SYSTEM_HOST, "localhost", "127.0.0.1"] + ENV.list("ALLOWED_HOSTS", [])

# Email: SMTP unless EMAIL_BACKEND says otherwise (notifications.backends.SesBackend for SES via the IAM role).
EMAIL_BACKEND = ENV.get("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
SITE_URL = ENV.get("SITE_URL", f"https://{DOMAIN}").rstrip("/")
CONTROL_URL = ENV.get("CONTROL_URL", f"https://{CONTROL_HOST}").rstrip("/")
OFFICE_URL = ENV.get("OFFICE_URL", f"https://{OFFICE_HOST}").rstrip("/")
SYSTEM_URL = ENV.get("SYSTEM_URL", f"https://{SYSTEM_HOST}").rstrip("/")

DATABASES = build_databases(ENV.get("DATABASE_URL"), None, require_ssl=True)

# Media: S3 prod/ folder. Credentials come from the EC2 instance role (no AWS keys in the server .env).
MEDIA_STORAGE, MEDIA_DESCRIPTION = build_media_storage(
    ENV, location_prefix="prod/", local_media_dir=PRIVATE_DIR.subdir("media"), require_credentials=False
)
STORAGES = {**STORAGES, "default": MEDIA_STORAGE}  # noqa: F405
MEDIA_DESCRIPTION, MEDIA_IS_LOCAL = finish_media_description(MEDIA_STORAGE, MEDIA_DESCRIPTION)
if MEDIA_IS_LOCAL:
    MEDIA_DESCRIPTION += " (WARNING: S3 not configured, files are lost when the container is replaced)"

# HTTPS behind Caddy (RULES.md section 9). HSTS stays off until the site has run on HTTPS without problems.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^health/$"]  # the container health check speaks plain http
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = [f"https://{DOMAIN}", f"https://{CONTROL_HOST}", f"https://{OFFICE_HOST}", f"https://{SYSTEM_HOST}"]
SECURE_HSTS_SECONDS = 0
TRUST_FORWARDED_FOR = True  # we only ever sit behind Caddy
CLIENT_IP_HEADER = ENV.get("CLIENT_IP_HEADER", "X-Client-IP")  # set by Caddy from {client_ip}; empty = use X-Forwarded-For


STARTUP_REPORT = build_startup_report("config.settings.prod")
STARTUP_REPORT["database"] = describe_database(DATABASES)
STARTUP_REPORT["hosts"] = f"office={OFFICE_HOST} control={CONTROL_HOST} system={SYSTEM_HOST}"
STARTUP_REPORT["media"] = MEDIA_DESCRIPTION
STARTUP_REPORT["media_is_local"] = MEDIA_IS_LOCAL
