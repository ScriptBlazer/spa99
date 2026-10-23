"""Home hero uses only the video and its poster (never the old fish-tank still); no photo repeats on Home."""
import re

from django.test import TestCase

from pages.templatetags.pages_media import hero_video
from plans.management.commands.seed_phase1 import seed_all


class HomeImageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_hero_tag_has_codecs_and_posters_and_no_fish_tank(self):
        hv = hero_video()
        self.assertIn("av01.0.08M.08", hv["sources"])
        self.assertIn("av01.0.04M.08", hv["sources"])
        self.assertIn("hero-poster-landscape", hv["poster"])
        self.assertIn("hero-poster-portrait", hv["poster_portrait"])
        self.assertNotIn("fish-tank", str(hv))

    def test_hero_falls_back_to_the_poster_when_no_video_files_exist(self):
        from unittest import mock

        real = hero_video.__globals__["_exists"]
        with mock.patch.dict(hero_video.__globals__, {"_exists": lambda p: real(p) and p.endswith(".webp")}):
            hv = hero_video()
        self.assertEqual(hv["sources"], "[]")
        self.assertIn("hero-poster-landscape", hv["poster"])
        self.assertNotIn("fish-tank", str(hv))

    def test_home_never_renders_the_fish_tank_still_and_no_photo_repeats(self):
        html = self.client.get("/").content.decode()
        self.assertNotIn("fish-tank", html)
        self.assertIn("hero-poster-portrait", html)
        names = re.findall(r"img/([a-z0-9-]+)-480\.webp", html)
        self.assertIn("cold-plunge", names)
        self.assertEqual(len(names), len(set(names)), names)
