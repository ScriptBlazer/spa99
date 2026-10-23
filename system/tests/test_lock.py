"""Lock behaviour (idle time read from the Security settings, remaining seconds from the server), the Security settings,
and the per-plan points boxes on the journey page."""
import re
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase

from journey.models import Option
from plans.models import Plan, SiteSettings
from system import services
from system.models import SystemChange
from system.tests.test_extras import SETTINGS_POST
from system.tests.test_rules import RulesTestCase
from system.tests.test_system import PASSWORD, make_user, sign_in, unlocked_client


class IdleLockTests(TestCase):
    def test_the_idle_time_comes_from_the_security_setting_and_the_page_shows_the_seconds_left(self):
        SiteSettings.objects.update_or_create(singleton_key="site", defaults={"lock_idle_minutes": 5})
        client, _ = sign_in(make_user())
        with mock.patch("system.services.time.time", return_value=1000.0):
            client.post("/unlock/", {"password": PASSWORD})
            page = client.get("/")
        self.assertContains(page, 'data-system-idle="300"')
        self.assertContains(page, 'data-system-remaining="300"')
        with mock.patch("system.services.time.time", return_value=1000.0 + 4 * 60):  # busy: the ping slides the window
            self.assertEqual(client.post("/unlock/ping/").json(), {"remaining": 300})
        with mock.patch("system.services.time.time", return_value=1000.0 + 8 * 60):  # 4 minutes after the ping: still unlocked
            self.assertEqual(client.get("/").status_code, 200)
        with mock.patch("system.services.time.time", return_value=1000.0 + 8 * 60 + 301):  # idle for 5 minutes and a second
            self.assertEqual(client.get("/").status_code, 302)
            self.assertEqual(client.post("/unlock/ping/").status_code, 403)

    def test_peek_reads_the_time_left_without_sliding_it(self):
        client, _ = sign_in(make_user())
        with mock.patch("system.services.time.time", return_value=1000.0):
            client.post("/unlock/", {"password": PASSWORD})
        with mock.patch("system.services.time.time", return_value=1000.0 + 600):
            self.assertEqual(client.post("/unlock/ping/", {"peek": "1"}).json(), {"remaining": 300})
        with mock.patch("system.services.time.time", return_value=1000.0 + 900 + 1):
            self.assertEqual(client.post("/unlock/ping/", {"peek": "1"}).status_code, 403)  # the peek did not slide it

    def test_the_longest_sign_in_comes_from_the_security_setting(self):
        SiteSettings.objects.update_or_create(singleton_key="site", defaults={"max_sign_in_hours": 2, "lock_idle_minutes": 240})
        client, _ = sign_in(make_user())
        start = client.session[services.SIGNED_IN_KEY]
        with mock.patch("system.services.time.time", return_value=start):
            client.post("/unlock/", {"password": PASSWORD})
        with mock.patch("system.services.time.time", return_value=start + 3600):
            self.assertEqual(client.get("/").status_code, 200)
        with mock.patch("system.services.time.time", return_value=start + 2 * 3600 + 60):
            self.assertEqual(client.get("/").status_code, 302)

    def test_the_settings_constants_are_the_defaults(self):
        site = SiteSettings.load()
        self.assertEqual((site.lock_idle_minutes, site.max_sign_in_hours), (15, 12))
        self.assertEqual((services.lock_idle_seconds(), services.session_age_seconds()), (900, 12 * 3600))


class SecuritySettingsTests(TestCase):
    def setUp(self):
        self.client = unlocked_client(make_user())

    def test_the_settings_page_has_a_security_group(self):
        response = self.client.get("/settings/")
        self.assertContains(response, "data-system-security")
        self.assertContains(response, 'name="lock_idle_minutes"')
        self.assertContains(response, 'name="max_sign_in_hours"')
        self.assertTrue({"lock_idle_minutes", "max_sign_in_hours"} <= set(response.context["risky_fields"]))

    def test_values_outside_the_range_are_refused(self):
        for field, bad in (("lock_idle_minutes", "0"), ("lock_idle_minutes", "241"), ("max_sign_in_hours", "0"), ("max_sign_in_hours", "73")):
            response = self.client.post("/settings/", SETTINGS_POST | {field: bad})
            self.assertEqual(response.status_code, 400, (field, bad))
            self.assertIn(field, response.context["form"].errors)
        site = SiteSettings.load()
        site.lock_idle_minutes = 500
        with self.assertRaises(ValidationError):
            site.full_clean()

    def test_a_change_is_logged_takes_effect_and_can_be_undone(self):
        response = self.client.post("/settings/", SETTINGS_POST | {"lock_idle_minutes": "30", "max_sign_in_hours": "8"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual((services.lock_idle_seconds(), services.session_age_seconds()), (1800, 8 * 3600))
        change = SystemChange.objects.get(field="lock_idle_minutes")
        self.assertEqual((change.old_value, change.new_value, change.section), (15, 30, "settings"))
        self.client.post(f"/changes/{change.pk}/undo/")
        self.assertEqual(services.lock_idle_seconds(), 900)


class PlanPointsTests(RulesTestCase):
    def test_the_journey_page_shows_one_small_box_per_plan_not_a_json_text(self):
        response = self.client.get("/journey/")
        slugs = list(Plan.objects.values_list("slug", flat=True))
        option = Option.objects.exclude(plan_points={}).first()
        html = response.content.decode()
        for slug in slugs:
            self.assertIn(f'name="{option.pk}-plan_points.{slug}"', html)
        self.assertNotIn("Plan points (JSON)", html)

    def test_the_boxes_are_assembled_into_the_points_object_validated_and_logged(self):
        option = Option.objects.exclude(plan_points={}).first()
        key = str(option.pk)
        slugs = list(Plan.objects.values_list("slug", flat=True))
        base = {f"{key}-label": option.label, f"{key}-order": str(option.order), f"{key}-active": "on", f"{key}-gold_points": str(option.gold_points),
                f"{key}-weight": "" if option.weight is None else str(option.weight), f"{key}-reason": option.reason}
        boxes = {f"{key}-plan_points.{slug}": "" for slug in slugs}
        bad = self.client.post(f"/journey/options/{option.pk}/", base | boxes | {f"{key}-plan_points.{slugs[0]}": "x"})
        self.assertEqual(bad.status_code, 400)
        self.assertContains(bad, "Points must be whole numbers", status_code=400)
        ok = self.client.post(f"/journey/options/{option.pk}/", base | boxes | {f"{key}-plan_points.{slugs[0]}": "4", f"{key}-plan_points.{slugs[-1]}": "2"})
        self.assertEqual(ok.status_code, 302)
        option.refresh_from_db()
        self.assertEqual(option.plan_points, {slugs[0]: 4, slugs[-1]: 2} if slugs[0] != slugs[-1] else {slugs[0]: 2})
        self.assertTrue(SystemChange.objects.filter(model_label="journey.option", field="plan_points").exists())
        again = self.client.post(f"/journey/options/{option.pk}/", base | {f"{key}-plan_points.{s}": str(option.plan_points.get(s, "")) for s in slugs})
        self.assertEqual(again.status_code, 302)
        self.assertEqual(SystemChange.objects.filter(model_label="journey.option", field="plan_points").count(), 1)  # no change, no entry
