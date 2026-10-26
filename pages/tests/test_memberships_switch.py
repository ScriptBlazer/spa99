"""2026-10-26: the Memberships page is hidden until opening (SiteSettings.memberships_public). The journey is the way in."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from plans.management.commands.seed_phase1 import seed_all
from plans.models import SiteSettings
from plans.tests.helpers import make_team_member, open_memberships
from plans.tests.test_sales import make_sale


class MembershipsSwitchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_it_is_off_by_default(self):
        self.assertFalse(SiteSettings.load().memberships_public)

    def test_hidden_the_page_sends_visitors_to_the_journey_and_the_links_disappear(self):
        response = self.client.get("/memberships/")
        self.assertEqual((response.status_code, response["Location"]), (302, "/journey/"))
        html = self.client.get("/visit/").content.decode()
        self.assertNotIn('href="/memberships/"', html)  # desktop nav, mobile menu and footer
        self.assertIn('href="/gold-card/"', html)  # the rest of the nav is still there
        self.assertNotIn("/memberships/", self.client.get("/sitemap.xml").content.decode())

    def test_the_sale_bar_points_at_the_journey_while_hidden(self):
        make_sale(start=-1, end=80)
        html = self.client.get("/").content.decode()
        self.assertIn("data-sale-bar", html)
        self.assertIn('class="sale-bar-link" href="/journey/"', html)
        open_memberships()
        self.assertIn('class="sale-bar-link" href="/memberships/#plans"', self.client.get("/").content.decode())

    def test_team_members_can_still_look_and_see_the_link(self):
        self.client.force_login(make_team_member("office@example.com"))
        self.assertEqual(self.client.get("/memberships/").status_code, 200)
        self.assertIn('href="/memberships/"', self.client.get("/visit/").content.decode())

    def test_public_once_switched_on(self):
        open_memberships()
        self.assertEqual(self.client.get("/memberships/").status_code, 200)
        self.assertIn('href="/memberships/"', self.client.get("/visit/").content.decode())

    def test_register_still_works_for_someone_who_came_through_the_journey(self):
        self.assertEqual(self.client.get("/register/?plan=tier-2").status_code, 200)


class NoPricesBeforeTheGateTests(TestCase):
    """Barry, 2026-10-26: no prices on pages reachable without leaving an email, while Memberships is hidden."""

    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_spa_and_home_show_no_price_while_hidden(self):
        spa = self.client.get("/the-spa/").content.decode()
        self.assertNotIn("£", spa)
        self.assertIn("Tailor your membership", spa)
        home = self.client.get("/").content.decode()
        home = home.replace("*An annual admin fee of £199 + VAT applies.", "")  # the Gold "free*" footnote is the one allowed figure (2026-10-26)
        self.assertNotIn("&pound;", home)
        self.assertNotIn("£", home)

    def test_spa_and_home_show_the_prices_once_public(self):
        open_memberships()
        self.assertIn("Memberships from £299 a month, £358.80 inc VAT.", self.client.get("/the-spa/").content.decode())
        self.assertIn("&pound;299", self.client.get("/").content.decode())


class EmailUnlocksMembershipsTests(TestCase):
    """2026-10-26: once he has given his email at the journey gate, Memberships is open to him in that browser."""

    @classmethod
    def setUpTestData(cls):
        seed_all()

    def _journey_cookie(self, email):
        from journey import services as journey_services
        session = journey_services.create_session()
        if email:
            journey_services.save_lead(session, email, True)
        self.client.cookies[journey_services.COOKIE_NAME] = session.key

    def test_a_session_with_an_email_opens_the_page_and_the_links(self):
        self._journey_cookie("lead@example.com")
        self.assertEqual(self.client.get("/memberships/").status_code, 200)
        self.assertIn('href="/memberships/"', self.client.get("/visit/").content.decode())

    def test_a_session_without_an_email_is_still_sent_to_the_journey(self):
        self._journey_cookie("")
        self.assertEqual(self.client.get("/memberships/").status_code, 302)

    def test_passing_the_gate_unlocks_it_in_the_same_browser(self):
        import json
        self.assertEqual(self.client.get("/memberships/").status_code, 302)
        self.client.post("/journey/lead/", json.dumps({"email": "new@example.com", "consent": True}), content_type="application/json")
        self.assertEqual(self.client.get("/memberships/").status_code, 200)

    def test_a_signed_in_member_is_let_in(self):
        self.client.force_login(get_user_model().objects.create_user("m2@example.com", "x-Pass-123456"))
        self.assertEqual(self.client.get("/memberships/").status_code, 200)

    def test_the_journey_page_gives_the_result_its_memberships_link(self):
        html = self.client.get("/journey/").content.decode()
        self.assertIn('"membershipsPage": "/memberships/"', html)
        self.assertIn("Explore all memberships", html)
