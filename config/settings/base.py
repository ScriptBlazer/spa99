"""Shared settings. dev.py and prod.py import * from here and only hold differences.

Config comes from common.envloader (env vars -> private .env -> project .env -> defaults).
"""
import os
import re
from datetime import time
from pathlib import Path

from common.envloader import load_env
from common.observability import init_sentry
from common.settings_helpers import build_databases, build_media_storage, describe_database

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV = load_env(BASE_DIR)
PRIVATE_DIR = ENV.private_dir

# Sentry: off when SENTRY_DSN is empty. Environment tag defaults to "live" under the prod settings, else "dev".
_default_sentry_environment = "live" if os.environ.get("DJANGO_SETTINGS_MODULE", "").endswith(".prod") else "dev"
SENTRY_STATE = init_sentry(ENV, _default_sentry_environment)  # "off" or "on(<environment>)"

# Not a secret: only ever used when SECRET_KEY is unset locally. prod.py refuses to start with it.
DEV_SECRET_KEY = "dev-insecure-key-not-for-production-use-0123456789abcdef"
SECRET_KEY = ENV.get("SECRET_KEY", DEV_SECRET_KEY)
DEBUG = False  # dev.py switches it on

DOMAIN = ENV.get("DOMAIN", "spa99.uk")
CONTROL_HOST = ENV.get("CONTROL_DOMAIN", "control.localhost")  # prod: control.spa99.uk (the building control room, parked)
OFFICE_HOST = ENV.get("OFFICE_DOMAIN", "office.localhost")  # prod: office.spa99.uk (the business back office)
SYSTEM_HOST = ENV.get("SYSTEM_DOMAIN", "system.localhost")  # prod: system.spa99.uk (developers only: the business rules)
DEFAULT_ADMIN_PATH = "backstage-7d3f9a/"  # committed, so public: dev only. prod.py refuses it.
ADMIN_PATH = ENV.get("ADMIN_PATH", DEFAULT_ADMIN_PATH).strip("/") + "/"  # hidden Django admin
# ALLOWED_HOSTS in the environment ADDS to these defaults (prod.py adds DOMAIN, CONTROL_DOMAIN, OFFICE_DOMAIN and SYSTEM_DOMAIN too).
ALLOWED_HOSTS = ["localhost", "127.0.0.1", ".localhost"] + ENV.list("ALLOWED_HOSTS", [])
CSRF_FAILURE_VIEW = "common.views.csrf_failure"

INSTALLED_APPS = [
    "common.admin_site.SpaAdminConfig",  # django.contrib.admin, superusers only
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "simple_history",
    "django_q",
    "common",
    "users",
    "plans",
    "content",
    "journey",
    "gold",
    "notifications",
    "mailings",
    "insights",
    "office",
    "system",
    "control",
    "pages",
    "chat",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "common.middleware.HostRoutingMiddleware",
    "system.middleware.SystemHeadersMiddleware",  # System host: never cached, never framed (wraps the gate's 404 too)
    "django.contrib.sessions.middleware.SessionMiddleware",
    "plans.middleware.SalePreviewMiddleware",  # public site: ?sale_preview=<signed token> shows an upcoming sale's bar in this browser
    "system.middleware.SystemGateMiddleware",  # System host: 404 for non-developers before CSRF can tell routes apart
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "common.observability.SentryContextMiddleware",  # Sentry host/staff tags and user id (no-op when Sentry is off)
    "system.middleware.AuditContextMiddleware",  # staff edits (admin too) are logged with IP and browser
    # Locked by default: every view needs a login unless marked @login_not_required.
    "common.middleware.LoginRequiredMiddleware",  # Django's lock; background (JSON) requests get 401 instead of a redirect
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "insights.middleware.VisitorCounterMiddleware",  # last: sees the final response; never slows or breaks a page
]

ROOT_URLCONF = "config.urls"  # public site; HostRoutingMiddleware swaps in config.urls_control
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "plans.context_processors.site",
                "plans.context_processors.sale",
                "users.context.member_area",
                "office.context.office",
                "system.context.system",
                "chat.context.chat",
            ],
        },
    },
]

# Database: DATABASE_URL if set, else SQLite in .private/ (never in OneDrive).
DATABASES = build_databases(ENV.get("DATABASE_URL"), BASE_DIR / ".private" / "db.sqlite3")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Cache: the database (table spa99_cache; `manage.py createcachetable`, run on start by entrypoint.sh), so the rate limits
# (sign-in, unlock) are shared by every gunicorn worker. Works on SQLite and Postgres. Tests and the e2e run override it.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "spa99_cache", "OPTIONS": {"MAX_ENTRIES": 100000}}}

AUTH_USER_MODEL = "users.User"
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/account/"
LOGOUT_REDIRECT_URL = "/login/"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
        "OPTIONS": {"user_attributes": ("email", "first_name", "last_name")},
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Sign-up rules. (Prices, hours, journey and Gold rules are database rows, not settings.)
MINIMUM_AGE = 18  # ACC-08; mirrored in common/static/common/js/validate.js
PASSWORD_RESET_TIMEOUT = 60 * 60  # seconds a password reset link works

# Email. Dev prints to the console, tests use the in-memory outbox, live sets EMAIL_BACKEND
# (notifications.backends.SesBackend for Amazon SES via the server's IAM role, or Django's SMTP backend).
EMAIL_BACKEND = ENV.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = ENV.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(ENV.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = ENV.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = ENV.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = ENV.bool("EMAIL_USE_TLS", True)
# Every address comes from the environment, nothing is hard-coded. DEFAULT_FROM_EMAIL is required in prod (dev.py has a
# dev-only default). DKIM is signed by the mail provider and DNS, not by Django.
DEFAULT_FROM_EMAIL = ENV.get("DEFAULT_FROM_EMAIL", "")
SERVER_EMAIL = ENV.get("SERVER_EMAIL", DEFAULT_FROM_EMAIL)
# Recipients (Gold approver, CC, contact email) are not here: developers edit them in System (SiteSettings).
AWS_SES_REGION_NAME = ENV.get("AWS_SES_REGION_NAME", "eu-west-2")
# SES bounce/complaint feedback arrives from this one SNS topic at POST /ses/notifications/. Empty = that endpoint is off (404).
SES_SNS_TOPIC_ARN = (ENV.get("SES_SNS_TOPIC_ARN", "") or "").strip()
# Postmark bounce/complaint webhook at POST /postmark/webhook/ (HTTP Basic). Off (404) unless BOTH are set.
POSTMARK_WEBHOOK_USER = (ENV.get("POSTMARK_WEBHOOK_USER", "") or "").strip()
POSTMARK_WEBHOOK_PASSWORD = (ENV.get("POSTMARK_WEBHOOK_PASSWORD", "") or "").strip()
# Group sends and invites go out at most this many a second (and never above what SES reports for the account). Not an env var:
# change it here if SES raises the account's rate. No pacing when the queue runs inline (development).
MAILING_RATE_PER_SECOND = 10
# Absolute links used in emails (no trailing slash).
SITE_WEBGL = ENV.bool("SITE_WEBGL", True)  # false = the 3D Gold Card never loads (CSS card only); read by base.html as data-webgl
SITE_URL = ENV.get("SITE_URL", f"https://{DOMAIN}").rstrip("/")
CONTROL_URL = ENV.get("CONTROL_URL", f"https://{CONTROL_HOST}").rstrip("/")
OFFICE_URL = ENV.get("OFFICE_URL", f"https://{OFFICE_HOST}").rstrip("/")
SYSTEM_URL = ENV.get("SYSTEM_URL", f"https://{SYSTEM_HOST}").rstrip("/")
# The lock code asked with the password to unlock System: digits only, 6 to 12. A secret: never logged or printed.
# Unset or invalid = password only in dev/CI (a startup warning says so); prod.py refuses to start without a valid one.
SYSTEM_UNLOCK_CODE_RAW = (ENV.get("SYSTEM_UNLOCK_CODE", "") or "").strip()
SYSTEM_UNLOCK_CODE_VALID = bool(re.fullmatch(r"[0-9]{6,12}", SYSTEM_UNLOCK_CODE_RAW))
SYSTEM_UNLOCK_CODE = SYSTEM_UNLOCK_CODE_RAW if SYSTEM_UNLOCK_CODE_VALID else ""
SYSTEM_ENV_LABEL = ENV.get("SYSTEM_ENV_LABEL", "DEV").upper()  # DEV or LIVE: the label System shows in the title bar and stripe (prod default LIVE)
SYSTEM_UNLOCK_SECONDS = 15 * 60  # System asks for the password again after this much idle time
SYSTEM_AUDIT_RETENTION_DAYS = int(ENV.get("SYSTEM_AUDIT_RETENTION_DAYS", "0") or 0)  # 0 = keep the audit log forever; used only by `manage.py prune_audit_log`
SYSTEM_SESSION_AGE = 12 * 60 * 60  # a System sign-in lasts 12 hours at most


# "Ask us" chat (docs/features/ai-chat.md). The key is a secret: never logged or printed. Blank = the chat is off (button hidden).
ANTHROPIC_API_KEY = (ENV.get("ANTHROPIC_API_KEY", "") or "").strip()
CHAT_MODEL = "claude-opus-5-5"
CHAT_MAX_TOKENS = 500  # per reply, thinking included (always on for this model, effort "low"): replies are a few sentences. A reply that hits it ends with "..." and the hand-off, never continues
CHAT_TIMEOUT_SECONDS = 45  # wall-clock limit for one streamed reply; the SDK's own timeout is per read
CHAT_GBP_PER_USD = "0.79"  # fixed rate used to turn token cost (USD) into pence for the cap. Update by hand if the rate moves a lot
CHAT_RETENTION_DAYS = 90  # the privacy notice says 90
# Abuse limits (docs/features/ai-chat.md, Security). All server side. The editable ones (messages per conversation, characters, rates,
# daily cap share, on/off) live in System > Assistant > Limits (chat.AssistantSettings); the rest are here.
CHAT_MAX_LINES = 6  # a message with more lines than this is treated as pasted text or code
CHAT_HISTORY_MESSAGES = 8  # the last this-many messages are sent to the model, no more
CHAT_MAX_CONVERSATIONS_PER_HOUR = 200  # new conversations, whole site
CHAT_OFF_TOPIC_LIMIT = 2  # off-topic or refused turns after which the conversation is closed
CHAT_COOKIE = "spa99_chat"  # set by GET /chat/state/: proves the request comes from the page
CHAT_COOKIE_SECONDS = 24 * 60 * 60

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Europe/London"
USE_I18N = True
USE_TZ = True

# Spa day (CAL-01..05): a spa day starts at 5am and ends at 3am the next morning.
SPA_DAY_START = time(5, 0)
SPA_DAY_END = time(3, 0)

# Static files (WhiteNoise, hashed names for cache busting) and media.
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_STORAGE, MEDIA_DESCRIPTION = build_media_storage(
    ENV,
    location_prefix="dev/",
    local_media_dir=PRIVATE_DIR.subdir("media"),
    require_credentials=True,
)


def finish_media_description(storage, description):
    """Adds a note when media is local only because the private folder could not be written to."""
    is_local = storage["BACKEND"].endswith("FileSystemStorage")
    if is_local and not PRIVATE_DIR.using_fallback and not str(storage["OPTIONS"]["location"]).startswith(str(PRIVATE_DIR.path)):
        description += " (private folder not writable, fell back to .private/)"
    return description, is_local


MEDIA_DESCRIPTION, MEDIA_IS_LOCAL = finish_media_description(MEDIA_STORAGE, MEDIA_DESCRIPTION)
# Control Library upload limits (MB per kind). Files stream to temp files above FILE_UPLOAD_MAX_MEMORY_SIZE (never held in memory);
# DATA_UPLOAD_MAX_MEMORY_SIZE only counts non-file fields, so it is not raised.
CONTROL_MAX_AUDIO_MB = int(ENV.get("CONTROL_MAX_AUDIO_MB", 50))
CONTROL_MAX_VIDEO_MB = int(ENV.get("CONTROL_MAX_VIDEO_MB", 500))
CONTROL_MAX_IMAGE_MB = int(ENV.get("CONTROL_MAX_IMAGE_MB", 20))
CONTROL_LIBRARY_MAX_GB = float(ENV.get("CONTROL_LIBRARY_MAX_GB", 10))  # total size of everything in the Library (demo value)
CONTROL_MEDIA_URL_HOURS = int(ENV.get("CONTROL_MEDIA_URL_HOURS", 12))  # how long signed links to Library files last (live)
FILE_UPLOAD_MAX_MEMORY_SIZE = 2_621_440  # 2.5 MB: anything bigger goes to a temp file on disk

STORAGES = {
    "default": MEDIA_STORAGE,
    "staticfiles": {"BACKEND": "common.storage.SpaStaticFilesStorage"},
}

# Background jobs: django-q2 with the ORM broker (database queue, no Redis).
Q_CLUSTER = {
    "name": "spa99",
    "orm": "default",
    "workers": 2,
    "timeout": 120,
    "retry": 180,
    "max_attempts": 3,  # a task that keeps dying is not retried forever (django-q2's default 0 = forever)
    "queue_limit": 50,
    "bulk": 5,
    "catch_up": False,
    "label": "Background jobs",
    "sync": False,
}

# Audit: trust X-Forwarded-For for the client IP only behind Caddy (prod).
TRUST_FORWARDED_FOR = False
# Header our proxy sets to the real client IP (off when empty). Prod: "X-Client-IP", written by Caddy (see Caddyfile).
CLIENT_IP_HEADER = ""

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django.request": {"level": "WARNING"}},
}


def build_startup_report(settings_module):
    """Built from settings; logged once by common.apps.CommonConfig.ready()."""
    return {
        "settings": settings_module,
        "env_sources": ENV.used_sources(),
        "private_dir": "fallback .private/" if PRIVATE_DIR.using_fallback else "private folder",
        "database": describe_database(DATABASES),
        "hosts": f"office={OFFICE_HOST} control={CONTROL_HOST} system={SYSTEM_HOST}",
        "media": MEDIA_DESCRIPTION,
        "sentry": SENTRY_STATE,
        "chat": "on" if ANTHROPIC_API_KEY else "off",
        "unlock_code_set": bool(SYSTEM_UNLOCK_CODE),
        "unlock_code_invalid": bool(SYSTEM_UNLOCK_CODE_RAW) and not SYSTEM_UNLOCK_CODE_VALID,
        "media_is_local": MEDIA_IS_LOCAL,
        "missing_keys": ENV.missing_example_keys(),
    }
