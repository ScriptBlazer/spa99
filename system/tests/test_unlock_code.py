"""The lock code: the only thing /unlock/ asks for, compared in constant time, never logged."""
import logging

from django.test import TestCase, override_settings

from system.models import SystemEvent
from system.tests.test_system import PASSWORD, make_user, sign_in

CODE = "493021"


@override_settings(SYSTEM_UNLOCK_CODE=CODE)
class UnlockCodeTests(TestCase):
    def setUp(self):
        self.client, _ = sign_in(make_user())

    def attempt(self, **data):
        return self.client.post("/unlock/", data)

    def locked(self):
        return self.client.get("/changes/").status_code == 302

    def test_the_code_alone_unlocks_and_the_form_does_not_ask_for_a_password(self):
        page = self.client.get("/unlock/")
        self.assertNotContains(page, 'name="password"')
        self.assertContains(page, 'name="code"')
        self.assertContains(page, 'inputmode="numeric"')
        self.assertContains(page, 'autocomplete="one-time-code"')
        self.assertContains(page, "Enter your lock code")
        self.assertTrue(self.attempt(code=CODE).status_code == 302 and not self.locked())
        self.assertTrue(SystemEvent.objects.filter(kind="unlock").exists())

    def test_a_password_is_not_a_code(self):
        response = self.attempt(password=PASSWORD)
        self.assertEqual((response.status_code, response.context["error"].startswith("Wrong code.")), (200, True))
        self.assertTrue(self.locked())
        self.assertEqual(self.attempt(code="000000").status_code, 200)
        event = SystemEvent.objects.filter(kind="unlock_failed").order_by("created_at").first()
        self.assertEqual(event.detail, {"reason": "code"})

    def test_the_code_never_reaches_logs_or_audit(self):
        with self.assertLogs(level=logging.DEBUG) as logs:
            logging.getLogger("spa99.test").info("marker")
            self.attempt(code="111111")
            self.attempt(code=CODE)
        text = "\n".join(logs.output)
        self.assertNotIn(CODE, text)
        self.assertNotIn("111111", text)
        for event in SystemEvent.objects.all():
            self.assertNotIn(CODE, f"{event.sentence} {event.detail}")
            self.assertNotIn("111111", f"{event.sentence} {event.detail}")


class NoCodeConfiguredTests(TestCase):
    """Dev and CI only: prod refuses to start without a code (config.settings.prod)."""

    def test_without_a_code_the_signed_in_developer_just_presses_unlock(self):
        client, _ = sign_in(make_user())
        self.assertNotContains(client.get("/unlock/"), 'name="code"')
        self.assertEqual(client.post("/unlock/").status_code, 302)
        self.assertEqual(client.get("/changes/").status_code, 200)
