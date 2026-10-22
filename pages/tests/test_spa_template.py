"""The spa page template: chips, room anchors, type tiles, the walk hook, and that hiding a room never leaves a dead link."""
import re

from django.test import TestCase

from plans.management.commands.seed_phase1 import seed_all
from plans.models import Facility


class SpaTemplateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def page(self):
        return self.client.get("/the-spa/").content.decode()

    def test_every_chip_has_a_room_to_land_on(self):
        html = self.page()
        chips = re.findall(r'class="chip" href="#([a-z-]+)"', html)
        self.assertEqual(len(chips), 8)
        for slug in chips:
            self.assertEqual(html.count(f'id="{slug}"'), 1, slug)

    def test_hidden_room_leaves_no_chip_and_no_section(self):
        Facility.objects.filter(slug="gym").update(visible=False)
        html = self.page()
        self.assertNotIn('href="#gym"', html)
        self.assertNotIn('id="gym"', html)

    def test_rooms_without_a_picture_show_the_type_tile_and_facts_render(self):
        Facility.objects.filter(slug="wet-sauna").update(image_name="")
        html = self.page()
        self.assertIn('class="type-tile"', html)  # a room with no picture keeps the swan type tile
        self.assertIn("Part of your visit", html)

    def test_walk_slots_and_the_pin_free_door(self):
        html = self.page()
        self.assertIn('data-walk="dry-sauna"', html)
        self.assertIn('data-walk="wet-sauna"', html)
        self.assertIn("Tailor your membership", html)
        self.assertNotIn("data-pin", html)

    def test_tiles_intro_appears_once(self):
        Facility.objects.filter(slug="relaxing-zone").update(display="tile")
        self.assertEqual(self.page().count('id="tiles-title"'), 1)

    def test_page_loads_only_the_spa_scene_modules_and_no_drawsvg(self):
        html = self.page()
        self.assertIn("common/js/spa.js", html)
        self.assertNotIn("DrawSVGPlugin", html)
