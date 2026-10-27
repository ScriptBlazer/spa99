"""System > Emails: access, editing the automatic emails (logged, undoable), mailings and invites through the views, and the audit
events. Mocked: in-memory outbox, SES is the dev/locmem path or a patched boto3."""
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from mailings.models import Invite, Mailing, MailingRecipient
from notifications.models import EmailLog, NotificationTemplate
from plans.management.commands.seed_phase1 import seed_all
from system.models import SystemChange, SystemEvent
from system.tests.test_system import PASSWORD, make_user, sign_in, unlocked_client
from users.models import InterestRegistration
from plans.models import Plan

User = get_user_model()
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "emails-tests"}}
UUID = "00000000-0000-0000-0000-000000000000"
PATHS = ["/emails/", "/emails/automatic/", "/emails/automatic/verify/", "/emails/mailings/", "/emails/mailings/new/",
         "/emails/invites/", "/emails/invites/new/", f"/emails/mailings/{UUID}/", f"/emails/invites/{UUID}/"]
POSTS = ["/emails/automatic/verify/save/", "/emails/automatic/verify/preview/", "/emails/automatic/verify/test/", "/emails/automatic/verify/reset/",
         "/emails/mailings/preview/", f"/emails/mailings/{UUID}/send/", f"/emails/mailings/{UUID}/schedule/", f"/emails/mailings/{UUID}/cancel/",
         "/emails/invites/review/", "/emails/invites/send/", "/emails/ses/refresh/"]


def member(email, consent=True):
    user = User.objects.create_user(email, PASSWORD, first_name="Sam", marketing_consent=consent, email_verified_at=timezone.now())
    InterestRegistration.objects.create(user=user, plan=Plan.objects.get(slug="tier-2"))
    return user


class EmailsAccessTests(TestCase):
    def test_everyone_below_developer_gets_404_and_a_locked_developer_is_sent_to_unlock(self):
        office = make_user("office@example.com", system=False)
        for client in (Client(HTTP_HOST="system.localhost"), sign_in(office)[0]):
            for path in PATHS:
                self.assertEqual(client.get(path).status_code, 404, path)
            for path in POSTS:
                self.assertEqual(client.post(path).status_code, 404, path)
        locked, _ = sign_in(make_user())
        self.assertEqual(locked.get("/emails/mailings/").status_code, 302)
        self.assertEqual(locked.post("/emails/automatic/verify/reset/").status_code, 302)
        self.assertFalse(NotificationTemplate.objects.exists())


class AutomaticEmailTests(TestCase):
    def setUp(self):
        seed_all()
        self.dev = make_user()
        self.client = unlocked_client(self.dev)

    def test_list_edit_context_and_save_through_the_change_log_with_undo(self):
        listing = self.client.get("/emails/automatic/").context["emails"]
        self.assertEqual({e["key"] for e in listing}, {"verify", "welcome", "password_reset", "password_changed", "team_invite", "gold_ack", "gold_invite", "gold_active",
                                                     "invite", "gold_approver", "gold_approver_repeat", "gold_final", "gold_sent_back", "gold_respond", "gold_declined"})
        self.assertNotIn("mailing", {e["key"] for e in listing})
        page = self.client.get("/emails/automatic/verify/")
        self.assertEqual([p["name"] for p in page.context["spec"]["placeholders"]], ["first_name", "valid_for"])
        self.assertTrue(page.context["spec"]["button_required"])
        self.assertIn("Please confirm your email address", page.context["form"].initial["body"])  # the editor shows what is sent
        bad = self.client.post("/emails/automatic/verify/save/", {"subject": "Hi {zzz}", "body": "No link {first_name}"})
        self.assertEqual(bad.status_code, 400)
        self.assertIn("subject", bad.context["form"].errors)
        self.assertTrue(any("button" in m for m in bad.context["form"].errors["body"]))
        self.assertEqual(NotificationTemplate.objects.get(key="verify").body, "")
        self.client.post("/emails/automatic/verify/save/", {"subject": "Please confirm, {first_name}", "body": "Hi {first_name}\n\n{button}\n\nBye"})
        row = NotificationTemplate.objects.get(key="verify")
        self.assertEqual((row.subject, row.body), ("Please confirm, {first_name}", "Hi {first_name}\n\n{button}\n\nBye"))
        entries = SystemChange.objects.filter(model_label="notifications.notificationtemplate", section="emails")
        self.assertEqual(sorted(entries.values_list("field", flat=True)), ["body", "subject"])
        self.client.post(f"/changes/{entries.get(field='body').pk}/undo/")
        row.refresh_from_db()
        self.assertEqual(row.body, "")  # undo put the old (default) value back as a new logged change
        # saving the built-in default stores blank, so the email keeps following the default
        self.client.post("/emails/automatic/verify/save/", {"subject": row.subject, "body": page.context["default_body"].replace("\n", "\r\n")})
        self.assertEqual(NotificationTemplate.objects.get(key="verify").body, "")

    def test_reset_to_default_is_one_logged_change_and_a_send_uses_the_new_wording(self):
        self.client.post("/emails/automatic/verify/save/", {"subject": "Custom", "body": "Custom {first_name}\n\n{button}"})
        from users.tasks import send_verification_email
        user = member("v@example.com")
        User.objects.filter(pk=user.pk).update(email_verified_at=None)
        send_verification_email(user.pk)
        self.assertEqual((mail.outbox[0].subject, "Custom Sam" in mail.outbox[0].body), ("Custom", True))
        self.client.post("/emails/automatic/verify/reset/")
        row = NotificationTemplate.objects.get(key="verify")
        self.assertEqual((row.subject, row.body), ("Confirm your email for Spa 99", ""))
        self.assertTrue(SystemChange.objects.filter(sentence__startswith="Changed verify"))
        send_verification_email(user.pk)
        self.assertEqual(mail.outbox[1].subject, "Confirm your email for Spa 99")
        self.assertIn("Please confirm your email address", mail.outbox[1].body)

    def test_preview_returns_html_and_text_or_errors(self):
        good = self.client.post("/emails/automatic/verify/preview/", {"subject": "Hi {first_name}", "body": "<i>x</i> {first_name}\n\n{button}"}).json()
        self.assertTrue(good["ok"])
        self.assertEqual(good["subject"], "Hi James")
        self.assertIn("&lt;i&gt;x&lt;/i&gt; James", good["html"])
        self.assertIn("example-link", good["text"])
        bad = self.client.post("/emails/automatic/verify/preview/", {"subject": "Hi", "body": "{nope}"}).json()
        self.assertEqual((bad["ok"], bad["html"]), (False, ""))
        self.assertIn("body", bad["errors"])

    @override_settings(CACHES=LOCMEM)
    def test_test_send_goes_only_to_the_developer_is_logged_and_rate_limited(self):
        cache.clear()
        for _ in range(5):
            self.assertEqual(self.client.post("/emails/automatic/welcome/test/", HTTP_ACCEPT="application/json").status_code, 200)
        self.assertEqual({tuple(m.to) for m in mail.outbox}, {("dev@example.com",)})
        self.assertTrue(mail.outbox[0].subject.startswith("[Test] "))
        self.assertEqual(EmailLog.objects.filter(template="welcome", status="sent").count(), 5)
        self.assertEqual(SystemEvent.objects.filter(kind=SystemEvent.EMAIL_TEST).count(), 5)
        self.assertEqual(self.client.post("/emails/automatic/welcome/test/", HTTP_ACCEPT="application/json").status_code, 429)
        self.assertEqual(self.client.post("/emails/automatic/gold_final/test/", HTTP_ACCEPT="application/json").status_code, 400)  # no test for the structured emails
        cache.clear()

    def test_overview_gives_the_state_and_cheap_counts(self):
        EmailLog.objects.create(to="a@example.com", subject="s", template="verify", status="sent", sent_at=timezone.now())
        context = self.client.get("/emails/").context
        self.assertEqual(context["ses"]["mode"], "dev")
        self.assertEqual((context["stats"]["sent_today"], context["stats"]["sent_week"], context["stats"]["suppressed_total"]), (1, 1, 0))


class MailingViewTests(TestCase):
    def setUp(self):
        seed_all()
        self.dev = make_user()
        self.client = unlocked_client(self.dev)
        for i in range(3):
            member(f"m{i}@example.com")

    def create(self, **over):
        data = {"name": "Opening", "subject": "Hello {first_name}", "body": "Hi {first_name}\n\nSoon.", "kind": "news", "group": "everyone", **over}
        response = self.client.post("/emails/mailings/new/", data)
        return Mailing.objects.get() if response.status_code == 302 else response

    def test_create_count_send_and_the_audit_event_with_counts(self):
        self.assertEqual(self.client.get("/emails/mailings/count/", {"group": "everyone", "kind": "news"}).json()["count"], 3)
        self.assertEqual(self.client.get("/emails/mailings/count/", {"group": "tier"}).json()["count"], None)
        bad = self.create(body="Hi {nope}")
        self.assertEqual(bad.status_code, 400)
        mailing = self.create()
        self.assertEqual((mailing.status, mailing.created_by), ("draft", self.dev))
        detail = self.client.get(f"/emails/mailings/{mailing.pk}/").context
        self.assertEqual((detail["live_count"], detail["can_send"], detail["progress"]["total"]), (3, True, 0))
        stale = self.client.post(f"/emails/mailings/{mailing.pk}/send/", {"expected_count": "9"}, HTTP_ACCEPT="application/json")
        self.assertEqual(stale.status_code, 400)  # the person saw another number: nothing sent
        self.assertEqual(len(mail.outbox), 0)
        self.client.post(f"/emails/mailings/{mailing.pk}/send/", {"expected_count": "3"})
        mailing.refresh_from_db()
        self.assertEqual((mailing.status, mailing.sent_count, len(mail.outbox)), ("sent", 3, 3))
        event = SystemEvent.objects.get(kind=SystemEvent.MAILING_SENT)
        self.assertEqual((event.detail["recipients"], event.detail["group"], event.user), (3, "everyone", self.dev))
        progress = self.client.get(f"/emails/mailings/{mailing.pk}/progress/").json()
        self.assertEqual((progress["status"], progress["sent"], progress["percent"], progress["finished"]), ("sent", 3, 100, True))
        self.assertEqual(self.client.post(f"/emails/mailings/{mailing.pk}/edit/", {"name": "x"}).status_code, 302)  # a sent mailing cannot be edited
        self.assertEqual(Mailing.objects.get().name, "Opening")

    @mock.patch("mailings.sending.enqueue")
    def test_schedule_and_cancel_write_events(self, enqueue):
        mailing = self.create()
        when = (timezone.localtime() + timezone.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        self.client.post(f"/emails/mailings/{mailing.pk}/schedule/", {"scheduled_at": when})
        mailing.refresh_from_db()
        self.assertEqual(mailing.status, "scheduled")
        scheduled = SystemEvent.objects.get(kind=SystemEvent.MAILING_SCHEDULED)
        self.assertEqual(scheduled.detail["recipients_now"], 3)
        self.client.post(f"/emails/mailings/{mailing.pk}/cancel/")
        mailing.refresh_from_db()
        self.assertEqual(mailing.status, "cancelled")
        self.assertEqual(SystemEvent.objects.get(kind=SystemEvent.MAILING_CANCELLED).detail["was"], "scheduled")
        self.assertEqual(self.client.post(f"/emails/mailings/{mailing.pk}/schedule/", {"scheduled_at": "soon"}, HTTP_ACCEPT="application/json").status_code, 400)

    @override_settings(DEBUG=False, EMAIL_BACKEND="notifications.backends.SesBackend", CACHES=LOCMEM)
    def test_sandbox_refuses_sends_with_a_clear_message_and_no_event(self):
        cache.clear()
        client = mock.Mock()
        client.get_account.return_value = {"ProductionAccessEnabled": False, "SendQuota": {}}
        with mock.patch("boto3.client", return_value=client):
            mailing = self.create()
            self.assertFalse(self.client.get(f"/emails/mailings/{mailing.pk}/").context["can_send"])
            response = self.client.post(f"/emails/mailings/{mailing.pk}/send/", HTTP_ACCEPT="application/json")
            invites = self.client.post("/emails/invites/send/", {"text": "a@example.com"}, HTTP_ACCEPT="application/json")
        for answer in (response, invites):
            self.assertEqual(answer.status_code, 400)
            self.assertIn("sandbox", answer.json()["message"])
        self.assertFalse(SystemEvent.objects.filter(kind__in=[SystemEvent.MAILING_SENT, SystemEvent.INVITES_SENT]).exists())
        self.assertFalse(MailingRecipient.objects.exists() or Invite.objects.exists())
        cache.clear()

    def test_invites_review_then_send_writes_the_event_and_tracks_the_batch(self):
        member("already@example.com")
        review = self.client.post("/emails/invites/review/", {"text": "Al Smith,al@example.com\nAlready,already@example.com\nbad"})
        self.assertEqual((review.context["report"]["ok"], review.context["report"]["counts"]["member"], review.context["report"]["counts"]["invalid"]), (1, 1, 1))
        self.assertFalse(Invite.objects.exists())  # review writes nothing
        too_big = self.client.post("/emails/invites/review/", {"text": "x@example.com\n" + "y" * 1_100_000})
        self.assertEqual(too_big.status_code, 400)
        sent = self.client.post("/emails/invites/send/", {"text": review.context["text"], "expected_ok": "1"})
        batch = Invite.objects.first().batch_id
        self.assertRedirects(sent, f"/emails/invites/{batch}/", fetch_redirect_response=False)
        self.assertEqual([m.to for m in mail.outbox], [["al@example.com"]])
        event = SystemEvent.objects.get(kind=SystemEvent.INVITES_SENT)
        self.assertEqual((event.detail["invites"], event.detail["skipped"]), (1, 1))
        detail = self.client.get(f"/emails/invites/{batch}/").context
        self.assertEqual((detail["summary"]["sent"], detail["summary"]["skipped"]), (1, 1))
        self.assertEqual(self.client.get(f"/emails/invites/{batch}/progress/").json()["sent"], 1)


class MailingEditorPageTests(TestCase):
    """The parts editor's page (docs/design/EMAIL-BUILDER-UI.md): what the template hands the script, and the Start from choice."""

    def setUp(self):
        seed_all()
        self.client = unlocked_client(make_user())

    def test_a_new_page_has_the_start_choice_and_the_editor_data_without_inline_script(self):
        page = self.client.get("/emails/mailings/new/")
        html = page.content.decode()
        self.assertContains(page, "Start from")
        self.assertContains(page, 'value="booking_open"')
        self.assertContains(page, 'name="blocks"')
        self.assertContains(page, 'id="se-blocks"')
        self.assertContains(page, 'id="se-block-types"')
        self.assertNotIn('name="body"', html)  # the old Body box is gone
        self.assertEqual(page.context["blocks"], [])
        self.assertContains(page, f'data-max-parts="{page.context["block_max_parts"]}"')
        self.assertContains(page, "system-icons.svg")

    def test_the_booking_starter_fills_the_parts_and_ticks_its_card(self):
        page = self.client.get("/emails/mailings/new/?start=booking_open")
        self.assertEqual([part["type"] for part in page.context["blocks"]], ["heading", "paragraph", "button", "small_print"])
        self.assertContains(page, 'data-start="booking_open"')
        self.assertContains(page, 'value="booking_open" checked')
        self.assertContains(page, "Booking is open at Spa 99")  # the subject, from the starter

    def test_an_old_draft_opens_as_paragraphs_with_the_split_note_and_no_start_choice(self):
        mailing = Mailing.objects.create(name="Old", subject="Hi", body="One\n\nTwo", kind="news", group="everyone")
        page = self.client.get(f"/emails/mailings/{mailing.pk}/edit/")
        self.assertEqual(page.context["blocks"], [{"type": "paragraph", "text": "One"}, {"type": "paragraph", "text": "Two"}])
        self.assertContains(page, "This draft was one block of text.")
        self.assertNotContains(page, "Start from")

    def test_a_draft_with_parts_has_no_split_note(self):
        mailing = Mailing.objects.create(name="New", subject="Hi", body="", blocks=[{"type": "heading", "text": "Hello"}], kind="news", group="everyone")
        page = self.client.get(f"/emails/mailings/{mailing.pk}/edit/")
        self.assertNotContains(page, "This draft was one block of text.")
        self.assertEqual(page.context["blocks"], [{"type": "heading", "text": "Hello"}])
        self.assertTrue(page.context["image_view_base"].endswith("/email-image/"))
