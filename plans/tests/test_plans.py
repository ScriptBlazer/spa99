from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from content.services import page_content
from plans import services
from plans.management.commands.seed_phase1 import seed_all
from plans.models import Plan, SiteSettings


class PlanServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_prices_inc_vat_match_pricing_doc(self):
        for slug, expected in {"tier-1": "358.80", "tier-2": "478.80", "tier-3": "598.80", "single-visit": "118.80", "gold": "0.00"}.items():
            plan = Plan.objects.get(slug=slug)
            self.assertEqual(services.price_inc_vat(plan.price_ex_vat), Decimal(expected), slug)

    def test_vat_rate_is_a_setting_not_a_constant(self):
        SiteSettings.objects.update(vat_rate=Decimal("25.00"))
        self.assertEqual(services.price_inc_vat(Decimal("100.00")), Decimal("125.00"))

    def test_site_settings_is_a_singleton_with_alert_recipients(self):
        first, second = SiteSettings.load(), SiteSettings.load()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(SiteSettings.objects.count(), 1)
        self.assertEqual(first.gold_alert_to_list, ["barry@bmlgroup.co.uk"])
        self.assertEqual(first.gold_alert_cc_list, ["moishe.berkowitz@bmlgroup.co.uk"])
        self.assertEqual((first.capacity, first.slot_length_minutes, first.slot_step_minutes, first.booking_notice_minutes), (25, 120, 30, 10))

    def test_plan_facts_follow_the_plan_row(self):
        plan = Plan.objects.get(slug="tier-2")
        self.assertEqual(services.plan_facts(plan)[:2], ["Book up to 3 days ahead", "8 visits a month"])
        plan.booking_window_days, plan.visits_per_month = 1, None
        self.assertEqual(services.plan_facts(plan)[:2], ["Book up to 1 day ahead", "Unlimited visits"])


class SeedTests(TestCase):
    def test_seed_is_idempotent_and_never_overwrites_edits(self):
        first = seed_all()
        self.assertGreater(sum(first.values()), 100)
        Plan.objects.filter(slug="tier-2").update(price_ex_vat=Decimal("410.00"))
        self.assertEqual(seed_all(), {})  # second run creates nothing
        self.assertEqual(Plan.objects.get(slug="tier-2").price_ex_vat, Decimal("410.00"))

    def test_dry_run_saves_nothing(self):
        out = StringIO()
        call_command("seed_phase1", "--dry-run", stdout=out)
        self.assertIn("Would create", out.getvalue())
        self.assertEqual(Plan.objects.count(), 0)
        call_command("seed_phase1", stdout=StringIO())
        self.assertEqual(Plan.objects.count(), 5)

    def test_every_website_page_has_seeded_copy_and_missing_sections_are_safe(self):
        seed_all()
        for key in ["home", "spa", "memberships", "gold", "journey", "book", "register", "account", "visit", "privacy", "terms"]:
            self.assertTrue(page_content(key), key)
        self.assertEqual(page_content("home")["hero"].heading, "Beyond Luxury.")
        self.assertEqual(page_content("home")["nope"].heading, "")  # unknown section: empty, no error
