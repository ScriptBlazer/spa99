"""System polish: the compact WhatsApp box on the Dashboard, the Launch group on Settings, and page structure (padding wrappers)."""
import re
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from pages import clicks
from system.tests.test_system import make_user, unlocked_client


class WhatsappBoxTests(TestCase):
    def setUp(self):
        self.client = unlocked_client(make_user())

    def test_box_shows_totals_trend_and_top_three_sources_without_a_day_table(self):
        today = timezone.localdate()
        for source, n in (("register", 5), ("journey", 3), ("visit", 2), ("chat", 1)):
            for _ in range(n):
                clicks.increment("whatsapp", source)
        clicks.increment("whatsapp", "register", day=today - timedelta(days=10))
        html = self.client.get("/").content.decode()
        box = html[html.index("data-system-whatsapp"):]
        for key, value in (("today", 11), ("week", 11), ("month", 12), ("all", 12)):
            self.assertRegex(box, rf'data-whatsapp-total="{key}"><div class="l">[^<]+</div><div class="v">{value}</div>')
        self.assertIn('role="img" aria-label="Clicks over the last 30 days"', box)
        self.assertEqual(box.count('class="sys-bar"'), 30)
        self.assertIn("Register 6", box)
        self.assertIn("Journey 3", box)
        self.assertIn("Visit 2", box)
        self.assertNotIn("Chat 1", box)  # only the top three
        self.assertNotIn("data-whatsapp-by-day", box)
        self.assertNotIn("<table", box.split("<details")[0])  # the day list is only inside "More details"
        self.assertIn("data-whatsapp-more", box)

    def test_empty_box_says_no_clicks_yet(self):
        html = self.client.get("/").content.decode()
        self.assertIn("No clicks yet.", html[html.index("data-system-whatsapp"):])


class SettingsLaunchTests(TestCase):
    def test_launch_group_orders_the_switches_and_links_to_payments(self):
        html = unlocked_client(make_user()).get("/settings/").content.decode()
        self.assertIn("<h3>Launch</h3>", html)
        self.assertNotIn("<h3>Stages</h3>", html)
        group = html[html.index("<h3>Launch</h3>"):html.index("<h3>Wording and tax</h3>")]
        self.assertIn('Card payments are opened separately in <a href="/payments/">Payments</a>.', group)
        names = re.findall(r'data-system-field="(\w+)"', group)
        self.assertEqual(names, ["opening_date", "opening_text", "register_interest_open", "journey_email_gate", "memberships_public", "booking_open"])
        self.assertIn("People can register their interest.", group)
        self.assertIn("Shows the Memberships page and prices. Off for the soft launch.", group)
        self.assertIn("Ask for an email at the end of the questionnaire.", group)


class PageStructureTests(TestCase):
    """The body of a panel that is not a table sits inside sys-pad or sys-group, so nothing touches the panel edge."""

    def test_payments_assistant_approval_and_merge_wrap_their_content(self):
        client = unlocked_client(make_user())
        payments = client.get("/payments/").content.decode()
        self.assertEqual(payments.count('<div class="sys-pad">'), 2)
        self.assertNotRegex(payments, r'</header>\s*<div class="sys-state"')
        assistant = client.get("/assistant/").content.decode()
        self.assertGreaterEqual(assistant.count('<div class="sys-pad">'), 1)
        self.assertIn('<div class="sys-group">', client.get("/approval/").content.decode())
        for path in ("/assistant/personality/", "/assistant/limits/"):
            self.assertIn('class="sys-group"', client.get(path).content.decode(), path)
