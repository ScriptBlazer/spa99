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

    def test_site_settings_is_a_singleton_and_contact_address_falls_back_to_the_from_address(self):
        first, second = SiteSettings.load(), SiteSettings.load()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(SiteSettings.objects.count(), 1)
        self.assertEqual((first.contact_email, first.contact_address), ("", "from@example.test"))
        first.contact_email = "hi@example.test"
        self.assertEqual(first.contact_address, "hi@example.test")
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
                         ["Off-peak, 5am to 6pm", "Book up to 1 day ahead", "1 booking at a time"])
        self.assertEqual(services.plan_pills(Plan.objects.get(slug="tier-3")), [
            "Off-peak and peak, 24 hours a day", "Book up to 7 days ahead", "3 bookings at a time", "1 guest a month"])
        plan = Plan.objects.get(slug="tier-2")  # a changed row or hours rule changes the words
        plan.upcoming_limit = 4
        OpeningRule.objects.filter(key="evening").update(end_time=time(2, 0))
        self.assertEqual(services.plan_pills(plan)[0::2], ["Off-peak and peak, 5am to 2am", "4 bookings at a time"])

    def test_card_has_tagline_fallback_and_pills(self):
        Plan.objects.filter(slug="tier-3").update(tagline="")
        cards = {c["slug"]: c for c in pages.purchasable_plans()}
        self.assertEqual(cards["tier-2"]["tagline"], "Your evenings, too.")
        self.assertEqual(cards["tier-3"]["tagline"], "Unlimited")
        self.assertEqual(cards["tier-2"]["render"], "dry-sauna")
        self.assertEqual(cards["tier-2"]["pills"][-1], "2 bookings at a time")  # Leil Shishi is hidden for now

    def test_compare_table_has_single_visit_gold_and_perk_rows(self):
        table = pages.compare_table(pages.purchasable_plans())
        labels = [r["label"] for r in table]
        self.assertEqual(labels[-2:], ["Waitlist", "BML members' events"])  # Leil Shishi is hidden for now (2026-10-26)
        self.assertNotIn("Leil Shishi", labels)
        merch = next(r for r in table if r["label"] == "Merch")["cells"]
        self.assertEqual([c["slug"] for c in merch], ["tier-1", "tier-2", "tier-3", "single-visit", "gold"])
        visits = next(r for r in table if r["label"] == "Visits a month")["cells"]
        self.assertEqual([c["text"] for c in visits], ["6", "8", "Unlimited", "1", "Unlimited"])  # Tier 3 says Unlimited, not All
        self.assertEqual([c["text"] for c in next(r for r in table if r["label"] == "When")["cells"]][:3], ["Off-peak", "Off-peak and peak", "Off-peak and peak"])

    def test_leil_shishi_switch_hides_it_everywhere_and_shows_it_again(self):
        self.assertFalse(SiteSettings.load().show_leil_shishi)  # default off
        tier2 = Plan.objects.get(slug="tier-2")
        self.assertNotIn("Leil Shishi option", services.plan_pills(tier2))
        self.assertNotIn("leil_shishi", [p["key"] for p in services.plan_display(tier2)["perks"]])
        self.assertNotIn("Leil Shishi when offered", dict(pages.gold_groups())["Beyond the spa"])
        SiteSettings.objects.update(show_leil_shishi=True)  # the data was never deleted
        self.assertIn("Leil Shishi option", services.plan_pills(tier2))
        self.assertIn("Leil Shishi", [r["label"] for r in pages.compare_table(pages.purchasable_plans())])
        self.assertIn("Leil Shishi when offered", dict(pages.gold_groups())["Beyond the spa"])

    def test_gold_column_shows_the_annual_fee_and_says_by_application_when_empty(self):
        def gold_cells():
            table = pages.compare_table(pages.purchasable_plans())
            return [next(r for r in table if r["label"] == label)["cells"][-1]["text"] for label in ("Price, ex VAT", "Price, inc VAT")]

        self.assertEqual(gold_cells(), ["£299 a year", "£358.80 a year"])  # default £299 ex VAT (2026-10-26)
        Plan.objects.filter(slug="gold").update(annual_fee=None)
        self.assertEqual(gold_cells(), ["By application", "By application"])  # no "TBC" text
        Plan.objects.filter(slug="gold").update(annual_fee=Decimal("150.00"))
        self.assertEqual(gold_cells(), ["£150 a year", "£180 a year"])
        Plan.objects.filter(slug="gold").update(visible=False)  # a hidden Gold Card leaves the table
        self.assertEqual(len(pages.compare_table(pages.purchasable_plans())[0]["cells"]), 4)

    def test_free_star_and_note_follow_the_gold_annual_fee(self):
        from django.template import Context, Template

        def render():
            return Template("{% load content_tags %}{% gold_fee_note %}").render(Context()).strip()

        gold_cta = page_content("memberships")["gold_cta"].body
        self.assertIn("free*, by application", gold_cta)
        self.assertIn("*An annual admin fee of £299 + VAT applies.", render())
        Plan.objects.filter(slug="gold").update(annual_fee=Decimal("150.50"))
        self.assertIn("£150.50 + VAT", render())
        Plan.objects.filter(slug="gold").update(annual_fee=None)  # no fee: plain "free", no note
        self.assertEqual(render(), "")
        self.assertIn("free, by application", page_content("memberships")["gold_cta"].body)
        self.assertNotIn("*", services.gold_star() + page_content("home")["gold_teaser"].body)
        self.assertEqual(services.gold_fee_note(), "")

    def test_open_24_hours_with_cleaning_hours_and_shabbos(self):
        self.assertEqual(pages.hours_summary(), "Open 24 hours a day")
        self.assertEqual(pages.hours_note(), "Open 24 hours a day. Cleaning hours 3am to 5am. Closed Shabbos and Yom Tov.")
        rows = pages.opening_hours()
        self.assertEqual(rows[0], ("Open", "24 hours a day"))
        self.assertIn(("Cleaning hours", "3am to 5am, every day"), rows)
        self.assertNotIn("Closed", [label for label, _ in rows])
        OpeningRule.objects.filter(key="evening").update(end_time=time(1, 0))  # the rules no longer fill the day: honest words
        self.assertEqual(pages.hours_summary(), "Open 5am to 1am")

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
