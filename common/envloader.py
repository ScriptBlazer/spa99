"""Settings loader: where configuration values come from.

Pure Python (no Django imports) because settings import it before Django is set up.

Load order, earlier wins:
    1. real environment variables
    2. $SPA99_PRIVATE_DIR/env/.env
    3. project .env
    4. defaults passed in the settings files (dev defaults)

If the private folder is missing or unreadable we fall back to git-ignored
`.private/` in the project. Nothing here may crash locally or in CI.
"""
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

DEFAULT_PRIVATE_DIR = "/Users/moishe/Library/CloudStorage/OneDrive-Personal/BML/Spa 99/Software Files"

SOURCE_ORDER = ["environment", "private .env", "project .env", "defaults"]
TRUE_VALUES = {"1", "true", "yes", "on"}


def _can_read(path):
    try:
        return path.is_dir() and os.access(path, os.R_OK | os.X_OK)
    except OSError:
        return False


def _can_write(path):
    try:
        return path.is_dir() and os.access(path, os.W_OK | os.X_OK)
    except OSError:
        return False


def _read_env_file(path):
    """Values from a .env file; {} if it is missing or unreadable. Empty values are dropped."""
    try:
        if not path.is_file():
            return {}
        return {key: value for key, value in dotenv_values(path).items() if value not in (None, "")}
    except (OSError, UnicodeDecodeError, ValueError) as error:
        # A corrupt .env must never crash the app; say so and carry on without it.
        logging.getLogger("spa99.startup").warning("Could not read %s (%s); ignoring it.", path, type(error).__name__)
        return {}


@dataclass
class PrivateDir:
    """The private folder, or the project's `.private/` fallback."""

    path: Path
    using_fallback: bool
    writable: bool
    fallback_path: Path

    def subdir(self, name):
        """A folder inside the private dir (created if possible). Falls back to .private/ if not writable."""
        base = self.path if self.writable else self.fallback_path
        target = base / name
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError:
            target = self.fallback_path / name
            target.mkdir(parents=True, exist_ok=True)
        return target


def resolve_private_dir(base_dir, environ, project_env=None):
    fallback = Path(base_dir) / ".private"
    configured = environ.get("SPA99_PRIVATE_DIR") or (project_env or {}).get("SPA99_PRIVATE_DIR")
    candidate = Path(configured or DEFAULT_PRIVATE_DIR)
    if _can_read(candidate):
        return PrivateDir(candidate, False, _can_write(candidate), fallback)
    fallback.mkdir(parents=True, exist_ok=True)
    return PrivateDir(fallback, True, True, fallback)


class Env:
    """Layered config lookup that remembers which sources actually supplied values."""

    def __init__(self, sources, private_dir, example_path=None):
        self.sources = sources  # list of (label, mapping), highest priority first
        self.private_dir = private_dir
        self.example_path = example_path
        self.used = set()

    def get(self, key, default=None):
        for label, mapping in self.sources:
            value = mapping.get(key)
            if value not in (None, ""):
                self.used.add(label)
                return value
        if default is not None:
            self.used.add("defaults")
        return default

    def bool(self, key, default=False):
        value = self.get(key)
        if value is None:
            return default
        return str(value).strip().lower() in TRUE_VALUES

    def list(self, key, default=None):
        value = self.get(key)
        if value is None:
            return list(default or [])
        return [item.strip() for item in value.split(",") if item.strip()]

    def has(self, key):
        return any(mapping.get(key) not in (None, "") for _, mapping in self.sources)

    def used_sources(self):
        return [label for label in SOURCE_ORDER if label in self.used]

    def missing_example_keys(self):
        """Keys in .env.example that no source provides. Keys whose comment says 'optional' are skipped."""
        return [key for key in example_keys(self.example_path) if not self.has(key)]


def example_keys(example_path):
    """Required keys in .env.example (a key is optional if the comment above it says so)."""
    if not example_path or not Path(example_path).is_file():
        return []
    keys, comment = [], ""
    for line in Path(example_path).read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            comment += " " + stripped.lower()
        elif stripped == "":
            comment = ""
        else:
            match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=", stripped)
            if match and "optional" not in comment:
                keys.append(match.group(1))
            comment = ""
    return keys


def load_env(base_dir, environ=None):
    base_dir = Path(base_dir)
    environ = os.environ if environ is None else environ
    if environ.get("SPA99_SKIP_ENV_FILES"):  # tests: environment variables and .private/ only
        fallback = base_dir / ".private"
        fallback.mkdir(parents=True, exist_ok=True)
        return Env([("environment", environ)], PrivateDir(fallback, True, True, fallback), base_dir / ".env.example")
    project_env = _read_env_file(base_dir / ".env")
    private = resolve_private_dir(base_dir, environ, project_env)
    private_env = {} if private.using_fallback else _read_env_file(private.path / "env" / ".env")
    sources = [("environment", environ), ("private .env", private_env), ("project .env", project_env)]
    return Env(sources, private, base_dir / ".env.example")


def pick_settings_module(base_dir, default, environ=None):
    """DJANGO_SETTINGS_MODULE using the same load order as everything else; `default` if none sets it.
    Used by manage.py, wsgi.py and asgi.py before Django starts."""
    return load_env(base_dir, environ).get("DJANGO_SETTINGS_MODULE") or default
