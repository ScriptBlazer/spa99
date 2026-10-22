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
CONTROL_HOST = ENV.get("CONTROL_DOMAIN", "control.localhost")  # prod: control.spa99.uk
ADMIN_PATH = ENV.get("ADMIN_PATH", "backstage-7d3f9a/").strip("/") + "/"  # hidden Django admin
ALLOWED_HOSTS = ENV.list("ALLOWED_HOSTS", ["localhost", "127.0.0.1", ".localhost"])

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
            ],
        },
    },
]

# Database: DATABASE_URL if set, else SQLite in .private/ (never in OneDrive).
DATABASES = build_databases(ENV.get("DATABASE_URL"), BASE_DIR / ".private" / "db.sqlite3")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "users.User"
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
STORAGES = {
    "default": MEDIA_STORAGE,
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
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
        "media": MEDIA_DESCRIPTION,
        "missing_keys": ENV.missing_example_keys(),
    }
