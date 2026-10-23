"""Virtual tour (frontend wiring): the hooks the 3D script needs are on the page, the module map lists real files, the tokens exist."""
import json
from pathlib import Path

from django.test import TestCase

from plans.management.commands.seed_phase1 import seed_all

STATIC = Path(__file__).resolve().parents[2] / "common" / "static" / "common"


class TourAssetsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def page(self, url="/tour/"):
        return self.client.get(url).content.decode()

    def test_page_loads_boot_only_and_hands_over_engine_and_modules(self):
        html = self.page()
        self.assertIn("common/js/tour/boot", html)
        self.assertNotIn("three.module", html)
        self.assertIn('data-engine="/static/common/js/tour/engine.js"', html)
        self.assertIn("common/css/tour.css", html)
        mods = json.loads(html.split('id="tour-modules" type="application/json">')[1].split("</script>")[0])
        self.assertIn("lounge", mods)
        for url in mods.values():
            self.assertTrue((STATIC / url.split("/static/common/")[1]).exists(), url)

    def test_label_and_icons_are_there(self):
        html = self.page("/tour/gym/")
        self.assertIn('class="tour-label">Virtual tour<', html)
        self.assertIn('id="tour-logo-stacked"', html)
        icons = (STATIC / "img" / "icons.svg").read_text()
        for name in ("hand-grabbing", "device-rotate", "arrow-right"):
            self.assertIn(f'id="{name}"', icons)

    def test_tour_tokens_exist(self):
        css = (STATIC / "css" / "tokens.css").read_text()
        for token in ("--color-light-warm", "--color-led-warm", "--color-travertine", "--color-sage", "--color-moss", "--duration-tour-fade",
                      "--color-iron", "--tour-caption-w", "--tour-ring", "--ease-glide", "--duration-settle", "--duration-glide-fade"):
            self.assertIn(token + ":", css)
