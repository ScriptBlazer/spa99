"""Sales on the public pages: the bar, the sale lines under prices, the end-preview link, no bar on reduced and member pages."""
from django.test import TestCase

from plans import sales
from plans.management.commands.seed_phase1 import seed_all
from plans.tests.test_sales import make_sale


class SalePageTests(TestCase):
    def setUp(self):
        seed_all()

    def test_no_sale_no_bar(self):
        html = self.client.get("/").content.decode()
        self.assertNotIn("data-sale-bar", html)
        self.assertNotIn("has-sale", html)

    def test_bar_and_lines_while_live(self):
        make_sale(start=-1, end=80)
        html = self.client.get("/memberships/").content.decode()
        self.assertIn("data-sale-bar", html)
        self.assertIn("20% off", html)
        self.assertIn("Tier 2 and Tier 3", html)
        self.assertIn("Christmas sale: £", html)
        self.assertIn("for your first 3 months", html)
        self.assertEqual(html.count('class="tier-sale"'), 2)
        self.assertLess(html.index("skip-link"), html.index("data-sale-bar"))
        self.assertLess(html.index("data-sale-bar"), html.index("site-header"))

    def test_reduced_pages_and_the_tour_have_no_bar(self):
        make_sale(start=-1, end=80)
        for path in ("/journey/", "/tour/"):
            response = self.client.get(path, follow=True)
            self.assertNotIn("data-sale-bar", response.content.decode(), path)

    def test_end_preview_link_clears_the_session_preview(self):
        sale = make_sale(start=48, end=72)
        self.client.get(f"/?sale_preview={sales.preview_token(sale)}")
        self.assertIn("End preview", self.client.get("/").content.decode())
        self.client.get("/?sale_preview=end")
        self.assertNotIn("data-sale-bar", self.client.get("/").content.decode())
