from datetime import time
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import RequestFactory, TestCase

from content.services import page_content
from pages import services as pages
from plans import services
from plans.management.commands.seed_phase1 import seed_all
from plans.models import OpeningRule, Plan, SiteSettings
from users.models import InterestRegistration, User


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

    def test_site_settings_is_a_singleton_and_contact_email_comes_from_env(self):
        first, second = SiteSettings.load(), SiteSettings.load()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(SiteSettings.objects.count(), 1)
        self.assertEqual(first.contact_email, "hello@example.test")
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


class MembershipsPageDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_plan_pills_come_from_the_row_and_the_opening_rules(self):
        self.assertEqual(services.plan_pills(Plan.objects.get(slug="tier-1")),
                         ["Daytime, 5am to 6pm", "Book up to 1 day ahead", "1 booking at a time"])
        self.assertEqual(services.plan_pills(Plan.objects.get(slug="tier-3")), [
            "Day and evening, 5am to 3am", "Book up to 7 days ahead", "3 bookings at a time", "1 guest a month", "Leil Shishi option"])
        plan = Plan.objects.get(slug="tier-2")  # a changed row or hours rule changes the words
        plan.upcoming_limit = 4
        OpeningRule.objects.filter(key="evening").update(end_time=time(2, 0))
        self.assertEqual(services.plan_pills(plan)[0::2], ["Day and evening, 5am to 2am", "4 bookings at a time"])

    def test_card_has_tagline_fallback_and_pills(self):
        Plan.objects.filter(slug="tier-3").update(tagline="")
        cards = {c["slug"]: c for c in pages.purchasable_plans()}
        self.assertEqual(cards["tier-2"]["tagline"], "Your evenings, too.")
        self.assertEqual(cards["tier-3"]["tagline"], "Unlimited")
        self.assertEqual(cards["tier-2"]["render"], "dry-sauna")
        self.assertEqual(cards["tier-2"]["pills"][-1], "Leil Shishi option")

    def test_compare_table_has_single_visit_column_and_perk_rows(self):
        table = pages.compare_table(pages.purchasable_plans())
        labels = [r["label"] for r in table]
        self.assertEqual(labels[-2:], ["Merch", "Leil Shishi"])
        leil = table[-1]["cells"]
        self.assertEqual([c["slug"] for c in leil], ["tier-1", "tier-2", "tier-3", "single-visit"])
        self.assertEqual([c["text"] for c in leil], ["No", "Option, £45 + VAT a place", "Option, £45 + VAT a place", "No"])

    def test_preselect_order(self):
        cards = pages.purchasable_plans()
        anon = RequestFactory().get("/memberships/")
        self.assertEqual(pages.selected_plan_slug(anon, cards), "tier-2")  # the highlight plan
        for bad in ("gold", "single-visit", "nonsense"):
            self.assertEqual(pages.selected_plan_slug(RequestFactory().get("/memberships/", {"plan": bad}), cards), "tier-2")
        self.assertEqual(pages.selected_plan_slug(RequestFactory().get("/memberships/", {"plan": "tier-3"}), cards), "tier-3")
        user = User.objects.create_user("a@example.com", "a-long-password-1")
        InterestRegistration.objects.create(user=user, plan=Plan.objects.get(slug="tier-1"))
        mine = RequestFactory().get("/memberships/")
        mine.user = user
        self.assertEqual(pages.selected_plan_slug(mine, cards), "tier-1")  # own interest beats the highlight
        mine = RequestFactory().get("/memberships/", {"plan": "tier-3"})
        mine.user = user
        self.assertEqual(pages.selected_plan_slug(mine, cards), "tier-3")  # ?plan= beats own interest
        Plan.objects.update(highlight=False)
        self.assertEqual(pages.selected_plan_slug(anon, pages.purchasable_plans()), "")
