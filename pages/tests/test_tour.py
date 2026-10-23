"""Virtual tour (server side): routes, the config the 3D script reads, nav link, and the create-if-missing rows."""
import json
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from content.models import Page, Section
from pages import services
from plans.management.commands.seed_phase1 import seed_all
from plans.models import Facility

ROOMS = ["lounge", "gym", "kitchenette", "massage-room", "dry-sauna", "wet-sauna", "relaxing-zone"]


class TourTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_every_toured_room_renders(self):
        self.assertEqual(reverse("tour"), "/tour/")
        for slug in ROOMS:
            url = services.tour_url(slug)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            self.assertContains(response, 'id="tour-config"')
            self.assertContains(response, 'aria-current="page"', count=3)  # room list, header, menu
            self.assertContains(response, "<title>")

    def test_lounge_slug_redirects_and_other_slugs_404(self):
        response = self.client.get("/tour/lounge/")
        self.assertRedirects(response, "/tour/", status_code=301)
        for slug in ("nope", "cold-plunge", "showers"):
            self.assertEqual(self.client.get(f"/tour/{slug}/").status_code, 404, slug)

    def test_hidden_room_leaves_the_tour(self):
        Facility.objects.filter(slug="gym").update(visible=False)
        self.assertEqual(self.client.get("/tour/gym/").status_code, 404)
        self.assertEqual([r["slug"] for r in services.tour_rooms()], [r for r in ROOMS if r != "gym"])

    def test_config_has_every_room_in_order(self):
        response = self.client.get("/tour/dry-sauna/")
        config = json.loads(response.content.decode().split('id="tour-config" type="application/json">')[1].split("</script>")[0])
        self.assertEqual(config["current"], "dry-sauna")
        self.assertEqual([r["slug"] for r in config["rooms"]], ROOMS)
        dry = config["rooms"][4]
        self.assertEqual((dry["name"], dry["order"], dry["tour_url"], dry["spa_url"]),
                         ("Dry sauna", 5, "/tour/dry-sauna/", "/the-spa/#dry-sauna"))
        self.assertEqual(dry["line"], "Pale wood, low light and a slow, dry heat.")
        self.assertTrue(dry["photo"].endswith(".jpg") or dry["photo"].endswith(".webp"))
        self.assertTrue(dry["alt"])
        lounge = config["rooms"][0]
        self.assertEqual((lounge["name"], lounge["tour_url"], lounge["spa_url"]), ("Lounge", "/tour/", "/the-spa/"))
        self.assertEqual(config["copy"]["hint"]["body"], "Drag to look around.")

    def test_edited_row_wins_and_blank_line_falls_back_to_the_facility(self):
        Section.objects.filter(page__key="tour", key="room_gym").update(heading="Training room", body="")
        gym = next(r for r in services.tour_rooms() if r["slug"] == "gym")
        self.assertEqual((gym["name"], gym["line"]), ("Training room", Facility.objects.get(slug="gym").short_line))

    def test_nav_and_spa_page_link_to_the_tour(self):
        home = self.client.get("/").content.decode()
        self.assertIn('href="/tour/"', home)
        self.assertIn("Virtual tour", home)
        spa = self.client.get("/the-spa/").content.decode()
        for slug in ROOMS[1:]:
            self.assertIn(f'href="/tour/{slug}/"', spa)
        self.assertNotIn('href="/tour/cold-plunge/"', spa)


class TourBackfillTests(TestCase):
    def run_backfill(self, *args):
        out = StringIO()
        call_command("backfill_site_data", *args, stdout=out)
        return out.getvalue()

    def test_creates_rows_only_if_missing(self):
        seed_all()
        Page.objects.filter(key="tour").delete()
        Section.objects.filter(page__key="spa", key="tour_link").delete()
        self.assertIn("Would change", self.run_backfill("--dry-run"))
        self.assertFalse(Page.objects.filter(key="tour").exists())
        self.run_backfill()
        self.assertEqual(Section.objects.filter(page__key="tour").count(), 11)
        self.assertTrue(Section.objects.filter(page__key="spa", key="tour_link").exists())
        Section.objects.filter(page__key="tour", key="hint").update(body="Look around.")
        self.run_backfill()
        self.assertEqual(Section.objects.get(page__key="tour", key="hint").body, "Look around.")
        self.assertEqual(Section.objects.filter(page__key="tour").count(), 11)
