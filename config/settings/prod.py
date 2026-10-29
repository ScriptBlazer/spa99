"""Live server. Refuses to start (ImproperlyConfigured, listing every problem) unless the live values are real:
see common.settings_helpers.prod_config_errors and the "required on live" block of .env.example."""
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import EMAIL_HOST, DEFAULT_ADMIN_PATH, DEV_SECRET_KEY, DOMAIN, ENV, finish_media_description, PRIVATE_DIR, build_startup_report
from common.settings_helpers import SMTP_BACKEND, build_databases, build_media_storage, describe_database, describe_email, prod_config_errors

# Email: Postmark over SMTP by default (launch provider, 2026-10-29). SES stays one .env line away:
# EMAIL_BACKEND=notifications.backends.SesBackend (uses the server's IAM role).
EMAIL_BACKEND = ENV.get("EMAIL_BACKEND", SMTP_BACKEND)

_errors = prod_config_errors(ENV, DEV_SECRET_KEY, DEFAULT_ADMIN_PATH, EMAIL_BACKEND)
if _errors:
    raise ImproperlyConfigured(
        "Spa 99 will not start on live settings. Fix the server .env (see .env.example):\n  - " + "\n  - ".join(_errors)
    )

DEBUG = False
CONTROL_HOST = ENV.get("CONTROL_DOMAIN")
OFFICE_HOST = ENV.get("OFFICE_DOMAIN")
SYSTEM_HOST = ENV.get("SYSTEM_DOMAIN")
SYSTEM_ENV_LABEL = ENV.get("SYSTEM_ENV_LABEL", "LIVE").upper()
# ALLOWED_HOSTS in the environment ADDS to these. localhost / 127.0.0.1: the container health check.
ALLOWED_HOSTS = [DOMAIN, CONTROL_HOST, OFFICE_HOST, SYSTEM_HOST, "localhost", "127.0.0.1"] + ENV.list("ALLOWED_HOSTS", [])

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
if MEDIA_IS_LOCAL:  # backstop: uploads on container disk would be lost on the next deploy
    raise ImproperlyConfigured("AWS_STORAGE_BUCKET_NAME must be set in production (uploads would be lost when the container is replaced).")

# HTTPS: Cloudflare (Full strict) -> Caddy (TLS) -> gunicorn over plain http. Caddy sets X-Forwarded-Proto (and overwrites
# any value a visitor sends), so Django trusts it to know the request was https.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^health/$"]  # the container health check speaks plain http
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = [f"https://{DOMAIN}", f"https://{CONTROL_HOST}", f"https://{OFFICE_HOST}", f"https://{SYSTEM_HOST}"]
# HSTS (2026-10-29): starts at 1 hour, so a launch-day HTTPS mistake only locks browsers out briefly. Raise to 31536000 (a year)
# in .env after a week of clean HTTPS. Subdomains and preload stay off: they cannot be undone quickly.
SECURE_HSTS_SECONDS = int(ENV.get("SECURE_HSTS_SECONDS", "3600") or 0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]  # subdomains / preload off on purpose (above)
TRUST_FORWARDED_FOR = True  # we only ever sit behind Caddy
CLIENT_IP_HEADER = ENV.get("CLIENT_IP_HEADER", "X-Client-IP")  # set by Caddy from {client_ip}; empty = use X-Forwarded-For


STARTUP_REPORT = build_startup_report("config.settings.prod")
STARTUP_REPORT["database"] = describe_database(DATABASES)
STARTUP_REPORT["hosts"] = f"office={OFFICE_HOST} control={CONTROL_HOST} system={SYSTEM_HOST}"
STARTUP_REPORT["media"] = MEDIA_DESCRIPTION
STARTUP_REPORT["media_is_local"] = MEDIA_IS_LOCAL
STARTUP_REPORT["email"] = describe_email(EMAIL_BACKEND, EMAIL_HOST)
