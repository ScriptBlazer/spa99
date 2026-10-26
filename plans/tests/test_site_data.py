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
        self.assertEqual(content.page_content("journey")["result_cta"].cta_label, "Register for {plan}")  # other braces untouched


class HoursAndLabelsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_shabbos_line_is_worked_out_from_the_offsets(self):
        self.assertIn(("Shabbos and Yom Tov", "Closes 2 hours before Shabbos and Yom Tov begin. Opens 1 hour after they end."),
                      pages.opening_hours())
        OpeningRule.objects.filter(key="shabbos-close").update(offset_minutes=90)
        self.assertIn(("Shabbos and Yom Tov", "Closes 90 minutes before Shabbos and Yom Tov begin. Opens 1 hour after they end."),
                      pages.opening_hours())
        OpeningRule.objects.filter(key__startswith="shabbos").update(offset_minutes=None, public_note="")
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


class JourneyAndGoldBackfillTests(TestCase):
    """2026-10-23 wording: only the exact old values are replaced, edited ones are left alone."""

    @classmethod
    def setUpTestData(cls):
        seed_all()

    def run_command(self):
        call_command("backfill_site_data", stdout=StringIO())

    def run_command_text(self):
        out = StringIO()
        call_command("backfill_site_data", stdout=out)
        return out.getvalue()

    def test_only_exact_old_values_change(self):
        from journey.models import Question
        Question.objects.filter(key="time").update(help_text="Choose any that fit.", min_choices=0)
        Question.objects.filter(key="facilities").update(help_text="Pick a few.", min_choices=0)  # edited by hand
        Section.objects.filter(page__key="journey", key="change_answers").update(cta_label="Change my answers")
        Section.objects.filter(page__key="gold-apply", key="screen_1").update(
            heading="Your property.", body="Our own words.")
        Section.objects.filter(page__key="journey", key="last_suggestion").delete()
        self.run_command()
        time, facilities = Question.objects.get(key="time"), Question.objects.get(key="facilities")
        self.assertEqual((time.help_text, time.min_choices), ("Choose at least one.", 1))
        self.assertEqual((facilities.help_text, facilities.min_choices), ("Pick a few.", 0))
        self.assertEqual(Section.objects.get(page__key="journey", key="change_answers").cta_label, "Start again")
        screen = Section.objects.get(page__key="gold-apply", key="screen_1")
        self.assertEqual((screen.heading, screen.body), ("About you.", "Our own words."))
        self.assertEqual(Section.objects.get(page__key="journey", key="last_suggestion").cta_label, "See my last suggestion")
        self.run_command()  # repeatable
        self.assertEqual(Question.objects.get(key="facilities").help_text, "Pick a few.")

    def test_round_4_wording_and_options_change_only_from_the_exact_old_values(self):
        from journey.models import Option, Question, SuggestionRule
        old = {("home", "opening", "heading"): "Launching {opening}.", ("spa", "opener_4", "body"): "Your robe and slippers are waiting.",
               ("spa", "moment_shower", "heading"): "In every shower.", ("spa", "moment_tote", "heading"): "On the way out.",
               ("spa", "arrive_kit", "heading"): "Every visit includes"}
        for (page, key, field), value in old.items():
            Section.objects.filter(page__key=page, key=key).update(**{field: value})
        Section.objects.filter(page__key="spa", key="step_2").update(body="Our own words.")  # edited by hand
        Option.objects.filter(question__key="company", value="sometimes").update(plan_points={"tier-2": 1, "tier-3": 1})
        Option.objects.filter(question__key="heard_via", value="bml").update(label="BML")
        Option.objects.filter(question__key="heard_via", value="social_media").delete()
        for question, value, label in (("company", "often", "Often with someone (Most visits.)"), ("heard_via", "instagram", "Instagram")):
            Option.objects.create(question=Question.objects.get(key=question), value=value, label=label, order=9)
        SuggestionRule.objects.filter(name__startswith="Evenings with guests").update(conditions=[
            {"question": "time", "any_of": ["evening", "late_night"]}, {"question": "company", "any_of": ["often"]}])
        call_command("backfill_site_data", "--dry-run", stdout=StringIO())
        self.assertEqual(Section.objects.get(page__key="home", key="opening").heading, "Launching {opening}.")  # dry run saves nothing
        self.run_command()
        self.assertEqual(Section.objects.get(page__key="home", key="opening").heading, "{opening}.")
        self.assertEqual(Section.objects.get(page__key="spa", key="opener_4").body, "Take your time. Nothing here is rushed.")
        self.assertEqual(Section.objects.get(page__key="spa", key="moment_shower").heading, "Between rounds.")
        self.assertEqual(Section.objects.get(page__key="spa", key="moment_tote").heading, "Until next time.")
        self.assertEqual(Section.objects.get(page__key="spa", key="arrive_kit").heading, "The details.")
        self.assertEqual(Section.objects.get(page__key="spa", key="step_2").body, "Our own words.")
        sometimes = Option.objects.get(question__key="company", value="sometimes")
        self.assertEqual(sometimes.plan_points, {"tier-3": 3})
        self.assertEqual(Option.objects.get(question__key="heard_via", value="bml").label, "BML member")
        self.assertTrue(Option.objects.filter(question__key="heard_via", value="social_media", active=True).exists())
        for value in ("often", "instagram"):  # retired, not deleted: old answers keep their label
            self.assertFalse(Option.objects.get(value=value).active)
        rule = SuggestionRule.objects.get(name__startswith="Evenings with guests")
        self.assertEqual(rule.conditions[1], {"question": "company", "any_of": ["sometimes", "often"]})
        self.assertIn("Nothing to change", self.run_command_text())


class RegisterWordingBackfillTests(TestCase):
    """'Register interest' becomes 'Register': only the exact old values change."""

    def test_exact_old_wording_is_replaced_and_edits_are_left_alone(self):
        seed_all()
        Section.objects.filter(page__key="journey", key="result_cta").update(cta_label="Register interest in {plan}")
        Section.objects.filter(page__key="home", key="opening").update(cta_label="Register interest")
        Section.objects.filter(page__key="book", key="placeholder").update(cta_label="Join the list")  # edited by hand
        call_command("backfill_site_data", "--dry-run", stdout=StringIO())
        self.assertEqual(Section.objects.get(page__key="home", key="opening").cta_label, "Register interest")  # dry run saves nothing
        call_command("backfill_site_data", stdout=StringIO())
        self.assertEqual(Section.objects.get(page__key="journey", key="result_cta").cta_label, "Register for {plan}")
        self.assertEqual(Section.objects.get(page__key="home", key="opening").cta_label, "Register")
        self.assertEqual(Section.objects.get(page__key="book", key="placeholder").cta_label, "Join the list")


class WithAFriendBackfillTests(TestCase):
    """2026-10-26: 'with someone' becomes 'with a friend' and 'Your membership' becomes 'Based on your answers'; edits stay."""

    def test_exact_old_wording_is_swapped_and_edited_wording_is_left_alone(self):
        from journey.models import Option, Question, SuggestionRule
        seed_all()
        sometimes = Option.objects.get(question__key="company", value="sometimes")
        Option.objects.filter(pk=sometimes.pk).update(label="Sometimes with someone (A friend now and then.)", reason="Sometimes with someone")
        Option.objects.create(question=Question.objects.get(key="company"), value="often", active=False, order=9,
                              label="Often with someone (Most visits.)", reason="Often with someone")
        SuggestionRule.objects.filter(name="Sometimes with a friend: not Tier 1").update(name="Sometimes with someone: not Tier 1")
        SuggestionRule.objects.filter(name="Sometimes with a friend: tie goes to Tier 3").update(name="Our own tie rule")  # edited by hand
        Section.objects.filter(page__key="journey", key="result_label").update(body="Your membership")
        call_command("backfill_site_data", "--dry-run", stdout=StringIO())
        self.assertEqual(Option.objects.get(pk=sometimes.pk).reason, "Sometimes with someone")  # dry run saves nothing
        call_command("backfill_site_data", stdout=StringIO())
        sometimes.refresh_from_db()
        self.assertEqual((sometimes.label, sometimes.reason), ("Sometimes with a friend (Now and then.)", "Sometimes with a friend"))
        often = Option.objects.get(question__key="company", value="often")
        self.assertEqual((often.label, often.reason, often.active), ("Often with a friend (Most visits.)", "Often with a friend", False))
        self.assertTrue(sometimes.history.filter(label="Sometimes with a friend (Now and then.)").exists())
        self.assertTrue(SuggestionRule.objects.filter(name="Sometimes with a friend: not Tier 1").exists())
        self.assertTrue(SuggestionRule.objects.filter(name="Our own tie rule").exists())
        self.assertEqual(Section.objects.get(page__key="journey", key="result_label").body, "Based on your answers")
