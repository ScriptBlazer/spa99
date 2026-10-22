"""Health, host routing, spa day, validators, audit and background task."""
from datetime import date, datetime, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import OperationalError
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django_q.models import Success

from common.middleware import HostRoutingMiddleware
from common.models import LoginEvent
from common.spa_day import spa_day_bounds, spa_day_for
from common.tasks import enqueue
from common.validators import normalise_email, normalise_uk_mobile, password_problems

LONDON = ZoneInfo("Europe/London")
UTC = ZoneInfo("UTC")


class HealthTests(TestCase):
    def test_ok_when_database_answers(self):
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_503_when_database_is_down(self):
        with mock.patch("common.views.connection.cursor", side_effect=OperationalError("down")):
            response = self.client.get("/health/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "error"})


class HostRoutingTests(SimpleTestCase):
    def urlconf_for(self, host):
        seen = {}

        def get_response(request):
            seen["urlconf"] = request.urlconf
            return HttpResponse()

        HostRoutingMiddleware(get_response)(RequestFactory().get("/", HTTP_HOST=host))
        return seen["urlconf"]

    def test_control_host_uses_control_urls_everything_else_public(self):
        self.assertEqual(self.urlconf_for("control.localhost:8000"), "config.urls_control")
        self.assertEqual(self.urlconf_for("CONTROL.localhost"), "config.urls_control")
        self.assertEqual(self.urlconf_for("localhost:8000"), "config.urls")
        self.assertEqual(self.urlconf_for("testserver"), "config.urls")


class ControlAccessTests(TestCase):
    """Locked by default on the control host; roles enforced in the view."""

    host = {"HTTP_HOST": "control.localhost"}

    def test_anonymous_is_sent_to_login_and_public_host_has_no_control_pages(self):
        response = self.client.get("/", **self.host)
        self.assertRedirects(response, "/login/?next=/", fetch_redirect_response=False)
        self.assertEqual(self.client.get("/").status_code, 404)  # public host has no control pages

    def test_only_staff_reach_the_index(self):
        User = get_user_model()
        member = User.objects.create_user("member@example.com", "a-long-password-1")
        staff = User.objects.create_user("staff@example.com", "a-long-password-1", is_staff=True)
        self.client.force_login(member)
        self.assertEqual(self.client.get("/", **self.host).status_code, 403)
        self.client.force_login(staff)
        self.assertEqual(self.client.get("/", **self.host).status_code, 200)


class SpaDayTests(SimpleTestCase):
    def day(self, *args, tz=LONDON, **kwargs):
        return spa_day_for(datetime(*args, tzinfo=tz, **kwargs))

    def test_boundaries(self):
        self.assertEqual(self.day(2026, 10, 22, 1, 0), date(2026, 10, 21))   # 1am: previous spa day
        self.assertEqual(self.day(2026, 10, 22, 2, 59), date(2026, 10, 21))
        self.assertEqual(self.day(2026, 10, 22, 3, 0), date(2026, 10, 22))   # closed 3-5am: upcoming day
        self.assertEqual(self.day(2026, 10, 22, 4, 0), date(2026, 10, 22))   # CAL-05
        self.assertEqual(self.day(2026, 10, 22, 5, 0), date(2026, 10, 22))
        self.assertEqual(self.day(2026, 10, 22, 23, 30), date(2026, 10, 22))

    def test_utc_input_is_converted_to_london_time(self):
        # 23:30 UTC in July is 00:30 BST the next calendar day: still the earlier spa day.
        self.assertEqual(self.day(2026, 7, 1, 23, 30, tz=UTC), date(2026, 7, 1))

    def test_clocks_going_back_both_1_30ams_are_the_same_spa_day(self):
        first, second = (datetime(2026, 10, 25, 1, 30, tzinfo=LONDON, fold=f) for f in (0, 1))
        self.assertNotEqual(first.utcoffset(), second.utcoffset())
        self.assertEqual(spa_day_for(first), date(2026, 10, 24))
        self.assertEqual(spa_day_for(second), date(2026, 10, 24))
        self.assertEqual(self.day(2026, 10, 25, 3, 30), date(2026, 10, 25))

    def test_clocks_going_forward(self):
        self.assertEqual(self.day(2027, 3, 28, 0, 30), date(2027, 3, 27))
        self.assertEqual(self.day(2027, 3, 28, 3, 30), date(2027, 3, 28))

    def test_boundaries_can_be_passed_in_and_naive_is_rejected(self):
        from datetime import time

        moment = datetime(2026, 10, 22, 3, 30, tzinfo=LONDON)
        self.assertEqual(spa_day_for(moment, day_end=time(4, 0)), date(2026, 10, 21))
        with self.assertRaises(ValueError):
            spa_day_for(datetime(2026, 10, 22, 3, 30))

    def test_bounds_span_the_clock_change(self):
        opens, closes = spa_day_bounds(date(2026, 10, 24))
        self.assertEqual((opens.hour, closes.hour), (5, 3))
        self.assertEqual(closes - opens, timedelta(hours=22))  # extra hour because clocks went back


class ValidatorTests(SimpleTestCase):
    def test_uk_mobile_is_normalised_to_e164(self):
        for raw in ("07912 345678", "+44 7912 345678", "(07912) 345-678", "0044 7912 345678"):
            self.assertEqual(normalise_uk_mobile(raw), "+447912345678", raw)

    def test_uk_mobile_rejects_landlines_foreign_and_junk(self):
        for raw in ("020 7946 0958", "+1 202 555 0123", "12345", "", "not a number"):
            with self.subTest(raw=raw), self.assertRaises(ValidationError):
                normalise_uk_mobile(raw)

    def test_email_is_trimmed_lowercased_and_checked(self):
        self.assertEqual(normalise_email("  Moishe@Example.COM "), "moishe@example.com")
        for bad in ("", "no-at-sign", "a@b"):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                normalise_email(bad)

    def test_password_rules(self):
        self.assertTrue(password_problems("short1"))
        self.assertTrue(password_problems("password123"))
        self.assertTrue(password_problems("1234567890123"))
        self.assertTrue(password_problems("moishe.berkowitz1", email="moishe.berkowitz@example.com"))
        self.assertTrue(password_problems("Berkowitzzz99", last_name="Berkowitz"))
        self.assertEqual(password_problems("violet-harbour-lantern-41", email="a@example.com"), [])


class LoginAuditTests(TestCase):
    host = {"HTTP_HOST": "control.localhost"}

    def setUp(self):
        self.user = get_user_model().objects.create_user("Staff@Example.com", "a-long-password-1", is_staff=True)

    def test_login_logout_and_failure_are_recorded(self):
        self.client.post("/login/", {"username": "wrong@example.com", "password": "nope"}, **self.host)
        failed = LoginEvent.objects.get(event=LoginEvent.FAILED)
        self.assertEqual(failed.attempted_email, "wrong@example.com")
        self.assertIsNone(failed.user)

        # Email login is case-insensitive.
        self.client.post("/login/", {"username": "STAFF@example.com", "password": "a-long-password-1"},
                         REMOTE_ADDR="203.0.113.7", **self.host)
        login = LoginEvent.objects.get(event=LoginEvent.LOGIN)
        self.assertEqual((login.user, login.ip_address), (self.user, "203.0.113.7"))
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.last_login)

        self.client.post("/logout/", **self.host)
        self.assertTrue(LoginEvent.objects.filter(event=LoginEvent.LOGOUT, user=self.user).exists())

    def test_login_does_not_write_user_history(self):
        before = self.user.history.count()
        self.client.post("/login/", {"username": "staff@example.com", "password": "a-long-password-1"}, **self.host)
        self.assertEqual(self.user.history.count(), before)

    @override_settings(TRUST_FORWARDED_FOR=True)
    def test_forwarded_ip_is_used_behind_the_proxy(self):
        self.client.post("/login/", {"username": "x@example.com", "password": "bad"},
                         HTTP_X_FORWARDED_FOR="198.51.100.9, 10.0.0.2", REMOTE_ADDR="10.0.0.2", **self.host)
        self.assertEqual(LoginEvent.objects.get().ip_address, "198.51.100.9")


class BackgroundTaskTests(TestCase):
    def test_example_task_runs_synchronously_in_tests(self):
        enqueue("common.tasks.heartbeat")
        self.assertEqual(Success.objects.filter(func="common.tasks.heartbeat").count(), 1)


class ErrorPageTests(SimpleTestCase):
    def test_error_pages_render_with_correct_headings(self):
        from django.template.loader import render_to_string

        expected = {
            "400.html": "That request didn&rsquo;t work",
            "403.html": "You don&rsquo;t have access to this page",
            "404.html": "We can&rsquo;t find that page",
            "500.html": "Something went wrong",
        }
        for name, heading in expected.items():
            with self.subTest(name=name):
                self.assertIn(f"<h1>{heading}</h1>", render_to_string(name))

    def test_csrf_failure_view_gives_friendly_403(self):
        from django.test import RequestFactory

        from common.views import csrf_failure

        response = csrf_failure(RequestFactory().post("/x/"))
        self.assertEqual(response.status_code, 403)
        self.assertIn("have access", response.content.decode())
