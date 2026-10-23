from unittest import mock

from django.core import mail
from django.test import SimpleTestCase, TestCase

from notifications.backends import SesBackend
from notifications.models import EmailLog
from notifications.services import send_templated


class SendTemplatedTests(TestCase):
    def test_sends_html_and_text_with_reply_to_and_logs_it(self):
        log = send_templated("verify", ["a@example.com"], "Confirm", {"first_name": "Al & Co", "url": "http://x/y?a=1&b=2"})
        self.assertEqual(log.status, EmailLog.SENT)
        message = mail.outbox[0]
        self.assertEqual(message.reply_to, ["from@example.test"])
        self.assertIn("http://x/y?a=1&b=2", message.body)  # the plain text version is not HTML-escaped
        self.assertIn("Al &amp; Co", message.alternatives[0][0])  # the HTML version is
        self.assertEqual(EmailLog.objects.get().subject, "Confirm")

    def test_failure_is_logged_not_raised(self):
        with mock.patch("notifications.services.EmailMultiAlternatives.send", side_effect=OSError("a@example.com refused")):
            with self.assertLogs("spa99.email", level="ERROR") as captured:
                log = send_templated("verify", ["a@example.com"], "Confirm", {"first_name": "A", "url": "u"})
        self.assertEqual((log.status, log.sent_at), (EmailLog.FAILED, None))
        self.assertIn("refused", log.error)
        output = "\n".join(captured.output)
        self.assertIn(f"email log {log.pk}", output)
        self.assertNotIn("a@example.com", output)  # personal data stays out of the logs


class SesBackendTests(SimpleTestCase):
    def test_sends_the_raw_message_to_every_recipient_through_the_client(self):
        client = mock.Mock()
        backend = SesBackend(client=client)
        message = mock.Mock()
        message.recipients.return_value = ["a@example.com", "cc@example.com"]
        message.message.return_value.as_bytes.return_value = b"raw"
        self.assertEqual(backend.send_messages([message]), 1)
        client.send_email.assert_called_once_with(
            Destination={"ToAddresses": ["a@example.com", "cc@example.com"]}, Content={"Raw": {"Data": b"raw"}}
        )

    def test_errors_raise_unless_silent(self):
        client = mock.Mock()
        client.send_email.side_effect = RuntimeError("denied")
        message = mock.Mock()
        message.recipients.return_value = ["a@example.com"]
        with self.assertRaises(RuntimeError):
            SesBackend(client=client).send_messages([message])
        self.assertEqual(SesBackend(client=client, fail_silently=True).send_messages([message]), 0)
