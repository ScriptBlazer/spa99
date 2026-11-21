"""Office: Analytics > Visitors data, Live now and the link maker's QR code (docs/features/analytics.md A8, A9)."""
from unittest import mock
from urllib.parse import quote

from django.db import connection
from django.http import HttpResponse
from django.test import Client, RequestFactory
from django.test.utils import CaptureQueriesContext

from django.conf import settings

from common import geoip
from insights import campaigns, metrics, rollup, visitors
from insights.metrics import K
from insights.middleware import VisitorCounterMiddleware
from insights.models import OfficeSnapshot
from office import analytics_visitors, snapshots
from office.tests.test_office import OFFICE, OfficeTestCase, get, staff

IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def visit(path, agent, addr, query="", referer=""):
    extra = {"HTTP_USER_AGENT": agent, "HTTP_HOST": "localhost", "REMOTE_ADDR": addr}
    if referer:
        extra["HTTP_REFERER"] = referer
    request = RequestFactory().get(path + query, **extra)
    request.urlconf = "config.urls"
    VisitorCounterMiddleware(lambda r: HttpResponse("x", content_type="text/html"))(request)
    return request


class VisitorsDataTests(OfficeTestCase):
    def setUp(self):
        visitors.forget_salts()
        self.addCleanup(geoip.reset)
        reader = mock.Mock()
        reader.get.return_value = {"country": {"iso_code": "GB"}}
        geoip._state.update(loaded=True, reader=reader)
        self.viewer, self.office, self.admin = staff("Viewer", "v@example.com"), staff("Office", "o@example.com"), staff("Admin", "a@example.com")
        self.dev = staff("Developer", "d@example.com")  # Analytics > Visitors is Developer and up only for now

    def make_traffic(self):
        first = visit("/memberships/", IPHONE, "203.0.113.1", "?utm_source=flyer&utm_medium=print&utm_campaign=spring&utm_content=qr")
        visit("/gold-card/", IPHONE, "203.0.113.1")
        visitors.record_step(first, "registered")
        visit("/", CHROME, "203.0.113.2", referer="https://www.google.com/")
        rollup.run()

    def test_the_payload_has_the_figures_the_screens_need(self):
        self.make_traffic()
        data = get(self.dev, "/analytics/visitors/data/?range=7d").json()
        self.assertEqual((data["range"], data["granularity"], len(data["labels"]), len(data["previous_labels"])), ("7d", "day", 7, 7))
        self.assertEqual(data["visitors_since"], metrics.day().isoformat())
        overview = data["overview"]
        self.assertEqual((overview["visitors"]["value"], overview["visits"]["value"], overview["pages_per_visit"]["value"], overview["bounce_rate_bp"]["value"]), (2, 2, 1.5, 5000))
        self.assertEqual(set(data["series"]), {"visitors", "visits", "pages_per_visit", "avg_visit_seconds", "bounce_rate_bp", "page_views"})
        self.assertEqual(len(data["series"]["visits"]["values"]), 7)
        self.assertEqual(data["series"]["visits"]["values"][-1], 2)
        self.assertEqual({d["dimension"]: d["value"] for d in data["devices"]}, {"mobile": 1, "desktop": 1, "tablet": 0})
        self.assertEqual((data["countries"][0]["dimension"], data["countries"][0]["label"], data["countries"][0]["value"]), ("gb", "United Kingdom", 2))
        self.assertEqual({c["channel"]: c["visits"] for c in data["channels"]}, {"campaign": 1, "search": 1, "social": 0, "email": 0, "referral": 0, "direct": 0})
        campaign = data["campaigns"][0]
        self.assertEqual((campaign["campaign"], campaign["placement"], campaign["visits"], campaign["steps"]["registered"]), ("spring", "Flyer QR", 1, 1))
        self.assertEqual(data["pages"]["first"][0]["visits"], 1)
        self.assertEqual(len(data["heatmap"]["rows"]), 7)
        self.assertEqual(len(data["heatmap"]["rows"][0]), 24)
        self.assertEqual(data["heatmap"]["total"], 2)
        self.assertIn("Not enough visits", data["sentences"]["busiest"])  # under 20 visits
        self.assertEqual(data["sentences"]["campaign"], "Top campaign: spring (1 visit).")
        self.assertEqual([b["bucket"] for b in data["visit_length"]], ["0-10s", "10-30s", "30s-1m", "1-3m", "3-10m", "10m+"])
        for key in ("browsers", "systems", "sources", "contact_taps", "geoip_available"):
            self.assertIn(key, data)

    def test_all_ranges_are_stored_and_a_missing_snapshot_is_an_empty_state(self):
        before = get(self.dev, "/analytics/visitors/data/?range=30d").json()
        self.assertTrue(before["updating"])
        self.assertEqual(before["overview"]["visits"]["value"], 0)
        self.make_traffic()
        self.assertEqual(set(OfficeSnapshot.objects.filter(page="visitors").values_list("range", flat=True)), {"7d", "30d", "90d", "all"})
        allrange = analytics_visitors.build("all", metrics.day())
        self.assertIsNone(allrange["overview"]["visits"]["previous"])  # All has no previous period
        self.assertEqual(allrange["previous_labels"], [])

    def test_endpoints_run_a_fixed_number_of_queries_whatever_the_data(self):
        paths = ["/analytics/visitors/data/?range=7d", "/analytics/visitors/data/?range=all", "/analytics/live.json"]

        def queries(path):
            client = Client(HTTP_HOST=OFFICE)
            client.force_login(self.dev)
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(client.get(path).status_code, 200)
            return len(ctx)
        empty = {p: queries(p) for p in paths}
        for i in range(5):
            visit("/memberships/", IPHONE, f"203.0.113.{10 + i}", f"?utm_source=s{i}&utm_campaign=c{i}")
        rollup.run()
        for path in paths:
            self.assertEqual(queries(path), empty[path], path)
        self.assertLessEqual(max(empty.values()), 12)

    def test_live_json_shape_and_developers_only(self):
        visit("/memberships/", IPHONE, "203.0.113.1")
        data = get(self.dev, "/analytics/live.json").json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["by_page"], [{"label": "memberships", "value": 1}])
        self.assertEqual(get(self.dev, "/analytics/live.json")["Cache-Control"].count("no-cache"), 1)
        self.assertEqual(get(None, "/analytics/live.json").status_code, 302)  # signed out: to the sign-in page
        nobody = staff(None, "nobody@example.com")
        self.assertEqual(get(nobody, "/analytics/live.json").status_code, 404)  # no team level: the address admits nothing
        self.assertEqual(get(nobody, "/analytics/visitors/data/").status_code, 404)

    def test_viewer_office_and_admin_are_refused_on_every_visitors_endpoint(self):
        link = campaigns.build_link("/memberships/", "flyer-qr", "spring", base=settings.SITE_URL)
        paths = ["/analytics/visitors/", "/analytics/visitors/data/", "/analytics/live.json", "/analytics/link.json?placement=email&name=x&page=home", "/analytics/qr.svg?url=" + quote(link, safe="")]
        for user in (self.viewer, self.office, self.admin):
            for path in paths:
                self.assertEqual(get(user, path).status_code, 403, path)  # the guard says 403 to a team level that is too low
        root = staff(None, "root@example.com", is_superuser=True)
        for path in paths:
            self.assertEqual(get(root, path).status_code, 200, path)

    def test_the_qr_code_is_for_our_own_addresses_only(self):
        link = campaigns.build_link("/memberships/", "flyer-qr", "spring", base=settings.SITE_URL)
        url = "/analytics/qr.svg?url=" + quote(link, safe="")
        ok = get(self.dev, url)
        self.assertEqual((ok.status_code, ok["Content-Type"]), (200, "image/svg+xml"))
        self.assertIn(b"<svg", ok.content)
        self.assertIn("no-cache", ok["Cache-Control"])
        for bad in ("http://[x", "https://evil.example/?x=1", "javascript:alert(1)", "", "/memberships/"):
            response = get(self.dev, "/analytics/qr.svg?url=" + quote(bad, safe=""))
            self.assertEqual(response.status_code, 400, bad)
