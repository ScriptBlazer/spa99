"""The WhatsApp short link /whatsapp/: redirect, fallback, aggregate counting, bots, the source allowlist. No network."""
from datetime import timedelta

from django.test import Client, TestCase
from django.utils import timezone

from pages import clicks
from pages.models import LinkClickDay
from plans.models import SiteSettings

URL = "https://wa.me/447530117902"
BROWSER = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) AppleWebKit/605.1.15 Safari/604.1"


class WhatsappLinkTests(TestCase):
    def setUp(self):
        SiteSettings.load()
        SiteSettings.objects.update(discount_contact_url=URL)
        self.client = Client(HTTP_USER_AGENT=BROWSER)

    def total(self, **filters):
        return sum(LinkClickDay.objects.filter(**filters).values_list("count", flat=True))

    def test_it_redirects_to_the_link_and_counts_the_click(self):
        response = self.client.get("/whatsapp/?from=register")
        self.assertEqual((response.status_code, response["Location"]), (302, URL))
        self.assertEqual(self.total(key="whatsapp", source="register", day=timezone.localdate()), 1)

    def test_a_blank_link_falls_back_to_the_visit_page_and_still_counts(self):
        SiteSettings.objects.update(discount_contact_url="")
        response = self.client.get("/whatsapp/")
        self.assertEqual((response.status_code, response["Location"]), (302, "/visit/"))
        self.assertEqual(self.total(), 1)

    def test_the_count_goes_up_by_one_each_time_in_one_row(self):
        for _ in range(3):
            self.client.get("/whatsapp/?from=chat")
        self.assertEqual(LinkClickDay.objects.count(), 1)
        self.assertEqual(LinkClickDay.objects.get().count, 3)
        clicks.increment("whatsapp", "chat", day=timezone.localdate() - timedelta(days=1))  # another day: its own row
        self.assertEqual(LinkClickDay.objects.count(), 2)

    def test_bots_are_redirected_but_not_counted(self):
        for agent in ("", "curl/8.0", "python-requests/2.31", "facebookexternalhit/1.1", "WhatsApp/2.23", "Googlebot/2.1", "SomeCrawler", "Spider-X", "Slack link preview", "WhatsApp-Preview"):
            response = Client(HTTP_USER_AGENT=agent).get("/whatsapp/?from=plans")
            self.assertEqual(response["Location"], URL)
        self.assertEqual(LinkClickDay.objects.count(), 0)

    def test_the_source_is_the_allowlisted_key_else_our_own_referring_path_else_direct(self):
        self.client.get("/whatsapp/?from=membership")
        self.client.get("/whatsapp/?from=<script>")  # not allowed: counted as other
        self.client.get("/whatsapp/", HTTP_REFERER="http://testserver/register/")
        self.client.get("/whatsapp/", HTTP_REFERER="https://elsewhere.example/page")
        self.client.get("/whatsapp/")
        self.client.get("/whatsapp/", HTTP_REFERER="http://testserver/" + "x" * 300)  # a made-up path is "other", never stored
        self.client.get("/whatsapp/", HTTP_REFERER="http://testserver/memberships/")
        got = dict(LinkClickDay.objects.values_list("source", "count"))
        self.assertEqual(got["other"], 2)
        self.assertEqual(got["register"], 1)
        self.assertEqual(got["membership"], 2)
        self.assertEqual(got["direct"], 2)
        self.assertTrue(set(got) <= {"membership", "other", "register", "direct"})
        self.assertNotIn("elsewhere", " ".join(got))

    def test_the_summary_totals_and_by_source(self):
        today = timezone.localdate()
        clicks.increment("whatsapp", "register", today)
        clicks.increment("whatsapp", "chat", today - timedelta(days=3))
        clicks.increment("whatsapp", "chat", today - timedelta(days=20))
        clicks.increment("whatsapp", "chat", today - timedelta(days=60))
        summary = clicks.summary()
        self.assertEqual((summary["today"], summary["week"], summary["month"], summary["all"]), (1, 2, 3, 4))
        self.assertEqual(len(summary["by_day"]), 30)
        self.assertEqual(summary["by_source"][0], {"source": "chat", "count": 3})

    def test_the_site_links_use_the_short_address(self):
        from pages.links import short_url

        self.assertEqual(short_url("chat"), "/whatsapp/?from=chat")
        self.assertEqual(short_url("anything"), "/whatsapp/?from=other")
        SiteSettings.objects.update(discount_contact_url="")
        self.assertEqual(short_url("chat"), "")

    def test_by_source_is_capped_and_robots_hides_the_link(self):
        for i in range(25):
            LinkClickDay.objects.create(key="whatsapp", day=timezone.localdate(), source=f"s{i}", count=1)
        self.assertEqual(len(clicks.summary()["by_source"]), 20)
        self.assertContains(self.client.get("/robots.txt"), "Disallow: /whatsapp/")


class WhatsappMessageTests(TestCase):
    """?msg= pre-fills the message from an allowlist (2026-10-29): unknown keys are ignored, nothing typed is ever forwarded."""

    def setUp(self):
        SiteSettings.load()
        SiteSettings.objects.update(discount_contact_url=URL)
        self.client = Client(HTTP_USER_AGENT=BROWSER)

    def test_gold_business_adds_the_encoded_text_and_counts_under_gold(self):
        response = self.client.get("/whatsapp/?from=gold&msg=gold_business")
        self.assertEqual(response["Location"], URL + "?text=Hi%2C%20I%27ve%20just%20applied%20for%20the%20Spa%2099%20Gold%20Card%20and%20I%27m%20happy%20to%20do%20business%20with%20BML.")
        self.assertEqual(sum(LinkClickDay.objects.filter(source="gold").values_list("count", flat=True)), 1)

    def test_unknown_keys_and_free_text_are_ignored(self):
        for query in ("msg=nope", "msg=Hello%20there", "msg=", "msg=__class__"):
            self.assertEqual(self.client.get(f"/whatsapp/?from=gold&{query}")["Location"], URL, query)

    def test_an_existing_query_is_kept_and_a_text_of_its_own_wins(self):
        SiteSettings.objects.update(discount_contact_url="https://api.whatsapp.com/send?phone=447530117902")
        self.assertTrue(self.client.get("/whatsapp/?msg=gold_business")["Location"].startswith("https://api.whatsapp.com/send?phone=447530117902&text=Hi%2C"))
        SiteSettings.objects.update(discount_contact_url=URL + "?text=Hello")
        self.assertEqual(self.client.get("/whatsapp/?msg=gold_business")["Location"], URL + "?text=Hello")

    def test_a_blank_link_still_goes_to_visit_without_a_message(self):
        SiteSettings.objects.update(discount_contact_url="")
        self.assertEqual(self.client.get("/whatsapp/?from=gold&msg=gold_business")["Location"], "/visit/")
