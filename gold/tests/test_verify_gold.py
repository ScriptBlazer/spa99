"""Gold for an applicant approved while his registration was unverified, the mobile on the invite, and an unverified account that holds a membership. Mocked: mail goes to the outbox."""
from datetime import date

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase

from gold import invites
from gold.models import GoldApplication, GoldInvite
from gold.tests.test_invite import PASSWORD, invite_mail, link_in, make_application, staff
from office import lists
from office.tests.test_leads import verify
from plans import payments
from plans.management.commands.seed_phase1 import seed_all
from plans.models import PaymentMark, Plan, Subscription
from users import services as user_services
from users.models import InterestRegistration
from users.tests.test_register import cleaned

User = get_user_model()


def post_invite(client, url, **over):
    client.get("/login/")
    data = {"password": PASSWORD, "date_of_birth": "1985-03-04", "men_only_accepted": "on", "privacy_accepted": "on", "csrfmiddlewaretoken": client.cookies["csrftoken"].value, **over}
    return client.post(url, data)


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def setUp(self):
        mail.outbox.clear()
        self.barry = staff()

    def register_dan(self, **over):
        return user_services.register_interest(cleaned(email="dan@example.com", **over)).user  # unverified


class VerifyAfterApprovalTests(Base):
    def test_verifying_his_registration_after_approval_gives_gold_once_and_kills_the_invite(self):
        account = self.register_dan()
        application = make_application()
        self.assertEqual(invites.approve_and_invite(application, self.barry), invites.INVITED)
        token = link_in(invite_mail()).rstrip("/").rsplit("/", 1)[1]
        mail.outbox.clear()
        verify(account)
        application.refresh_from_db()
        self.assertEqual(application.user, account)
        self.assertEqual(InterestRegistration.objects.get(user=account).plan.slug, "gold")
        self.assertEqual(invites.read_invite(token)[0], invites.INVALID)  # the invite is dead: it cannot replace the account
        self.assertEqual((invites.resend_invite(application), invites.approve_and_invite(application, self.barry)), (invites.SKIPPED, invites.SKIPPED))
        active = [m for m in mail.outbox if "Gold" in m.subject]
        again = len(mail.outbox)
        from users.services import link_earlier_data

        link_earlier_data(account)  # a second pass finds nothing new to activate
        self.assertEqual(len(mail.outbox), again)
        self.assertEqual(len(active), 1)

    def test_a_waiting_application_is_only_linked_and_gets_no_gold(self):
        account = self.register_dan()
        application = make_application()
        verify(account)
        application.refresh_from_db()
        self.assertEqual((application.user, application.status), (account, GoldApplication.NEW))
        self.assertNotEqual(InterestRegistration.objects.get(user=account).plan.slug, "gold")


class MobileOnTheInviteTests(Base):
    def test_a_real_unverified_member_can_use_his_registered_mobile_on_the_invite(self):
        self.register_dan(mobile="07912 345678")
        application = make_application()  # applied with +447912345678
        invites.approve_and_invite(application, self.barry)
        url = "/" + link_in(invite_mail()).split("/", 3)[3]
        client = Client(enforce_csrf_checks=True)
        self.assertNotContains(client.get(url), 'name="mobile"')  # the number is not in the way
        self.assertEqual(post_invite(client, url).status_code, 302)
        self.assertEqual(User.objects.get(email="dan@example.com").mobile, "+447912345678")

    def test_a_mobile_on_somebody_elses_account_still_asks_again(self):
        self.register_dan(mobile="07911 111222")
        User.objects.create_user("other@example.com", PASSWORD, mobile="+447912345678")
        application = make_application()
        invites.approve_and_invite(application, self.barry)
        url = "/" + link_in(invite_mail()).split("/", 3)[3]
        client = Client(enforce_csrf_checks=True)
        self.assertContains(client.get(url), 'name="mobile"')
        self.assertContains(post_invite(client, url, mobile="07912 345678"), "already registered", status_code=400)


class MembershipOnAnUnverifiedAccountTests(Base):
    def set_up_membership(self, account):
        plan = Plan.objects.get(slug="tier-2")
        return payments.set_up_manually(InterestRegistration.objects.get(user=account), self.barry, plan, date(2026, 12, 1))

    def test_approving_with_a_membership_on_the_unverified_account_sends_no_invite_and_says_what_to_do(self):
        account = self.register_dan()
        self.set_up_membership(account)
        application = make_application()
        self.assertEqual(invites.approve_and_invite(application, self.barry), invites.NEEDS_STAFF)
        application.refresh_from_db()
        self.assertEqual(application.status, GoldApplication.APPROVED)
        self.assertFalse(GoldInvite.objects.exists())
        self.assertEqual(invites.resend_invite(application), invites.SKIPPED)
        self.assertFalse(invites.can_resend(application))
        verify(account)  # the next step: he verifies that account, and Gold is added to it with the membership intact
        self.assertEqual(InterestRegistration.objects.get(user=account).plan.slug, "gold")
        self.assertEqual(Subscription.objects.filter(registration__user=account, status="active").count(), 1)

    def test_the_office_approve_button_tells_staff_the_next_step_in_plain_words(self):
        from django.contrib.messages import get_messages

        from common import levels
        from plans.tests.helpers import make_team_member

        self.set_up_membership(self.register_dan())
        application = make_application()
        approver = make_team_member("approver@example.test", levels.OFFICE, approver=True)
        client = Client(HTTP_HOST="office.localhost")
        client.force_login(approver)
        response = client.post(f"/gold/{application.pk}/approve/")
        self.assertEqual(response.status_code, 302)
        text = " ".join(str(m) for m in get_messages(response.wsgi_request))
        self.assertIn("NO invite was sent", text)
        self.assertIn("verification email", text)

    def test_a_membership_set_up_after_the_invite_went_out_is_never_erased_by_it(self):
        account = self.register_dan()
        application = make_application()
        invites.approve_and_invite(application, self.barry)
        invite = GoldInvite.objects.get()
        self.set_up_membership(account)
        with self.assertRaises(invites.InviteError) as refused:
            invites.accept_invite(invites.make_token(invite), {"password": PASSWORD, "date_of_birth": date(1985, 3, 4)})
        self.assertIn("membership", refused.exception.text)
        self.assertTrue(User.objects.filter(pk=account.pk).exists())
        self.assertEqual((Subscription.objects.count(), PaymentMark.objects.count()), (1, 1))
        self.assertIsNone(GoldInvite.objects.get().used_at)

    def test_an_old_row_linked_to_an_unverified_account_can_be_resent_but_a_verified_one_cannot(self):
        account = self.register_dan()
        application = make_application()
        invites.approve_and_invite(application, self.barry)
        GoldApplication.objects.filter(pk=application.pk).update(user=account)  # the old code linked by address alone
        application.refresh_from_db()
        self.assertTrue(lists.gold_detail(application)["can_resend"])  # the Office Resend button is offered
        self.assertEqual(invites.resend_invite(application), invites.INVITED)
        User.objects.filter(pk=account.pk).update(email_verified_at=application.approved_at)
        application.refresh_from_db()
        self.assertEqual(invites.resend_invite(application), invites.SKIPPED)


class RowAlreadyLinkedTests(Base):
    """The old code linked a row to an unverified account at registration. Verifying must still give Gold, once, and never for a row of another account."""

    def approved_row_linked_to(self, account):
        application = make_application()
        self.assertEqual(invites.approve_and_invite(application, self.barry), invites.INVITED)
        GoldApplication.objects.filter(pk=application.pk).update(user=account)
        mail.outbox.clear()
        return application

    def test_a_row_already_linked_to_the_unverified_account_gives_gold_on_verify_once(self):
        account = self.register_dan()
        application = self.approved_row_linked_to(account)
        verify(account)
        self.assertEqual(InterestRegistration.objects.get(user=account).plan.slug, "gold")
        self.assertEqual(len([m for m in mail.outbox if "Gold" in m.subject]), 1)
        self.assertTrue(GoldInvite.objects.filter(application=application, revoked_at__isnull=False).exists())
        verify(account)  # a replayed link: already verified, nothing again
        self.assertEqual(len([m for m in mail.outbox if "Gold" in m.subject]), 1)

    def test_a_row_linked_to_another_account_is_not_activated(self):
        account = self.register_dan()
        other = User.objects.create_user("other@example.com", PASSWORD)
        self.approved_row_linked_to(other)
        verify(account)
        self.assertNotEqual(InterestRegistration.objects.get(user=account).plan.slug, "gold")
        self.assertEqual([m for m in mail.outbox if "Gold" in m.subject], [])
