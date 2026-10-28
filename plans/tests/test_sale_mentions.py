"""Sale mentions (docs/design/SALE-MENTIONS.md): the end and months phrasing, the mentions on The spa, Home and Book, the journey result line."""
from datetime import datetime
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.template import Context, Template

from journey import engine
from journey.tests.test_journey import make_session
from plans import sales
from plans.management.commands.seed_phase1 import seed_all
from plans.tests.helpers import open_memberships
from plans.tests.test_sales import make_sale

LONDON = ZoneInfo("Europe/London")


def at(*args):
    return datetime(*args, tzinfo=LONDON)


def bar(ends, starts=at(2026, 12, 1, 9, 0), months=3):
    return {"ends_at": ends.isoformat(), "starts_at": starts.isoformat(), "months": months}


class PhrasingTests(TestCase):
    now = at(2026, 12, 10, 12, 0)

    def until(self, ends):
        return sales.sale_until(bar(ends), self.now)

    def test_midnight_end_reads_as_the_previous_day(self):
        self.assertEqual(self.until(at(2026, 12, 25, 0, 0)), "24 December")

    def test_2359_is_that_date(self):
        self.assertEqual(self.until(at(2026, 12, 24, 23, 59)), "24 December")

    def test_other_time_has_the_clock(self):
        self.assertEqual(self.until(at(2026, 12, 24, 18, 0)), "24 December, 18:00")
        self.assertEqual(self.until(at(2026, 12, 4, 9, 5)), "4 December, 09:05")

    def test_today_and_the_coming_midnight(self):
        self.assertEqual(self.until(at(2026, 12, 10, 18, 0)), "18:00 today")
        self.assertEqual(self.until(at(2026, 12, 11, 0, 0)), "midnight tonight")

    def test_london_time_in_summer(self):
        utc_end = datetime(2026, 7, 24, 23, 0, tzinfo=ZoneInfo("UTC"))  # 00:00 BST on the 25th
        self.assertEqual(sales.sale_until(bar(utc_end), at(2026, 7, 1, 12, 0)), "24 July")

    def test_months(self):
        self.assertEqual(sales.months_phrase(1), "for your first month")
        self.assertEqual(sales.months_phrase(3), "for your first 3 months")

    def test_upcoming_from(self):
        self.assertEqual(sales.sale_from(bar(at(2026, 12, 25), starts=at(2026, 12, 1, 0, 0)), at(2026, 11, 20)), "1 December")
        self.assertEqual(sales.sale_from(bar(at(2026, 12, 25)), at(2026, 11, 20)), "1 December, 09:00")
        data = sales.mention(bar(at(2026, 12, 25)), at(2026, 11, 20))
        self.assertTrue(data["upcoming"])
        self.assertFalse(sales.mention(bar(at(2026, 12, 25)), at(2026, 12, 2))["upcoming"])
        self.assertIsNone(sales.mention(None))


class MentionPageTests(TestCase):
    def setUp(self):
        seed_all()
        open_memberships()

    def test_present_during_a_live_sale(self):
        make_sale(start=-1, end=80, plans=("tier-2", "tier-3"))
        spa = self.client.get("/the-spa/").content.decode()
        self.assertIn("sale-mention--eyebrow", spa)
        self.assertIn("Christmas sale", spa)
        self.assertIn("20% off Tier 2 and Tier 3", spa)
        self.assertIn("until ", spa)
        self.assertIn('<span class="sr-only">, </span>', spa)
        start = spa.index("sale-mention--eyebrow")
        self.assertNotIn("£", spa[start:spa.index("</p>", start)])  # no prices before the email gate
        for path in ("/", "/book/"):
            html = self.client.get(path).content.decode()
            self.assertIn("sale-mention--note", html, path)
            self.assertIn("register by ", html, path)
            self.assertIn("to keep 20% off Tier 2 and Tier 3 for your first 3 months.", html, path)
            self.assertIn('class="mark-glyph" aria-hidden="true"', html[html.index("sale-mention--note"):], path)

    def test_one_month_wording_on_the_note(self):
        make_sale(start=-1, end=80, months=1)
        self.assertIn("for your first month.", self.client.get("/book/").content.decode())

    def test_absent_without_a_sale_ended_and_elsewhere(self):
        for path in ("/", "/the-spa/", "/book/"):
            self.assertNotIn("sale-mention", self.client.get(path).content.decode(), path)
        make_sale(start=-3, end=-1, name="Over")
        self.assertNotIn("sale-mention", self.client.get("/book/").content.decode())
        make_sale(start=-1, end=80, name="Live")
        for path in ("/visit/", "/memberships/", "/gold-card/", "/tour/", "/login/"):
            self.assertNotIn("sale-mention", self.client.get(path).content.decode(), path)

    def test_preview_of_an_upcoming_sale_shows_from_and_note(self):
        sale = make_sale(start=24, end=100)
        self.client.post("/sale-preview/", {"token": sales.preview_token(sale), "next": "/"})
        spa = self.client.get("/the-spa/").content.decode()
        self.assertIn("sale-mention--eyebrow", spa)
        self.assertIn("from ", spa[spa.index("sale-mention-when"):spa.index("sale-mention-when") + 100])
        self.assertNotIn("until", spa[spa.index("sale-mention-when"):spa.index("sale-mention-when") + 100])
        self.assertIn("sale-mention--note", self.client.get("/book/").content.decode())

    def test_partial_renders_nothing_without_a_sale(self):
        out = Template('{% include "common/_sale_mention.html" with kind="note" %}').render(Context({"sale_bar": None}))
        self.assertEqual(out.strip(), "")


class JourneyResultLineTests(TestCase):
    def setUp(self):
        seed_all()
        open_memberships()

    def answers(self):
        return dict(time=["evening"], frequency="two_three", facilities=["gym"], industry="tech")  # suggests Tier 2

    def test_line_only_when_the_suggested_plan_is_in_a_live_sale(self):
        self.assertIsNone(engine.complete(make_session(**self.answers()))["suggested"]["sale_line"])
        make_sale(start=-1, end=80, plans=("tier-2",))
        line = engine.complete(make_session(**self.answers()))["suggested"]["sale_line"]
        self.assertRegex(line, r"^Register during the Christmas sale and keep £\d+(\.\d\d)? a month for your first 3 months\.$")
        self.assertEqual(engine.preview(make_session(**self.answers()))["suggested"]["sale_line"], line)

    def test_none_when_the_plan_is_not_in_the_sale_and_never_for_a_preview(self):
        make_sale(start=-1, end=80, plans=("tier-3",))
        self.assertIsNone(engine.complete(make_session(**self.answers()))["suggested"]["sale_line"])

    def test_an_upcoming_sale_gives_no_line(self):
        make_sale(start=100, end=200, plans=("tier-2",))  # a preview would show it on the bar; the result never promises it
        self.assertIsNone(engine.complete(make_session(**self.answers()))["suggested"]["sale_line"])

    def test_matches_the_register_screen_and_single_visit_says_a_visit(self):
        make_sale(start=-1, end=80, plans=("tier-2", "single-visit"), months=1)
        offer = sales.register_offer()
        line = engine.complete(make_session(**self.answers()))["suggested"]["sale_line"]
        self.assertEqual(line, sales.register_line(offer, "tier-2"))
        self.assertIn("a month for your first month.", line)
        visit = sales.register_line(offer, "single-visit")
        self.assertIn(" a visit for your first month.", visit)
        page = self.client.get("/register/").content.decode()
        self.assertIn(line, page)  # the Register plan card says the same words
