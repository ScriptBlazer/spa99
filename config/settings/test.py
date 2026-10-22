"""Tests and CI. Dev settings, but isolated: in-memory media, plain static files, synchronous jobs.

Deviation from BML RULES.md (tests on dev settings): the manifest static storage needs collectstatic
when DEBUG is off, which tests do not want. Everything else is dev.
"""
from .dev import *  # noqa: F401,F403

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
Q_CLUSTER = {**Q_CLUSTER, "sync": True}  # noqa: F405
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
STARTUP_REPORT = None  # keep test output quiet
