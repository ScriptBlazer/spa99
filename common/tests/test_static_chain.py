"""The hashed static build must have more passes than the longest import chain (common/storage.py)."""
import os
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from common.storage import SpaStaticFilesStorage

IMPORT = re.compile(
    r"""(?:import|export)\s[^'"]*?from\s*['"]([^'"]+)['"]|import\s*['"]([^'"]+)['"]|@import\s+(?:url\()?['"]?([^'")]+)"""
)


class StaticImportChainTests(SimpleTestCase):
    def test_passes_cover_the_longest_import_chain(self):
        base = Path(settings.BASE_DIR)
        graph = {}
        for path in base.glob("*/static/**/*"):
            if path.suffix not in {".js", ".mjs", ".css"} or "vendor" in path.parts:
                continue
            deps = []
            for match in IMPORT.finditer(path.read_text(encoding="utf-8", errors="ignore")):
                ref = next(g for g in match.groups() if g)
                if ref.startswith("."):
                    target = Path(os.path.normpath(path.parent / ref))
                    if target.exists():
                        deps.append(target)
            graph[path] = deps

        def depth(path, seen=()):
            if path in seen:
                self.fail(f"Import loop through {path.relative_to(base)}")
            return 1 + max((depth(d, seen + (path,)) for d in graph.get(path, [])), default=0)

        longest = max(depth(p) for p in graph)
        self.assertGreater(SpaStaticFilesStorage.max_post_process_passes, longest)
