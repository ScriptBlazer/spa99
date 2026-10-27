"""Postmark bounce and spam-complaint webhook. Mocked: the test client plays Postmark, nothing leaves the machine."""
import base64
import json

from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from notifications.models import EmailSuppression

URL = "/postmark/webhook/"


def basic(user="pm", password="s3cret"):
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


@override_settings(POSTMARK_WEBHOOK_USER="pm", POSTMARK_WEBHOOK_PASSWORD="s3cret")
class PostmarkFeedbackTests(TestCase):
    def setUp(self):
        cache.clear()

    def post(self, record, auth=None):
        headers = {"HTTP_AUTHORIZATION": auth or basic()}
        return Client().post(URL, json.dumps(record), content_type="application/json", **headers)

    def bounce(self, kind="HardBounce", **extra):
        return {"RecordType": "Bounce", "Type": kind, "ID": 1, "Email": "Gone@Example.com", "Inactive": False, **extra}

    def test_hard_bounce_is_suppressed_lower_case(self):
        self.assertEqual(self.post(self.bounce(Details="550 no such user")).status_code, 200)
        row = EmailSuppression.objects.get()
        self.assertEqual((row.email, row.reason), ("gone@example.com", EmailSuppression.HARD_BOUNCE))

    def test_spam_complaint_is_suppressed_and_replaces_a_bounce_reason(self):
        self.post(self.bounce())
        self.post({"RecordType": "SpamComplaint", "ID": 2, "Email": "gone@example.com"})
        row = EmailSuppression.objects.get()
        self.assertEqual((row.reason, row.count), (EmailSuppression.COMPLAINT, 2))

    def test_soft_and_transient_bounces_are_ignored_but_answer_200(self):
        for kind in ("SoftBounce", "Transient", "AutoResponder"):
            self.assertEqual(self.post(self.bounce(kind)).status_code, 200)
        self.assertEqual(self.post({"RecordType": "Delivery", "Email": "a@b.com"}).status_code, 200)
        self.assertFalse(EmailSuppression.objects.exists())

    def test_a_bounce_that_deactivated_the_address_is_stored(self):
        self.post(self.bounce("SoftBounce", Inactive=True))
        self.assertEqual(EmailSuppression.objects.get().reason, EmailSuppression.HARD_BOUNCE)

    def test_repeat_delivery_changes_nothing_but_a_new_bounce_updates_last_seen(self):
        self.post(self.bounce())
        first = EmailSuppression.objects.get()
        self.post(self.bounce())  # Postmark retry: same ID
        self.assertEqual(EmailSuppression.objects.get().count, 1)
        self.post(self.bounce(ID=7))
        later = EmailSuppression.objects.get()
        self.assertEqual(later.count, 2)
        self.assertGreaterEqual(later.last_seen, first.last_seen)
        self.assertEqual(later.first_seen, first.first_seen)

    def test_wrong_or_missing_credentials_get_401_and_store_nothing(self):
        self.assertEqual(self.post(self.bounce(), auth=basic("pm", "nope")).status_code, 401)
        self.assertEqual(self.post(self.bounce(), auth=basic("other", "s3cret")).status_code, 401)
        self.assertEqual(self.post(self.bounce(), auth="Bearer x").status_code, 401)
        self.assertEqual(Client().post(URL, "{}", content_type="application/json").status_code, 401)
        self.assertFalse(EmailSuppression.objects.exists())

    def test_bad_body_is_400_and_get_is_405(self):
        self.assertEqual(Client().post(URL, "nope", content_type="application/json", HTTP_AUTHORIZATION=basic()).status_code, 400)
        self.assertEqual(Client().get(URL).status_code, 405)

    def test_off_with_404_unless_both_values_are_set(self):
        for user, password in (("", ""), ("pm", ""), ("", "s3cret")):
            with override_settings(POSTMARK_WEBHOOK_USER=user, POSTMARK_WEBHOOK_PASSWORD=password):
                self.assertEqual(self.post(self.bounce()).status_code, 404)
        self.assertFalse(EmailSuppression.objects.exists())

    def test_junk_records_are_ignored_with_200(self):
        for record in ({"RecordType": "Bounce", "Type": "HardBounce"},
                       {"RecordType": "Bounce", "Type": "HardBounce", "Email": 123},
                       {"RecordType": "Bounce", "Type": "HardBounce", "Email": ["a@b.com"]},
                       {"RecordType": "SpamComplaint", "Email": {"a": 1}},
                       {"RecordType": "Bounce", "Type": 5, "Email": "a@b.com"},
                       {"RecordType": ["Bounce"], "Email": "a@b.com"},
                       self.bounce(Email="@"), self.bounce(Email="a b@c d"), self.bounce(Email="a\x00@b.com")):
            self.assertEqual(self.post(record).status_code, 200, record)
        self.assertFalse(EmailSuppression.objects.exists())

    def test_unsubscribe_bounce_is_stored_as_a_complaint(self):
        self.post(self.bounce("Unsubscribe"))
        self.assertEqual(EmailSuppression.objects.get().reason, EmailSuppression.COMPLAINT)

    def test_oversize_body_is_413(self):
        big = "x" * (256 * 1024 + 1)
        self.assertEqual(Client().post(URL, big, content_type="application/json", HTTP_AUTHORIZATION=basic()).status_code, 413)

    def test_malformed_credentials_get_401(self):
        for header in ("Basic !!!notbase64", "Basic " + base64.b64encode(b"pm").decode(), "Basic", basic("pm", "")):
            self.assertEqual(self.post(self.bounce(), auth=header).status_code, 401, header)
