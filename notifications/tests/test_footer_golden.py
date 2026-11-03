"""Email flexibility (2026-11-03): with nothing edited, every email renders byte-for-byte as before the editable footer, sender,
heading and button existed. The files in golden/ were rendered by the code before the change (REGEN_GOLDEN=1 rewrites them: only
do that when an email is meant to change)."""
import os
from pathlib import Path

from django.test import TestCase

from notifications.services import preview_email
from plans.management.commands.seed_phase1 import seed_all

GOLDEN = Path(__file__).parent / "golden"
UNSUB = {"unsubscribe_url": "https://spa99.uk/unsubscribe/fixed/", "notice": "You are receiving this because you gave us your email."}
CASES = [("verify", {}), ("welcome", {}), ("lead_next_morning", UNSUB), ("password_changed", {}), ("invite", UNSUB), ("gold_final", {})]


class GoldenTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_defaults_render_as_before(self):
        for key, extra in CASES:
            with self.subTest(key=key):
                email = preview_email(key, f"Subject of {key}", "", extra)
                for kind in ("html", "text"):
                    path = GOLDEN / f"{key}.{kind}"
                    if os.environ.get("REGEN_GOLDEN"):
                        path.write_text(email[kind], encoding="utf-8")
                    self.assertEqual(email[kind], path.read_text(encoding="utf-8"), f"{key} {kind} changed")
