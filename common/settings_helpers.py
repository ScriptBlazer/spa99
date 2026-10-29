"""Small pure helpers used by the settings files (no Django imports)."""
import re
from urllib.parse import urlparse

import dj_database_url

SQLITE_ENGINE = "django.db.backends.sqlite3"


def build_databases(database_url, sqlite_path, require_ssl=False):
    """DATABASES dict: DATABASE_URL if given, else SQLite at `sqlite_path`. Works on SQLite and Postgres."""
    if database_url:
        config = dj_database_url.parse(database_url, conn_max_age=60, conn_health_checks=True)
    else:
        config = {"ENGINE": SQLITE_ENGINE, "NAME": str(sqlite_path)}
    options = config.setdefault("OPTIONS", {})
    if config["ENGINE"] == SQLITE_ENGINE:
        # Web and worker processes share one file: wait for locks and take the write lock up front.
        options.setdefault("timeout", 20)
        options.setdefault("transaction_mode", "IMMEDIATE")
    elif require_ssl:
        options.setdefault("sslmode", "require")
    return {"default": config}


def describe_database(databases):
    """e.g. 'sqlite3:.private/db.sqlite3' or 'postgresql:spa99@host'. Never includes credentials."""
    config = databases["default"]
    engine = config["ENGINE"].rsplit(".", 1)[-1]
    if engine == "sqlite3":
        return f"sqlite3:{config['NAME']}"
    return f"{engine}:{config.get('NAME', '')}@{config.get('HOST') or 'localhost'}"


def build_media_storage(env, location_prefix, local_media_dir, require_credentials):
    """Default (media) storage: private S3 when configured, otherwise local files.

    Returns (storage_config, description). Never raises on missing settings.
    """
    bucket = env.get("AWS_STORAGE_BUCKET_NAME")
    access_key = env.get("AWS_ACCESS_KEY_ID")
    secret_key = env.get("AWS_SECRET_ACCESS_KEY")
    has_credentials = bool(access_key and secret_key)
    if bucket and (has_credentials or not require_credentials):
        options = {
            "bucket_name": bucket,
            "region_name": env.get("AWS_S3_REGION_NAME", "eu-west-2"),
            "location": location_prefix,
            "default_acl": None,
            "querystring_auth": True,  # private bucket, signed URLs
            "querystring_expire": 3600,
            "signature_version": "s3v4",
            "file_overwrite": False,
        }
        if has_credentials:  # in prod the EC2 instance role is used instead
            options.update(access_key=access_key, secret_key=secret_key)
        return (
            {"BACKEND": "storages.backends.s3.S3Storage", "OPTIONS": options},
            f"s3:{bucket}/{location_prefix}",
        )
    storage = {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": str(local_media_dir), "base_url": "/media/"},
    }
    return storage, f"local:{local_media_dir}"


def hostname_of(value):
    """'https://x.example/' or 'x.example:8000' -> 'x.example'."""
    value = (value or "").strip()
    parsed = urlparse(value if "//" in value else f"//{value}")
    return (parsed.hostname or "").lower()


# ---------- production checks (config/settings/prod.py) ----------

# Every key here must be in .env.example (common/tests/test_env_example.py checks it).
PROD_REQUIRED_KEYS = (
    "SECRET_KEY",
    "DATABASE_URL",
    "SYSTEM_UNLOCK_CODE",
    "ADMIN_PATH",
    "DEFAULT_FROM_EMAIL",
    "AWS_STORAGE_BUCKET_NAME",
    "DOMAIN",
    "OFFICE_DOMAIN",
    "SYSTEM_DOMAIN",
    "CONTROL_DOMAIN",
)
PROD_SMTP_KEYS = ("EMAIL_HOST", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD")
SMTP_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
_PLACEHOLDER_MARKERS = ("<", ">", "change-me", "changeme")  # .env.example placeholders look like <this>
_WEAK_SECRET_MARKERS = ("insecure", "change-me", "changeme", "dummy")
# Backends that print, store or drop mail: never on live (emails would vanish without an error).
_NON_SENDING_BACKENDS = ("console", "locmem", "dummy", "filebased")


def _looks_like_placeholder(value):
    return any(marker in value.lower() for marker in _PLACEHOLDER_MARKERS)


def prod_config_errors(env, dev_secret_key, default_admin_path, email_backend):
    """Everything wrong with the live configuration, as plain sentences (empty list = fine). Never includes values."""
    errors = []
    for key in PROD_REQUIRED_KEYS:
        value = (env.get(key) or "").strip()
        if not value:
            errors.append(f"{key} is not set.")
        elif key != "DEFAULT_FROM_EMAIL" and _looks_like_placeholder(value):  # From has <...> around the address
            errors.append(f"{key} still holds the placeholder from .env.example.")
    secret = (env.get("SECRET_KEY") or "").strip()
    if secret and (secret == dev_secret_key or len(secret) < 40 or any(m in secret.lower() for m in _WEAK_SECRET_MARKERS)):
        errors.append("SECRET_KEY must be a real random secret (50 characters; never the dev or example one).")
    database_url = (env.get("DATABASE_URL") or "").strip()
    if database_url and not database_url.startswith(("postgres://", "postgresql://")):
        errors.append("DATABASE_URL must be the managed PostgreSQL (postgres://...), never SQLite.")
    code = (env.get("SYSTEM_UNLOCK_CODE") or "").strip()
    if code and not re.fullmatch(r"[0-9]{6,12}", code):
        errors.append("SYSTEM_UNLOCK_CODE must be digits only, 6 to 12.")
    admin_path = (env.get("ADMIN_PATH") or "").strip("/ ")
    if admin_path and admin_path == default_admin_path.strip("/"):
        errors.append("ADMIN_PATH must be your own value, not the committed example.")
    for key in ("DOMAIN", "OFFICE_DOMAIN", "SYSTEM_DOMAIN", "CONTROL_DOMAIN"):
        host = (env.get(key) or "").strip().lower()
        if host and (host.endswith("localhost") or "://" in host or "/" in host):
            errors.append(f"{key} must be a bare public host name (e.g. spa99.uk), not a URL or localhost.")
    if any(name in email_backend.lower() for name in _NON_SENDING_BACKENDS):
        errors.append("EMAIL_BACKEND prints or drops mail; live must really send (leave it blank for SMTP/Postmark).")
    if email_backend == SMTP_BACKEND:
        missing = [key for key in PROD_SMTP_KEYS if not (env.get(key) or "").strip()]
        placeholders = [key for key in PROD_SMTP_KEYS if key not in missing and _looks_like_placeholder(env.get(key))]
        if placeholders:
            errors.append(f"{', '.join(placeholders)} still hold the placeholder from .env.example.")
        if missing:
            errors.append(f"SMTP email needs {', '.join(missing)} (Postmark: host smtp.postmarkapp.com, user and password = server token).")
        elif (env.get("EMAIL_HOST") or "").strip() == "localhost":
            errors.append("EMAIL_HOST is localhost; live sends through Postmark (smtp.postmarkapp.com).")
    return errors


def describe_email(backend, host):
    """Short label for the startup log, e.g. 'smtp:smtp.postmarkapp.com', 'ses' or 'console'. Never credentials."""
    if backend == SMTP_BACKEND:
        return f"smtp:{host}"
    if backend.endswith("SesBackend"):
        return "ses"
    return backend.rsplit(".", 2)[-2] if backend.count(".") >= 2 else backend
