"""2026-11-03: Barry's next-morning email has no "Questions? ... write to hello@" footer line (replies reach him); other emails keep it."""
from django.test import TestCase

from notifications.services import preview_email
from plans.management.commands.seed_phase1 import seed_all


class ContactLineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_next_morning_email_leaves_out_the_contact_line(self):
        email = preview_email("lead_next_morning", "Welcome to Spa 99", "")
        self.assertNotIn("Questions? Reply to this email or write to", email["html"])
        self.assertNotIn("Questions? Reply to this email or write to", email["text"])

    def test_other_emails_keep_it(self):
        email = preview_email("office_message", "Hello", "")
        self.assertIn("Questions? Reply to this email or write to", email["html"])
