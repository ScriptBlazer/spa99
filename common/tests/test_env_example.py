""".env.example is the server's checklist: every variable the code, docker-compose.yml or entrypoint.sh reads must be in it,
and every key live requires must be marked required (not optional) or explained there."""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from common.envloader import example_keys
from common.settings_helpers import PROD_REQUIRED_KEYS, PROD_SMTP_KEYS

BASE = Path(settings.BASE_DIR)
EXAMPLE = BASE / ".env.example"
# Read by code but internal plumbing, not configuration: test/e2e harness switches and Django's own reloader flag.
NOT_CONFIG = {"RUN_MAIN", "SPA99_SKIP_ENV_FILES"}
SKIP_DIRS = {".venv", "venv", "e2e", "tests", "node_modules", ".git", ".private", "staticfiles"}
CODE_READ = re.compile(r"""\b(?:ENV|env|environ|os\.environ)\s*(?:\.(?:get|bool|list|has)\(|\[)\s*["']([A-Z][A-Z0-9_]+)["']""")
SHELL_READ = re.compile(r"\$\{([A-Z][A-Z0-9_]+)")


def listed_keys():
    return {m.group(1) for m in re.finditer(r"^([A-Z][A-Z0-9_]*)=", EXAMPLE.read_text(), re.M)}


def keys_read_by_code():
    found = set()
    for path in BASE.rglob("*.py"):
        if SKIP_DIRS & set(path.relative_to(BASE).parts):
            continue
        found |= set(CODE_READ.findall(path.read_text(encoding="utf-8", errors="ignore")))
    for name in ("docker-compose.yml", "entrypoint.sh"):
        found |= set(SHELL_READ.findall((BASE / name).read_text()))
    return found - NOT_CONFIG


class EnvExampleTests(SimpleTestCase):
    def test_every_variable_the_code_reads_is_listed(self):
        missing = sorted(keys_read_by_code() - listed_keys())
        self.assertEqual(missing, [], "Add these to .env.example with a one-line comment")

    def test_the_scan_really_finds_reads(self):  # guards against the regex silently matching nothing
        self.assertTrue({"SECRET_KEY", "DATABASE_URL", "SENTRY_DSN", "AWS_STORAGE_BUCKET_NAME", "GUNICORN_THREADS", "APP_TAG"} <= keys_read_by_code())

    def test_every_key_live_requires_is_listed(self):
        self.assertEqual(sorted(set(PROD_REQUIRED_KEYS + PROD_SMTP_KEYS) - listed_keys()), [])

    def test_live_secrets_are_required_and_placeholders_only(self):
        required = set(example_keys(EXAMPLE))
        for key in ("SECRET_KEY", "SYSTEM_UNLOCK_CODE", "ADMIN_PATH", "DEFAULT_FROM_EMAIL", "DOMAIN"):
            self.assertIn(key, required)  # the startup log warns when they are missing
        values = dict(re.findall(r"^([A-Z][A-Z0-9_]*)=(.*)$", EXAMPLE.read_text(), re.M))
        for key in ("SECRET_KEY", "SYSTEM_UNLOCK_CODE", "EMAIL_HOST_PASSWORD", "AWS_SECRET_ACCESS_KEY", "ANTHROPIC_API_KEY", "SENTRY_DSN",
                    "POSTMARK_WEBHOOK_PASSWORD"):
            value = values[key].strip("'\"")
            self.assertTrue(value == "" or value.startswith("<"), f"{key} must be blank or a <placeholder> in .env.example")
