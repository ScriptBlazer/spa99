"""Review round: a sending address cannot be somebody else's, a Gold Delete leaves no listed thread behind, and a chat that wrote first shows on its lead's page.
Mocked: nothing real is sent."""
from django.test import override_settings

from emailchat import sender as sender_mod
from emailchat import services
from emailchat.models import Message, StaffSender, Thread
from emailchat.tests.test_direct_mail import BARRY, forward
from emailchat.tests.test_emailchat import Base, office
from emailchat.tests.test_office_sender import SENDING, staff


@override_settings(**SENDING)
class SendingAddressTests(Base):
    def test_a_developer_cannot_give_one_staff_member_another_ones_login_or_sending_address(self):
        from system.tests.test_system import unlocked_client
        from system.tests.test_team import at

        dev = at("developer", "dev@example.com")
        barry, moishe = staff("barry@staff.example.test", "Barry"), staff("moishe@bml.example.test", "Moishe")
        StaffSender.objects.create(user=moishe, sending_address="moishe.sends@staff.example.test")
        client = unlocked_client(dev)
        for who, taken in ((moishe, "barry@staff.example.test"), (barry, "Moishe.Sends@staff.example.test")):  # Barry's login address; Moishe's sending address
            self.assertContains(client.post(f"/team/{who.pk}/email/", {"sending_address": taken, "signature": ""}), "belongs to another person", status_code=400)
        self.assertEqual(StaffSender.objects.get(user=moishe).sending_address, "moishe.sends@staff.example.test")
        self.assertEqual(client.post(f"/team/{moishe.pk}/email/", {"sending_address": "moishe.sends@staff.example.test", "signature": ""}).status_code, 302)  # his own is fine

    def test_an_address_already_stored_that_is_somebody_elses_is_never_the_from(self):
        barry, moishe = staff("barry@staff.example.test", "Barry"), staff("moishe@bml.example.test", "Moishe")
        StaffSender.objects.create(user=moishe, sending_address="barry@staff.example.test")  # saved before the rule existed
        self.assertEqual(sender_mod.sender_for(moishe).source, "site")
        self.assertEqual(sender_mod.sender_for(barry).address, "barry@staff.example.test")


class GoldDeleteTests(Base):
    def test_a_direct_thread_from_the_applicants_address_is_not_listed_on_his_gold_page_and_a_linked_one_is_erased(self):
        from gold import actions, services as gold_services
        from gold.tests.test_gold import application_data
        from office import tools

        application = gold_services.submit_application(application_data(email="dan@example.com"))[0]
        direct_thread = Thread.objects.create(email="dan@example.com", subject="Direct", direct_to=BARRY)
        Message.objects.create(thread=direct_thread, direction="in", body_text="x", status="received", from_address="dan@example.com")
        linked = Thread.objects.create(email="dan@example.com", subject="Linked", application=application)
        target = tools.gold_target(application.pk)
        self.assertEqual(list(services.threads_for(target.addresses, target.user, target.application)), [linked])
        actions.delete_application(application, self.approver)
        self.assertEqual(list(Thread.objects.values_list("subject", flat=True).filter(subject__in=["Direct", "Linked"])), ["Direct"])  # the unlinked one was never his
        self.assertTrue(services.is_unproven(Thread.objects.get(subject="Direct")))  # still in the Email tab, for staff to link or delete


class ChatThatWroteFirstTests(Base):
    def test_an_unlinked_chat_on_a_leads_number_shows_open_on_his_page_with_an_unread_badge(self):
        from office.tests.test_leads import lead
        from whatsapp.models import Contact, Message as WaMessage

        session = lead("frank@example.com")
        type(session).objects.filter(pk=session.pk).update(lead_mobile="+447400123464", lead_first_name="Frank")
        contact = Contact.objects.create(phone="+447400123464", profile_name="Frank")
        WaMessage.objects.create(contact=contact, direction="in", kind="text", body="Hi", status="received")
        Contact.objects.filter(pk=contact.pk).update(last_message_at=session.created_at, last_direction="in")
        page = office(self.approver, "get", f"/leads/{session.pk}/")
        self.assertContains(page, "Open WhatsApp chat")
        self.assertContains(page, "o-badge-count")
        self.assertContains(page, f'href="/whatsapp/{contact.pk}/?from=lead%3A{session.pk}"')
