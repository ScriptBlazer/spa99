"""Tests and CI. Dev settings, but isolated: in-memory media, plain static files, synchronous jobs.

Deviation from BML RULES.md (tests on dev settings): the manifest static storage needs collectstatic
when DEBUG is off, which tests do not want. Everything else is dev.
"""
import os

# Tests must not depend on a developer's private or project .env files (or write into the private folder):
# environment variables only. Must be set before base.py loads the environment.
os.environ["SPA99_SKIP_ENV_FILES"] = "1"

from .dev import *  # noqa: E402,F401,F403

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
Q_CLUSTER = {**Q_CLUSTER, "sync": True}  # noqa: F405
CACHES = {"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}  # rate limits off unless a test turns them on
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
DEFAULT_FROM_EMAIL = "Spa 99 <from@example.test>"
SERVER_EMAIL = DEFAULT_FROM_EMAIL
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
STARTUP_REPORT = None  # keep test output quiet

# Expected failures (503 health check, 403/404 responses) would otherwise spam the test output.
LOGGING = {  # noqa: F405
    **LOGGING,  # noqa: F405
    "loggers": {
        "django.request": {"level": "CRITICAL"},
        "spa99.health": {"level": "CRITICAL"},
        "spa99.visitors": {"level": "CRITICAL"},  # a test breaks the counter on purpose
        "spa99.email": {"level": "CRITICAL"},  # tests that break sending on purpose
    },
}
