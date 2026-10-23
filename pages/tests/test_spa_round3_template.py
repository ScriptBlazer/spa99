"""Round 3 template logic on The spa and Home: which opener picture, the moments only when their picture exists, the kit, the tote, the Home slippers inset."""
import re
from unittest import mock

from django.test import TestCase

from content import images
from content.models import Section
from pages.templatetags import pages_media
from plans.management.commands.seed_phase1 import seed_all


NEW = ["robe", "robe-portrait", "towel-bench", "towel-bench-portrait", "slippers", "slippers-portrait", "toiletries", "towel-rail",
       "tote", "bottle-gym", "door-wide", "door-wide-portrait"]


def built(*names):
    """The image set for a test: the real manifest minus every round 3 render, plus exactly these names (copies of an existing
    entry). Each test states which images exist; the real manifest never decides. Nothing is written to disk."""
    base = images.manifest()
    kept = {k: v for k, v in base.items() if k not in NEW}
    return mock.patch.object(images, "manifest", lambda: {**kept, **{n: dict(base["dry-sauna"]) for n in names}})


class SpaRound3TemplateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def spa(self):
        return self.client.get("/the-spa/").content.decode()

    def test_without_the_new_pictures_the_page_has_no_holes(self):
        with built():
            html = self.spa()
        self.assertIn('data-opener="door-gold"', html)  # the robe is not built yet: the old door stands in
        for hook in ("sp-moment", "sp-tote", "sp-detail", "home-slippers"):
            self.assertNotIn(hook, html)
        self.assertEqual(html.count('class="kit-item"'), 4)  # the kit keeps its labels on swan tiles
        self.assertEqual(html.count("data-opener-line"), 4)
        self.assertNotIn("Eight spaces, one quiet visit", html)

    def test_robe_opener_with_a_phone_picture(self):
        with built("robe", "robe-portrait"):
            html = self.spa()
        self.assertIn('data-opener="robe" data-portrait', html)
        self.assertIn("robe-portrait-480.webp", html)
        self.assertIn("A white robe with the gold swan hanging on a bronze hook", html)
        self.assertEqual(len(re.findall(r'rel="preload" as="image"', html)), 2)  # desktop and phone, never both on one screen

    def test_moments_appear_in_their_places_and_only_with_a_picture(self):
        with built("towel-bench", "toiletries", "towel-rail", "slippers", "tote", "bottle-gym"):
            html = self.spa()
        order = [m for m in re.findall(r'id="(dry-sauna|tiles-title|gym|relaxing-zone|how-title)"|sp-moment--(towel|shower|slippers)', html)]
        flat = [a or b for a, b in order]
        self.assertEqual(flat[:3], ["towel", "dry-sauna", "tiles-title"])
        self.assertLess(flat.index("shower"), flat.index("relaxing-zone"))
        self.assertLess(flat.index("slippers"), flat.index("gym"))
        self.assertIn('class="scene sp-band sp-band--tote', html)
        self.assertIn("sp-detail", html)  # the gym's bottle inset
        with built("towel-rail"):
            html = self.spa()
        self.assertEqual((html.count("sp-pair-a"), html.count("sp-pair-b")), (0, 1))  # the shower pair stands on one picture
        self.assertNotIn("sp-moment--towel", html)

    def test_turning_a_moment_off_in_the_admin_removes_it(self):
        Section.objects.filter(page__key="spa", key="moment_slippers").update(heading="")
        with built("slippers", "towel-bench"):
            html = self.spa()
        self.assertNotIn("sp-moment--slippers", html)
        self.assertIn("sp-moment--towel", html)

    def test_door_switch_plays_the_video_only_when_its_files_exist(self):
        Section.objects.filter(page__key="spa", key="opener_image").update(body="door-wide")
        with built("door-wide"):
            self.assertIn('data-opener="door"', self.spa())
            self.assertNotIn("door-video", self.spa())
            with mock.patch.object(pages_media, "_exists", lambda p: "spa-door" in p):
                self.assertIn("door-video", self.spa())

    def test_home_gets_the_slippers_inset_only_when_the_picture_exists(self):
        with built():
            self.assertNotIn("home-slippers", self.client.get("/").content.decode())
        with built("slippers"):
            self.assertIn("home-slippers", self.client.get("/").content.decode())
