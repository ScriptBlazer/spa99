"""Sentry setup with a fake transport: nothing leaves the machine."""
import logging
from io import StringIO
from unittest import mock

import sentry_sdk
from django.contrib.auth import get_user_model
from django.core.exceptions import DisallowedHost, PermissionDenied
from django.core.management import call_command
from django.http import Http404
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from sentry_sdk.transport import Transport

from common import observability
from common.envloader import Env


class FakeTransport(Transport):
    def __init__(self, options=None):
        super().__init__(options)
        self.events = []

    def capture_envelope(self, envelope):
        if envelope.get_event():
            self.events.append(envelope.get_event())


def env_with(**values):
    return Env([("environment", values)], private_dir=None)


class SentryTestCase(SimpleTestCase):
    def start(self, **values):
        self.transport = FakeTransport()
        values = {"SENTRY_DSN": "https://key@o0.ingest.sentry.io/1", **values}
        state = observability.init_sentry(env_with(**values), "dev", transport=self.transport)
        self.addCleanup(self.stop)
        return state

    @staticmethod
    def stop():
        sentry_sdk.init()
        for scope in (sentry_sdk.get_global_scope(), sentry_sdk.get_isolation_scope(), sentry_sdk.get_current_scope()):
            scope.clear()

    @property
    def events(self):
        sentry_sdk.flush()
        return self.transport.events


class InitTests(SentryTestCase):
    def test_off_without_dsn(self):
        self.addCleanup(self.stop)
        self.assertEqual(observability.init_sentry(env_with(), "dev"), "off")
        self.assertIsNone(sentry_sdk.get_client().dsn)

    def test_on_uses_environment_and_release_from_env(self):
        self.assertEqual(self.start(), "on(dev)")
        self.assertEqual(self.start(SENTRY_ENVIRONMENT="live", APP_VERSION="1.2.3"), "on(live)")
        options = sentry_sdk.get_client().options
        self.assertEqual((options["release"], options["send_default_pii"], options["traces_sample_rate"]), ("1.2.3", False, 0.0))


class ScrubTests(SimpleTestCase):
    def test_request_is_scrubbed(self):
        event = {
            "request": {
                "url": "https://spa99.uk/journey/step/?email=a@b.co&x=1",
                "query_string": "email=a@b.co&x=1",
                "cookies": {"sessionid": "s"},
                "data": {"password": "p"},
                "headers": {"Cookie": "c", "Authorization": "a", "X-CSRFToken": "t", "Accept": "text/html"},
            }
        }
        request = observability.before_send(event, {})["request"]
        self.assertNotIn("cookies", request)
        self.assertNotIn("data", request)
        self.assertNotIn("query_string", request)  # /journey/ query strings are dropped
        self.assertEqual(request["headers"], {"Accept": "text/html"})

    def test_other_query_strings_hide_sensitive_keys(self):
        event = {"request": {"url": "https://spa99.uk/faq/?page=2&mobile=0777", "query_string": "page=2&mobile=0777"}}
        self.assertEqual(observability.before_send(event, {})["request"]["query_string"], "page=2&mobile=[Filtered]")

    def test_sensitive_keys_emails_and_user(self):
        event = {
            "user": {"id": "7", "email": "a@b.co", "username": "x"},
            "message": "Could not email jo@example.com",
            "extra": {"first_name": "Jo", "count": 3, "nested": {"api_token": "t"}},
            "exception": {"values": [{"value": "bad jo@example.com", "stacktrace": {"frames": [{"vars": {"phone": "1", "n": 2}}]}}]},
        }
        out = observability.before_send(event, {})
        self.assertEqual(out["user"], {"id": "7"})
        self.assertNotIn("jo@example.com", str(out))
        self.assertEqual(out["extra"], {"first_name": "[Filtered]", "count": 3, "nested": {"api_token": "[Filtered]"}})
        self.assertEqual(out["exception"]["values"][0]["stacktrace"]["frames"][0]["vars"], {"phone": "[Filtered]", "n": 2})

    def test_rate_limited_and_disallowed_host_events_are_dropped(self):
        self.assertIsNone(observability.before_send({"contexts": {"response": {"status_code": 429}}}, {}))
        self.assertIsNone(observability.before_send({"logger": "django.security.DisallowedHost"}, {}))


class CaptureTests(SentryTestCase):
    def test_ignored_exceptions_are_dropped_and_others_sent(self):
        self.start()
        for error in (Http404(), PermissionDenied(), DisallowedHost(), BrokenPipeError()):
            sentry_sdk.capture_exception(error)
        self.assertEqual(self.events, [])
        sentry_sdk.capture_exception(ValueError("real bug"))
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0]["tags"]["host"], "worker")

    def test_error_logs_become_events_and_info_does_not(self):
        self.start()
        logging.getLogger("spa99.test").info("fine")
        logging.getLogger("spa99.test").error("broken for jo@example.com")
        self.assertEqual(len(self.events), 1)
        self.assertNotIn("jo@example.com", str(self.events[0]))

    def test_django_q_failure_reaches_sentry(self):
        """django-q's monitor logs "Failed ..." at ERROR on logger django-q."""
        from django_q.monitor import monitor

        self.start()
        task = {"name": "boom", "func": "common.tasks.heartbeat", "result": "ValueError('x') : Traceback", "success": False}
        results = iter([task, "STOP"])
        with mock.patch("django_q.monitor.save_task"):
            monitor(mock.Mock(get=lambda: next(results)), broker=mock.Mock())
        failed = [e for e in self.events if "Failed" in str(e.get("logentry"))]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["level"], "error")


class MiddlewareTagTests(TestCase, SentryTestCase):
    def tags_for(self, user, urlconf=None):
        request = RequestFactory().get("/")
        request.user = user
        if urlconf:
            request.urlconf = urlconf
        observability.SentryContextMiddleware(lambda r: sentry_sdk.capture_message("hi"))(request)
        return self.events[-1]

    def test_host_staff_tags_and_user_id_only(self):
        self.start()
        staff = get_user_model().objects.create_user(email="s@example.com", password="x" * 12, is_staff=True)
        event = self.tags_for(staff, "config.urls_office")
        self.assertEqual((event["tags"]["host"], event["tags"]["staff"]), ("office", "true"))
        self.assertEqual(event["user"], {"id": str(staff.pk)})
        from django.contrib.auth.models import AnonymousUser

        event = self.tags_for(AnonymousUser())
        self.assertEqual((event["tags"]["host"], event["tags"]["staff"]), ("public", "false"))


class CommandTests(SentryTestCase):
    def test_without_dsn(self):
        out = StringIO()
        with override_settings(SENTRY_STATE="off"):
            call_command("sentry_test", stdout=out)
        self.assertIn("Sentry is off", out.getvalue())

    def test_with_dsn_prints_event_ids_not_dsn(self):
        state = self.start()
        out = StringIO()
        with override_settings(SENTRY_STATE=state):
            call_command("sentry_test", stdout=out)
        self.assertIn("event id", out.getvalue())
        self.assertNotIn("ingest.sentry.io", out.getvalue())
        self.assertEqual(len(self.events), 2)
