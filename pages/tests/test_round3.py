"""Round 3 data: Gold facts and perk visibility, opener lines, amenity moment placement, kit, sign-in shell, backfill."""
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from content.models import Page, Section
from pages import services as pages
from plans.management.commands.seed_phase1 import seed_all
from plans.models import Facility, OpeningRule, Plan


def moments(*keys):
    return {k: {"key": k, "heading": k, "body": "", "pictures": []} for k in keys}


def order(sections):
    return [s["moment"]["key"] if s["kind"] == "moment" else
            s["feature"]["slug"] if s["kind"] == "feature" else "tiles" for s in sections]


class GoldFactsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def gold(self, **fields):
        Plan.objects.filter(slug="gold").update(**fields)
        return pages.gold_facts()

    def test_seeded_figures_pills_and_perks(self):
        facts = pages.gold_facts()
        self.assertEqual([(f["value"], f["label"]) for f in facts["figures"]],
                         [("Unlimited", "visits"), ("Any time", "5am to 3am"), ("7 days", "to book ahead"), ("2", "guests a month")])
        self.assertEqual(facts["pills"], ["3 bookings at a time", "Cancel up to 5 hours before", "First call from the waitlist"])
        self.assertEqual([p["name"] for p in facts["perks"]],
                         ["Each merch release", "Leil Shishi when offered", "BML members' events"])
        self.assertEqual(facts["perks"][1]["note"], "The Thursday evening meal, included.")

    def test_figures_follow_the_plan(self):
        facts = self.gold(visits_per_month=4, hours=Plan.DAYTIME_ONLY, booking_window_days=1, guests_per_month=0, upcoming_limit=1)
        self.assertEqual([(f["value"], f["label"]) for f in facts["figures"]],
                         [("4", "visits a month"), ("Daytime", "5am to 6pm"), ("1 day", "to book ahead")])
        self.assertEqual(facts["pills"][0], "1 booking at a time")
        days = facts["figures"][2]
        self.assertEqual((days["number"], days["suffix"]), (1, " day"))

    def test_hidden_plan_gives_none(self):
        self.assertIsNone(self.gold(visible=False))

    def test_private_perks_are_hidden_everywhere_and_merch_stays_by_default(self):
        plan = Plan.objects.get(slug="gold")
        plan.perks = [dict(p, public=False) if p["key"] in ("events", "waitlist_priority") else p for p in plan.perks]
        plan.save()
        self.assertNotIn("BML members' events", [p["name"] for p in pages.gold_facts()["perks"]])
        self.assertNotIn("First call from the waitlist", pages.gold_facts()["pills"])
        groups = dict(pages.gold_groups())
        self.assertNotIn("BML members' events", groups["Beyond the spa"])
        self.assertIn("Each merch release", groups["Beyond the spa"])
        self.assertNotIn("First call from the waitlist", groups["Your visits"])


class OpenerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_lines_fill_hours_closure_and_room_count(self):
        lines = pages.opener_lines()
        self.assertEqual(lines[0], {"statement": "Open 5am to 3am.", "note": "Every day. Closed for Shabbos and Yom Tov."})
        self.assertEqual(lines[2]["note"], "Eight rooms, all part of the same visit.")
        self.assertEqual(len(lines), 4)

    def test_hiding_a_room_or_changing_hours_changes_the_lines(self):
        Facility.objects.filter(slug="gym").update(visible=False)
        OpeningRule.objects.filter(key="evening").update(end_time="02:00")
        lines = pages.opener_lines()
        self.assertEqual(lines[0]["statement"], "Open 5am to 2am.")
        self.assertEqual(lines[2]["note"], "Seven rooms, all part of the same visit.")

    def test_missing_values_never_leave_a_gap(self):
        OpeningRule.objects.filter(kind=OpeningRule.CLOSE_BEFORE_CANDLES).update(public_title="")
        self.assertEqual(pages.opener_lines()[0]["note"], "Every day.")
        OpeningRule.objects.filter(kind=OpeningRule.PERIOD).update(active=False)
        self.assertEqual([l["statement"] for l in pages.opener_lines()][0], "For men only.")  # line 1 skipped, not "Open ."

    def test_empty_heading_skips_a_line(self):
        Section.objects.filter(page__key="spa", key="opener_2").update(heading="")
        self.assertEqual([l["statement"] for l in pages.opener_lines()][1], "Heat, steam, cold and rest.")

    def test_picture_falls_back_to_a_built_one(self):
        with mock.patch("pages.services.images.has_image", side_effect=lambda n: n == "door-gold"):
            picture = pages.opener_picture()
        self.assertEqual((picture["name"], picture["portrait"], picture["is_door"]), ("door-gold", "", True))
        with mock.patch("pages.services.images.has_image", side_effect=lambda n: n in ("robe", "robe-portrait")):
            picture = pages.opener_picture()
        self.assertEqual((picture["name"], picture["portrait"], picture["is_door"]), ("robe", "robe-portrait", False))
        with mock.patch("pages.services.images.has_image", return_value=False):
            self.assertEqual(pages.opener_picture()["name"], "")


class MomentTests(TestCase):
    def sections(self, *keys):
        feature = lambda slug: {"kind": "feature", "feature": {"slug": slug}}
        return [feature("dry"), {"kind": "tiles", "tiles": []}, feature("relax"), feature("gym")], moments(*keys)

    def test_placement_by_rule(self):
        sections, found = self.sections("towel", "shower", "slippers")
        self.assertEqual(order(pages.place_moments(sections, found)),
                         ["towel", "dry", "tiles", "shower", "relax", "slippers", "gym"])

    def test_no_tiles_puts_the_shower_after_the_first_feature(self):
        sections, found = self.sections("towel", "shower", "slippers")
        sections = [s for s in sections if s["kind"] != "tiles"]
        self.assertEqual(order(pages.place_moments(sections, found)), ["towel", "dry", "shower", "relax", "slippers", "gym"])

    def test_no_feature_after_the_shower_puts_slippers_last_and_no_rooms_still_works(self):
        sections, found = self.sections("shower", "slippers")
        self.assertEqual(order(pages.place_moments(sections[:2], found)), ["dry", "tiles", "shower", "slippers"])
        self.assertEqual(order(pages.place_moments([], moments("towel", "shower", "slippers"))), ["towel", "shower", "slippers"])

    def test_slippers_without_shower_and_input_is_not_changed(self):
        sections, found = self.sections("slippers")
        before = list(sections)
        self.assertEqual(order(pages.place_moments(sections, found)), ["dry", "tiles", "relax", "slippers", "gym"])
        self.assertEqual(sections, before)

    def test_moments_need_a_heading_and_a_picture(self):
        seed_all()
        with mock.patch("pages.services.images.has_image", side_effect=lambda n: n in ("towel-bench", "toiletries", "tote")):
            found = pages.spa_moments()
            self.assertEqual(sorted(found), ["shower", "tote", "towel"])  # slippers: no picture
            self.assertEqual([p["has_image"] for p in found["shower"]["pictures"]], [True, False])  # towel-rail not built yet
            Section.objects.filter(page__key="spa", key="moment_towel").update(heading="")
            self.assertNotIn("towel", pages.spa_moments())
        with mock.patch("pages.services.images.has_image", return_value=False):
            self.assertEqual(pages.spa_moments(), {})


class KitAndSigninTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_kit_parsing_and_unknown_image(self):
        Section.objects.filter(page__key="spa", key="arrive_kit").update(body="Towels | towel-bench | 45% 50%\nRobe\n\nTie | nope")
        with mock.patch("pages.services.images.has_image", side_effect=lambda n: n == "towel-bench"):
            items = pages.arrive_kit()["items"]
        self.assertEqual([(i["label"], i["name"], i["focus"], i["has_image"]) for i in items],
                         [("Towels", "towel-bench", "45% 50%", True), ("Robe", "", "50% 50%", False), ("Tie", "nope", "50% 50%", False)])

    def test_every_visit_sentence_comes_from_the_kit(self):
        visit = pages.every_visit()
        self.assertEqual(visit["text"], "Every visit: towels, robe, slippers and toiletries, and every room.")
        self.assertEqual((visit["cta_label"], visit["cta_url"]), ("See the spa", "/the-spa/"))
        Section.objects.filter(page__key="spa", key="arrive_kit").update(body="Robe | robe")
        self.assertIn("Every visit: robe, and", pages.every_visit()["text"])
        Section.objects.filter(page__key="memberships", key="every_visit").update(visible=False)
        self.assertIsNone(pages.every_visit())

    def test_signin_shell_uses_rows_and_falls_back(self):
        shell = pages.signin_shell()
        self.assertEqual((shell["heading"], shell["caption"], shell["name"]), ("Welcome back.", "Your own locker, every visit.", "lockers"))
        self.assertEqual(shell["address_line"][0], "99 Vale Road, London N4 1PR")
        Page.objects.filter(key="signin").delete()
        self.assertEqual(pages.signin_shell()["lead"], "Sign in to your Spa 99 account.")

    def test_gym_detail_name_does_not_block_saving_before_it_is_built(self):
        gym = Facility.objects.get(slug="gym")
        self.assertEqual(gym.detail_image_name, "bottle-gym")
        gym.full_clean()  # unchanged, not built yet: fine
        gym.detail_image_name = "nope"
        with self.assertRaises(Exception):
            gym.full_clean()


class BackfillRound3Tests(TestCase):
    def test_fills_gaps_only_and_runs_twice(self):
        seed_all()
        Page.objects.filter(key="signin").delete()
        Section.objects.filter(page__key="spa", key__in=["opener_1", "moment_towel", "arrive_kit"]).delete()
        Section.objects.filter(page__key="gold", key="apply_note").delete()
        Section.objects.filter(page__key="spa", key="opener_2").update(heading="Men only, hand edited.")
        Section.objects.filter(page__key="spa", key="step_2_pills").update(body="Towel, robe and slippers\nYour own locker\nPhones stay in the locker")
        Section.objects.filter(page__key="spa", key="opener_image").delete()  # deleted rows come back (nothing to protect)
        gold = Plan.objects.get(slug="gold")
        gold.perks = [{k: v for k, v in p.items() if k != "note"} for p in gold.perks]
        gold.save()
        Facility.objects.filter(slug="gym").update(detail_image_name="", detail_alt="")
        out = StringIO()
        call_command("backfill_site_data", "--dry-run", stdout=out)
        self.assertIn("Dry run", out.getvalue())
        self.assertFalse(Page.objects.filter(key="signin").exists())
        call_command("backfill_site_data", stdout=StringIO())
        self.assertTrue(Section.objects.filter(page__key="signin", key="caption").exists())
        self.assertTrue(Section.objects.filter(page__key="spa", key="opener_1").exists())
        self.assertEqual(Section.objects.get(page__key="spa", key="opener_2").heading, "Men only, hand edited.")
        self.assertEqual(Section.objects.get(page__key="spa", key="step_2_pills").body, "Your own locker\nPhones stay in the locker")
        self.assertEqual(Facility.objects.get(slug="gym").detail_image_name, "bottle-gym")
        self.assertEqual(pages.gold_facts()["perks"][1]["note"], "The Thursday evening meal, included.")
        out = StringIO()
        call_command("backfill_site_data", stdout=out)
        self.assertNotIn("round 3", out.getvalue())


class ViewContextTests(TestCase):
    """The contract the templates rely on (docs in the commit message and the hand-off)."""

    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_pages_give_the_templates_their_data(self):
        spa = self.client.get("/the-spa/").context
        for key in ("opener_lines", "opener", "arrive_kit", "tote", "sections"):
            self.assertIn(key, spa)
        self.assertEqual(len(spa["opener_lines"]), 4)
        gold = self.client.get("/gold-card/").context
        self.assertEqual(len(gold["gold"]["figures"]), 4)
        self.assertIn("every_visit", self.client.get("/memberships/").context)
