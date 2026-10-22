"""Small pure helpers used by the settings files (no Django imports)."""
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
