"""The spa page data: room grouping that survives hidden rooms, fact validation, visit pills, copy placeholders."""
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from content import services as content
from content.models import Section
from pages import services as pages
from plans.management.commands.seed_phase1 import seed_all
from plans.models import Facility, Plan, SiteSettings


def layout(sections):
    return [(s["feature"]["slug"], s["companion"]["slug"] if s["companion"] else None, s["side"]) if s["kind"] == "feature"
            else [t["slug"] for t in s["tiles"]] for s in sections]


class SpaSectionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def sections(self):
        return pages.spa_sections(pages.facility_cards())

    def test_seed_gives_the_four_compositions_with_alternating_sides(self):
        self.assertEqual(layout(self.sections()), [
            ("dry-sauna", None, "left"), ["wet-sauna", "cold-plunge", "showers"],
            ("relaxing-zone", "massage-room", "right"), ("gym", "kitchenette", "left")])

    def test_hiding_rooms_never_breaks_the_layout(self):
        Facility.objects.filter(slug__in=["dry-sauna", "gym", "wet-sauna"]).update(visible=False)
        self.assertEqual(layout(self.sections()), [
            ["cold-plunge", "showers"], ("relaxing-zone", "massage-room", "left"), ["kitchenette"]])

    def test_extra_and_lonely_companions_become_tiles_and_long_runs_split(self):
        Facility.objects.update(display="tile")
        Facility.objects.filter(slug="gym").update(display="feature")
        Facility.objects.filter(slug__in=["massage-room", "kitchenette", "cold-plunge"]).update(display="companion")
        # order: dry-sauna wet-sauna cold-plunge showers relaxing-zone massage-room gym kitchenette
        self.assertEqual(layout(self.sections()), [
            ["dry-sauna", "wet-sauna", "cold-plunge"], ["showers", "relaxing-zone", "massage-room"],
            ("gym", "kitchenette", "left")])

    def test_room_count_word_follows_visible_rooms(self):
        self.assertEqual(content.page_content("spa")["intro"].body, "Eight spaces, one quiet visit.")
        Facility.objects.filter(slug="gym").update(visible=False)
        self.assertEqual(content.page_content("spa")["intro"].body, "Seven spaces, one quiet visit.")


class FacilityValidationTests(TestCase):
    def check(self, **fields):
        Facility(name="Room", slug="room", **fields).full_clean()

    def test_facts_must_be_up_to_four_short_texts(self):
        self.check(facts=["One", "Two", "Three", "Four"])
        for bad in (["a"] * 5, ["x" * 33], [""], "text", [1]):
            with self.subTest(bad=bad), self.assertRaises(ValidationError) as ctx:
                self.check(facts=bad)
            self.assertIn("facts", ctx.exception.message_dict)

    def test_image_names_must_exist_in_the_manifest(self):
        self.check(image_name="gym", detail_image_name="lounge")
        with self.assertRaises(ValidationError) as ctx:
            self.check(image_name="nope", detail_image_name="nope")
        self.assertEqual(set(ctx.exception.message_dict), {"image_name", "detail_image_name"})


class VisitPillsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_pills_come_from_plans_hours_and_copy(self):
        pills = pages.visit_pills()
        self.assertEqual(pills["book"][0], "Book 1 to 7 days ahead")  # the tiers' windows differ, cancel hours do not all agree
        self.assertNotIn("Cancel", " ".join(pills["book"]))
        self.assertEqual(pills["book"][-1], "Booking opens with membership")
        self.assertEqual(pills["arrive"][-1], "Phones stay in the locker")
        self.assertEqual(pills["stay"][0], "Open 5am to 3am")
        self.assertIn("Closed for Shabbos and Yom Tov", pills["stay"])
        self.assertEqual(pills["stay"][-1], "Every room is part of the visit")

    def test_pills_follow_the_data(self):
        Plan.objects.filter(kind=Plan.MONTHLY).update(booking_window_days=2, cancel_hours=12)
        SiteSettings.objects.update(booking_open=True)
        pills = pages.visit_pills()
        self.assertEqual(pills["book"], ["Book up to 2 days ahead", "Cancel up to 12 hours before"])
        Plan.objects.filter(slug="tier-1").update(cancel_hours=6)
        self.assertEqual(pages.visit_pills()["book"], ["Book up to 2 days ahead"])  # plans disagree: cancel pill omitted

    def test_next_from_line_uses_the_lowest_monthly_price(self):
        line = pages.next_from_line()
        self.assertRegex(line, r"^Memberships from £\d+ a month, £[\d.]+ inc VAT\.$")

    def test_spa_page_renders_with_the_new_context(self):
        response = self.client.get("/the-spa/")
        for name in ("facilities", "sections", "room_count", "visit_pills", "next_from", "hours", "hours_facts"):
            self.assertIn(name, response.context)


class BackfillTests(TestCase):
    def test_backfill_fills_empty_slots_and_fixes_old_wording(self):
        seed_all()
        Facility.objects.update(display="tile", image_name="", image_focus="50% 50%", facts=[])
        Facility.objects.filter(slug="massage-room").update(short_line="A quiet room for a massage, by appointment.")
        Section.objects.filter(page__key="spa", key="intro").update(body="Eight spaces, one quiet visit.")
        Section.objects.filter(page__key="spa", key="next").update(cta_label="Explore your membership")
        Section.objects.filter(page__key="spa", key="tiles_intro").delete()
        Facility.objects.filter(slug="gym").update(facts=["Mine"])
        call_command("backfill_site_data", "--dry-run", stdout=StringIO())
        self.assertEqual(Facility.objects.get(slug="gym").display, "tile")  # dry run saved nothing
        call_command("backfill_site_data", stdout=StringIO())
        self.assertEqual(Facility.objects.get(slug="dry-sauna").display, "feature")
        self.assertEqual(Facility.objects.get(slug="gym").facts, ["Mine"])  # hand edits stay
        self.assertEqual(Facility.objects.get(slug="massage-room").short_line, "A quiet room for massage, part of your visit.")
        self.assertEqual(Section.objects.get(page__key="spa", key="next").cta_label, "Tailor your membership")
        self.assertEqual(Section.objects.get(page__key="spa", key="intro").body, "{rooms} spaces, one quiet visit.")
        self.assertTrue(Section.objects.filter(page__key="spa", key="tiles_intro").exists())

    def test_backfill_swaps_stand_in_images_only_while_unchanged(self):
        seed_all()
        Facility.objects.filter(slug="cold-plunge").update(image_name="cold-tub")
        Facility.objects.filter(slug="kitchenette").update(image_name="gym")  # a hand edit
        call_command("backfill_site_data", stdout=StringIO())
        self.assertEqual(Facility.objects.get(slug="cold-plunge").image_name, "cold-plunge")
        self.assertEqual(Facility.objects.get(slug="kitchenette").image_name, "gym")
