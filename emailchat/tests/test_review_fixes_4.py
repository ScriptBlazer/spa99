"""Release-gate review fixes: chats and the stranger rule (unproven mobile), the Gold-linked thread on an address correction, and merge moving chats. Mocked: nothing real is sent."""
from django.utils import timezone

from emailchat import services
from emailchat.models import Message, Thread
from emailchat.tests.test_emailchat import Base
from gold import services as gold_services
from gold.tests.test_gold import application_data
from office.tests.test_leads import lead
from outreach import services as outreach
from users import merge, services as user_services, tokens
from users.models import User
from users.tests.test_register import cleaned
from whatsapp import services as whatsapp
from whatsapp.models import Contact


class UnprovenMobileTests(Base):
    def test_an_unverified_accounts_mobile_finds_no_chat_until_it_is_verified_but_its_own_links_stay(self):
        victim = Contact.objects.create(phone="+447912345678", lead_email="victim@example.com")
        stranger = user_services.register_interest(cleaned(email="victim@example.com", mobile="07912 345678")).user
        self.assertEqual(stranger.mobile, "+447912345678")
        addresses = {"victim@example.com"}

        def found(person):
            return list(whatsapp.contacts_for_person(person, addresses))

        self.assertEqual(found(stranger), [])  # registering did not link the lead's chat to the account either
        self.assertIsNone(Contact.objects.get(pk=victim.pk).user_id)
        whatsapp.erase_person(stranger, addresses)
        self.assertTrue(Contact.objects.filter(pk=victim.pk).exists())  # staff erasure of the account never touched the lead's chat
        own = Contact.objects.create(phone="+447912345999", user=stranger)
        self.assertEqual(found(stranger), [own])  # a chat linked to the account stays
        user_services.verify_email(tokens.make_verify_token(stranger))  # verifying proves the ADDRESS, and the lead's chat is on that address
        stranger.refresh_from_db()
        self.assertCountEqual(found(stranger), [victim, own])  # once the address is proven the chat on that address is his (never because of the number)


class GoldLinkedThreadTests(Base):
    def test_an_application_lookup_finds_a_thread_on_another_address_so_export_and_erasure_cover_it(self):
        application, _ = gold_services.submit_application(application_data(email="old@example.com"))
        thread = Thread.objects.create(email="new@example.com", lead_email="new@example.com", subject="Moved earlier", application=application)
        Message.objects.create(thread=thread, direction="in", body_text="hello", status="received")
        account = User.objects.create_user("old@example.com", "a-long-test-password-1", email_verified_at=timezone.now())
        gold_services.link_user_applications(account)
        self.assertEqual(list(services.threads_for_person(account, {"old@example.com"})), [thread])
        self.assertEqual(len(services.export_for(services.threads_for_person(account, {"old@example.com"}))), 1)
        self.assertEqual(list(services.threads_for_person(None, {"old@example.com"})), [thread])  # staff export by the applicant's address
        self.assertEqual(services.erase_person(account, {"old@example.com"})["email_threads"], 1)
        self.assertFalse(Thread.objects.filter(pk=thread.pk).exists())

    def test_a_lead_correction_leaves_a_gold_linked_thread_on_the_applicants_address(self):
        lead("old@example.com")
        application, _ = gold_services.submit_application(application_data(email="old@example.com"))
        _, gold_thread = services.create_thread("old@example.com", "Gold chat", self.approver)
        _, plain_thread = services.create_thread("old@example.com", "Lead chat", self.approver)
        Thread.objects.filter(pk=plain_thread.pk).update(application=None)
        self.assertEqual(gold_thread.application_id, application.pk)
        self.assertEqual(outreach.correct_lead_email("old@example.com", "new@example.com", self.approver)[0], outreach.DONE)
        gold_thread.refresh_from_db()
        plain_thread.refresh_from_db()
        self.assertEqual(gold_thread.email, "old@example.com")  # staff replies still go to the applicant, not to whoever owns the corrected address
        self.assertEqual(plain_thread.email, "new@example.com")
        self.assertEqual(list(services.threads_for_person(None, {"old@example.com"})), [gold_thread])  # export and erasure by the applicant's address
        self.assertEqual(list(services.threads_for_person(None, {"new@example.com"})), [plain_thread])
        self.assertEqual(services.erase_person(None, {"new@example.com"})["email_threads"], 1)  # lead erasure takes his own thread only
        self.assertTrue(Thread.objects.filter(pk=gold_thread.pk).exists())

    def test_a_gold_thread_moves_when_the_application_is_already_on_the_new_address(self):
        application, _ = gold_services.submit_application(application_data(email="new@example.com"))
        thread = Thread.objects.create(email="old@example.com", lead_email="old@example.com", application=application)
        services.move_address("old@example.com", "new@example.com")
        thread.refresh_from_db()
        self.assertEqual((thread.email, thread.lead_email), ("new@example.com", "new@example.com"))


class MergeMovesChatsTests(Base):
    def test_merge_moves_threads_and_whatsapp_chats_to_keep_before_the_removed_account_is_deleted(self):
        keep = user_services.register_interest(cleaned(email="keep@example.com", mobile="07912345601")).user
        gone = user_services.register_interest(cleaned(email="gone@example.com", mobile="07912345602")).user
        User.objects.filter(pk__in=[keep.pk, gone.pk]).update(email_verified_at=timezone.now())
        keep.refresh_from_db()
        gone.refresh_from_db()
        owned = Thread.objects.create(email="gone@example.com", subject="His", user=gone)
        by_address = Thread.objects.create(email="gone@example.com", subject="Same address")
        other = Thread.objects.create(email="someone@example.com", subject="Not his")
        chat = Contact.objects.create(phone="+447912345602", user=gone, lead_email="gone@example.com")
        boss = User.objects.create_user("boss@example.com", "x-Pass-123456", is_superuser=True, is_staff=True)
        merge.merge(boss, keep, gone)
        for row in (owned, by_address, other, chat):
            row.refresh_from_db()
        self.assertEqual((owned.user_id, owned.email), (keep.pk, "keep@example.com"))
        self.assertEqual((by_address.user_id, by_address.email), (keep.pk, "keep@example.com"))
        self.assertEqual((other.user_id, other.email), (None, "someone@example.com"))
        self.assertEqual((chat.user_id, chat.lead_email), (keep.pk, "keep@example.com"))
        self.assertCountEqual(services.threads_for_person(keep, {"keep@example.com"}), [owned, by_address])
        self.assertEqual(list(whatsapp.contacts_for_person(keep, {"keep@example.com"})), [chat])
        self.assertEqual(services.erase_person(keep, {"keep@example.com"})["email_threads"], 2)
