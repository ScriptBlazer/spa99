"""Postmark Open records (invite email opened) and the bounce log. Mocked: the test client plays Postmark, nothing leaves the machine."""
import base64
import json
from datetime import timedelta
from uuid import uuid4

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from mailings.models import Invite
from notifications import bouncelog
from notifications.models import EmailBounce, EmailSuppression
from system.tests.test_system import make_user, sign_in, unlocked_client

AUTH = "Basic " + base64.b64encode(b"pm:s3cret").decode()


@override_settings(POSTMARK_WEBHOOK_USER="pm", POSTMARK_WEBHOOK_PASSWORD="s3cret")
class PostmarkBase(TestCase):
    def setUp(self):
        cache.clear()

    def post(self, record):
        return Client().post("/postmark/webhook/", json.dumps(record), content_type="application/json", HTTP_AUTHORIZATION=AUTH)


class InviteOpenTests(PostmarkBase):
    def invite(self):
        return Invite.objects.create(email="a@x.com", status=Invite.SENT, batch_id=uuid4())

    def test_first_open_is_kept_and_a_repeat_changes_nothing(self):
        invite = self.invite()
        record = {"RecordType": "Open", "Email": "a@x.com", "Metadata": {"invite": invite.token}, "ReceivedAt": "2026-10-30T09:00:00Z"}
        self.assertEqual(self.post(record).status_code, 200)
        first = Invite.objects.get(pk=invite.pk)
        self.assertEqual((first.email_opened_at.isoformat(), first.status, first.opened_at), ("2026-10-30T09:00:00+00:00", Invite.SENT, None))
        self.post({**record, "ReceivedAt": "2026-10-31T09:00:00Z"})
        self.assertEqual(Invite.objects.get(pk=invite.pk).email_opened_at, first.email_opened_at)

    def test_bad_or_missing_metadata_is_ignored_with_200_and_never_matched_by_address(self):
        invite = self.invite()
        for metadata in (None, {}, {"invite": 123}, {"invite": ["x"]}, {"invite": "x" * 500}, {"invite": "nosuchtoken123"}, "text"):
            self.assertEqual(self.post({"RecordType": "Open", "Email": "a@x.com", "Metadata": metadata}).status_code, 200)
        self.assertIsNone(Invite.objects.get(pk=invite.pk).email_opened_at)

    def test_a_bad_date_falls_back_to_now(self):
        invite = self.invite()
        self.post({"RecordType": "Open", "Metadata": {"invite": invite.token}, "ReceivedAt": "yesterday"})
        self.assertLess(timezone.now() - Invite.objects.get(pk=invite.pk).email_opened_at, timedelta(minutes=1))


class BounceLogTests(PostmarkBase):
    def test_soft_and_hard_are_logged_but_only_hard_suppresses(self):
        self.post({"RecordType": "Bounce", "Type": "SoftBounce", "ID": 1, "Email": "Soft@X.com", "Details": "Mailbox full", "BouncedAt": "2026-10-29T10:00:00Z"})
        self.post({"RecordType": "Bounce", "Type": "HardBounce", "ID": 2, "Email": "hard@x.com", "MessageID": "m-1"})
        self.post({"RecordType": "SpamComplaint", "ID": 3, "Email": "spam@x.com"})
        kinds = {b.email: (b.kind, b.postmark_type) for b in EmailBounce.objects.all()}
        self.assertEqual(kinds, {"soft@x.com": ("soft", "SoftBounce"), "hard@x.com": ("hard", "HardBounce"), "spam@x.com": ("complaint", "SpamComplaint")})
        self.assertEqual(EmailBounce.objects.get(email="soft@x.com").received_at.isoformat(), "2026-10-29T10:00:00+00:00")
        self.assertEqual(sorted(EmailSuppression.objects.values_list("email", flat=True)), ["hard@x.com", "spam@x.com"])

    def test_the_same_postmark_record_is_stored_once(self):
        record = {"RecordType": "Bounce", "Type": "HardBounce", "ID": 9, "Email": "a@x.com"}
        self.post(record)
        self.post(record)
        self.assertEqual(EmailBounce.objects.count(), 1)

    def test_prune_removes_only_rows_older_than_a_year(self):
        old, new = timezone.now() - timedelta(days=400), timezone.now()
        EmailBounce.objects.create(email="o@x.com", kind="soft", received_at=old)
        EmailBounce.objects.create(email="n@x.com", kind="soft", received_at=new)
        self.assertEqual(bouncelog.prune(), 1)
        self.assertEqual(EmailBounce.objects.get().email, "n@x.com")


class BouncesPageTests(TestCase):
    def setUp(self):
        now = timezone.now()
        EmailBounce.objects.create(email="soft@x.com", kind="soft", postmark_type="SoftBounce", received_at=now)
        EmailBounce.objects.create(email="hard@x.com", kind="hard", postmark_type="HardBounce", received_at=now - timedelta(days=10))
        EmailSuppression.objects.create(email="hard@x.com", reason="hard_bounce", first_seen=now, last_seen=now)

    def test_developer_sees_the_log_filter_suppressed_badge_and_dashboard_count(self):
        client = unlocked_client(make_user())
        page = client.get("/emails/bounces/").content.decode()
        self.assertIn("soft@x.com", page)
        self.assertIn("hard@x.com", page)
        self.assertEqual(page.count(">Suppressed</span>"), 1)
        only = client.get("/emails/bounces/?kind=hard").content.decode()
        self.assertIn("hard@x.com", only)
        self.assertNotIn("soft@x.com", only)
        dashboard = client.get("/").content.decode()
        self.assertRegex(dashboard, r'data-system-bounces><a href="/emails/bounces/">1</a>')  # the 10 day old one is outside 7 days

    def test_lower_levels_get_404(self):
        client, _ = sign_in(make_user("office@example.com", system=False))
        self.assertEqual(client.get("/emails/bounces/").status_code, 404)
