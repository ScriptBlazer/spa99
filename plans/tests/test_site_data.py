"""Facts and wording that used to be written in code now come from rows (2026-10-22 review)."""
from datetime import date
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.test import TestCase

from content import services as content
from content.models import Section
from notifications.models import NotificationTemplate
from notifications.services import send_templated, subject_for
from pages import services as pages
from plans.management.commands.seed_phase1 import seed_all
from plans.models import Facility, OpeningRule, Plan, SiteSettings


class SiteSettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_address_and_opening_label_have_defaults_and_follow_the_date(self):
        site = SiteSettings.load()
        self.assertEqual(site.address_one_line, "99 Vale Road, London N4 1PR")
        self.assertEqual(site.opening_label, "January 2027")
        SiteSettings.objects.update(opening_date=date(2027, 2, 14), address_street="1 New Street", address_postcode="N4 9ZZ")
        site = SiteSettings.load()
        self.assertEqual(site.opening_label, "February 2027")
        self.assertEqual(site.address_one_line, "1 New Street, London N4 9ZZ")

    def test_emails_use_the_site_address_and_the_subject_rows(self):
        SiteSettings.objects.update(address_street="1 New Street")
        NotificationTemplate.objects.filter(key="verify").update(subject="Please confirm, {name}")
        self.assertEqual(subject_for("verify", name="Hugo"), "Please confirm, Hugo")
        send_templated("password_reset", ["a@example.com"], subject_for("password_reset"), {"first_name": "A", "url": "http://x/"})
        self.assertIn("1 New Street, London N4 1PR", mail.outbox[0].body)
        NotificationTemplate.objects.all().delete()
        self.assertEqual(subject_for("welcome"), "Welcome to Spa 99")  # built-in default if a row is deleted

    def test_opening_placeholder_in_copy_follows_the_site_settings(self):
        self.assertEqual(content.page_content("home")["hero"].body, "A private spa for men in North London. Opening January 2027.")
        SiteSettings.objects.update(opening_date=date(2027, 3, 1))
        self.assertIn("Opening March 2027.", content.page_content("home")["hero"].body)
        self.assertIn("Opening March 2027.", content.page_meta("home")["meta_description"])
        self.assertEqual(content.page_content("journey")["result_cta"].cta_label, "Register interest in {plan}")  # other braces untouched


class HoursAndLabelsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_shabbos_line_is_a_field_on_the_rule(self):
        self.assertIn(("Shabbos and Yom Tov", "Closed from Friday afternoon until Saturday night"), pages.opening_hours())
        OpeningRule.objects.filter(key="shabbos-close").update(public_note="Closed on Shabbos")
        self.assertIn(("Shabbos and Yom Tov", "Closed on Shabbos"), pages.opening_hours())
        OpeningRule.objects.filter(key="shabbos-close").update(public_note="")
        self.assertFalse([row for row in pages.opening_hours() if "Shabbos" in row[0]])
        self.assertEqual(pages.hours_summary(), "Open 5am to 3am")

    def test_facility_alt_and_gold_perk_phrases_come_from_rows(self):
        Facility.objects.filter(slug="gym").update(image_alt="A bright gym")
        Facility.objects.filter(slug="showers").update(image_alt="")
        alts = {card["slug"]: card["alt"] for card in pages.facility_cards()}
        self.assertEqual((alts["gym"], alts["showers"]), ("A bright gym", "Showers"))
        beyond = dict(pages.gold_groups())["Beyond the spa"]
        self.assertEqual(beyond, ["Each merch release", "Leil Shishi when offered", "BML members' events"])

    def test_one_label_splitter(self):
        self.assertEqual(pages.split_label("Early morning (5 to 9am)"), ("Early morning", "5 to 9am"))
        self.assertEqual(pages.split_label("Weekly"), ("Weekly", ""))

    def test_only_visible_monthly_plans_allow_interest(self):
        flags = {p.slug: p.interest_allowed for p in Plan.objects.all()}
        self.assertEqual(flags, {"tier-1": True, "tier-2": True, "tier-3": True, "gold": False, "single-visit": False})
        cards = {c["slug"]: c["interest_allowed"] for c in pages.purchasable_plans()}
        self.assertFalse(cards["single-visit"])
        Plan.objects.filter(slug="tier-1").update(visible=False)
        self.assertFalse(Plan.objects.get(slug="tier-1").interest_allowed)


class BackfillCommandTests(TestCase):
    """The command that updates an install made before these fixes. Dry run saves nothing."""

    @classmethod
    def setUpTestData(cls):
        seed_all()

    def setUp(self):
        Section.objects.filter(page__key="home", key="hero").update(body="Opening January 2027.")
        Facility.objects.filter(slug="gym").update(image_alt="")
        OpeningRule.objects.filter(key="shabbos-close").update(public_note="", public_title="")

    def run_command(self, *args):
        out = StringIO()
        call_command("backfill_site_data", *args, stdout=out)
        return out.getvalue()

    def test_dry_run_changes_nothing_and_the_real_run_is_repeatable(self):
        text = self.run_command("--dry-run")
        self.assertIn("Would change", text)
        self.assertEqual(Section.objects.get(page__key="home", key="hero").body, "Opening January 2027.")
        self.assertEqual(Facility.objects.get(slug="gym").image_alt, "")

        self.run_command()
        self.assertEqual(Section.objects.get(page__key="home", key="hero").body, "Opening {opening}.")
        self.assertTrue(Facility.objects.get(slug="gym").image_alt)
        self.assertTrue(OpeningRule.objects.get(key="shabbos-close").public_note)
        self.assertIn("Nothing to change", self.run_command())
