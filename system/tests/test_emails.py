"""System > Emails: access, editing the automatic emails (logged, undoable), mailings and invites through the views, and the audit
events. Mocked: in-memory outbox, SES is the dev/locmem path or a patched boto3."""
import csv
import io
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from mailings import invites as invites_module, lists, sending
from mailings.models import ContactList, ContactListMember, EmailOptOut, Invite, Mailing, MailingRecipient, MailingTemplate
from notifications import suppression
from notifications.models import EmailLog, EmailSuppression, NotificationTemplate
from plans.management.commands.seed_phase1 import seed_all
from system.models import SystemChange, SystemEvent
from system.tests.test_system import PASSWORD, make_user, sign_in, unlocked_client
from users.models import InterestRegistration
from plans.models import Plan

User = get_user_model()
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "emails-tests"}}
UUID = "00000000-0000-0000-0000-000000000000"
PATHS = ["/emails/", "/emails/suppressions/", "/emails/bounces/", "/emails/automatic/", "/emails/automatic/verify/", "/emails/mailings/", "/emails/mailings/new/",
         "/emails/groups/", "/emails/groups/new/", f"/emails/mailings/{UUID}/", f"/emails/mailings/{UUID}/confirm/", f"/emails/groups/{UUID}/",
         f"/emails/groups/{UUID}/add/", f"/emails/groups/past-invites/{UUID}/", "/emails/invites/", f"/emails/invites/{UUID}/"]
POSTS = ["/emails/automatic/verify/save/", "/emails/automatic/verify/preview/", "/emails/automatic/verify/test/", "/emails/automatic/verify/reset/",
         "/emails/mailings/preview/", f"/emails/mailings/{UUID}/send/", f"/emails/mailings/{UUID}/schedule/", f"/emails/mailings/{UUID}/cancel/",
         "/emails/groups/review/", "/emails/groups/save/", "/emails/groups/problems/", f"/emails/groups/{UUID}/edit/", f"/emails/groups/{UUID}/delete/",
         f"/emails/mailings/{UUID}/resume/", f"/emails/groups/{UUID}/members/{UUID}/remove/", "/payments/confirm/", "/emails/automatic/invite/to-group/", f"/emails/mailings/{UUID}/auto/", "/emails/ses/refresh/"]


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
                                                     "invite", "gold_approver", "gold_approver_repeat", "gold_final", "gold_sent_back", "gold_respond", "gold_declined", "payment_window_open", "payment_window_reminder", "payment_staff_alert"})
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
        stale = self.client.post(f"/emails/mailings/{mailing.pk}/send/", {"confirm": "yes", "expected_count": "9"}, HTTP_ACCEPT="application/json")
        self.assertEqual(stale.status_code, 400)  # the person saw another number: nothing sent
        self.assertEqual(stale.json()["message"], "The number changed: 3 now. Check and send again.")
        self.assertEqual(len(mail.outbox), 0)
        self.client.post(f"/emails/mailings/{mailing.pk}/send/", {"confirm": "yes", "expected_count": "3"})
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
        bare = self.client.post(f"/emails/mailings/{mailing.pk}/schedule/", {"scheduled_at": when}, HTTP_ACCEPT="application/json")
        self.assertEqual(bare.status_code, 400)  # scheduling a send needs the pop-up's confirmation too
        self.client.post(f"/emails/mailings/{mailing.pk}/schedule/", {"scheduled_at": when, "confirm": "yes", "expected_count": "3"})
        mailing.refresh_from_db()
        self.assertEqual(mailing.status, "scheduled")
        scheduled = SystemEvent.objects.get(kind=SystemEvent.MAILING_SCHEDULED)
        self.assertEqual(scheduled.detail["recipients_now"], 3)
        self.client.post(f"/emails/mailings/{mailing.pk}/cancel/")
        mailing.refresh_from_db()
        self.assertEqual(mailing.status, "cancelled")
        self.assertEqual(SystemEvent.objects.get(kind=SystemEvent.MAILING_CANCELLED).detail["was"], "scheduled")
        self.assertEqual(self.client.post(f"/emails/mailings/{mailing.pk}/schedule/", {"scheduled_at": "soon", "confirm": "yes", "expected_count": "3"}, HTTP_ACCEPT="application/json").status_code, 400)

    @override_settings(DEBUG=False, EMAIL_BACKEND="notifications.backends.SesBackend", CACHES=LOCMEM)
    def test_sandbox_refuses_sends_with_a_clear_message_and_no_event(self):
        cache.clear()
        client = mock.Mock()
        client.get_account.return_value = {"ProductionAccessEnabled": False, "SendQuota": {}}
        with mock.patch("boto3.client", return_value=client):
            mailing = self.create()
            self.assertFalse(self.client.get(f"/emails/mailings/{mailing.pk}/").context["can_send"])
            response = self.client.post(f"/emails/mailings/{mailing.pk}/send/", {"confirm": "yes", "expected_count": "3"}, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("sandbox", response.json()["message"])
        self.assertFalse(SystemEvent.objects.filter(kind=SystemEvent.MAILING_SENT).exists())
        self.assertFalse(MailingRecipient.objects.exists() or Invite.objects.exists())
        cache.clear()

    def test_a_send_needs_the_confirmation_and_the_number_the_popup_showed(self):
        mailing = self.create()
        url = f"/emails/mailings/{mailing.pk}/send/"
        for data in ({}, {"expected_count": "3"}, {"confirm": "no", "expected_count": "3"}, {"confirm": "yes"}):  # a stray POST, a script, a missing number
            self.assertEqual(self.client.post(url, data, HTTP_ACCEPT="application/json").status_code, 400, data)
        self.assertEqual(self.client.post(url, {"confirm": "yes", "expected_count": "2"}, HTTP_ACCEPT="application/json").json()["message"],
                         "The number changed: 3 now. Check and send again.")
        self.assertEqual((len(mail.outbox), Mailing.objects.get().status, MailingRecipient.objects.count()), (0, "draft", 0))
        self.assertEqual(self.client.post(url, {"confirm": "yes", "expected_count": "3"}, HTTP_ACCEPT="application/json").status_code, 200)
        self.assertEqual(len(mail.outbox), 3)
        again = self.client.post(url, {"confirm": "yes", "expected_count": "3"}, HTTP_ACCEPT="application/json")  # a double click
        self.assertEqual(again.status_code, 400)
        self.assertEqual(len(mail.outbox), 3)

    @mock.patch("mailings.sending.enqueue")
    def test_carrying_on_a_send_also_needs_the_confirmation(self, enqueue):
        mailing = self.create()
        sending.start(mailing, self.dev)
        Mailing.objects.filter(pk=mailing.pk).update(status="paused")
        url = f"/emails/mailings/{mailing.pk}/resume/"
        self.assertEqual(self.client.post(url, HTTP_ACCEPT="application/json").status_code, 400)
        self.assertEqual(Mailing.objects.get().status, "paused")
        self.assertEqual(self.client.post(url, {"confirm": "yes"}, HTTP_ACCEPT="application/json").status_code, 200)
        self.assertEqual(Mailing.objects.get().status, "sending")

    def test_the_confirm_data_has_the_count_the_from_address_and_who_sends(self):
        EmailOptOut.objects.create(email="m0@example.com")
        mailing = self.create()
        data = self.client.get(f"/emails/mailings/{mailing.pk}/confirm/").json()
        self.assertEqual((data["count"], data["to"], data["title"], data["subject"]), (2, "Everyone registered", "Opening", "Hello {first_name}"))
        self.assertEqual(data["from"], "Spa 99 <from@example.test>")
        self.assertEqual((data["skipped"], data["through"]), (1, "Development (printed in the server log, not sent)"))
        self.assertIn("unsubscribed", data["skipped_why"])

    @override_settings(DEBUG=True, EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend", EMAIL_HOST="smtp.postmarkapp.com")
    def test_the_confirm_data_says_postmark_and_the_reply_to_when_it_differs(self):
        from plans.models import SiteSettings

        SiteSettings.objects.update_or_create(singleton_key="site", defaults={"contact_email": "help@example.test"})
        mailing = self.create()
        data = self.client.get(f"/emails/mailings/{mailing.pk}/confirm/").json()
        self.assertEqual((data["through"], data["reply_to"]), ("Postmark", "help@example.test"))
        self.assertEqual(data["from"], "Spa 99 <from@example.test>")


class GroupsAndListsViewTests(TestCase):
    def setUp(self):
        seed_all()
        self.dev = make_user()
        self.client = unlocked_client(self.dev)
        member("already@example.com")

    def review(self, text, **extra):
        return self.client.post("/emails/groups/review/", {"text": text, "name": "Gym", "category": "Fitness", **extra})

    def save(self, review, **extra):
        return self.client.post("/emails/groups/save/", {"text": review.context["text"], "token": review.context["token"], "name": "Gym", "category": "Fitness",
                                                          "expected_ok": str(review.context["report"]["ok"]), **extra}, HTTP_ACCEPT="application/json")

    def test_the_groups_tab_shows_automatic_groups_with_counts_and_the_tabs_are_in_order(self):
        page = self.client.get("/emails/groups/")
        self.assertEqual([g["key"] for g in page.context["automatic_groups"]],
                         ["everyone", "tier", "gold", "opted_in", "unconfirmed", "between", "applicants", "leads"])
        self.assertEqual(next(g for g in page.context["automatic_groups"] if g["key"] == "everyone")["count"], 1)
        html = page.content.decode()
        order = [html.index(f'data-tab="{t}"') for t in ("automatic", "mailings", "groups", "templates", "suppressions")]
        self.assertEqual(order, sorted(order))
        self.assertNotIn('data-tab="invites"', html)

    def test_the_new_list_and_add_more_pages_draw_with_the_category_suggestions(self):
        ContactList.objects.create(name="Gym", category="Fitness")
        page = self.client.get("/emails/groups/new/")
        self.assertContains(page, 'value="Fitness"')  # the existing category is offered
        self.assertContains(page, 'name="name"')
        lst = ContactList.objects.get()
        add = self.client.get(f"/emails/groups/{lst.pk}/add/")
        self.assertContains(add, f'name="list" value="{lst.pk}"')
        self.assertNotContains(add, 'name="category"')

    def test_review_says_ready_heads_up_or_needs_fixing_and_writes_nothing(self):
        self.assertContains(self.review("Al,al@example.com"), 'data-se-state="ready"')
        warn = self.review("Al,al@example.com\nAl,al@example.com\nMem,already@example.com")
        self.assertContains(warn, 'data-se-state="warnings"')
        self.assertContains(warn, "Save list (2 people)")
        self.assertContains(self.review("Al,al@example.com\nBad,not-an-email"), 'data-se-state="blocked"')
        self.assertContains(self.client.post("/emails/groups/review/", {"text": ""}), 'data-se-state="file-error"', status_code=400)
        self.assertFalse(ContactList.objects.exists() or Invite.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_go_back_and_fix_returns_the_paste_form_with_the_text_name_category_and_the_problems(self):
        text = "Al,al@example.com\nBad,not-an-email\nCy,=cmd@example.com"
        review = self.review(text)
        self.assertContains(review, "Go back and fix")
        self.assertContains(review, "data-se-go-back")
        self.assertContains(review, 'data-se-fix-email')
        back = self.client.post("/emails/groups/fix/", {"text": review.context["text"], "name": "My list", "category": "Gym members"})
        self.assertContains(back, 'value="My list"')
        self.assertContains(back, 'value="Gym members"')
        self.assertContains(back, "Al,al@example.com\nBad,not-an-email")
        self.assertContains(back, "Row 2: Not a valid email address.")
        self.assertContains(back, "Row 3: Starts with")
        self.assertFalse(ContactList.objects.exists())
        # a whole-file problem also offers Go back and fix, with the text so it can be edited
        nocolumn = self.client.post("/emails/groups/review/", {"text": "Name,Phone\nAl,07", "name": "X"})
        self.assertContains(nocolumn, "Go back and fix", status_code=400)
        self.assertContains(nocolumn, "Al,07", status_code=400)

    def test_an_inline_fix_of_an_email_or_a_name_rechecks_and_clears_the_error_keeping_the_other_rows(self):
        import json

        text = "name,email\nAl,al@example.com\nBad,not-an-email\n=cmd,cy@example.com\nDi,di@example.com"
        review = self.review(text)
        self.assertEqual({r["line"]: r["status"] for r in review.context["report"]["rows"] if r["level"] == "error"}, {3: "invalid", 4: "unsafe"})
        fixed = self.client.post("/emails/groups/review/", {"text": review.context["text"], "name": "Gym", "edits": json.dumps([{"line": 3, "name": "Bo", "email": "bo@example.com"}])})
        report = fixed.context["report"]
        self.assertEqual([(r["line"], r["email"], r["status"]) for r in report["rows"]],
                         [(2, "al@example.com", "ok"), (3, "bo@example.com", "ok"), (4, "cy@example.com", "unsafe"), (5, "di@example.com", "ok")])  # same rows, same order
        self.assertTrue(fixed.context["token"] == "" and report["blocked"])  # one error left
        both = self.client.post("/emails/groups/review/", {"text": fixed.context["text"], "name": "Gym", "edits": json.dumps([{"line": 4, "name": "Cy", "email": "cy@example.com"}])})
        self.assertEqual((both.context["report"]["problems"], both.context["report"]["can_save"]), (0, True))
        self.assertTrue(both.context["token"])
        saved = self.save(both)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(ContactList.objects.get().members.count(), 4)

    def test_ambiguous_rows_are_settled_by_choosing_a_name(self):
        import json

        review = self.review("Al Smith,al@example.com\nAlan Smith,al@example.com\nBo,bo@example.com")
        rows = review.context["report"]["rows"]
        self.assertEqual([r["status"] for r in rows], ["ambiguous", "ambiguous", "ok"])
        self.assertEqual(rows[0]["choices"], ["Al Smith", "Alan Smith"])
        self.assertContains(review, 'list="se-names-1"')
        pick = [{"line": 1, "name": "Alan Smith", "email": "al@example.com"}, {"line": 2, "name": "Alan Smith", "email": "al@example.com"}]
        fixed = self.client.post("/emails/groups/review/", {"text": review.context["text"], "name": "Gym", "edits": json.dumps(pick)})
        report = fixed.context["report"]
        self.assertEqual(([r["status"] for r in report["rows"]], report["problems"], report["can_save"]), (["ok", "duplicate", "ok"], 0, True))
        self.assertEqual(report["rows"][0]["name"], "Alan Smith")

    def test_saving_a_list_writes_the_event_sends_nothing_and_a_second_save_with_the_token_is_the_same_list(self):
        review = self.review("Al Smith,al@example.com\nMem,already@example.com")
        first, second = self.save(review), self.save(review)  # double click, lag, back and resubmit, second tab
        self.assertEqual((first.status_code, second.status_code), (200, 200))
        self.assertEqual((first.json()["repeated"], second.json()["repeated"]), (False, True))
        self.assertEqual(first.json()["list"], second.json()["list"])
        lst = ContactList.objects.get()
        self.assertEqual((lst.members.count(), lst.category, ContactList.objects.count(), len(mail.outbox)), (2, "Fitness", 1, 0))
        self.assertEqual(SystemEvent.objects.filter(kind=SystemEvent.LIST_CREATED).count(), 1)
        detail = self.client.get(f"/emails/groups/{lst.pk}/", {"q": "al@"})
        self.assertEqual([m.email for m in detail.context["members"]], ["al@example.com"])
        self.assertContains(self.client.get("/emails/groups/"), "Gym")

    def test_errors_give_no_token_and_a_forged_token_for_a_broken_list_cannot_save(self):
        review = self.review("Al,al@example.com\nBad,nope")
        self.assertEqual((review.context["report"]["blocked"], review.context["token"]), (True, ""))
        self.assertContains(review, "Download problem rows")
        forged = invites_module.issue_token(self.dev, review.context["text"])
        again = self.client.post("/emails/groups/save/", {"text": review.context["text"], "token": forged, "name": "Gym"}, HTTP_ACCEPT="application/json")
        self.assertEqual(again.status_code, 400)
        other = self.review("Bo,bo@example.com")
        edited = self.client.post("/emails/groups/save/", {"text": "Cy,cy@example.com", "token": other.context["token"], "name": "Gym"}, HTTP_ACCEPT="application/json")
        self.assertIn("not the one", edited.json()["message"])
        self.assertFalse(ContactList.objects.exists())

    def test_add_more_rename_remove_and_delete_through_the_views(self):
        lst = ContactList.objects.create(name="Gym")
        ContactListMember.objects.create(list=lst, email="al@example.com", name="Al")
        review = self.client.post("/emails/groups/review/", {"text": "Al,al@example.com\nCy,cy@example.com", "list": str(lst.pk)})
        self.assertEqual((review.context["report"]["ok"], review.context["report"]["exists"]), (1, 1))
        self.assertContains(review, "Add 1 person")
        saved = self.client.post("/emails/groups/save/", {"text": review.context["text"], "token": review.context["token"], "list": str(lst.pk)}, HTTP_ACCEPT="application/json")
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(lst.members.count(), 2)
        self.client.post(f"/emails/groups/{lst.pk}/edit/", {"name": "Gym 2", "category": "Sport"})
        lst.refresh_from_db()
        self.assertEqual((lst.name, lst.category), ("Gym 2", "Sport"))
        member_row = lst.members.get(email="cy@example.com")
        self.client.post(f"/emails/groups/{lst.pk}/members/{member_row.pk}/remove/")
        self.assertEqual(lst.members.count(), 1)
        self.client.post(f"/emails/groups/{lst.pk}/delete/")
        self.assertFalse(ContactList.objects.exists())
        self.assertEqual(SystemEvent.objects.filter(kind=SystemEvent.LIST_CHANGED).count(), 3)

    def test_problem_rows_download_is_a_safe_csv(self):
        response = self.client.post("/emails/groups/problems/", {"text": "Al,al@example.com\n=HYPERLINK(1),evil@example.com\nBad,nope\nMem,al@example.com"})
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(rows[0], ["Row", "Level", "Name", "Email", "What to do"])
        self.assertEqual([(r[0], r[1]) for r in rows[1:]], [("1", "Fix this"), ("2", "Fix this"), ("3", "Fix this"), ("4", "Fix this")])
        self.assertTrue(rows[2][2].startswith("'="))

    def test_a_group_send_can_pick_an_uploaded_list_and_a_service_kind_is_refused(self):
        lst = ContactList.objects.create(name="Gym")
        for email in ("al@example.com", "bo@example.com"):
            ContactListMember.objects.create(list=lst, email=email)
        EmailOptOut.objects.create(email="bo@example.com")
        self.assertEqual(self.client.get("/emails/mailings/count/", {"group": "list", "kind": "news", "list_id": str(lst.pk)}).json()["count"], 1)
        refused = self.client.get("/emails/mailings/count/", {"group": "list", "kind": "service", "list_id": str(lst.pk)}).json()
        self.assertEqual(refused["count"], None)
        self.assertIn("News or an Invitation", refused["errors"]["group"][0])
        form = {"name": "Hi", "subject": "Hi", "body": "Hello", "kind": "news", "group": "list", "list_id": str(lst.pk)}
        self.client.post("/emails/mailings/new/", form)
        mailing = Mailing.objects.get()
        self.assertEqual(mailing.params, {"list_id": str(lst.pk)})
        self.client.post(f"/emails/mailings/{mailing.pk}/send/", {"confirm": "yes", "expected_count": "1"})
        self.assertEqual([m.to for m in mail.outbox], [["al@example.com"]])
        service = self.client.post("/emails/mailings/new/", {**form, "kind": "service"})
        self.assertEqual(Mailing.objects.count(), 2)  # saved as a draft, but it can never be sent
        draft = Mailing.objects.exclude(pk=mailing.pk).get()
        refused_send = self.client.post(f"/emails/mailings/{draft.pk}/send/", {"confirm": "yes", "expected_count": "0"}, HTTP_ACCEPT="application/json")
        self.assertEqual(refused_send.status_code, 400)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(service.status_code, 302)


class SendToGroupTests(TestCase):
    def setUp(self):
        seed_all()
        self.dev = make_user()
        self.client = unlocked_client(self.dev)
        self.lst = ContactList.objects.create(name="Gym")
        for name, email in (("Al Smith", "al@example.com"), ("Bo Jones", "bo@example.com"), ("Mem", "already@example.com")):
            ContactListMember.objects.create(list=self.lst, email=email, name=name)
        member("already@example.com")

    def test_only_suitable_emails_have_the_button(self):
        self.assertContains(self.client.get("/emails/automatic/invite/"), "Send to a group")
        for key in ("verify", "password_reset", "gold_invite", "gold_active", "welcome", "team_invite"):
            self.assertNotContains(self.client.get(f"/emails/automatic/{key}/"), "Send to a group")
            self.assertEqual(self.client.post(f"/emails/automatic/{key}/to-group/").status_code, 404)

    def test_the_button_makes_a_prefilled_draft_then_test_then_send_with_personal_links_and_tracking(self):
        self.client.post("/emails/automatic/invite/save/", {"subject": "Join us, {first_name}", "body": "Hi {first_name}\n\n{button}\n\nWelcome."})
        response = self.client.post("/emails/automatic/invite/to-group/")
        mailing = Mailing.objects.get()
        self.assertRedirects(response, f"/emails/mailings/{mailing.pk}/", fetch_redirect_response=False)
        self.assertEqual((mailing.status, mailing.kind, mailing.automatic_key, mailing.subject, mailing.created_by), ("draft", "invitation", "invite", "Join us, {first_name}", self.dev))
        page = self.client.get(f"/emails/mailings/{mailing.pk}/")
        self.assertContains(page, "Welcome.")  # the email's own wording is the preview
        self.assertEqual(page.context["can_send"], False)  # no list chosen yet
        self.client.post(f"/emails/mailings/{mailing.pk}/auto/", {"list_id": str(self.lst.pk)})
        mailing.refresh_from_db()
        self.assertEqual((mailing.group, mailing.params), ("list", {"list_id": str(self.lst.pk)}))
        self.client.post(f"/emails/mailings/{mailing.pk}/test/")
        self.assertEqual([(m.to, m.subject.startswith("[Test] Join us")) for m in mail.outbox], [(["dev@example.com"], True)])
        self.assertEqual(MailingRecipient.objects.count() + Invite.objects.count(), 0)  # a test creates no recipients and no invites
        confirm = self.client.get(f"/emails/mailings/{mailing.pk}/confirm/").json()
        self.assertEqual((confirm["count"], confirm["title"], confirm["to"], confirm["skipped"]), (2, "Invitation to register", "Uploaded list: Gym", 1))
        self.assertIn("already members", confirm["skipped_why"])
        bare = self.client.post(f"/emails/mailings/{mailing.pk}/send/", HTTP_ACCEPT="application/json")
        self.assertEqual(bare.status_code, 400)
        self.assertEqual(len(mail.outbox), 1)
        self.client.post(f"/emails/mailings/{mailing.pk}/send/", {"confirm": "yes", "expected_count": "2"})
        sent = [m for m in mail.outbox if m.to != ["dev@example.com"]]
        self.assertEqual(sorted(m.to[0] for m in sent), ["al@example.com", "bo@example.com"])
        invite = Invite.objects.get(email="al@example.com")
        self.assertEqual((invite.batch_id, invite.status), (mailing.pk, "sent"))
        self.assertIn(f"/invite/{invite.token}/", next(m for m in sent if m.to == ["al@example.com"]).body)
        self.assertEqual(sent[0].subject, "Join us, Al" if sent[0].to == ["al@example.com"] else "Join us, Bo")
        self.assertEqual(SystemEvent.objects.filter(kind=SystemEvent.MAILING_SENT).count(), 1)
        detail = self.client.get(f"/emails/mailings/{mailing.pk}/")
        self.assertEqual(detail.context["invite_summary"]["sent"], 2)
        self.assertEqual(self.client.get(f"/emails/groups/past-invites/{mailing.pk}/").status_code, 200)
        self.client.post(f"/emails/mailings/{mailing.pk}/send/", {"confirm": "yes", "expected_count": "2"})  # a double click sends nothing more
        self.assertEqual(len(mail.outbox), 3)

    def test_a_double_click_on_send_to_a_group_makes_one_draft(self):
        self.client.post("/emails/automatic/invite/to-group/")
        self.client.post("/emails/automatic/invite/to-group/")
        self.assertEqual(Mailing.objects.count(), 1)

    def test_the_payments_confirm_data_has_the_count_and_the_from_address(self):
        data = self.client.get("/payments/confirm/").json()  # setUp made one member
        self.assertEqual((data["count"], data["title"], data["to"], data["from"]), (1, "Payments are open", "Registered members", "Spa 99 <from@example.test>"))

    def test_the_old_invite_addresses_redirect_for_good_to_groups(self):
        for path in ("/emails/invites/", "/emails/invites/new/", f"/emails/invites/{UUID}/"):
            response = self.client.get(path)
            self.assertEqual((response.status_code, response["Location"]), (301, "/emails/groups/"), path)
        self.assertEqual(self.client.post("/emails/invites/send/")["Location"], "/emails/groups/")


class MailingEditorPageTests(TestCase):
    """The parts editor's page (docs/design/EMAIL-BUILDER-UI.md): what the template hands the script, and the Start from choice."""

    def setUp(self):
        seed_all()
        self.client = unlocked_client(make_user())

    def test_a_new_page_has_the_start_choice_and_the_editor_data_without_inline_script(self):
        page = self.client.get("/emails/mailings/new/")
        html = page.content.decode()
        self.assertContains(page, "Start from")
        booking = MailingTemplate.objects.get(key="booking_open")
        self.assertContains(page, f'value="{booking.pk}"')
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
        booking = MailingTemplate.objects.get(key="booking_open")
        self.assertEqual(page.context["start"], str(booking.pk))
        self.assertContains(page, f'data-start="{booking.pk}"')
        self.assertContains(page, f'value="{booking.pk}" checked')
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


class SuppressionsMovedTests(TestCase):
    def test_the_old_address_redirects_permanently_and_the_tab_is_in_emails(self):
        client = unlocked_client(make_user())
        old = client.get("/suppressions/")
        self.assertEqual((old.status_code, old["Location"]), (301, "/emails/suppressions/"))
        page = client.get("/emails/suppressions/")
        self.assertContains(page, 'data-tab="suppressions" aria-current="page"')
        self.assertNotContains(client.get("/emails/"), ">Email suppressions</a>")


@override_settings(DEBUG=True, EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend", EMAIL_HOST="smtp.postmarkapp.com", EMAIL_HOST_PASSWORD="tok-secret")
class ProviderModeTests(TestCase):
    def test_the_pages_say_who_sends_hide_amazon_numbers_and_never_show_credentials(self):
        seed_all()
        client = unlocked_client(make_user())
        for path in ("/emails/", "/emails/mailings/"):
            page = client.get(path)
            self.assertContains(page, "Sending through Postmark \u2713")
            self.assertNotContains(page, "not Amazon SES")
            self.assertNotContains(page, "tok-secret")
            self.assertNotContains(page, "Check now")
        self.assertEqual(client.get("/emails/").context["ses"]["mode"], "provider")


class MailingFormTemplateUiTests(TestCase):
    """Markup the editor script relies on: the Save as template panel, the test address, and the Templates tab."""

    def setUp(self):
        seed_all()
        self.client = unlocked_client(make_user())

    def test_the_form_has_the_save_as_template_panel_and_the_addresses_the_script_posts_to(self):
        page = self.client.get("/emails/mailings/new/")
        self.assertContains(page, "data-se-save-template")
        self.assertContains(page, 'data-se-tpl-name')
        self.assertContains(page, 'data-test-url="/emails/mailings/test/"')
        self.assertContains(page, 'data-template-url="/emails/mailings/templates/save/"')
        booking = MailingTemplate.objects.get(key="booking_open")
        self.assertContains(page, f'name="start" value="{booking.pk}"')

    def test_the_templates_tab_lists_them_with_rename_and_delete(self):
        page = self.client.get("/emails/templates/")
        self.assertContains(page, 'data-tab="templates" aria-current="page"')
        self.assertContains(page, "Booking is open")
        self.assertContains(page, "data-system-template-rename")


class PagerTests(TestCase):
    def setUp(self):
        seed_all()
        self.client = unlocked_client(make_user())
        self.lst = ContactList.objects.create(name="Big")
        ContactListMember.objects.bulk_create([ContactListMember(list=self.lst, email=f"p{i:03d}@example.com") for i in range(130)])

    def test_the_pager_shows_the_range_and_page_links_and_hides_with_one_page(self):
        page = self.client.get(f"/emails/groups/{self.lst.pk}/", {"page": 2})
        self.assertContains(page, "51&ndash;100")
        self.assertContains(page, 'aria-label="Pages"')
        self.assertContains(page, 'aria-current="page"')
        self.assertContains(page, "of <span class=\"mono\">130</span>")
        small = ContactList.objects.create(name="Small")
        self.assertNotContains(self.client.get(f"/emails/groups/{small.pk}/"), "data-system-pager")

    def test_filters_are_kept_in_the_links_and_only_page_changes(self):
        page = self.client.get(f"/emails/groups/{self.lst.pk}/", {"q": "example", "page": 1})
        self.assertContains(page, "?q=example&amp;page=2")
        self.assertNotContains(page, "page=1&amp;page")

    def test_a_bad_page_number_falls_back_without_crashing(self):
        for value in ("999", "abc", "-3", "0"):
            page = self.client.get(f"/emails/groups/{self.lst.pk}/", {"page": value})
            self.assertEqual(page.status_code, 200, value)
        self.assertEqual(self.client.get(f"/emails/groups/{self.lst.pk}/", {"page": "999"}).context["members"].number, 3)
        self.assertEqual(self.client.get(f"/emails/groups/{self.lst.pk}/", {"page": "abc"}).context["members"].number, 1)


class ListStatusTests(TestCase):
    """Status per person on an uploaded list, the filter chips, the invite button and Add more."""

    def setUp(self):
        seed_all()
        self.dev = make_user()
        self.client = unlocked_client(self.dev)
        self.lst = ContactList.objects.create(name="Gym")
        self.other = ContactList.objects.create(name="Other")
        now = timezone.now()
        batch = "00000000-0000-0000-0000-000000000009"

        def invite(email, status, days_ago=1, expires_in=10, **kw):
            row = Invite.objects.create(email=email, batch_id=batch, status=status, sent_at=now - timedelta(days=days_ago), **kw)
            Invite.objects.filter(pk=row.pk).update(expires_at=now + timedelta(days=expires_in), created_at=now - timedelta(days=days_ago))
            return row

        for email in ("new@example.com", "sent@example.com", "opened@example.com", "reg@example.com", "expired@example.com", "unsub@example.com",
                      "bounce@example.com", "mem@example.com", "memunsub@example.com", "oldreg@example.com"):
            ContactListMember.objects.create(list=self.lst, email=email, name=email.split("@")[0])
        ContactListMember.objects.create(list=self.other, email="sent@example.com")
        invite("sent@example.com", Invite.SENT)  # from another list's send: still counts here
        invite("opened@example.com", Invite.OPENED)
        invite("reg@example.com", Invite.REGISTERED)
        invite("expired@example.com", Invite.SENT, days_ago=40, expires_in=-5)
        invite("oldreg@example.com", Invite.REGISTERED, days_ago=60)
        invite("oldreg@example.com", Invite.SENT, days_ago=1)  # the latest wins: waiting again
        EmailOptOut.objects.create(email="unsub@example.com")
        EmailOptOut.objects.create(email="memunsub@example.com")
        suppression.add("bounce@example.com", EmailSuppression.HARD_BOUNCE)
        member("mem@example.com")
        member("memunsub@example.com")  # an account wins over unsubscribed

    def statuses(self, **params):
        page = lists.members_page(self.lst, **params)
        return {m.email.split("@")[0]: m.status for m in page}

    def test_status_precedence_and_the_latest_invite_from_any_batch(self):
        self.assertEqual(self.statuses(), {"new": "not_invited", "sent": "invited", "opened": "opened", "reg": "registered", "expired": "expired",
                                           "unsub": "unsubscribed", "bounce": "bounced", "mem": "member", "memunsub": "member", "oldreg": "invited"})
        with self.assertNumQueries(2):  # the page and its count, not one per person
            lists.members_page(self.lst)

    def test_filter_counts_and_the_filter_with_search(self):
        counts = lists.status_counts(self.lst)
        self.assertEqual(counts, {"all": 10, "member": 2, "unsubscribed": 1, "bounced": 1, "registered": 1, "opened": 1, "invited": 2, "expired": 1, "not_invited": 1})
        self.assertEqual(set(self.statuses(status="invited")), {"sent", "oldreg"})
        self.assertEqual(set(self.statuses(status="invited", query="sent")), {"sent"})
        self.assertEqual(lists.status_counts(self.lst, "sent")["all"], 1)
        page = self.client.get(f"/emails/groups/{self.lst.pk}/?status=invited&q=e")
        self.assertContains(page, "Invited 2")
        self.assertContains(page, "Invite expired 1")

    def test_pager_links_keep_the_filter_and_search(self):
        for n in range(60):
            ContactListMember.objects.create(list=self.lst, email=f"bulk{n}@example.com")
        page = self.client.get(f"/emails/groups/{self.lst.pk}/?status=not_invited&q=bulk")
        self.assertContains(page, "status=not_invited")
        self.assertContains(page, "page=2")
        self.assertEqual(len(page.context["members"].object_list), 50)

    def test_the_number_on_the_button_is_the_number_the_send_reaches(self):
        page = self.client.get(f"/emails/groups/{self.lst.pk}/")
        reach = page.context["reach"]
        self.assertEqual(reach, 3)  # new, expired, and reg (its account is gone, so the send rules let him be invited again); members, waiting, opened, unsubscribed, bounced are out
        self.assertContains(page, "Invite 3 people (new, or their invite expired)")
        draft = Mailing.objects.create(name="x", subject="s", kind=Mailing.INVITATION, group="list", params={"list_id": str(self.lst.pk)}, automatic_key="invite", created_by=self.dev)
        self.assertEqual(len(list(sending.segments.rows("list", draft.params, draft.kind, draft.has_personal_links))), reach)
        ContactListMember.objects.filter(list=self.lst).exclude(email__in=("new@example.com", "expired@example.com")).delete()  # reg goes too
        Invite.objects.filter(email="expired@example.com").update(expires_at=timezone.now() + timedelta(days=3))
        Invite.objects.create(email="new@example.com", batch_id=UUID, status=Invite.QUEUED)
        page = self.client.get(f"/emails/groups/{self.lst.pk}/")
        self.assertNotContains(page, "Invite the")
        self.assertContains(page, "Everyone on this list has been invited")

    def test_the_button_makes_a_draft_for_the_list_and_sends_nothing(self):
        response = self.client.post("/emails/automatic/invite/to-group/", {"list_id": str(self.lst.pk)})
        mailing = Mailing.objects.get()
        self.assertRedirects(response, f"/emails/mailings/{mailing.pk}/", fetch_redirect_response=False)
        self.assertEqual((mailing.status, mailing.kind, mailing.group, mailing.params), ("draft", "invitation", "list", {"list_id": str(self.lst.pk)}))
        self.assertEqual((len(mail.outbox), Invite.objects.count(), MailingRecipient.objects.count()), (0, 6, 0))  # the six made in setUp
        bare = self.client.post(f"/emails/mailings/{mailing.pk}/send/", HTTP_ACCEPT="application/json")  # no confirm: refused
        self.assertEqual(bare.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(self.client.get(f"/emails/mailings/{mailing.pk}/confirm/").json()["count"], 3)
        self.assertEqual(self.client.post("/emails/automatic/invite/to-group/", {"list_id": UUID}).status_code, 404)
        for bad in ("not-a-uuid", "123", "<script>"):
            self.assertEqual(self.client.post("/emails/automatic/invite/to-group/", {"list_id": bad}).status_code, 404, bad)

    def test_add_people_from_the_groups_row_and_add_more_only_adds_new_addresses(self):
        self.assertContains(self.client.get("/emails/groups/"), f'href="/emails/groups/{self.lst.pk}/add/"')
        text = "name,email\nNew One,new@example.com\nFresh,fresh@example.com\nFresh Two,fresh2@example.com"
        row = invites_module.find_token(invites_module.issue_token(self.dev, text, str(self.lst.pk)), self.dev, text, str(self.lst.pk))
        response = self.client.post("/emails/groups/save/", {"text": text, "token": row.token, "list": str(self.lst.pk)}, follow=True)
        self.assertRedirects(response, f"/emails/groups/{self.lst.pk}/")
        self.assertContains(response, "Added 2 new people (1 was already on the list)")
        self.assertEqual(self.lst.members.count(), 12)
        self.assertEqual(self.lst.members.filter(email="new@example.com").count(), 1)
        again = invites_module.find_token(invites_module.issue_token(self.dev, text, str(self.lst.pk)), self.dev, text, str(self.lst.pk))
        self.client.post("/emails/groups/save/", {"text": text, "token": again.token, "list": str(self.lst.pk)})  # nobody new: refused, nothing doubled
        self.assertEqual(self.lst.members.count(), 12)
