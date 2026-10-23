"""Shared settings. dev.py and prod.py import * from here and only hold differences.

Config comes from common.envloader (env vars -> private .env -> project .env -> defaults).
"""
from datetime import time
from pathlib import Path

from common.envloader import load_env
from common.settings_helpers import build_databases, build_media_storage, describe_database

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV = load_env(BASE_DIR)
PRIVATE_DIR = ENV.private_dir

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
    "django.contrib.admin",
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
    "insights",
    "office",
    "system",
    "pages",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "common.middleware.HostRoutingMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Locked by default: every view needs a login unless marked @login_not_required.
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
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
                "office.context.office",
                "system.context.system",
            ],
        },
    },
]

# Database: DATABASE_URL if set, else SQLite in .private/ (never in OneDrive).
DATABASES = build_databases(ENV.get("DATABASE_URL"), BASE_DIR / ".private" / "db.sqlite3")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "users.User"
OFFICE_SESSION_AGE = 30 * 24 * 60 * 60  # staff sign-ins on the Office host last 30 days (SESSION_COOKIE_AGE stays Django's default for the public site)
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
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
EMAIL_VERIFY_MAX_AGE = 24 * 60 * 60  # seconds a verification link works
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
# Absolute links used in emails (no trailing slash).
SITE_WEBGL = ENV.bool("SITE_WEBGL", True)  # false = the 3D Gold Card never loads (CSS card only); read by base.html as data-webgl
SITE_URL = ENV.get("SITE_URL", f"https://{DOMAIN}").rstrip("/")
CONTROL_URL = ENV.get("CONTROL_URL", f"https://{CONTROL_HOST}").rstrip("/")
OFFICE_URL = ENV.get("OFFICE_URL", f"https://{OFFICE_HOST}").rstrip("/")
SYSTEM_URL = ENV.get("SYSTEM_URL", f"https://{SYSTEM_HOST}").rstrip("/")
SYSTEM_ENV_LABEL = ENV.get("SYSTEM_ENV_LABEL", "DEV").upper()  # DEV or LIVE: the label System shows in the title bar and stripe (prod default LIVE)
SYSTEM_UNLOCK_SECONDS = 15 * 60  # System asks for the password again after this much idle time
SYSTEM_SESSION_AGE = 12 * 60 * 60  # a System sign-in lasts 12 hours at most


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
        "media_is_local": MEDIA_IS_LOCAL,
        "missing_keys": ENV.missing_example_keys(),
    }
