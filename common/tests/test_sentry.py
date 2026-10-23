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

    def test_release_is_empty_not_git_when_unset(self):
        self.start()
        self.assertEqual(sentry_sdk.get_client().options["release"], "")  # "" stops the SDK running git

    def test_on_uses_environment_and_release_from_env(self):
        self.assertEqual(self.start(), "on(dev)")
        self.assertEqual(self.start(SENTRY_ENVIRONMENT="live", APP_VERSION="1.2.3"), "on(live)")
        options = sentry_sdk.get_client().options
        self.assertEqual((options["release"], options["send_default_pii"], options["traces_sample_rate"]), ("1.2.3", False, 0.0))


class ScrubTests(SentryTestCase):
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

    def test_header_allowlist_drops_ip_and_referer(self):
        headers = {"X-Client-IP": "1.2.3.4", "CF-Connecting-IP": "1.2.3.4", "True-Client-IP": "1.2.3.4",
                   "Referer": "https://spa99.uk/x?email=a", "User-Agent": "UA", "Accept-Language": "en"}
        out = observability.before_send({"request": {"url": "https://spa99.uk/", "headers": headers}}, {})
        self.assertEqual(out["request"]["headers"], {"User-Agent": "UA", "Accept-Language": "en"})

    def test_staff_host_query_dropped_and_q_sensitive_on_public(self):
        office = {"request": {"url": "https://office.localhost/people/?q=Jo", "query_string": "q=Jo&page=2"}}
        self.assertNotIn("query_string", observability.before_send(office, {})["request"])
        public = {"request": {"url": "https://spa99.uk/faq/?q=Jo", "query_string": "q=Jo&page=2"}}
        self.assertEqual(observability.before_send(public, {})["request"]["query_string"], "q=[Filtered]&page=2")

    def test_transactions_are_scrubbed_too(self):
        self.start(SENTRY_TRACES_SAMPLE_RATE="1")
        self.assertIs(sentry_sdk.get_client().options["before_send_transaction"], observability.before_send)
        event = {"type": "transaction", "request": {"url": "https://office.localhost/?q=Jo", "query_string": "q=Jo", "cookies": {"a": "b"}}}
        self.assertEqual(observability.before_send(event, {})["request"], {"url": "https://office.localhost/"})

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
        self.assertNotIn("vars", out["exception"]["values"][0]["stacktrace"]["frames"][0])

    def test_rate_limit_drop_only_for_own_429_responses(self):
        self.assertIsNotNone(observability.before_send({"message": "Stripe said Too Many Requests"}, {}))

    def test_rate_limited_and_disallowed_host_events_are_dropped(self):
        self.assertIsNone(observability.before_send({"contexts": {"response": {"status_code": 429}}}, {}))
        self.assertIsNone(observability.before_send({"logger": "django.security.DisallowedHost"}, {}))


class CaptureTests(SentryTestCase):
    def test_ignored_exceptions_are_dropped_and_others_sent(self):
        self.start()
        for error in (Http404(), PermissionDenied(), DisallowedHost()):
            sentry_sdk.capture_exception(error)
        self.assertEqual(self.events, [])
        sentry_sdk.capture_exception(ConnectionResetError("job socket"))  # no request: a real problem, kept
        self.assertEqual(len(self.events), 1)
        sentry_sdk.capture_exception(ValueError("real bug"))
        self.assertEqual(len(self.events), 2)
        self.assertEqual(self.events[1]["tags"]["host"], "worker")

    def test_local_variables_are_never_sent(self):
        self.start()

        def handler():
            first, contact = "Jo", "0770" + "0900123"  # noqa: F841
            raise ValueError("boom")

        try:
            handler()
        except ValueError:
            sentry_sdk.capture_exception()
        self.assertEqual(len(self.events), 1)
        self.assertFalse(any("vars" in f for e in self.events[0]["exception"]["values"] for f in e["stacktrace"]["frames"]))

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
