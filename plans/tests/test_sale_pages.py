"""Sales on the public pages: the bar, the sale lines under prices, the end-preview link, no bar on reduced and member pages."""
from django.test import TestCase

from plans import sales
from plans.management.commands.seed_phase1 import seed_all
from plans.tests.helpers import open_memberships
from plans.tests.test_sales import make_sale


class SalePageTests(TestCase):
    def setUp(self):
        seed_all()
        open_memberships()

    def test_no_sale_no_bar(self):
        html = self.client.get("/").content.decode()
        self.assertNotIn("data-sale-bar", html)
        self.assertNotIn("has-sale", html)

    def test_strip_on_other_pages_band_on_home_and_memberships(self):
        make_sale(start=-1, end=80)
        html = self.client.get("/the-spa/").content.decode()
        self.assertIn("data-sale-bar", html)
        self.assertNotIn("data-sale-band", html)
        self.assertLess(html.index("skip-link"), html.index("data-sale-bar"))
        self.assertLess(html.index("data-sale-bar"), html.index("site-header"))
        for path in ("/", "/memberships/"):
            html = self.client.get(path).content.decode()
            self.assertIn("data-sale-band", html, path)
            self.assertNotIn("data-sale-bar", html, path)
            self.assertNotIn("has-sale", html, path)
            self.assertNotIn("data-sale-close", html, path)

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

    def test_reduced_pages_and_the_tour_have_no_bar(self):
        make_sale(start=-1, end=80)
        for path in ("/journey/", "/tour/"):
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
