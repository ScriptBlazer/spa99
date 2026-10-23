"""The lock code: asked with the password, compared in constant time, one generic error, never logged."""
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

    def test_right_password_and_right_code_unlock(self):
        self.assertTrue(self.attempt(password=PASSWORD, code=CODE).status_code == 302 and not self.locked())
        self.assertTrue(SystemEvent.objects.filter(kind="unlock").exists())

    def test_a_wrong_code_is_refused_with_the_generic_error_and_logged_as_code(self):
        response = self.attempt(password=PASSWORD, code="000000")
        self.assertEqual((response.status_code, response.context["error"]), (200, "Password or code is wrong."))
        self.assertTrue(self.locked())
        self.assertEqual(self.attempt(password=PASSWORD).context["error"], "Password or code is wrong.")  # no code at all
        event = SystemEvent.objects.filter(kind="unlock_failed").order_by("created_at").first()
        self.assertEqual(event.detail, {"reason": "code"})

    def test_a_wrong_password_is_refused_with_the_same_error_and_logged_as_password(self):
        response = self.attempt(password="wrong", code=CODE)
        self.assertEqual(response.context["error"], "Password or code is wrong.")
        self.assertTrue(self.locked())
        self.assertEqual(SystemEvent.objects.get(kind="unlock_failed").detail, {"reason": "password"})

    def test_the_code_field_is_on_the_form_and_the_code_never_reaches_logs_or_audit(self):
        self.assertContains(self.client.get("/unlock/"), 'name="code"')
        with self.assertNoLogs(level=logging.DEBUG) if False else self.assertLogs(level=logging.DEBUG) as logs:
            logging.getLogger("spa99.test").info("marker")
            self.attempt(password="wrong", code="111111")
            self.attempt(password=PASSWORD, code=CODE)
        text = "\n".join(logs.output)
        self.assertNotIn(CODE, text)
        self.assertNotIn("111111", text)
        for event in SystemEvent.objects.all():
            self.assertNotIn(CODE, f"{event.sentence} {event.detail}")
            self.assertNotIn("111111", f"{event.sentence} {event.detail}")


class NoCodeConfiguredTests(TestCase):
    def test_without_a_code_unlock_is_password_only_and_the_field_is_hidden(self):
        client, _ = sign_in(make_user())
        self.assertNotContains(client.get("/unlock/"), 'name="code"')
        self.assertEqual(client.post("/unlock/", {"password": PASSWORD}).status_code, 302)
        self.assertEqual(client.get("/changes/").status_code, 200)
