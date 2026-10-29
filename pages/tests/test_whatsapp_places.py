"""2026-10-29: the quiet WhatsApp line on the Memberships page, the journey result and the Visit page; the Tailor button in The spa hero."""
import json
import re
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from content.models import Section
from pages.models import LinkClickDay
from plans.management.commands.seed_phase1 import seed_all
from plans.models import SiteSettings
from plans.tests.helpers import open_memberships

URL = "https://wa.me/447441919990"
LINE = "Looking for a better rate?"


class WhatsappPlacesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        open_memberships()

    def set_url(self, url):
        SiteSettings.load()
        SiteSettings.objects.update(discount_contact_url=url)

    def journey_config(self):
        html = self.client.get("/journey/").content.decode()
        return json.loads(re.search(r'<script id="journey-config" type="application/json">(.*?)</script>', html, re.S).group(1))

    def test_memberships_shows_one_line_on_the_short_link_in_a_new_tab(self):
        self.set_url(URL)
        html = self.client.get("/memberships/").content.decode()
        self.assertEqual(html.count(LINE), 1)
        self.assertIn('href="/whatsapp/?from=memberships" target="_blank" rel="noopener noreferrer">WhatsApp us<span class="sr-only"> (opens in a new tab)</span>', html)
        self.assertNotIn("wa.me", html)

    def test_memberships_hides_the_line_when_blank(self):
        self.set_url("")
        self.assertNotIn(LINE, self.client.get("/memberships/").content.decode())

    def test_the_journey_result_gets_the_short_link_or_nothing(self):
        self.set_url(URL)
        self.assertEqual(self.journey_config()["whatsappUrl"], "/whatsapp/?from=journey")
        self.set_url("")
        self.assertEqual(self.journey_config()["whatsappUrl"], "")

    def test_visit_shows_whatsapp_next_to_the_email_when_set(self):
        self.set_url(URL)
        html = self.client.get("/visit/").content.decode()
        self.assertIn('href="/whatsapp/?from=visit" target="_blank" rel="noopener noreferrer">WhatsApp<span class="sr-only"> (opens in a new tab)</span>', html)
        self.set_url("")
        self.assertNotIn("/whatsapp/", self.client.get("/visit/").content.decode())

    def test_the_new_keys_are_counted_under_their_own_name(self):
        self.set_url(URL)
        agent = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) AppleWebKit/605.1.15 Safari/604.1"
        for key in ("memberships", "journey", "visit"):
            self.client.get(f"/whatsapp/?from={key}", HTTP_USER_AGENT=agent)
        got = dict(LinkClickDay.objects.filter(day=timezone.localdate()).values_list("source", "count"))
        self.assertEqual(got, {"memberships": 1, "journey": 1, "visit": 1})


class SpaHeroButtonTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_the_hero_has_the_tailor_button_and_the_bottom_one_stays(self):
        html = self.client.get("/the-spa/").content.decode()
        self.assertEqual(html.count("Tailor your membership"), 2)
        hero = html.split('class="door-chips"')[0]
        self.assertIn('class="btn btn-primary btn-block-phone" href="/journey/">Tailor your membership', hero)

    def test_backfill_fills_an_empty_hero_button_and_leaves_an_edited_one(self):
        Section.objects.filter(page__key="spa", key="intro").update(cta_label="", cta_url="")
        call_command("backfill_site_data", stdout=StringIO())
        intro = Section.objects.get(page__key="spa", key="intro")
        self.assertEqual((intro.cta_label, intro.cta_url), ("Tailor your membership", "/journey/"))
        Section.objects.filter(page__key="spa", key="intro").update(cta_label="Find yours")
        call_command("backfill_site_data", stdout=StringIO())
        self.assertEqual(Section.objects.get(page__key="spa", key="intro").cta_label, "Find yours")
