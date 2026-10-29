"""Editable email wording (placeholders, escaping, defaults) and the SES production gate. Mocked: no real AWS."""
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from notifications import emailbody, ses
from notifications.models import NotificationTemplate
from notifications.services import preview_email, send_templated

VERIFY = emailbody.SPECS["verify"]
SES_BACKEND = "notifications.backends.SesBackend"
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "ses-tests"}}


class PlaceholderTests(SimpleTestCase):
    def test_unknown_placeholder_missing_button_and_stray_braces_are_field_errors(self):
        errors = emailbody.validate(VERIFY, subject="Hi {nope}", body="Hello {first_name} {oops} {button")
        self.assertIn("Unknown placeholder {nope}", errors["subject"][0])
        self.assertTrue(any("Unknown placeholder {oops}" in m for m in errors["body"]))
        self.assertTrue(any("{ or }" in m for m in errors["body"]))
        self.assertTrue(any("Add {button}" in m for m in errors["body"]))  # verify needs its link
        self.assertEqual(emailbody.validate(VERIFY, body="Hello {first_name}\n\n{button}", subject="Hi {first_name}"), {})
        self.assertEqual(emailbody.validate(VERIFY, body="  "), {})  # blank = the default
        self.assertIn("body", emailbody.validate(emailbody.SPECS["gold_ack"], body="Hi {button}"))  # that email has no link
        self.assertIn("body", emailbody.validate(emailbody.SPECS["gold_final"], body="Anything"))  # subject-only email

    def test_every_default_body_passes_its_own_validation(self):
        for spec in emailbody.listed_specs():
            if spec.editable:
                self.assertEqual(emailbody.validate(spec, body=spec.default_body), {}, spec.key)


class RenderTests(TestCase):
    def test_preview_escapes_html_in_the_text_and_in_values(self):
        result = preview_email("verify", "Hi {first_name}", "<b>Hello</b> {first_name}\n\n{button}")
        self.assertIn("&lt;b&gt;Hello&lt;/b&gt; James", result["html"])
        self.assertNotIn("<b>Hello</b>", result["html"])
        self.assertEqual(result["subject"], "Hi James")
        self.assertIn("<b>Hello</b> James", result["text"])  # plain text is not escaped
        send_templated("verify", ["a@example.com"], "S", {"first_name": "<script>x</script>", "url": "https://x.test/?a=1&b=2"})
        html = mail.outbox[0].alternatives[0][0]
        self.assertIn("&lt;script&gt;", html)
        self.assertIn('href="https://x.test/?a=1&amp;b=2"', html)  # the button link, escaped

    def test_button_and_blank_paragraphs(self):
        html, text = emailbody.render(emailbody.SPECS["welcome"], "A\n\n{discount_line}\n\n{button}\n\nB", {"discount_line": ""}, button_url="")
        self.assertEqual(text, "A\n\nB")  # an empty optional line leaves no gap; no button when no link

    def test_stored_body_is_used_and_an_invalid_one_falls_back_to_the_default(self):
        row = NotificationTemplate.objects.create(key="verify", subject="Confirm")
        row.body = "Custom for {first_name}.\n\n{button}"
        row.save()
        send_templated("verify", ["a@example.com"], "S", {"first_name": "Al", "url": "https://x.test/v/"})
        self.assertIn("Custom for Al.", mail.outbox[0].body)
        row.body = "Broken {nope}"  # e.g. edited in the Django admin: never breaks a send
        row.save()
        send_templated("verify", ["a@example.com"], "S", {"first_name": "Al", "url": "https://x.test/v/"})
        self.assertIn("Please confirm your email address", mail.outbox[1].body)


@override_settings(DEBUG=False, EMAIL_BACKEND=SES_BACKEND, CACHES=LOCMEM)
class SesGateTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def account(self, production, **quota):
        client = mock.Mock()
        client.get_account.return_value = {"ProductionAccessEnabled": production, "SendQuota": {
            "Max24HourSend": 50000.0, "SentLast24Hours": 12.0, "MaxSendRate": 14.0, **quota}}
        return mock.patch("boto3.client", return_value=client), client

    def test_production_allows_and_is_cached_for_an_hour(self):
        patch, client = self.account(True)
        with patch:
            first, second = ses.ses_status(), ses.ses_status()
        self.assertEqual((first["mode"], first["allowed"], first["max_24h"], first["sent_24h"], first["max_rate"]), ("production", True, 50000.0, 12.0, 14.0))
        self.assertEqual(second["mode"], "production")
        client.get_account.assert_called_once()  # the second answer came from the cache
        with patch:
            ses.require_sending_allowed()

    def test_sandbox_refuses_with_a_clear_message(self):
        patch, _ = self.account(False, Max24HourSend=200.0)
        with patch:
            status = ses.ses_status()
            with self.assertRaises(ses.SendingRefused) as refused:
                ses.require_sending_allowed()
        self.assertEqual((status["mode"], status["allowed"], status["max_24h"]), ("sandbox", False, 200.0))
        self.assertIn("sandbox", str(refused.exception))

    def test_an_error_is_unknown_never_raised_and_refuses(self):
        with mock.patch("boto3.client", side_effect=RuntimeError("no credentials")):
            with self.assertLogs("spa99.email", level="ERROR"):
                status = ses.ses_status()
            with self.assertRaises(ses.SendingRefused):
                ses.require_sending_allowed()
        self.assertEqual((status["mode"], status["allowed"]), ("unknown", False))

    @override_settings(DEBUG=True, EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    def test_a_console_backend_is_dev_and_allowed_without_calling_aws(self):
        with mock.patch("boto3.client") as client:
            status = ses.ses_status()
        self.assertEqual((status["mode"], status["allowed"]), ("dev", True))
        client.assert_not_called()

    @override_settings(DEBUG=True, EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend", EMAIL_HOST="smtp.postmarkapp.com",
                       EMAIL_HOST_PASSWORD="secret-token")
    def test_another_provider_is_allowed_whatever_DEBUG_says_and_shows_no_credentials(self):
        with mock.patch("boto3.client") as client:
            status = ses.ses_status()
            ses.require_sending_allowed()
        client.assert_not_called()
        self.assertEqual((status["mode"], status["allowed"], status["max_24h"]), ("provider", True, None))
        self.assertEqual(status["provider"], "Sending through Postmark \u2713")
        self.assertNotIn("secret-token", str(status))

    @override_settings(DEBUG=True)
    def test_ses_is_gated_even_when_DEBUG_is_on(self):
        with mock.patch("boto3.client") as client:
            client.return_value.get_account.return_value = {"ProductionAccessEnabled": False}
            self.assertEqual(ses.ses_status()["mode"], "sandbox")


class BackendCheckTests(TestCase):
    @override_settings(EMAIL_BACKEND="notifications.backends.SesBakend", CACHES=LOCMEM)
    def test_a_mistyped_ses_path_refuses_sending(self):
        status = ses.ses_status()
        self.assertEqual((status["mode"], status["allowed"]), ("unknown", False))
        self.assertIn("mistyped", status["message"])

    @override_settings(EMAIL_BACKEND="nowhere.Backend", CACHES=LOCMEM)
    def test_a_backend_that_cannot_be_loaded_refuses_sending(self):
        self.assertFalse(ses.ses_status()["allowed"])

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend", EMAIL_HOST="localhost")
    def test_a_provider_with_no_host_warns_but_is_allowed(self):
        status = ses.ses_status()
        self.assertEqual((status["mode"], status["allowed"]), ("provider", True))
        self.assertIn("incomplete", status["warning"])
