"""Review round 2 of WhatsApp. Mocked: no real Twilio call."""
from datetime import timedelta

from django.utils import timezone

from gold import services as gold_services
from gold.models import GoldApplication
from gold.tests.test_gold import application_data
from outreach import services as outreach
from users import services as user_services
from users.tests.test_register import cleaned
from whatsapp import services
from whatsapp.models import Contact, Message, Template
from whatsapp.tests.test_whatsapp import PHONE, SENDER, Base, office, twilio_post


class StatusWithoutSavedSidTests(Base):
    def test_a_tick_finds_a_message_whose_sid_was_never_saved_through_the_callback_address(self):
        self.open_window()
        _, sent = services.send_text(self.contact, self.approver, "Hello")
        Message.objects.filter(pk=sent.pk).update(twilio_sid=None, status="queued", claimed_at=timezone.now() - timedelta(minutes=20), updated_at=timezone.now() - timedelta(minutes=20))
        sent.refresh_from_db()
        self.assertTrue(services.can_retry(sent))  # the page would offer Try again, which could send a second WhatsApp
        params = {"MessageSid": "SMlost", "MessageStatus": "delivered", "From": f"whatsapp:{SENDER}", "To": f"whatsapp:{PHONE}"}
        twilio_post("/twilio/whatsapp/status/?m=999999", params)  # a message id that is not ours, or the wrong number: nothing changes
        sent.refresh_from_db()
        self.assertIsNone(sent.twilio_sid)
        twilio_post(f"/twilio/whatsapp/status/?m={sent.pk}", {**params, "To": "whatsapp:+447400999999"})
        sent.refresh_from_db()
        self.assertIsNone(sent.twilio_sid)
        twilio_post(f"/twilio/whatsapp/status/?m={sent.pk}", params)
        sent.refresh_from_db()
        self.assertEqual((sent.twilio_sid, sent.status), ("SMlost", "delivered"))
        self.assertFalse(services.can_retry(sent))


class StuckReachesAnOpenPageTests(Base):
    def test_a_message_that_turns_stuck_is_sent_once_and_never_again(self):
        self.open_window()
        message = Message.objects.create(contact=self.contact, direction="out", kind="text", body="Hi", status="queued", claimed_at=timezone.now())
        start = timezone.now()
        quiet = services.poll_updates(Message.objects.filter(contact=self.contact), message.pk, start, start + timedelta(minutes=1))
        self.assertEqual(list(quiet), [])
        later = services.poll_updates(Message.objects.filter(contact=self.contact), message.pk, start + timedelta(minutes=1), start + timedelta(minutes=11))
        self.assertEqual([m.pk for m in later], [message.pk])
        again = services.poll_updates(Message.objects.filter(contact=self.contact), message.pk, start + timedelta(minutes=11), start + timedelta(minutes=12))
        self.assertEqual(list(again), [])


class GoldNumberChangeTests(Base):
    def gold_with_chat(self, email="gl@example.com", mobile="+447400333333"):
        application, _ = gold_services.submit_application(application_data(email=email, mobile=mobile))
        application.refresh_from_db()
        contact = Contact.objects.create(phone=application.mobile)
        services.resolve_links(contact)
        Message.objects.create(contact=contact, direction="in", status="received", body="private gold chat", twilio_sid="SMgold")
        return application, contact

    def test_the_old_chat_is_still_found_after_the_number_changes_and_erased_with_the_lead(self):
        application, contact = self.gold_with_chat()
        self.assertEqual(contact.application_id, application.pk)
        outreach.set_gold_mobile(application, self.approver, "07400 444444", "GB")
        found = services.contacts_for_person(None, {"gl@example.com"}, services.person_phones(None, {"gl@example.com"}))
        self.assertIn(contact.pk, [c.pk for c in found])
        services.erase_person(None, {"gl@example.com"})
        self.assertFalse(Contact.objects.filter(pk=contact.pk).exists())

    def test_a_number_on_another_gold_applicant_is_refused_but_his_own_is_allowed(self):
        application, _ = self.gold_with_chat("g1@example.com", "+447400111111")
        other, _ = gold_services.submit_application(application_data(email="g2@example.com", mobile="+447400222222"))
        result, errors = outreach.set_gold_mobile(other, self.approver, "+447400111111", "GB")
        self.assertEqual(result, outreach.INVALID)
        self.assertIn("already on", errors["mobile"])
        self.assertIsNone(services.owner_of_phone(application.mobile, exclude_email="g1@example.com"))  # his own application
        self.assertIsNotNone(services.owner_of_phone(application.mobile, exclude_email="someone@example.com"))

    def test_the_gold_page_with_a_number_has_a_change_button(self):
        application, _ = self.gold_with_chat("g3@example.com", "+447400555555")
        html = office(self.approver, "get", f"/gold/{application.pk}/").content.decode()
        self.assertIn('data-dialog="mobile"', html)
        self.assertIn("data-change-mobile", html)


class TemplateQuoteTests(Base):
    def test_a_template_with_no_text_never_sends_its_internal_name(self):
        template = Template.objects.create(content_sid="HX9", name="spa99_internal_promo_v3", body="", approval_status="approved")
        empty = Message.objects.create(contact=self.contact, direction="out", kind="template", body="", template=template, status="delivered", twilio_sid="SMt")
        self.assertEqual(services.quote_text(empty), "Internal promo v3")  # staff still see which template it was
        sent = services.outgoing_text(Message(body="ok", kind="text", reply_to=empty))
        self.assertNotIn("spa99", sent)
        self.assertEqual(sent, "> Message\n\nok")
