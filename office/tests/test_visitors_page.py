"""Office: the Analytics > Visitors page and the link maker's address endpoint (docs/features/analytics-design.md)."""
from django.db import connection
from django.test.utils import CaptureQueriesContext
from unittest import mock

from insights import campaigns, metrics, rollup
from insights.metrics import K
from office import analytics_visitors, snapshots, visitors_page
from office.tests.test_office import OfficeTestCase, get, staff

LINK = "/analytics/link.json"


def payload(**over):
    """An empty Visitors payload with some figures set (what the page shapes)."""
    data = analytics_visitors.empty("30d", "all")
    data.update(over)
    return data


class VisitorsPageTests(OfficeTestCase):
    def setUp(self):
        self.viewer, self.office, self.admin = staff("Viewer", "v@example.com"), staff("Office", "o@example.com"), staff("Admin", "a@example.com")
        self.dev, self.root = staff("Developer", "d@example.com"), staff(None, "root@example.com", is_superuser=True)

    def test_the_page_renders_for_developer_and_superuser_with_the_sub_nav_and_every_card(self):
        for user in (self.dev, self.root):
            response = get(user, "/analytics/visitors/")
            self.assertEqual(response.status_code, 200)
            html = response.content.decode()
            self.assertIn('aria-label="Analytics"', html)
            self.assertEqual(html.count('aria-current="page"'), 2)  # the Analytics rail item and the Visitors link
            for title in ("On the site now", "Overview", "Where visits come from", "Campaigns", "Pages", "Contact taps", "What people use", "Countries", "How long visits last", "When people visit"):
                self.assertIn(title, html)
            self.assertIn("Updating…", html)  # no snapshot yet: empty states, not a blank page
            self.assertIn("No visits in this range yet.", html)

    def test_the_developer_has_the_link_maker(self):
        html = get(self.dev, "/analytics/visitors/").content.decode()
        self.assertIn("Make a campaign link", html)
        self.assertIn("data-linkmaker", html)

    def test_the_journey_page_shows_visitors_to_developer_and_up_only(self):
        for user in (self.dev, self.root):
            html = get(user, "/analytics/").content.decode()
            self.assertIn("See Visitors", html)
            self.assertIn('href="/analytics/visitors/"', html)
            self.assertIn('aria-label="Analytics"', html)
            self.assertNotIn("Top pages", html)
        for user in (self.viewer, self.office, self.admin):
            response = get(user, "/analytics/")
            self.assertEqual(response.status_code, 200)
            html = response.content.decode()
            self.assertNotIn("See Visitors", html)
            self.assertNotIn('aria-label="Analytics"', html)
            self.assertNotIn("/analytics/visitors/", html)

    def test_the_range_is_shared_between_the_two_sub_pages(self):
        get(self.dev, "/analytics/?range=7d")  # remembered in the session
        client_get = get(self.dev, "/analytics/visitors/?range=90d")
        self.assertIn('value="90d" checked', client_get.content.decode())

    def test_the_page_runs_a_fixed_number_of_queries(self):
        def count():
            with CaptureQueriesContext(connection) as queries:
                self.assertEqual(get(self.dev, "/analytics/visitors/").status_code, 200)
            return len(queries)
        empty = count()
        for day in range(1, 6):
            metrics.count(K.VISITS, "", 20 * day, counter=False)
            metrics.count(K.CAMPAIGN_VISITS, f"flyer|print|c{day}|qr", 5, counter=False)
            metrics.count(K.ENTRY_PAGES, f"page{day}", 3, counter=False)
        snapshots.build_everything()
        self.assertEqual(count(), empty)  # data does not add queries


class LinkEndpointTests(OfficeTestCase):
    def setUp(self):
        self.dev = staff("Developer", "d@example.com")

    def test_a_developer_gets_the_address_from_build_link(self):
        query = "?placement=flyer-qr&name=Spring%20open%20day!&page=memberships"
        data = get(self.dev, LINK + query).json()
        self.assertEqual(data["name"], "spring-open-day")
        self.assertEqual(data["url"], campaigns.build_link("/memberships/", "flyer-qr", "Spring open day!", base=__import__("django.conf", fromlist=["settings"]).settings.SITE_URL))
        self.assertIn("utm_source=flyer&utm_medium=print&utm_campaign=spring-open-day&utm_content=qr", data["url"])

    def test_no_address_until_a_place_a_name_and_a_page_are_all_chosen(self):
        for query in ("?name=spring&page=home", "?placement=email&page=home", "?placement=email&name=spring", "?placement=nope&name=spring&page=home", "?placement=email&name=spring&page=elsewhere", "?placement=email&name=%21%21&page=home"):
            self.assertEqual(get(self.dev, LINK + query).json()["url"], "", query)
        self.assertEqual(get(self.dev, LINK + "?name=Spring%20Fair").json()["name"], "spring-fair")  # the cleaned name shows as you type

    def test_only_our_own_pages_can_be_picked(self):
        self.assertEqual(visitors_page.link_page_path("home"), "/")
        self.assertEqual(visitors_page.link_page_path("journey"), "/journey/")
        self.assertEqual(visitors_page.link_page_path("https://evil.example/"), "")


class VisitorsWordingTests(OfficeTestCase):
    def test_numbers_are_worded_the_way_the_brief_says(self):
        self.assertEqual([visitors_page.seconds_text(s) for s in (8, 45, 80, 120, 3900, 3600)], ["8s", "45s", "1m 20s", "2m", "1h 5m", "1h"])
        self.assertEqual([visitors_page.pct(bp) for bp in (0, 460, 4200, 1000)], ["0%", "4.6%", "42%", "10%"])
        self.assertEqual(visitors_page.plural(1, "visit"), "1 visit")
        self.assertEqual(visitors_page.plural(1204, "visit"), "1,204 visits")

    def tiles(self, visits, previous_visits, since, **extra):
        data = payload(visitors_since=since, previous_labels=["2026-10-01"], today="2026-11-21")
        o = data["overview"]
        o["visits"].update(value=visits, previous=previous_visits)
        o["pages_per_visit"].update(value=2.4, previous=2.1)
        o["avg_visit_seconds"].update(value=80, previous=68)
        o["bounce_rate_bp"].update(value=4200, previous=3800)
        return {t["key"]: t for t in visitors_page._tiles(data)}

    def test_a_rate_built_on_fewer_than_ten_visits_says_not_enough_yet(self):
        few, plenty = self.tiles(9, 50, "2026-09-01"), self.tiles(10, 50, "2026-09-01")
        for key in ("pages_per_visit", "avg_visit_seconds", "bounce_rate_bp"):
            self.assertEqual((few[key]["value"], few[key]["small"]), ("Not enough yet", True))
        self.assertEqual([plenty[k]["value"] for k in ("pages_per_visit", "avg_visit_seconds", "bounce_rate_bp")], ["2.4", "1m 20s", "42%"])

    def test_change_lines_are_plain_words_and_say_counting_since_before_the_start_date(self):
        tiles = self.tiles(100, 80, "2026-09-01")
        self.assertEqual(tiles["visits"]["change"], "+20 on the previous 30 days")
        self.assertEqual(tiles["pages_per_visit"]["change"], "+0.3 on the previous 30 days")
        self.assertEqual(tiles["avg_visit_seconds"]["change"], "12s longer than the previous 30 days")
        self.assertEqual(tiles["bounce_rate_bp"]["change"], "4 points higher than the previous 30 days")
        early = self.tiles(100, 80, "2026-11-03")  # the previous period starts before the first day of figures
        self.assertTrue(all(t["change"] == "Counting since 3 Nov" for t in early.values()))
        self.assertEqual(visitors_page.early_note(payload(visitors_since="2026-11-03", today="2026-11-21")), "Visitor figures started on 3 November 2026, so the first weeks will look thin.")
        self.assertTrue(visitors_page.early_note(payload(who="real", visitors_since="2026-11-03", today="2026-11-21")).startswith("Real visitor figures started on 3 November 2026"))
        self.assertEqual(visitors_page.early_note(payload(visitors_since="2026-09-01", today="2026-11-21")), "")

    def test_live_says_one_person_not_one_people_and_zero_calmly(self):
        live = {"count": 1, "by_page": [{"label": "the-spa", "value": 1}], "by_country": [{"label": "gb", "value": 1}], "by_device": [{"label": "mobile", "value": 1}], "by_channel": [{"label": "referral", "value": 1}]}
        context = visitors_page.live_context(live)
        self.assertEqual((context["count"], context["line"], context["empty"]), (1, "in the last 5 minutes", False))
        self.assertEqual([r["rows"][0]["label"] for r in context["lists"]], ["The spa", "United Kingdom", "Phone", "Other sites"])
        none = visitors_page.live_context({"count": 0, "by_page": [], "by_country": [], "by_device": [], "by_channel": []})
        self.assertEqual((none["line"], none["empty"]), ("No one on the site right now.", True))

    def test_the_heat_map_needs_twenty_visits_and_levels_split_at_quarters(self):
        rows = [[0] * 24 for _ in range(7)]
        rows[6][20] = 28
        rows[0][9] = 8
        rows[1][9] = 1
        heat = visitors_page._heat(payload(heatmap={"days": list(range(7)), "rows": rows, "max": 28, "total": 37}))
        levels = {(c["d"], c["h"]): c["level"] for c in heat["cells"]}
        self.assertTrue(heat["show"])
        self.assertEqual((levels[(6, 20)], levels[(0, 9)], levels[(1, 9)], levels[(3, 3)]), (4, 2, 1, 0))
        self.assertFalse(visitors_page._heat(payload())["show"])
        self.assertEqual(len(heat["cells"]), 168)

    def test_countries_show_when_there_is_data_even_if_geoip_is_unavailable(self):
        rows = [{"dimension": "GB", "label": "United Kingdom", "value": 12, "share_bp": 10000}]
        shown = visitors_page._countries(payload(countries=rows, geoip_available=False))
        self.assertEqual(len(shown["rows"]), 1)
        self.assertNotIn("not available", shown["summary"])
        self.assertEqual(shown["summary"], "Most visitors come from United Kingdom.")
        self.assertIn("not available", visitors_page._countries(payload(countries=[], geoip_available=True))["summary"])

    def test_early_pages_do_not_pretend_to_know_time_or_scroll(self):
        most = [{"page": "home", "label": "Home", "views": 40, "reported_views": 9, "avg_seconds": 80, "scroll": {}, "scrolled_half_bp": 6400},
                {"page": "visit", "label": "Visit", "views": 30, "reported_views": 10, "avg_seconds": 80, "scroll": {}, "scrolled_half_bp": 6400}]
        rows = visitors_page._pages(payload(pages={"most_viewed": most, "first": [], "last": []}))["most"]
        self.assertEqual((rows[0]["avg"], rows[0]["scroll"]), (None, None))
        self.assertEqual((rows[1]["avg"], rows[1]["scroll"], rows[1]["line"]), ("1m 20s", "64%", "1m 20s on the page, 64% scrolled halfway"))
