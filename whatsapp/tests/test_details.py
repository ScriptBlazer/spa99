"""The Details rows in the Reach out card (lead, person, Gold): who sees which control, the person mobile dialog's view, and a lead's email changed with no bounce."""
from gold import services as gold_services
from gold.tests.test_gold import application_data
from notifications.models import EmailSuppression
from office.tests.test_leads import lead, verify
from outreach import services as outreach
from outreach.models import PersonEdit
from users import services as user_services
from users.tests.test_register import cleaned
from whatsapp import services
from whatsapp.models import Contact
from whatsapp.tests.test_whatsapp import Base, office


class DetailsTests(Base):
    def lead_page(self, user, email="dee@example.com", mobile="07400 123456"):
        session = lead(email)
        outreach.set_lead_contact(email, self.approver, first_name="Dee", mobile=mobile or None)
        return session, office(user, "get", f"/leads/{session.pk}/").content.decode()

    def person(self, mobile="07400123789"):
        user = user_services.register_interest(cleaned(email="acc@example.com", mobile=mobile)).user
        verify(user)
        return user

    def test_lead_page_an_editor_gets_name_mobile_and_email_controls_a_reader_only_values(self):
        _, html = self.lead_page(self.approver)
        self.assertEqual(html.count("data-details"), 1)
        for hook in ("data-change-name", "data-change-mobile", "data-change-email"):
            self.assertEqual(html.count(hook + ">"), 1, hook)
        self.assertNotIn("data-add-mobile", html)
        _, reader = self.lead_page(self.reader, "dee2@example.com")
        self.assertIn("data-details", reader)
        self.assertIn("dee2@example.com", reader)
        for hook in ("data-change-name", "data-change-mobile", "data-change-email", "data-add-mobile", 'data-dialog="correct-email"'):
            self.assertNotIn(hook, reader)

    def test_lead_with_no_mobile_has_one_add_and_the_grey_line_is_plain_text(self):
        _, html = self.lead_page(self.approver, "none@example.com", mobile="")
        self.assertEqual(html.count("data-add-mobile"), 1)
        self.assertEqual(html.count('data-dialog-open="mobile"'), 2)  # the name's Add and the mobile's Add, both on the Details rows
        self.assertIn("Add a number to enable WhatsApp", html)
        self.assertNotIn("o-channel-add", html)

    def test_person_page_mobile_has_add_or_change_and_the_email_is_text_with_no_control(self):
        user = self.person()
        html = office(self.approver, "get", f"/people/{user.pk}/").content.decode()
        self.assertEqual(html.count("data-change-mobile"), 1)  # one control only: the rail card no longer carries a second
        self.assertEqual(html.count("data-mobile-row"), 1)
        self.assertIn("acc@example.com", html)
        for hook in ("data-change-email", "data-change-name", "correct-email"):
            self.assertNotIn(hook, html)
        reader = office(self.reader, "get", f"/people/{user.pk}/").content.decode()
        self.assertIn("data-details", reader)
        self.assertNotIn("data-change-mobile", reader)
        self.assertIn("+447400123789", reader)
        user.mobile = None
        user.save(update_fields=["mobile"])
        self.assertEqual(office(self.approver, "get", f"/people/{user.pk}/").content.decode().count("data-add-mobile"), 1)

    def test_gold_page_has_the_mobile_row_only(self):
        application, _ = gold_services.submit_application(application_data(email="gd@example.com", mobile="+447400123999"))
        html = office(self.approver, "get", f"/gold/{application.pk}/").content.decode()
        self.assertEqual(html.count("data-change-mobile"), 1)
        for hook in ("data-change-email", "data-change-name"):
            self.assertNotIn(hook, html)
        reader = office(self.reader, "get", f"/gold/{application.pk}/").content.decode()
        self.assertIn("data-details", reader)
        self.assertNotIn("data-change-mobile", reader)

    def test_person_mobile_dialog_is_prefilled_saved_audited_refuses_a_taken_number_and_the_chat_follows(self):
        user = self.person()
        page = office(self.approver, "get", f"/people/{user.pk}/")
        self.assertEqual(page.context["whatsapp"]["edit_url"], f"/people/{user.pk}/mobile/")
        self.assertContains(page, "Now: +447400123789.")  # the dialog's hint
        self.assertEqual(page.context["whatsapp"]["state"], "ready")
        other = self.person_other()
        taken = office(self.approver, "post", f"/people/{user.pk}/mobile/", {"mobile_country": "GB", "mobile": "07400 123555"}, HTTP_X_REQUESTED_WITH="fetch").json()
        self.assertFalse(taken["ok"])
        self.assertEqual(taken["errors"]["mobile"], f"This number is already on {other.get_full_name() or other.email}.")
        saved = office(self.approver, "post", f"/people/{user.pk}/mobile/", {"mobile_country": "GB", "mobile": "07400 123790"}, HTTP_X_REQUESTED_WITH="fetch").json()
        self.assertTrue(saved["ok"])
        user.refresh_from_db()
        self.assertEqual(user.mobile, "+447400123790")
        self.assertTrue(PersonEdit.objects.filter(email="acc@example.com", what=PersonEdit.MOBILE, before="+447400123789", after="+447400123790").exists())
        contact = services.get_or_create_contact("+447400123790")
        self.assertTrue(Contact.objects.filter(pk=contact.pk).exists())
        again = office(self.approver, "get", f"/people/{user.pk}/")
        self.assertEqual(again.context["whatsapp"]["mobile"], "+447400123790")
        self.assertContains(again, "+447400123790")
        self.assertEqual(office(self.reader, "post", f"/people/{user.pk}/mobile/", {"mobile": "07400 123111"}).status_code, 403)

    def person_other(self):
        other = user_services.register_interest(cleaned(email="other@example.com", mobile="07400123555")).user
        verify(other)
        return other

    def test_a_lead_email_changes_without_a_bounce_with_the_right_words_one_dialog_and_audit(self):
        session, html = self.lead_page(self.approver, "typo@example.com")
        self.assertEqual(html.count('data-dialog="correct-email"'), 1)
        self.assertEqual(html.count('data-dialog-open="correct-email"'), 1)  # the Details Change, no bounce notice
        self.assertIn("Change the email", html)
        self.assertNotIn("Correct the email", html)
        self.assertNotIn("bounce list", html)
        answer = office(self.approver, "post", f"/leads/{session.pk}/email/", {"email": "fixed@example.com"}, follow=True)
        self.assertIn("Email changed.", " ".join(str(m) for m in answer.context["messages"]))
        self.assertTrue(PersonEdit.objects.filter(what=PersonEdit.EMAIL, before="typo@example.com", after="fixed@example.com").exists())
        self.assertFalse(EmailSuppression.objects.exists())  # nothing was suppressed, nothing is invented
        self.assertIn("fixed@example.com", answer.content.decode())

    def test_a_bounced_lead_keeps_the_correct_the_email_wording_and_still_one_dialog(self):
        from django.utils import timezone

        session = lead("bad@example.com")
        EmailSuppression.objects.create(email="bad@example.com", reason="hard_bounce", first_seen=timezone.now(), last_seen=timezone.now())
        html = office(self.approver, "get", f"/leads/{session.pk}/").content.decode()
        self.assertEqual(html.count('data-dialog="correct-email"'), 1)
        self.assertIn("Correct the email", html)
        self.assertIn("The old one stays on the bounce list.", html)
