"""SES bounce and complaint feedback through Amazon SNS. Mocked: no real AWS (the certificate download is patched)."""
import base64
import datetime
import json
import unittest
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from notifications import sns, suppression
from notifications.models import EmailLog, EmailSuppression
from notifications.services import send_templated
from system.models import SystemEvent
from system.tests.test_system import make_user, unlocked_client
from users import tasks

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from cryptography.x509.oid import NameOID
except ImportError:  # pragma: no cover - pip install -r requirements.txt provides it
    x509 = None

TOPIC = "arn:aws:sns:eu-west-2:123456789012:spa99-ses-feedback"
CERT_URL = "https://sns.eu-west-2.amazonaws.com/SimpleNotificationService-test.pem"
User = get_user_model()


def make_signed(message_type="Notification", version="2", **extra):
    """(message dict, certificate PEM): a message signed by a throwaway key, like SNS would."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "sns.test")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(1).not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=1))
            .sign(key, hashes.SHA256()))
    message = {"Type": message_type, "MessageId": "m1", "TopicArn": TOPIC, "Timestamp": "2026-10-25T10:00:00.000Z",
               "Message": "{}", "SignatureVersion": version, "SigningCertURL": CERT_URL, **extra}
    algorithm = hashes.SHA256() if version == "2" else hashes.SHA1()
    message["Signature"] = base64.b64encode(key.sign(sns.string_to_sign(message), padding.PKCS1v15(), algorithm)).decode()
    return message, cert.public_bytes(serialization.Encoding.PEM)


def ses_message(body):
    return {"Type": "Notification", "MessageId": "m1", "TopicArn": TOPIC, "Timestamp": "t", "Message": json.dumps(body)}


@unittest.skipIf(x509 is None, "cryptography is not installed")
class SignatureTests(TestCase):
    def setUp(self):
        cache.clear()

    def verify(self, message, pem):
        with mock.patch("notifications.sns._fetch", return_value=pem):
            sns.verify_signature(message)

    def test_valid_signatures_are_accepted_for_both_versions(self):
        for version in ("1", "2"):
            cache.clear()
            self.verify(*make_signed(version=version))
        cache.clear()
        self.verify(*make_signed("SubscriptionConfirmation", SubscribeURL="https://sns.eu-west-2.amazonaws.com/?x=1", Token="t"))
        cache.clear()
        self.verify(*make_signed(Subject="Hello"))  # Subject is part of what is signed when present

    def test_changed_message_wrong_certificate_and_bad_version_are_rejected(self):
        message, pem = make_signed()
        self.verify(message, pem)
        cache.clear()
        with self.assertRaises(sns.Rejected):
            self.verify({**message, "Message": '{"x": 1}'}, pem)
        cache.clear()
        with self.assertRaises(sns.Rejected):
            self.verify(message, make_signed()[1])
        with self.assertRaises(sns.Rejected):
            self.verify({**message, "SignatureVersion": "3"}, pem)
        with self.assertRaises(sns.Rejected):
            self.verify({**message, "Signature": "not base64!"}, pem)


class CertificateUrlTests(TestCase):
    def test_only_sns_https_hosts_are_trusted(self):
        for good in (CERT_URL, "https://sns.us-east-1.amazonaws.com/x.pem"):
            self.assertTrue(sns.trusted_sns_url(good), good)
        for bad in ("http://sns.eu-west-2.amazonaws.com/x.pem", "https://sns.eu-west-2.amazonaws.com.evil.com/x.pem",
                    "https://evil.com/sns.eu-west-2.amazonaws.com/x.pem", "https://xsns.eu-west-2.amazonaws.com/x.pem",
                    "https://sns.eu-west-2.amazonaws.com@evil.com/x.pem", "https://user@sns.eu-west-2.amazonaws.com/x.pem",
                    "https://sns.eu-west-2.amazonaws.com:8443/x.pem", "https://s3.eu-west-2.amazonaws.com/x.pem", "ftp://sns.eu-west-2.amazonaws.com/x.pem", ""):
            self.assertFalse(sns.trusted_sns_url(bad), bad)

    def test_an_evil_certificate_url_is_never_downloaded(self):
        cache.clear()
        with mock.patch("notifications.sns._fetch") as fetch:
            for url in ("https://evil.com/cert.pem", "https://sns.eu-west-2.amazonaws.com/cert.txt"):
                with self.assertRaises(sns.Rejected):
                    sns.signing_certificate(url)
        fetch.assert_not_called()


@override_settings(SES_SNS_TOPIC_ARN=TOPIC)
class EndpointTests(TestCase):
    def post(self, message):
        body = message if isinstance(message, str) else json.dumps(message)
        return Client().post("/ses/notifications/", body, content_type="text/plain; charset=UTF-8")

    def feedback(self, body):
        with mock.patch("notifications.sns.verify_signature"):
            return self.post(ses_message(body))

    def bounce(self, kind="Permanent", feedback_id="f1", email="Gone@Example.com"):
        return {"notificationType": "Bounce", "bounce": {"bounceType": kind, "bounceSubType": "General", "feedbackId": feedback_id,
                "bouncedRecipients": [{"emailAddress": email, "diagnosticCode": "550 no such user"}]}}

    @override_settings(SES_SNS_TOPIC_ARN="")
    def test_it_is_off_until_a_topic_is_set(self):
        self.assertEqual(self.post({}).status_code, 404)

    def test_bad_requests_are_refused(self):
        self.assertEqual(Client().get("/ses/notifications/").status_code, 405)
        self.assertEqual(self.post("not json").status_code, 403)
        self.assertEqual(self.post("[1]").status_code, 403)
        with mock.patch("notifications.sns.verify_signature") as verify:
            self.assertEqual(self.post({**ses_message({}), "TopicArn": "arn:aws:sns:eu-west-2:1:other"}).status_code, 403)
        verify.assert_not_called()  # the wrong topic is refused before any certificate is fetched
        self.assertEqual(self.post({**ses_message({}), "SignatureVersion": "2", "Signature": "AAAA", "SigningCertURL": "https://evil.com/c.pem"}).status_code, 403)
        self.assertEqual(self.post(" " * (sns.MAX_BODY_BYTES + 1)).status_code, 413)
        self.assertEqual(EmailSuppression.objects.count(), 0)

    def test_subscription_confirmation_calls_the_subscribe_url(self):
        url = "https://sns.eu-west-2.amazonaws.com/?Action=ConfirmSubscription&Token=t"
        message = {**ses_message({}), "Type": "SubscriptionConfirmation", "SubscribeURL": url, "Token": "t"}
        with mock.patch("notifications.sns.verify_signature"), mock.patch("notifications.sns._fetch") as fetch:
            self.assertEqual(self.post(message).status_code, 200)
            fetch.assert_called_once_with(url)
            fetch.reset_mock()
            self.assertEqual(self.post({**message, "SubscribeURL": "https://evil.com/confirm"}).status_code, 403)
            fetch.assert_not_called()

    def test_permanent_bounce_suppresses_and_transient_does_not(self):
        self.assertEqual(self.feedback(self.bounce("Transient")).status_code, 200)
        self.assertEqual(EmailSuppression.objects.count(), 0)
        self.assertEqual(self.feedback(self.bounce()).status_code, 200)
        row = EmailSuppression.objects.get()
        self.assertEqual((row.email, row.reason, row.count), ("gone@example.com", EmailSuppression.HARD_BOUNCE, 1))
        self.assertIn("550", row.detail)

    def test_complaint_suppresses_every_complained_address(self):
        self.feedback({"notificationType": "Complaint", "complaint": {"feedbackId": "c1", "complaintFeedbackType": "abuse",
                       "complainedRecipients": [{"emailAddress": "a@example.com"}, {"emailAddress": "B@example.com"}]}})
        self.assertEqual(set(EmailSuppression.objects.values_list("email", "reason")), {("a@example.com", "complaint"), ("b@example.com", "complaint")})

    def test_delivery_is_ignored_and_a_repeat_changes_nothing(self):
        self.feedback({"notificationType": "Delivery", "delivery": {"recipients": ["ok@example.com"]}})
        self.assertEqual(EmailSuppression.objects.count(), 0)
        self.feedback(self.bounce())
        self.feedback(self.bounce())  # SNS delivers at least once: the same feedback id is a repeat
        self.assertEqual(EmailSuppression.objects.get().count, 1)
        self.feedback(self.bounce(feedback_id="f2"))  # a different bounce for the same address
        self.assertEqual(EmailSuppression.objects.get().count, 2)
        self.feedback({"notificationType": "Complaint", "complaint": {"feedbackId": "c9", "complainedRecipients": [{"emailAddress": "gone@example.com"}]}})
        self.assertEqual(EmailSuppression.objects.get().reason, EmailSuppression.COMPLAINT)  # the stronger reason wins


class SendingGuardTests(TestCase):
    def test_every_account_email_skips_a_suppressed_address_without_raising(self):
        suppression.add("Gone@Example.com", EmailSuppression.HARD_BOUNCE, "f1")
        user = User.objects.create_user("gone@example.com", "Correct-horse-9")
        for task in (tasks.send_verification_email, tasks.send_password_reset_email, tasks.send_welcome_email, tasks.send_team_invite_email):
            with self.assertLogs("spa99.email", level="WARNING"):
                self.assertEqual(task(user.pk), EmailLog.SUPPRESSED, task.__name__)
        self.assertEqual(mail.outbox, [])
        self.assertEqual(EmailLog.objects.filter(status=EmailLog.SUPPRESSED).count(), 4)

    def test_other_recipients_still_get_the_email_and_a_suppressed_cc_is_dropped(self):
        suppression.add("gone@example.com", EmailSuppression.COMPLAINT, "c1")
        log = send_templated("verify", ["ok@example.com"], "Confirm", {"first_name": "A", "url": "u"}, cc=["GONE@example.com"])
        self.assertEqual(log.status, EmailLog.SENT)
        self.assertEqual((mail.outbox[0].to, mail.outbox[0].cc), (["ok@example.com"], []))

    def test_the_reset_form_answers_the_same_for_a_suppressed_address(self):
        suppression.add("gone@example.com", EmailSuppression.HARD_BOUNCE, "f1")
        User.objects.create_user("gone@example.com", "Correct-horse-9")
        User.objects.create_user("fine@example.com", "Correct-horse-9")
        client = Client()
        with self.captureOnCommitCallbacks(execute=True):
            first = client.post("/forgot-password/", {"email": "gone@example.com"})
            second = client.post("/forgot-password/", {"email": "fine@example.com"})
        self.assertEqual((first.status_code, first.content), (second.status_code, second.content))
        self.assertEqual([m.to for m in mail.outbox], [["fine@example.com"]])


class SystemSuppressionTests(TestCase):
    def setUp(self):
        self.row = suppression.add("gone@example.com", EmailSuppression.HARD_BOUNCE, "f1") and EmailSuppression.objects.get()

    def test_developer_sees_the_list_and_removing_is_audit_logged(self):
        client = unlocked_client(make_user())
        self.assertContains(client.get("/suppressions/"), "gone@example.com")
        self.assertEqual(client.post(f"/suppressions/{self.row.pk}/remove/").status_code, 302)
        self.assertFalse(suppression.is_suppressed("gone@example.com"))
        event = SystemEvent.objects.get(kind=SystemEvent.SUPPRESSION_REMOVED)
        self.assertEqual((event.user_label, event.detail["email"]), ("dev@example.com", "gone@example.com"))
        self.assertIn("gone@example.com", event.sentence)

    def test_below_developer_gets_404_and_nothing_is_removed(self):
        client = unlocked_client(make_user("dev@example.com"))
        office = make_user("office@example.com", system=False)
        from system.tests.test_system import sign_in

        office_client, _ = sign_in(office)
        self.assertEqual(office_client.get("/suppressions/").status_code, 404)
        self.assertEqual(office_client.post(f"/suppressions/{self.row.pk}/remove/").status_code, 404)
        self.assertTrue(suppression.is_suppressed("gone@example.com"))
        self.assertFalse(SystemEvent.objects.filter(kind=SystemEvent.SUPPRESSION_REMOVED).exists())
        self.assertEqual(client.get("/suppressions/").status_code, 200)
