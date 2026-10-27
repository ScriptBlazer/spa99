"""Gold actions and the audit trail (docs/features/gold-actions.md). Email is mocked (the locmem outbox) and the queue runs
inline, so a send happens inside the request that asked for it."""
from unittest import mock

from django.contrib import admin as django_admin
from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection, transaction
from django.core import mail
from django.test import Client, RequestFactory, TestCase

from common import levels
from gold import actions, approval, audit, invites, tasks
from gold import services as gold_services
from gold.admin import GoldApplicationAdmin
from gold.models import AppendOnlyError, ApplicationEvent, GoldApplication
from gold.tests.test_gold import application_data
from plans.management.commands.seed_phase1 import seed_all
from plans.tests.helpers import make_team_member, set_recipients

User = get_user_model()
OFFICE = "office.localhost"
REASON = "Not a fit for Gold at this time"


def office(user, path, data=None):
    client = Client(HTTP_HOST=OFFICE)
    client.force_login(user)
    return client.post(path, data) if data is not None else client.get(path)


def events(application, action=None):
    rows = ApplicationEvent.objects.filter(application=application).order_by("at", "id")
    return list(rows.filter(action=action) if action else rows)


class ActionsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        set_recipients()
        cls.approver = make_team_member("approver@example.test", levels.OFFICE, approver=True)
        cls.reader = make_team_member("reader@example.test", levels.OFFICE)
        cls.final = make_team_member("final@example.test", levels.ADMIN, final=True)

    def application(self, **over):
        application, _ = gold_services.submit_application(application_data(**over))
        mail.outbox.clear()
        return application


class TrailTests(ActionsTestCase):
    def test_every_step_is_recorded_with_who_how_and_the_status_change(self):
        application = self.application()
        self.assertEqual([(e.action, e.channel, e.to_status) for e in events(application)], [("submitted", "system", "new"), ("email_sent", "system", ""), ("email_sent", "system", "")])  # approver email, thank-you
        office(self.approver, f"/gold/{application.pk}/approve/", {"token": approval.make_approve_token(application)})
        approved = events(application, "approved")[0]
        self.assertEqual((approved.actor, approved.channel, approved.from_status, approved.to_status, approved.meta["result"]),
                         (self.approver, "email_link", "new", "approved", "invited"))
        self.assertIn("approver@example.test", approved.actor_label)
        self.assertTrue(any(e.meta.get("template") == "gold_invite" for e in events(application, "email_sent")))  # the invite went out
        office(self.approver, f"/gold/{application.pk}/resend/", {})
        self.assertEqual(events(application, "invite_resent")[0].channel, "office")
        office(self.approver, f"/gold/{application.pk}/approve/", {})  # already approved: nothing changes, nothing is recorded
        self.assertEqual(len(events(application, "approved")), 1)

    def test_low_potential_final_steps_and_failed_email_are_recorded(self):
        application = self.application(email="low@example.com", mobile="+447911000111")
        GoldApplication.objects.filter(pk=application.pk).update(potential_level="low")
        office(self.approver, f"/gold/{application.pk}/approve/", {})
        self.assertEqual([(e.action, e.to_status) for e in events(application, "sent_for_final")], [("sent_for_final", "awaiting_final")])
        office(self.final, f"/gold/{application.pk}/final/send-back/", {"note": "Please check the portfolio"})
        back = events(application, "sent_back")[0]
        self.assertEqual((back.actor, back.message, back.from_status, back.to_status), (self.final, "Please check the portfolio", "awaiting_final", "new"))
        office(self.approver, f"/gold/{application.pk}/approve/", {})  # after a send back it goes straight through
        self.assertEqual(events(application, "approved")[0].to_status, "approved")
        GoldApplication.objects.filter(pk=application.pk).update(status="awaiting_final", final_requested_at=application.created_at)
        with mock.patch("django.core.mail.EmailMultiAlternatives.send", side_effect=OSError("no server")):
            tasks.send_gold_emails(str(application.pk), acknowledge=False)
        failed = events(application, "email_failed")[0]
        self.assertEqual(failed.meta["template"], "gold_approver")
        self.assertIn("no server", failed.meta["error"])

    def test_the_admin_action_and_a_status_edit_are_recorded_as_admin(self):
        application = self.application()
        approval.approve(application, self.approver, channel=audit.ADMIN)
        self.assertEqual(events(application, "approved")[0].channel, "admin")
        other = self.application(email="other@example.com", mobile="+447911000222")
        request = RequestFactory().post("/")
        request.user = self.approver
        form = mock.Mock(changed_data=[])  # a history Revert reports no change, the status still moved
        other.status = "contacted"
        GoldApplicationAdmin(GoldApplication, django_admin.site).save_model(request, other, form, True)
        changed = events(other, "status_changed_admin")[0]
        self.assertEqual((changed.from_status, changed.to_status, changed.channel, changed.actor), ("new", "contacted", "admin", self.approver))


class DeclineTests(ActionsTestCase):
    def test_a_reason_is_required_and_a_mistake_keeps_the_form_open_with_the_text(self):
        application = self.application()
        short = office(self.approver, f"/gold/{application.pk}/decline/", {"reason": "no", "email_applicant": "1", "email_message": ""})
        self.assertEqual(short.status_code, 400)
        page = short.content.decode()
        self.assertIn('data-gold-dialog="decline" data-open', page)
        self.assertIn("at least 10 characters", page)
        self.assertIn("Write the message to send", page)
        application.refresh_from_db()
        self.assertEqual((application.status, len(events(application, "declined"))), ("new", 0))
        self.assertEqual(office(self.approver, f"/gold/{application.pk}/decline/", {}).status_code, 400)  # nothing at all

    def test_decline_logs_the_reason_and_emails_nobody_unless_ticked(self):
        application = self.application()
        office(self.approver, f"/gold/{application.pk}/decline/", {"reason": REASON})
        application.refresh_from_db()
        declined = events(application, "declined")[0]
        self.assertEqual((application.status, declined.message, declined.from_status, declined.to_status, declined.actor, declined.channel),
                         ("declined", REASON, "new", "declined", self.approver, "office"))
        self.assertFalse(declined.meta["email_applicant"])
        self.assertEqual(mail.outbox, [])
        office(self.approver, f"/gold/{application.pk}/decline/", {"reason": REASON})  # a double submit: still one event
        self.assertEqual(len(events(application, "declined")), 1)

    def test_ticking_email_sends_exactly_the_typed_message_and_logs_it(self):
        application = self.application()
        page = office(self.approver, f"/gold/{application.pk}/").content.decode()
        self.assertIn("not able to offer you a Gold Card", page)  # prefilled from the editable gold_declined email
        office(self.approver, f"/gold/{application.pk}/decline/", {"reason": REASON, "email_applicant": "1", "email_message": "Hi Dan,\n\nSorry, not this time. <b>Thanks</b>"})
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual((message.to, message.reply_to), (["dan@example.com"], ["hello@example.test"]))
        self.assertIn("Sorry, not this time. <b>Thanks</b>", message.body)
        self.assertIn("&lt;b&gt;Thanks&lt;/b&gt;", message.alternatives[0][0])  # escaped in the html version
        sent = events(application, "email_sent")[-1]
        self.assertEqual((sent.meta["template"], sent.meta["recipient"]), ("gold_declined", "dan@example.com"))
        self.assertTrue(events(application, "declined")[0].meta["email_applicant"])


class RespondAndNoteTests(ActionsTestCase):
    def test_respond_emails_with_reply_to_sets_contacted_and_stays_open(self):
        application = self.application()
        office(self.approver, f"/gold/{application.pk}/respond/", {"message": "Which properties do you own?\nPlease list them."})
        application.refresh_from_db()
        self.assertEqual(application.status, "contacted")
        message = mail.outbox[0]
        self.assertEqual((message.to, message.reply_to), (["dan@example.com"], ["hello@example.test"]))
        self.assertIn("Which properties do you own?\nPlease list them.", message.body)
        responded = events(application, "responded")[0]
        self.assertEqual((responded.message, responded.from_status, responded.to_status, responded.actor), ("Which properties do you own?\nPlease list them.", "new", "contacted", self.approver))
        self.assertEqual(events(application, "email_sent")[-1].meta["template"], "gold_respond")
        office(self.approver, f"/gold/{application.pk}/respond/", {"message": "Which properties do you own?\nPlease list them."})  # double submit
        self.assertEqual((len(events(application, "responded")), len(mail.outbox)), (1, 1))
        self.assertEqual(invites.approve_and_invite(application, self.approver, channel="office"), invites.INVITED)  # still open for a decision

    def test_a_note_is_internal_only_and_respond_is_closed_once_decided(self):
        application = self.application()
        office(self.approver, f"/gold/{application.pk}/note/", {"note": "He replied by phone: owns 12 flats"})
        note = events(application, "note_added")[0]
        self.assertEqual((note.message, note.from_status, note.to_status), ("He replied by phone: owns 12 flats", "", ""))
        self.assertEqual((mail.outbox, GoldApplication.objects.get(pk=application.pk).status), ([], "new"))
        self.assertEqual(office(self.approver, f"/gold/{application.pk}/note/", {"note": " "}).status_code, 400)
        invites.decline_application(application, self.approver, REASON, channel="office")
        self.assertEqual(actions.respond(application, self.approver, "Hello again")[0], actions.CLOSED)
        self.assertEqual(actions.add_note(application, self.approver, "Closed, noted for the file")[0], actions.DONE)  # notes any time


class PermissionAndLinkTests(ActionsTestCase):
    def test_view_only_users_see_the_trail_but_cannot_act(self):
        application = self.application()
        office(self.approver, f"/gold/{application.pk}/note/", {"note": "<script>alert(1)</script>\nsecond line"})
        for user in (self.reader, self.final):
            page = office(user, f"/gold/{application.pk}/")
            self.assertContains(page, "data-gold-timeline")
            self.assertContains(page, "&lt;script&gt;alert(1)&lt;/script&gt;<br>second line")  # escaped, line breaks kept
            self.assertNotContains(page, "data-gold-open")
            before = ApplicationEvent.objects.count()
            for action, data in (("decline", {"reason": REASON}), ("respond", {"message": "Hello there"}), ("note", {"note": "A note"})):
                self.assertEqual(office(user, f"/gold/{application.pk}/{action}/", data).status_code, 403)
            self.assertEqual(ApplicationEvent.objects.count(), before)
        self.assertContains(office(self.approver, f"/gold/{application.pk}/"), 'data-gold-open="respond"')

    def test_the_approver_email_links_open_the_office_forms(self):
        gold_services.submit_application(application_data())
        email = next(m for m in mail.outbox if m.to == ["approver@example.test"])
        decline = next(line.split(": ")[1] for line in email.body.splitlines() if line.startswith("Decline"))
        respond = next(line.split(": ")[1] for line in email.body.splitlines() if line.startswith("Respond"))
        self.assertTrue(decline.endswith("?do=decline") and respond.endswith("?do=respond"))
        self.assertIn("?do=respond", email.alternatives[0][0])
        path = lambda url: "/" + url.split("/", 3)[3]  # noqa: E731
        self.assertContains(office(self.approver, path(decline)), 'data-gold-dialog="decline" data-open')
        self.assertContains(office(self.approver, path(respond)), 'data-gold-dialog="respond" data-open')
        application = GoldApplication.objects.get()
        invites.decline_application(application, self.approver, REASON, channel="office")
        decided = office(self.approver, path(respond))
        self.assertNotContains(decided, "data-open")  # already decided: no form, a calm note instead
        self.assertContains(decided, "already been decided")


class ImmutabilityAndErasureTests(ActionsTestCase):
    def test_events_cannot_be_edited_or_deleted_but_survive_an_account_going(self):
        application = self.application()
        event = audit.record(application, "note_added", actor=self.approver, channel="office", message="kept")
        event.message = "changed"
        with self.assertRaises(AppendOnlyError):
            event.save()
        with self.assertRaises(AppendOnlyError):
            event.delete()
        with self.assertRaises(AppendOnlyError):
            ApplicationEvent.objects.filter(pk=event.pk).update(message="x")
        with self.assertRaises(AppendOnlyError):
            ApplicationEvent.objects.filter(pk=event.pk).delete()
        self.approver.delete()
        event = ApplicationEvent.objects.get(pk=event.pk)
        self.assertEqual((event.actor, event.message), (None, "kept"))
        self.assertIn("approver@example.test", event.actor_label)

    def test_erasing_the_applicant_removes_the_trail_and_the_export_carries_it(self):
        application = self.application()
        actions.add_note(application, self.approver, "Phone: 07700 900123")
        exported = gold_services.export_applications("dan@example.com")[0]["history"]
        self.assertIn("Phone: 07700 900123", [e["message"] for e in exported])
        self.assertNotIn("approver@example.test", str(exported))
        self.assertGreater(ApplicationEvent.objects.count(), 0)
        gold_services.delete_applications("dan@example.com")
        self.assertEqual(ApplicationEvent.objects.count(), 0)


class HardeningTests(ActionsTestCase):
    def test_a_posted_channel_or_bad_token_never_makes_it_an_email_link(self):
        application = self.application()
        office(self.approver, f"/gold/{application.pk}/approve/", {"channel": "email_link", "token": "forged"})
        self.assertEqual(events(application, "approved")[0].channel, "office")
        other = self.application(email="o@example.com", mobile="+447911000444")
        page = office(self.approver, f"/gold/{other.pk}/?t={approval.make_approve_token(other)}")  # the email link opens the full page
        self.assertContains(page, 'name="token"')
        self.assertNotContains(office(self.approver, f"/gold/{other.pk}/?t=junk"), 'name="token"')

    def test_the_database_refuses_edits_but_allows_delete_and_an_account_going(self):
        application = self.application()
        event = audit.record(application, "note_added", actor=self.approver, message="kept")
        with self.assertRaises(DatabaseError), transaction.atomic():
            ApplicationEvent._base_manager.filter(pk=event.pk).update(message="x")
        with self.assertRaises(DatabaseError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("UPDATE gold_applicationevent SET message = 'x'")
        self.approver.delete()  # ON DELETE SET NULL on actor_id is the one update allowed
        self.assertIsNone(ApplicationEvent.objects.get(pk=event.pk).actor_id)

    def test_a_form_error_after_someone_else_decided_redirects_with_a_warning(self):
        application = self.application()
        invites.decline_application(application, self.reader, REASON, channel="office")
        response = office(self.approver, f"/gold/{application.pk}/respond/", {"message": "x"})
        self.assertEqual(response.status_code, 302)
        follow = Client(HTTP_HOST=OFFICE)
        follow.force_login(self.approver)
        self.assertContains(follow.post(f"/gold/{application.pk}/respond/", {"message": "x"}, follow=True), "Already decided by someone else")

    def test_export_has_the_declined_email_text_and_all_email_results_are_logged(self):
        application = self.application()
        invites.decline_application(application, self.approver, REASON, channel="office", email_message="Sorry Dan, not now")
        exported = gold_services.export_applications("dan@example.com")[0]["history"]
        self.assertIn("Sorry Dan, not now", [e.get("email_message") for e in exported])
        self.assertTrue(any(e.meta.get("template") == "gold_ack" for e in events(application, "email_sent")))
        low = self.application(email="l@example.com", mobile="+447911000555")
        GoldApplication.objects.filter(pk=low.pk).update(potential_level="low")
        office(self.approver, f"/gold/{low.pk}/approve/", {})
        self.assertTrue(any(e.meta.get("template") == "gold_final" for e in events(low, "email_sent")))
