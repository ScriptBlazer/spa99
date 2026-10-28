"""Sales on the public pages: the bar (always on, on every public page, not dismissible), the sale lines under prices, the preview link
end to end, no bar on reduced and member pages."""
import time
from unittest import mock

from django.test import Client, TestCase, override_settings

from plans import sales
from plans.management.commands.seed_phase1 import seed_all
from plans.tests.helpers import open_memberships
from plans.tests.test_sales import make_sale


PUBLIC_PAGES = ("/", "/the-spa/", "/tour/", "/memberships/", "/gold-card/", "/book/", "/visit/", "/register/", "/login/", "/privacy/", "/terms/")


class SalePageTests(TestCase):
    def setUp(self):
        seed_all()
        open_memberships()

    def test_no_sale_no_bar(self):
        html = self.client.get("/").content.decode()
        self.assertNotIn("data-sale-bar", html)
        self.assertNotIn("has-sale", html)

    def test_bar_is_on_top_of_every_public_page_and_cannot_be_dismissed(self):
        make_sale(start=-1, end=80)
        for path in PUBLIC_PAGES:
            html = self.client.get(path).content.decode()
            self.assertIn("data-sale-bar", html, path)
            self.assertIn('class="has-sale"', html, path)
            self.assertLess(html.index("skip-link"), html.index("data-sale-bar"), path)
            self.assertLess(html.index("data-sale-bar"), html.index("site-header"), path)
            for gone in ("data-sale-close", "sale-bar-close", "Hide the sale bar", "spa99.sale.dismissed", "sale-off"):
                self.assertNotIn(gone, html, (path, gone))

    def test_bar_and_band_together_on_home_and_memberships(self):
        make_sale(start=-1, end=80)
        for path in ("/", "/memberships/"):
            html = self.client.get(path).content.decode()
            self.assertIn("data-sale-bar", html, path)
            self.assertIn("data-sale-band", html, path)
        self.assertNotIn("data-sale-band", self.client.get("/the-spa/").content.decode())

    def test_bar_stops_after_the_end_and_while_upcoming(self):
        make_sale(start=-2, end=-1, name="Over")
        make_sale(start=24, end=48, name="Soon")
        for path in PUBLIC_PAGES:
            html = self.client.get(path).content.decode()
            self.assertNotIn("data-sale-bar", html, path)
            self.assertNotIn("has-sale", html, path)

    def test_bar_goes_when_the_sale_is_ended_now(self):
        sale = make_sale(start=-1, end=80)
        self.assertIn("data-sale-bar", self.client.get("/visit/").content.decode())
        sales.end_now(sale, None)
        self.assertNotIn("data-sale-bar", self.client.get("/visit/").content.decode())

    def test_the_bar_renders_the_countdown_for_no_js(self):
        make_sale(start=-1, end=26)
        html = self.client.get("/visit/").content.decode()
        self.assertRegex(html, r"data-sale-count>1d 0[0-3]h")
        make_sale_last_day = self.client.get("/visit/")  # same page again: still on
        self.assertContains(make_sale_last_day, "data-sale-bar")

    def test_band_text_and_lines_while_live(self):
        make_sale(start=-1, end=80)
        html = self.client.get("/memberships/").content.decode()
        self.assertIn("20% off Tier 2 and Tier 3.", html)
        self.assertIn("Keep it for your first 3 months.", html)
        self.assertIn("Choose your membership", html)
        self.assertIn("Christmas sale: £", html)
        self.assertIn("for your first 3 months", html)
        self.assertEqual(html.count('class="tier-sale"'), 2)
        self.assertLess(html.index('id="plans"'), html.index("data-sale-band"))
        self.assertLess(html.index("data-sale-band"), html.index('id="compare"'))
        home = self.client.get("/").content.decode()
        self.assertLess(home.index('data-scene="hero"'), home.index("data-sale-band"))
        self.assertLess(home.index("data-sale-band"), home.index('data-scene="ritual"'))

    def test_reduced_pages_have_no_bar(self):
        make_sale(start=-1, end=80)
        for path in ("/journey/",):
            response = self.client.get(path, follow=True)
            self.assertNotIn("data-sale-bar", response.content.decode(), path)

    def test_end_preview_link_clears_the_session_preview(self):
        sale = make_sale(start=48, end=72)
        self.client.get(f"/?sale_preview={sales.preview_token(sale)}")
        page = self.client.get("/").content.decode()
        self.assertIn("End preview", page)
        self.assertIn("Starts ", page)
        self.client.get("/?sale_preview=end")
        self.assertNotIn("data-sale-band", self.client.get("/").content.decode())


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "sale-preview-tests"}})
class PreviewFlowTests(TestCase):
    """The preview link end to end with the real (shared) cache, so the single use is really enforced."""

    def setUp(self):
        seed_all()
        open_memberships()
        from django.core.cache import cache
        cache.clear()
        self.sale = make_sale(start=48, end=72)
        self.link = f"/?sale_preview={sales.preview_token(self.sale)}"

    def test_first_open_sets_the_preview_for_that_browser_on_every_public_page(self):
        browser = Client()
        for path in PUBLIC_PAGES:
            self.assertNotIn("data-sale-bar", browser.get(path).content.decode(), path)  # nothing before the link
        page = browser.get(self.link).content.decode()
        self.assertIn("data-sale-bar", page)
        self.assertIn("End preview", page)
        for path in PUBLIC_PAGES:
            html = browser.get(path).content.decode()
            self.assertIn("data-sale-bar", html, path)
            self.assertIn("sale-bar-preview", html, path)
            self.assertNotIn("data-sale-close", html, path)

    def test_second_open_of_the_same_link_does_nothing(self):
        first, second = Client(), Client()
        first.get(self.link)
        self.assertNotIn("data-sale-bar", second.get(self.link).content.decode())  # spent: another browser gets nothing
        self.assertNotIn("data-sale-bar", second.get("/visit/").content.decode())
        self.assertIn("data-sale-bar", first.get(self.link).content.decode())  # the first browser keeps it, opening again changes nothing
        self.assertIn("data-sale-bar", first.get("/visit/").content.decode())

    def test_a_probe_does_not_spend_the_link(self):
        Client().head(self.link)
        browser = Client()
        self.assertIn("data-sale-bar", browser.get(self.link).content.decode())

    def test_end_preview_ends_it(self):
        browser = Client()
        browser.get(self.link)
        self.assertNotIn("data-sale-bar", browser.get("/visit/?sale_preview=end").content.decode())
        self.assertNotIn("data-sale-bar", browser.get("/").content.decode())

    def test_the_preview_lasts_an_hour(self):
        browser = Client()
        browser.get(self.link)
        with mock.patch("plans.sales.time.time", return_value=time.time() + sales.PREVIEW_SECONDS - 60):
            self.assertIn("data-sale-bar", browser.get("/visit/").content.decode())
        with mock.patch("plans.sales.time.time", return_value=time.time() + sales.PREVIEW_SECONDS + 60):
            self.assertNotIn("data-sale-bar", browser.get("/visit/").content.decode())

    def test_an_expired_link_does_nothing(self):
        with mock.patch("django.core.signing.time.time", return_value=time.time() + sales.PREVIEW_SECONDS + 60):
            self.assertNotIn("data-sale-bar", Client().get(self.link).content.decode())

    def test_an_ended_sale_cannot_be_previewed_and_a_live_sale_shows_for_everyone(self):
        sales.end_now(self.sale, None)
        self.assertNotIn("data-sale-bar", Client().get(self.link).content.decode())
        make_sale(start=-1, end=5, name="Live now")
        self.assertIn("Live now", Client().get("/visit/").content.decode())
