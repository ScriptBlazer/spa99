"""Control demo: who may open it, that the state is built from real rows, and that nothing here changes server data."""
import json
import re
from datetime import datetime
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import Client, TestCase

from control import demo
from plans.management.commands.seed_phase1 import seed_all
from plans.models import Facility, SiteSettings

User = get_user_model()
HOST = "control.localhost"
PATHS = ("/", "/rooms/", "/music/", "/screens/", "/schedule/", "/library/", "/password/", "/?room=dry-sauna", "/rooms/?room=gym")


def person(group=None, **extra):
    user = User.objects.create_user(f"{group or 'none'}{User.objects.count()}@example.com", "a-long-password-1", **extra)
    if group:
        user.groups.add(Group.objects.get(name=group))
    return user


def get(user, path, host=HOST):
    client = Client(HTTP_HOST=host)
    if user:
        client.force_login(user)
    return client.get(path)


class ControlTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        call_command("setup_roles", stdout=StringIO())


class AccessTests(ControlTestCase):
    def test_signed_out_visitors_are_sent_to_sign_in(self):
        for path in PATHS:
            response = get(None, path)
            self.assertEqual(response.status_code, 302, path)
            self.assertIn("/login/", response["Location"])

    def test_members_and_office_level_get_a_plain_404(self):
        member = person()
        office = person("Office", is_staff=True)
        for user in (member, office):
            for path in PATHS:
                self.assertEqual(get(user, path).status_code, 404, f"{user.email} {path}")

    def test_admin_developer_and_superuser_get_in(self):
        users = [person("Admin", is_staff=True), person("Developer", is_staff=True),
                 User.objects.create_superuser("root@example.com", "a-long-password-1")]
        for user in users:
            for path in PATHS:
                response = get(user, path)
                self.assertEqual(response.status_code, 200, f"{user.email} {path}")
                self.assertContains(response, "Rooms, music and screens are pretend. The Library is real.")
                self.assertContains(response, "Pretend building. Library is real.")
                self.assertContains(response, "<title>DEMO ")

    def test_the_control_pages_are_not_on_the_other_hosts(self):
        admin = person("Admin", is_staff=True)
        for host in ("localhost", "office.localhost", "system.localhost"):
            self.assertEqual(get(admin, "/screens/", host=host).status_code, 404, host)

    def test_sign_in_page_carries_the_demo_banner(self):
        self.assertContains(get(None, "/login/"), "Pretend building")


class StateTests(ControlTestCase):
    def test_rooms_are_the_visible_facilities_in_order_with_reception_first(self):
        Facility.objects.filter(slug="gym").update(visible=False)
        names = [r["name"] for r in demo.demo_state()["rooms"]]
        expected = ["Reception and lounge", "Hallway", "Changing room"] + [f.name for f in Facility.objects.filter(visible=True).order_by("order", "name")]
        self.assertEqual(names, expected)
        self.assertNotIn("Gym", names)
        self.assertEqual(names[:3], ["Reception and lounge", "Hallway", "Changing room"])
        self.assertEqual(names[3], "Dry sauna")

    def test_a_new_room_gets_lights_and_music_only(self):
        Facility.objects.create(name="Quiet room", slug="quiet-room", order=99)
        room = next(r for r in demo.demo_state()["rooms"] if r["slug"] == "quiet-room")
        self.assertTrue(room["caps"]["lights"] and room["caps"]["music"])
        self.assertIsNone(room["caps"]["climate"])
        self.assertIsNone(room["caps"]["screen"])

    def test_climate_only_on_saunas_and_plunge(self):
        climate = {r["slug"] for r in demo.demo_state()["rooms"] if r["caps"]["climate"]}
        self.assertEqual(climate, {"dry-sauna", "wet-sauna", "cold-plunge"})

    def test_capacity_comes_from_site_settings_and_people_stay_within_it(self):
        SiteSettings.objects.update(capacity=12)
        for hour in (6, 12, 19, 21, 23):
            state = demo.demo_state(datetime(2026, 10, 24, hour, 15, tzinfo=demo.LONDON))
            self.assertEqual(state["capacity"], 12)
            self.assertLessEqual(state["people"], 12)
            self.assertEqual(sum(r["people"] for r in state["rooms"]), state["people"])

    def test_closed_hours_are_empty_and_the_scene_follows_the_clock(self):
        night = demo.demo_state(datetime(2026, 10, 23, 3, 30, tzinfo=demo.LONDON))
        self.assertFalse(night["open"])
        self.assertEqual(night["people"], 0)
        self.assertEqual(night["active_scene"], "cleaning")
        evening = demo.demo_state(datetime(2026, 10, 24, 21, 14, tzinfo=demo.LONDON))
        self.assertTrue(evening["open"])
        self.assertEqual(evening["active_scene"], "evening")

    def test_week_has_seven_lanes_with_shabbos_spans_from_the_rules(self):
        week = demo.demo_state(datetime(2026, 10, 24, 12, 0, tzinfo=demo.LONDON))["week"]  # a Saturday
        self.assertEqual(len(week), 7)
        friday = next(d for d in week if d["date"] == "2026-10-30")
        saturday = week[0]
        self.assertTrue(any(c["kind"] == "shabbos" for c in friday["closed"]))
        self.assertTrue(any(c["kind"] == "shabbos" for c in saturday["closed"]))
        self.assertTrue(any("Example time" in note for note in friday["notes"]))

    def test_state_is_printed_once_and_can_be_read_back(self):
        response = get(person("Admin", is_staff=True), "/")
        match = re.search(r'<script id="ctl-demo" type="application/json">(.*?)</script>', response.content.decode(), re.S)
        self.assertIsNotNone(match)
        state = json.loads(match.group(1))
        self.assertEqual(state["rooms"][0]["name"], "Reception and lounge")
        self.assertEqual(response.content.decode().count('id="ctl-demo"'), 1)

    def test_the_page_works_as_a_snapshot_without_scripts(self):
        response = get(person("Admin", is_staff=True), "/")
        for text in ("Dry sauna", "Cold plunge", "Wristbands active", "Lockers in use", "Scene", "Floor plan"):
            self.assertContains(response, text)
        self.assertContains(get(person("Admin", is_staff=True), "/?room=dry-sauna"), 'data-room="dry-sauna"')


class NothingIsSavedTests(ControlTestCase):
    def test_pages_have_no_forms_that_post_except_sign_out_and_password(self):
        admin = person("Admin", is_staff=True)
        for path in ("/", "/rooms/", "/music/", "/screens/", "/schedule/"):
            html = get(admin, path).content.decode()
            actions = re.findall(r"<form[^>]*method=\"post\"[^>]*>", html)
            self.assertTrue(actions, path)
            for action in actions:
                self.assertIn("/logout/", action)
            self.assertNotIn("hx-post", html)
            self.assertNotIn("hx-put", html)

    def test_only_the_library_modules_talk_to_the_server(self):
        from pathlib import Path

        folder = Path(__file__).resolve().parents[2] / "common/static/common/js/control"
        talkers = {"libdata.js", "upload.js"}  # the Library: real files and playlists (fetch and XHR)
        for path in sorted(folder.glob("*.js")):
            source = path.read_text()
            if path.name in talkers:
                continue
            for word in ("fetch(", "XMLHttpRequest", "sendBeacon", "WebSocket", "EventSource"):
                if path.name == "app.js" and word == "fetch(":
                    continue  # app.js fetches the next page's HTML (GET) when you change tab
                self.assertNotIn(word, source, f"{path.name} uses {word}")

    def test_posting_to_the_pages_is_refused_and_changes_nothing(self):
        admin = person("Admin", is_staff=True)
        client = Client(HTTP_HOST=HOST)
        client.force_login(admin)
        before = (Facility.objects.count(), SiteSettings.load().capacity)
        for path in ("/", "/rooms/", "/music/", "/schedule/", "/screens/"):
            self.assertEqual(client.post(path, {"capacity": 1, "name": "x"}).status_code, 405, path)
        self.assertEqual((Facility.objects.count(), SiteSettings.load().capacity), before)


class PasswordTests(ControlTestCase):
    def test_an_admin_changes_their_own_password_and_lands_back_on_the_control_host(self):
        admin = person("Admin", is_staff=True)
        client = Client(HTTP_HOST=HOST)
        client.force_login(admin)
        page = client.get("/password/")
        self.assertContains(page, "Change your password")
        response = client.post("/password/", {"old_password": "a-long-password-1", "new_password1": "another-long-pass-2", "new_password2": "another-long-pass-2"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/password/")
        admin.refresh_from_db()
        self.assertTrue(admin.check_password("another-long-pass-2"))
