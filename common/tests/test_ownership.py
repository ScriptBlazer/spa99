"""Who owns a chat or thread: the one rule (common.ownership), through the real views where possible. Mocked: nothing is sent, the queue runs inline."""
import json

from django.test import Client, override_settings
from django.utils import timezone

from common import levels, ownership
from emailchat import services as emailchat
from emailchat.models import Message as EmailMessage, Thread
from emailchat.tests.test_emailchat import CONFIG as EMAIL_CONFIG, office
from gold import services as gold_services
from gold.models import GoldApplication
from gold.tests.test_gold import application_data
from journey import services as journey
from office.tests.test_leads import verify
from office.tests.test_office import OfficeTestCase
from plans.tests.helpers import make_team_member
from users import merge, services as user_services
from users.models import User
from users.tests.test_register import cleaned, signup_data
from whatsapp import services as whatsapp
from whatsapp.models import Contact, Message as WhatsAppMessage

VICTIM = "victim@example.com"


@override_settings(**EMAIL_CONFIG)
class Base(OfficeTestCase):
    def setUp(self):
        self.admin = make_team_member("admin@example.test", levels.ADMIN)

    def public_client(self):
        client = Client(HTTP_HOST="localhost")
        client.get("/gold/options/")
        return client

    def register(self, email, mobile="07912 345678"):
        response = Client(HTTP_HOST="localhost").post("/register/", signup_data(email=email, mobile=mobile))
        self.assertIn(response.status_code, (200, 302))
        return User.objects.get(email__iexact=email)

    def apply(self, client, **over):
        token = client.cookies["csrftoken"].value
        response = client.post("/gold/apply/", json.dumps(application_data(privacy_accepted=True, **over)), content_type="application/json", headers={"X-CSRFToken": token})
        self.assertEqual(response.status_code, 201, response.content)
        return GoldApplication.objects.get(email__iexact=over.get("email", "dan@example.com"))

    def thread_with_words(self, email=VICTIM, words="Private reply from the victim"):
        _, thread = emailchat.create_thread(email, "Gold chat", self.admin)
        EmailMessage.objects.create(thread=thread, direction="in", body_text=words, status="received")
        thread.refresh_from_db()
        return thread

    def export(self, user):
        return office(self.admin, "get", f"/people/{user.pk}/export/").content.decode()


class StrangerRegistersWithAVictimsAddressTests(Base):
    def test_register_then_apply_links_nothing_so_export_and_delete_never_touch_the_victims_thread(self):
        stranger = self.register(VICTIM)
        self.assertIsNone(stranger.email_verified_at)
        application = self.apply(self.public_client(), email=VICTIM)
        self.assertIsNone(application.user_id)  # an unverified account never takes the application
        thread = self.thread_with_words()
        self.assertEqual(thread.application_id, application.pk)
        self.assertNotIn("Private reply from the victim", self.export(stranger))
        office(self.admin, "post", f"/people/{stranger.pk}/delete/")
        self.assertFalse(User.objects.filter(pk=stranger.pk).exists())
        self.assertTrue(Thread.objects.filter(pk=thread.pk).exists())  # the victim's thread survives the stranger's erasure
        self.assertTrue(GoldApplication.objects.filter(pk=application.pk).exists())

    def test_an_old_link_on_live_data_is_not_trusted_either(self):
        stranger = self.register(VICTIM)
        application = self.apply(self.public_client(), email=VICTIM)
        GoldApplication.objects.filter(pk=application.pk).update(user=stranger)  # what the old code left on live: an application linked to an unverified account
        thread = self.thread_with_words()
        self.assertNotIn("Private reply from the victim", self.export(stranger))
        office(self.admin, "post", f"/people/{stranger.pk}/delete/")
        self.assertTrue(Thread.objects.filter(pk=thread.pk).exists())

    def test_verifying_links_the_application_and_then_the_thread_is_his(self):
        member = self.register("dan@example.com")
        application = self.apply(self.public_client(), email="dan@example.com")
        self.assertIsNone(application.user_id)
        thread = self.thread_with_words("dan@example.com", "Dan's own reply")
        self.assertNotIn("Dan's own reply", self.export(member))
        verify(member)
        application.refresh_from_db()
        thread.refresh_from_db()
        self.assertEqual((application.user_id, thread.user_id), (member.pk, member.pk))
        self.assertIn("Dan's own reply", self.export(member))

    def test_approving_and_the_invite_still_work_for_an_application_with_no_account_link(self):
        from gold import invites
        from gold.tests.test_invite import staff

        self.register("dan@example.com")
        application = self.apply(self.public_client(), email="dan@example.com")
        self.assertEqual(invites.approve_and_invite(application, staff()), invites.ACTIVATED)  # an existing account is activated and linked by the approval itself
        application.refresh_from_db()
        self.assertIsNotNone(application.user_id)


class UnverifiedMemberWhatsAppTests(Base):
    def test_staff_opening_his_chat_links_it_so_export_and_delete_find_it(self):
        member = self.register("acc@example.com", mobile="07400 123789")
        contact = whatsapp.get_or_create_contact("+447400123789")
        WhatsAppMessage.objects.create(contact=contact, direction="in", kind="text", body="my words", status="received")
        self.assertIsNone(contact.user_id)  # unverified: the number links nothing by itself
        self.assertNotIn("my words", self.export(member))
        office(self.admin, "get", f"/people/{member.pk}/whatsapp/")  # "Open WhatsApp chat": staff's explicit choice
        contact.refresh_from_db()
        self.assertEqual(contact.user_id, member.pk)
        self.assertIn("my words", self.export(member))
        office(self.admin, "post", f"/people/{member.pk}/delete/")
        self.assertFalse(Contact.objects.filter(pk=contact.pk).exists())
        self.assertEqual(WhatsAppMessage.objects.filter(contact_id=contact.pk).count(), 0)

    def test_a_leads_chat_is_not_claimed_from_a_strangers_page(self):
        stranger = self.register("stranger@example.com", mobile="07400 123790")
        chat = Contact.objects.create(phone="+447400123790", lead_email=VICTIM, name="Victim")
        office(self.admin, "get", f"/people/{stranger.pk}/whatsapp/")
        chat.refresh_from_db()
        self.assertIsNone(chat.user_id)  # staff could open it, but it was not linked: it has a lead address that is not his


class StrangerWithALeadsMobileTests(Base):
    def test_verifying_his_own_email_does_not_take_the_leads_chat_name_or_export(self):
        session = journey.create_session("Mozilla/5.0")
        journey.save_lead(session, VICTIM, True, first_name="Leo", mobile="07400 123790", require_details=True)
        chat = whatsapp.get_or_create_contact("+447400123790")
        WhatsAppMessage.objects.create(contact=chat, direction="in", kind="text", body="lead words", status="received")
        stranger = self.register("stranger@example.com", mobile="07400 123790")
        verify(stranger)
        chat.refresh_from_db()
        self.assertEqual((chat.user_id, chat.name, chat.lead_email), (None, "Leo", VICTIM))
        self.assertNotIn("lead words", self.export(stranger))
        lead_export = office(self.admin, "get", f"/leads/{session.pk}/export/").content.decode()
        self.assertIn("lead words", lead_export)  # the lead's own export still has it

    def test_a_chat_with_no_lead_address_still_links_to_the_verified_account_on_the_number(self):
        chat = whatsapp.get_or_create_contact("+447400123791")
        member = self.register("acc@example.com", mobile="07400 123791")
        verify(member)
        chat.refresh_from_db()
        self.assertEqual(chat.user_id, member.pk)


class MergeOfAnUnverifiedAccountTests(Base):
    def test_victims_gold_thread_and_chat_stay_where_they_are(self):
        keep = self.register("keep@example.com", mobile="07912345601")
        verify(keep)
        keep.refresh_from_db()
        gone = self.register(VICTIM, mobile="07912345602")
        application, _ = gold_services.submit_application(application_data(email=VICTIM, mobile="+447912345699"))
        GoldApplication.objects.filter(pk=application.pk).update(user=gone)  # as the old code linked it
        thread = self.thread_with_words()
        chat = Contact.objects.create(phone="+447912345699", application=application, lead_email=VICTIM)
        boss = User.objects.create_user("boss@example.com", "x-Pass-123456", is_superuser=True, is_staff=True)
        merge.merge(boss, keep, gone)
        for row in (application, thread, chat):
            row.refresh_from_db()
        self.assertEqual((application.user_id, application.email), (None, VICTIM))
        self.assertEqual((thread.user_id, thread.email, thread.application_id), (None, VICTIM, application.pk))  # staff replies still go to the victim
        self.assertEqual((chat.user_id, chat.lead_email), (None, VICTIM))
        self.assertEqual(list(emailchat.threads_for_person(keep, {"keep@example.com"})), [])


class GoldDeleteTests(Base):
    def test_deleting_an_applicants_application_erases_his_threads_and_chats(self):
        application, _ = gold_services.submit_application(application_data(email="solo@example.com", mobile="+447400555001"))
        thread = self.thread_with_words("solo@example.com", "applicant words")
        chat = whatsapp.get_or_create_contact("+447400555001")
        WhatsAppMessage.objects.create(contact=chat, direction="in", kind="text", body="applicant chat", status="received")
        self.assertEqual((thread.application_id, chat.application_id), (application.pk, application.pk))
        office(self.admin, "post", f"/gold/{application.pk}/delete/")
        self.assertFalse(GoldApplication.objects.filter(pk=application.pk).exists())
        self.assertFalse(Thread.objects.filter(pk=thread.pk).exists())
        self.assertFalse(Contact.objects.filter(pk=chat.pk).exists())
        self.assertEqual(EmailMessage.objects.filter(thread_id=thread.pk).count(), 0)

    def test_a_thread_owned_by_an_account_stays_reachable(self):
        member = User.objects.create_user("acc@example.com", "a-long-test-password-1", email_verified_at=timezone.now())
        application, _ = gold_services.submit_application(application_data(email="acc@example.com"))
        thread = self.thread_with_words("acc@example.com", "his words")
        self.assertEqual(thread.user_id, member.pk)
        office(self.admin, "post", f"/gold/{application.pk}/delete/")
        self.assertTrue(Thread.objects.filter(pk=thread.pk, user=member).exists())


class JoinsUpOnVerifyTests(Base):
    def test_a_leads_thread_and_chat_join_his_account_when_he_verifies(self):
        session = journey.create_session("Mozilla/5.0")
        journey.save_lead(session, "hugo@example.com", True, first_name="Hugo", mobile="07400 123792", require_details=True)
        chat = whatsapp.get_or_create_contact("+447400123792")
        WhatsAppMessage.objects.create(contact=chat, direction="in", kind="text", body="hugo chat", status="received")
        thread = self.thread_with_words("hugo@example.com", "hugo thread")
        member = self.register("hugo@example.com", mobile="07400 123792")
        self.assertNotIn("hugo thread", self.export(member))
        verify(member)
        exported = self.export(member)
        self.assertIn("hugo thread", exported)
        self.assertIn("hugo chat", exported)
        thread.refresh_from_db()
        chat.refresh_from_db()
        self.assertEqual((thread.user_id, chat.user_id), (member.pk, member.pk))


class RuleTests(Base):
    def test_mobile_link_and_claim_follow_the_rule(self):
        verified = User.objects.create_user("v@example.com", "a-long-test-password-1", email_verified_at=timezone.now())
        unverified = User.objects.create_user("u@example.com", "a-long-test-password-1")
        self.assertTrue(ownership.mobile_link_ok("", verified))
        self.assertTrue(ownership.mobile_link_ok("V@example.com", verified))
        self.assertFalse(ownership.mobile_link_ok("other@example.com", verified))
        self.assertFalse(ownership.mobile_link_ok("", unverified))
        free, led = Contact.objects.create(phone="+447400555101"), Contact.objects.create(phone="+447400555102", lead_email="other@example.com")
        self.assertTrue(ownership.claim(free, unverified))
        self.assertFalse(ownership.claim(led, unverified))
        self.assertFalse(ownership.claim(free, verified))  # already owned: never taken
        self.assertEqual(ownership.trusted_addresses(unverified, {"U@example.com"}), set())
        self.assertEqual(ownership.trusted_addresses(None, {"U@example.com"}), {"u@example.com"})
