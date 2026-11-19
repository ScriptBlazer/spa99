"""Guard: app code must not hard-code the spa99 domains (decision 2026-11-16). Domains come from settings (.env), addresses from System."""
import os
import subprocess
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2]
EXTENSIONS = {".py", ".html", ".txt", ".js", ".json", ".css"}
BANNED = ("spa99.uk", "spa99.co.uk")
SKIP_DIRS = {"tests", "migrations", "docs", "staticfiles", ".venv", "venv", "node_modules", ".private", ".git", "__pycache__"}
ALLOWED = {("config/settings/base.py", 'DOMAIN = ENV.get("DOMAIN", "spa99.uk")')}  # the one kept fallback: exact file and line


def source_files():
    try:
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):  # no git (or not a checkout): walk the folders instead
        out = []
        for folder, dirs, names in os.walk(ROOT):
            dirs[:] = [d for d in dirs if not d.startswith(".")]  # skip every dot-folder (.git, .venv, .private ...)
            out += [os.path.relpath(os.path.join(folder, n), ROOT) for n in names]
    for rel in out:
        path = Path(rel)
        if path.suffix in EXTENSIONS and not SKIP_DIRS & set(path.parts) and not path.name.startswith("test_") and (ROOT / path).is_file():
            yield rel


class NoHardCodedDomainsTests(SimpleTestCase):
    def test_no_spa99_domain_in_app_code(self):
        files = list(source_files())
        self.assertGreater(len(files), 100)  # the scan really found the project
        found = []
        for rel in files:
            for number, line in enumerate((ROOT / rel).read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if any(name in line for name in BANNED) and (rel, line.strip()) not in ALLOWED:
                    found.append(f"{rel}:{number}: {line.strip()[:120]}")
        self.assertEqual(found, [], "Hard-coded spa99 domain (use settings or System):\n" + "\n".join(found))
