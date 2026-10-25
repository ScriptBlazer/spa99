"""Control v2: the floor plan, zones and screens in the demo state, the pages, and the browser rules (run with node)."""
import re
import shutil
import subprocess
from pathlib import Path

from django.test import SimpleTestCase

from control import demo, plan
from control.tests.test_control import ControlTestCase, get, person


class PlanTests(SimpleTestCase):
    def test_every_room_of_the_real_plan_is_drawn_and_controllable_ones_link(self):
        drawing = plan.build()
        ids = {s["id"] for s in drawing["shapes"]}
        for needed in ("dry-sauna", "wet-sauna", "showers", "cold-plunge", "relaxing", "changing", "hallway", "kitchenette", "massage", "gym", "entrance", "stairs", "electrical"):
            self.assertIn(needed, ids)
        self.assertEqual({s["slug"] for s in drawing["shapes"] if s["slug"]},
                         {"dry-sauna", "wet-sauna", "showers", "cold-plunge", "relaxing-zone", "changing-room", "hallway", "kitchenette", "massage-room", "gym", "reception-lounge"})
        self.assertNotIn("corridor", {s["slug"] for s in drawing["shapes"]})

    def test_phone_plan_is_the_transposed_one_and_every_controllable_room_is_thick_enough(self):
        phone, scale = plan.build(phone=True), 343 / plan.PHONE_BOX[0]
        self.assertEqual(phone["viewbox"], f"0 0 {plan.PHONE_BOX[0]} {plan.PHONE_BOX[1]}")
        for shape in phone["shapes"]:
            if shape["slug"]:
                self.assertGreaterEqual(min(float(shape["w"]), float(shape["h"])) * scale, 56, shape["id"])

    def test_rooms_do_not_overlap(self):
        boxes = [(r["id"], r["box"]) for r in plan.GEOMETRY]
        for i, (a, (ax1, ay1, ax2, ay2)) in enumerate(boxes):
            for b, (bx1, by1, bx2, by2) in boxes[i + 1:]:
                if "entrance" in (a, b) or "survey" in (a, b):
                    continue  # the entrance is an L shape inside a larger box
                self.assertFalse(ax1 < bx2 and bx1 < ax2 and ay1 < by2 and by1 < ay2, f"{a} overlaps {b}")


class Model3dTests(SimpleTestCase):
    def test_the_3d_outlines_cover_every_room_and_walls_between_rooms_are_the_gaps(self):
        data = plan.model()
        by_slug = {r["slug"]: r for r in data["rooms"] if r["slug"]}
        self.assertEqual(set(by_slug), {"dry-sauna", "wet-sauna", "showers", "cold-plunge", "relaxing-zone", "changing-room", "hallway", "kitchenette", "massage-room", "gym", "reception-lounge"})
        self.assertNotIn("survey", {r["id"] for r in data["rooms"]})  # the not-surveyed ghost is not drawn
        dry = by_slug["dry-sauna"]["points"]
        self.assertEqual(dry, [[12 + plan.INSET, 14 + plan.INSET], [142 - plan.INSET, 14 + plan.INSET], [142 - plan.INSET, 192 - plan.INSET], [12 + plan.INSET, 192 - plan.INSET]])
        self.assertGreater(len(by_slug["reception-lounge"]["points"]), 4)  # the L shaped entrance keeps its outline


class SceneAndOverviewPageTests(ControlTestCase):
    def test_overview_ships_the_3d_model_data_and_its_2d_fallback(self):
        html = get(person("Admin", is_staff=True), "/").content.decode()
        self.assertIn('data-model-canvas', html)
        self.assertIn('id="ctl-plan3d"', html)
        self.assertEqual(html.count('class="ctl-plan ctl-plan-'), 2)

    def test_scene_chips_open_the_editor_and_are_labelled_scenes(self):
        for path in ("/", "/rooms/"):
            html = get(person("Admin", is_staff=True), path).content.decode()
            self.assertIn(">Scenes ", html)
            self.assertEqual(len(re.findall(r'<button type="button" class="ctl-scene" data-scene="', html)), 5)
            self.assertEqual(html.count('data-active="true"'), 1)  # the scene for the time of day shows Active
            self.assertNotIn("aria-pressed", re.search(r'<div class="ctl-scenes".*?</div>', html, re.S).group(0))


class StateV2Tests(ControlTestCase):
    def test_hallway_and_changing_room_are_there_and_corridor_is_gone(self):
        state = demo.demo_state()
        slugs = [r["slug"] for r in state["rooms"]]
        self.assertEqual(slugs[:3], ["reception-lounge", "hallway", "changing-room"])
        self.assertNotIn("corridor", slugs)
        hallway = state["rooms"][1]
        self.assertTrue(hallway["caps"]["lights"])
        self.assertEqual(state["version" if "version" in state else "v"], demo.STATE_VERSION)

    def test_six_screens_and_five_zones_with_one_zone_per_room(self):
        state = demo.demo_state()
        self.assertEqual([s["id"] for s in state["screens"]], ["reception", "lounge", "hallway", "gym", "relaxing-zone", "kitchenette"])
        self.assertEqual([z["id"] for z in state["zones"]], ["lounge", "wet-area", "relaxing-zone", "massage-room", "gym"])
        rooms = [slug for z in state["zones"] for slug in z["rooms"]]
        self.assertEqual(len(rooms), len(set(rooms)))
        self.assertNotIn("dry-sauna", rooms)  # no speakers in the saunas
        self.assertEqual(len(state["spotify"]), 6)
        self.assertEqual([p["name"] for p in state["spotify"]], ["Warm Room", "Low Light", "Slow Morning", "Gym Tempo", "Kitchen Radio", "After Hours"])

    def test_pages_have_their_homes(self):
        admin = person("Admin", is_staff=True)
        overview = get(admin, "/").content.decode()
        self.assertEqual(overview.count('class="ctl-plan ctl-plan-'), 2)
        self.assertIn("Open until", overview)
        self.assertIn("Entrance, Vale Road", overview)
        for path, needle in (("/rooms/", "ctl-rgrid"), ("/music/", "data-player"), ("/screens/", "ctl-sgrid"), ("/schedule/", "data-slane")):
            self.assertContains(get(admin, path), needle)
        for path in ("/", "/rooms/", "/music/", "/screens/", "/schedule/", "/library/"):
            html = get(admin, path).content.decode()
            for tab in ("Overview", "Rooms", "Music", "Screens", "Schedule", "Library"):
                self.assertIn(f">{tab}</a>", html, path)
            self.assertIn("data-more-open", html)

    def test_rooms_page_shows_the_real_photo_with_the_light_layers(self):
        html = get(person("Admin", is_staff=True), "/rooms/").content.decode()
        self.assertIn("dry-sauna-800", html)
        for layer in ("l-night", "l-lamps", "l-pool", "l-warm", "l-cool"):
            self.assertIn(layer, html)
        self.assertIn("--o-night:", html)

    def test_demo_chips_are_on_the_pretend_groups(self):
        admin = person("Admin", is_staff=True)
        self.assertContains(get(admin, "/rooms/?room=dry-sauna"), "ctl-chip-demo")
        self.assertContains(get(admin, "/"), "ctl-chip-demo")


class BrowserRulesTests(SimpleTestCase):
    def test_queue_rules_pass_under_node(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        folder = Path(__file__).resolve().parent / "js"
        files = sorted(str(f) for f in folder.glob("*.test.mjs"))  # files, not the folder: Node 22 (CI) can't take a folder
        result = subprocess.run([node, "--test", *files], capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout[-2000:] + result.stderr[-2000:])

    def test_every_module_parses(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        root = Path(__file__).resolve().parents[2] / "common/static/common/js"
        for path in [root / "control.js", *sorted((root / "control").glob("*.js"))]:
            result = subprocess.run([node, "--check", str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, f"{path.name}: {result.stderr}")

    def test_photo_layer_maths_matches_the_server(self):
        from control import present

        o = present.layers(True, 60, 2700)
        self.assertAlmostEqual(o["night"], 0.88 * 0.4 ** 1.2, places=6)
        self.assertAlmostEqual(o["warm"], (300 / 800) * 0.28, places=6)
        self.assertEqual(o["cool"], 0)
        self.assertEqual(present.layers(False, 60, 2700), {"night": 0.94, "lamps": 0, "pool": 0, "warm": 0, "cool": 0})
        self.assertAlmostEqual(present.layers(True, 100, 4000)["cool"], 0.35)
