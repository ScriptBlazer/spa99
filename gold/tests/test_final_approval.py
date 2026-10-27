"""Final approval of Low potential Gold applications (docs/features/gold-final-approval.md). Email is mocked (the locmem
outbox), the queue runs inline, no real clock: the expired link is made by signing while time is patched."""
import re
import time
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase
from django.utils import timezone

from common import levels
from gold import approval, invites
from gold import services as gold_services
from gold.models import ApproverDelivery, GoldApplication
from gold.tests.test_gold import application_data
from plans.management.commands.seed_phase1 import seed_all
from plans.tests.helpers import make_team_member

User = get_user_model()
OFFICE = "office.localhost"


def office(user, path, data=None):
    client = Client(HTTP_HOST=OFFICE)
    if user:
        client.force_login(user)
    return client.post(path, data) if data is not None else client.get(path)


def low_application(**over):
    application, _ = gold_services.submit_application(application_data(**over))
    GoldApplication.objects.filter(pk=application.pk).update(potential_level="low", potential_score=0)
    mail.outbox.clear()
    application.refresh_from_db()
    return application


def to(message):
    return sorted(message.to)


class FinalApprovalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        cls.approver = make_team_member("approver@example.test", levels.OFFICE, approver=True)
        cls.approver2 = make_team_member("approver2@example.test", levels.OFFICE, approver=True)
        cls.final = make_team_member("final@example.test", levels.ADMIN, final=True)

    def sent_for_final(self):
        application = low_application()
        self.assertEqual(approval.approve(application, self.approver), approval.AWAITING)
        return application

    def link_from(self, message, name):
        return re.search(r"%s: (http\S+)" % name, message.body).group(1)

    def test_low_potential_waits_for_final_approval_and_the_applicant_is_told_nothing(self):
        application = self.sent_for_final()
        application.refresh_from_db()
        self.assertEqual(application.status, GoldApplication.AWAITING_FINAL)
        self.assertEqual((application.final_requested_by, application.approved_at), (self.approver, None))
        self.assertFalse(application.invites.exists())
        self.assertEqual(len(mail.outbox), 1)  # only the final approver is emailed
        message = mail.outbox[0]
        self.assertEqual(to(message), ["final@example.test"])
        self.assertEqual(message.subject, "Final approval: Dan Cohen (Low potential)")
        self.assertIn("/final/", self.link_from(message, "Confirm approval"))
        self.assertTrue(self.link_from(message, "Send back").startswith(f"http://office.localhost:8000/gold/{application.pk}/final/"))
        self.assertNotIn("!", message.subject + message.body)

    def test_confirm_runs_the_normal_approval_and_tells_the_applicant(self):
        application = self.sent_for_final()
        mail.outbox.clear()
        self.assertEqual(approval.final_confirm(application, self.final), invites.INVITED)
        application.refresh_from_db()
        self.assertEqual((application.status, application.approved_by), (GoldApplication.APPROVED, self.final))
        self.assertEqual([to(m) for m in mail.outbox], [["dan@example.com"]])  # the invite
        self.assertEqual(approval.final_confirm(application, self.final), invites.SKIPPED)  # a second tap does nothing

    def test_send_back_returns_it_to_the_queue_and_emails_every_approver_with_the_note(self):
        ApproverDelivery.objects.create(user=self.approver2, use_account_email=False, other_email="elsewhere@example.test")
        application = self.sent_for_final()
        mail.outbox.clear()
        self.assertTrue(approval.send_back(application, self.final, "  Not convinced about this one.  "))
        application.refresh_from_db()
        self.assertEqual((application.status, application.sent_back_by, application.sent_back_note), (GoldApplication.NEW, self.final, "Not convinced about this one."))
        self.assertIsNotNone(application.sent_back_at)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(to(message), ["approver@example.test", "elsewhere@example.test"])  # approver2 chose another address
        self.assertEqual(message.subject, "Dan Cohen was approved, but the potential is Low. Are you sure?")
        self.assertIn("Not convinced about this one.", message.body)
        self.assertIn(f"/gold/{application.pk}/?t=", message.body)
        self.assertFalse(approval.send_back(application, self.final))  # no longer awaiting final approval
        with self.assertRaises(approval.NoteTooLong):
            approval.clean_note("x" * 1001)

    def test_the_next_approval_after_a_send_back_goes_straight_through(self):
        application = self.sent_for_final()
        approval.send_back(application, self.final)
        mail.outbox.clear()
        self.assertEqual(approval.approve(application, self.approver2), invites.INVITED)
        application.refresh_from_db()
        self.assertEqual(application.status, GoldApplication.APPROVED)
        self.assertEqual([to(m) for m in mail.outbox], [["dan@example.com"]])

    def test_a_declined_after_send_back_stays_possible_and_the_final_approver_cannot_decline(self):
        application = self.sent_for_final()
        self.assertFalse(invites.decline_application(application))  # awaiting final: nobody declines it
        self.assertEqual(office(self.final, f"/gold/{application.pk}/decline/", {}).status_code, 403)  # Final approver alone is not an approver
        self.assertEqual(GoldApplication.objects.get(pk=application.pk).status, GoldApplication.AWAITING_FINAL)
        approval.send_back(application, self.final)
        self.assertTrue(invites.decline_application(application))

    def test_not_low_is_unchanged_and_no_final_approver_means_straight_approval_with_a_warning(self):
        high, _ = gold_services.submit_application(application_data())
        self.assertEqual(approval.approve(high, self.approver), invites.INVITED)
        self.assertEqual(GoldApplication.objects.get(pk=high.pk).status, GoldApplication.APPROVED)

        User.objects.filter(pk=self.final.pk).update(is_active=False)  # nobody left to give the final approval
        low = low_application(email="lee@example.com", first_name="Lee")
        self.assertTrue(office(self.approver, f"/gold/{low.pk}/").context["final_approver_missing"])
        self.assertEqual(approval.approve(low, self.approver), invites.INVITED)
        self.assertEqual(GoldApplication.objects.get(pk=low.pk).status, GoldApplication.APPROVED)

    def test_the_office_shows_the_state_and_only_a_final_approver_gets_the_buttons(self):
        application = self.sent_for_final()
        page = office(self.final, f"/gold/{application.pk}/")
        self.assertContains(page, "Awaiting final approval")
        self.assertContains(page, "data-final-confirm")
        self.assertContains(page, "data-final-send-back")
        self.assertNotContains(office(self.approver, f"/gold/{application.pk}/"), "data-final-confirm")
        self.assertEqual(office(self.final, f"/gold/{application.pk}/final/send-back/", {"note": "Hold on"}).status_code, 302)
        page = office(self.approver, f"/gold/{application.pk}/")
        self.assertContains(page, "data-sent-back-note")
        self.assertContains(page, "Hold on")
        self.assertContains(office(self.approver, "/gold/?status=all"), "Sent back")

    def test_the_one_tap_links_refuse_the_wrong_person_a_used_link_and_an_expired_one(self):
        application = self.sent_for_final()
        url = re.search(r"Confirm approval: (http\S+)", mail.outbox[0].body).group(1).replace("http://office.localhost:8000", "")
        path, token = url.split("?")[0], url.split("/final/")[1].split("/")[0]

        self.assertEqual(Client(HTTP_HOST=OFFICE).get(path).status_code, 302)  # signed out: sign in, then continue
        self.assertEqual(office(self.approver, path).status_code, 403)  # an approver without the final role
        self.assertEqual(office(self.approver, f"/gold/{application.pk}/final/confirm/", {"token": token}).status_code, 403)
        self.assertEqual(office(None, "/gold/", None).status_code, 302)
        self.assertEqual(office(self.final, f"/gold/{application.pk}/final/not-a-token/").status_code, 410)  # forged
        self.assertEqual(office(self.final, path).status_code, 200)

        confirm = office(self.final, f"/gold/{application.pk}/final/confirm/", {"token": token})
        self.assertEqual(confirm.status_code, 302)
        self.assertEqual(GoldApplication.objects.get(pk=application.pk).status, GoldApplication.APPROVED)
        self.assertEqual(office(self.final, path).status_code, 410)  # used
        again = office(self.final, f"/gold/{application.pk}/final/send-back/", {"token": token, "note": "late"})
        self.assertEqual(again.status_code, 410)
        self.assertEqual(GoldApplication.objects.get(pk=application.pk).sent_back_at, None)

        other = self.sent_for_final_other()
        with mock.patch("time.time", return_value=time.time() - 15 * 86400):
            old = approval.make_final_token(other)
        self.assertEqual(office(self.final, f"/gold/{other.pk}/final/{old}/").status_code, 410)  # older than 14 days
        self.assertEqual(office(self.final, f"/gold/{other.pk}/final/{approval.make_final_token(other)}/").status_code, 200)
        self.assertEqual(office(self.final, f"/gold/{application.pk}/final/{approval.make_final_token(other)}/").status_code, 410)  # another application's token

    def sent_for_final_other(self):
        other = low_application(email="otto@example.com", first_name="Otto")
        approval.approve(other, self.approver)
        other.refresh_from_db()
        return other

    def test_the_suppression_guard_still_applies_to_the_new_emails(self):
        from notifications.models import EmailLog, EmailSuppression

        now = timezone.now()
        EmailSuppression.objects.create(email="final@example.test", reason="hard_bounce", first_seen=now, last_seen=now)
        application = low_application()
        approval.approve(application, self.approver)
        self.assertEqual(mail.outbox, [])
        self.assertTrue(EmailLog.objects.filter(template="gold_final", status="suppressed").exists())
