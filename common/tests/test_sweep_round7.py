"""The last ownership sweep (2026-11-04): an address typed on a public form never sets a link or marks anything for someone else. Gold apply and relink on a thread; Register and a
person's invite; failed sign-ins typed with an address. Mocked: nothing is sent."""
import uuid

from django.utils import timezone

from common.models import LoginEvent
from common.tests.test_ownership import VICTIM, Base
from emailchat import services as emailchat
from emailchat.tests.test_emailchat import office
from emailchat.models import Thread
from gold.models import GoldApplication
from mailings.models import Invite
from office.tests.test_leads import verify
from users import services as user_services


class RelinkNeverLinksByTypedAddressTests(Base):
    def test_a_gold_application_typed_with_a_leads_address_does_not_link_his_thread_so_gold_delete_leaves_it(self):
        thread = self.thread_with_words(VICTIM, "the lead's words", lead_email=VICTIM)  # staff started it from the lead's page
        application = self.apply(self.public_client(), email=VICTIM)  # a stranger applies with the lead's address
        emailchat.relink(VICTIM, application.email)
        thread.refresh_from_db()
        self.assertIsNone(thread.application_id)
        self.assertEqual(thread.lead_email, VICTIM)  # what staff set is untouched
        office(self.admin, "post", f"/gold/{application.pk}/delete/")
        self.assertFalse(GoldApplication.objects.filter(pk=application.pk).exists())
        self.assertTrue(Thread.objects.filter(pk=thread.pk).exists())  # before the fix the delete erased it

    def test_a_typed_address_thread_links_nothing_and_a_page_start_links_what_staff_chose(self):
        typed = self.thread_with_words("typed@example.com", "x")
        self.assertEqual((typed.user_id, typed.lead_email, typed.application_id), (None, "", None))
        application = self.apply(self.public_client(), email="gold@example.com")
        started = self.thread_with_words("gold@example.com", "y", application=application)
        self.assertEqual((started.application_id, started.lead_email), (application.pk, "gold@example.com"))


class RegisterNeverMarksSomeoneElsesInviteTests(Base):
    def test_registering_with_an_invited_address_marks_the_invite_only_once_the_address_is_verified(self):
        invite = Invite.objects.create(name="V", email=VICTIM, batch_id=uuid.uuid4(), status=Invite.SENT, expires_at=timezone.now() + timezone.timedelta(days=30))
        stranger = self.register(VICTIM)
        invite.refresh_from_db()
        self.assertEqual((invite.status, invite.registered_user_id), (Invite.SENT, None))  # an unverified account may be a stranger's
        verify(stranger)
        invite.refresh_from_db()
        self.assertEqual((invite.status, invite.registered_user_id), (Invite.REGISTERED, stranger.pk))


class FailedSignInsTests(Base):
    def test_attempts_typed_with_an_unverified_accounts_address_are_not_his_to_export_or_erase(self):
        stranger = self.register(VICTIM)
        other = LoginEvent.objects.create(event=LoginEvent.FAILED, attempted_email=VICTIM, ip_address="198.51.100.9")  # the real owner's wrong tries, or an attacker's: not the stranger's
        own = LoginEvent.objects.create(event=LoginEvent.LOGIN, user=stranger, attempted_email=VICTIM, ip_address="203.0.113.1")
        exported = user_services.export_user_data(stranger)
        self.assertNotIn("198.51.100.9", str(exported))
        self.assertIn("203.0.113.1", str(exported))
        user_services.delete_user_data(stranger)
        self.assertTrue(LoginEvent.objects.filter(pk=other.pk).exists())
        self.assertFalse(LoginEvent.objects.filter(pk=own.pk).exists())

    def test_once_verified_they_are_his(self):
        member = self.register("dan@example.com")
        verify(member)
        member.refresh_from_db()
        LoginEvent.objects.create(event=LoginEvent.FAILED, attempted_email="dan@example.com", ip_address="198.51.100.10")
        self.assertIn("198.51.100.10", str(user_services.export_user_data(member)))
