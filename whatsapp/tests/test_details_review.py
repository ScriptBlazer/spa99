"""Review fixes on the Details rows: a changed lead email, the Gold mobile of an unverified account, a name that survives adding a number, blank keeps."""
from django.utils import timezone

from gold import services as gold_services
from gold.tests.test_gold import application_data
from journey.models import JourneySession
from mailings.models import EmailOptOut
from notifications.models import EmailLog, EmailSuppression
from office import tools
from office.tests.test_leads import lead
from outreach import services as outreach
from outreach.models import ArchivedLead, NextMorningEmail
from users import services as user_services
from users.tests.test_register import cleaned
from whatsapp.models import Contact
from whatsapp.tests.test_whatsapp import Base, office


class DetailsReviewTests(Base):
    def test_a_lead_email_cannot_take_a_gold_archived_or_chat_only_address_and_a_long_one_is_invalid(self):
        lead("typo@example.com")
        gold_services.submit_application(application_data(email="gold@example.com"))
        ArchivedLead.objects.create(email="away@example.com")
        Contact.objects.create(phone="+447400123456", lead_email="chat@example.com")
        for address, kind in (("gold@example.com", "gold"), ("away@example.com", "archived"), ("chat@example.com", "chat")):
            result, owner = outreach.correct_lead_email("typo@example.com", address, self.approver)
            self.assertEqual((result, owner["kind"]), (outreach.TAKEN, kind))
        self.assertEqual(outreach.correct_lead_email("typo@example.com", "a" * 300 + "@example.com", self.approver)[0], outreach.INVALID)
        self.assertTrue(JourneySession.objects.filter(lead_email="typo@example.com").exists())

    def test_a_lead_on_a_gold_application_is_refused_a_change(self):
        lead("both@example.com")
        gold_services.submit_application(application_data(email="both@example.com"))
        result, message = outreach.correct_lead_email("both@example.com", "new@example.com", self.approver)
        self.assertEqual((result, message), (outreach.INVALID, "This address is on a Gold application. Change it there."))

    def test_gold_mobile_with_an_unverified_account_changes_the_application_and_the_page(self):
        application, _ = gold_services.submit_application(application_data(email="gd@example.com", mobile="+447400123999"))
        account = user_services.register_interest(cleaned(email="gd@example.com", mobile="07400123111")).user  # not verified
        application.user = account
        application.save(update_fields=["user"])
        self.assertEqual(outreach.set_gold_mobile(application, self.approver, "07400 123777", "GB")[0], outreach.DONE)
        application.refresh_from_db()
        account.refresh_from_db()
        self.assertEqual((application.mobile, account.mobile), ("+447400123777", "+447400123111"))
        page = office(self.approver, "get", f"/gold/{application.pk}/")
        self.assertEqual(page.context["whatsapp"]["mobile"], "+447400123777")

    def test_a_saved_name_shows_with_no_mobile_and_adding_a_number_keeps_it_and_blank_keeps(self):
        session = lead("dee@example.com")
        outreach.set_lead_contact("dee@example.com", self.approver, first_name="Dee")
        page = office(self.approver, "get", f"/leads/{session.pk}/")
        self.assertEqual(page.context["whatsapp"]["first_name"], "Dee")
        self.assertEqual(tools.mobile_and_name(tools.target_for("lead", session.pk)), ("", "Dee"))
        office(self.approver, "post", f"/leads/{session.pk}/contact/", {"first_name": "", "mobile_country": "GB", "mobile": "07400 123456"})
        self.assertEqual(JourneySession.objects.get(pk=session.pk).lead_first_name, "Dee")
        office(self.approver, "post", f"/leads/{session.pk}/contact/", {"first_name": "Dee", "mobile": ""})
        self.assertEqual(JourneySession.objects.get(pk=session.pk).lead_mobile, "+447400123456")

    def test_person_and_gold_posts_with_no_or_blank_mobile_keep_the_number(self):
        user = user_services.register_interest(cleaned(email="acc@example.com", mobile="07400123789")).user
        from office.tests.test_leads import verify

        verify(user)
        for data in ({}, {"mobile": ""}):
            office(self.approver, "post", f"/people/{user.pk}/mobile/", data)
        user.refresh_from_db()
        self.assertEqual(user.mobile, "+447400123789")
        application, _ = gold_services.submit_application(application_data(email="gd@example.com", mobile="+447400123999"))
        office(self.approver, "post", f"/gold/{application.pk}/mobile/", {"mobile": ""})
        application.refresh_from_db()
        self.assertEqual(application.mobile, "+447400123999")

    def test_a_change_after_the_follow_up_went_does_not_send_again_and_keeps_the_opt_out_and_logs(self):
        lead("typo@example.com")
        now = timezone.now()
        NextMorningEmail.objects.create(email="typo@example.com", lead_at=now, due_at=now, sent_at=now)
        EmailOptOut.objects.create(email="typo@example.com")
        EmailLog.objects.create(to="typo@example.com", template="lead_next_morning", subject="Hi", status="sent", sent_at=now)
        self.assertEqual(outreach.correct_lead_email("typo@example.com", "fixed@example.com", self.approver)[0], outreach.DONE)
        self.assertTrue(NextMorningEmail.objects.filter(email="fixed@example.com", sent_at__isnull=False).exists())
        self.assertFalse(NextMorningEmail.objects.filter(email="typo@example.com").exists())
        self.assertTrue(EmailOptOut.objects.filter(email="fixed@example.com").exists())
        self.assertTrue(EmailLog.objects.filter(to="fixed@example.com", status="sent").exists())

    def test_a_bounced_change_drops_the_row_and_the_logs_so_a_resend_stays_the_staff_action(self):
        lead("bad@example.com")
        now = timezone.now()
        NextMorningEmail.objects.create(email="bad@example.com", lead_at=now, due_at=now, sent_at=now)
        EmailLog.objects.create(to="bad@example.com", template="lead_next_morning", subject="Hi", status="failed")
        EmailSuppression.objects.create(email="bad@example.com", reason="hard_bounce", first_seen=now, last_seen=now)
        self.assertEqual(outreach.correct_lead_email("bad@example.com", "good@example.com", self.approver)[0], outreach.DONE)
        self.assertFalse(NextMorningEmail.objects.exists())
        self.assertFalse(EmailLog.objects.exists())
