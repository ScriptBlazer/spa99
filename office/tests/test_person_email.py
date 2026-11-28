"""Office > person page > Change email for a registered customer (docs/features/office-outreach.md "Change a customer's email"). Mocked: in-memory mail, no real services."""
import re

from django.utils import timezone

from django.core import mail
from django.test import Client

from common import levels
from gold import services as gold_services
from gold.tests.test_gold import application_data
from journey.models import JourneySession
from office.tests.test_leads import lead
from office.tests.test_office import OFFICE, OfficeTestCase
from outreach import services as outreach_services
from outreach.models import PersonEdit, StickyNote
from plans import payments
from users.models import InterestRegistration
from plans.models import PaymentNotice
from plans.tests.helpers import make_team_member
from system import team_account
from system.services import ChangeRefused
from gold.models import GoldApplication
from insights.models import MetricCounter
from notifications.models import EmailLog, EmailSuppression
from system.models import SystemChange, SystemEvent
from users import services as user_services
from users import tokens
from users import tokens as user_tokens
from users.models import User
from users.tests.test_register import cleaned


def post_to(user, path):
    client = Client(HTTP_HOST=OFFICE)
    client.force_login(user)
    return client.post(path)


def post(user, pk, email):
    client = Client(HTTP_HOST=OFFICE)
    client.force_login(user)
    return client.post(f"/people/{pk}/email/", {"email": email})


class CustomerEmailTests(OfficeTestCase):
    def setUp(self):
        self.admin = make_team_member("admin@example.test", levels.ADMIN)
        self.customer = user_services.register_interest(cleaned(email="david@thegrapevine.co.um", plan="tier-2", mobile="07911120001")).user

    def change(self, new, actor=None):
        with self.captureOnCommitCallbacks(execute=True):
            return post(actor or self.admin, self.customer.pk, new)

    def confirm_link(self, address):
        """The token in the confirm email sent to `address`."""
        body = next(m for m in mail.outbox if m.to == [address] and "Confirm" in m.subject).alternatives[0][0] if False else next(m.body for m in mail.outbox if m.to == [address] and "onfirm" in m.subject)
        return re.search(r"/verify/([^/\s]+)/", body).group(1)

    def test_admin_changes_the_login_email_he_is_unverified_and_confirming_links_the_unlinked_rows(self):
        old = "david@thegrapevine.co.um"
        journey = JourneySession.objects.create(lead_email=old)  # never linked: nobody had proven the address
        application = gold_services.submit_application(application_data(email=old))[0]
        self.assertIsNone(application.user_id)
        self.customer.marketing_consent = True
        self.customer.save()
        old_token = tokens.make_verify_token(self.customer)
        stay = Client()
        stay.force_login(self.customer)
        mail.outbox.clear()
        response = self.change("  David@TheGrapevine.co.uk ")
        self.assertRedirects(response, f"/people/{self.customer.pk}/", fetch_redirect_response=False, target_status_code=200)
        user = User.objects.get(pk=self.customer.pk)
        self.assertEqual(user.email, "david@thegrapevine.co.uk")
        self.assertIsNone(user.email_verified_at)  # not proven until he uses the new link
        self.assertTrue(user.marketing_consent)
        journey.refresh_from_db(), application.refresh_from_db()
        self.assertEqual((journey.lead_email, application.email), ("david@thegrapevine.co.uk", "david@thegrapevine.co.uk"))
        self.assertEqual(application.history.first().email, "david@thegrapevine.co.uk")
        self.assertNotIn("_auth_user_id", stay.session)
        edit = PersonEdit.objects.get(what=PersonEdit.EMAIL)
        self.assertEqual((edit.before, edit.after, edit.by), (old, "david@thegrapevine.co.uk", self.admin))
        self.assertEqual(user.history.first().history_user, self.admin)
        self.assertTrue(SystemChange.objects.filter(section="team", field="email", old_value=old).exists())  # the System audit too
        self.assertTrue(SystemEvent.objects.filter(detail__old=old, detail__customer=True).exists())
        self.assertEqual(sorted(m.to[0] for m in mail.outbox if "login email was changed" in m.subject), ["david@thegrapevine.co.uk", old])
        confirm = [m for m in mail.outbox if "onfirm" in m.subject]
        self.assertEqual([m.to for m in confirm], [["david@thegrapevine.co.uk"]])  # a fresh confirm link, to the new address only
        self.assertEqual(user_tokens.read_verify_token(old_token)[0], user_tokens.INVALID)  # the old link cannot verify the new address
        status, _ = user_services.verify_email(self.confirm_link("david@thegrapevine.co.uk"))
        self.assertEqual(status, user_tokens.VERIFIED)
        journey.refresh_from_db(), application.refresh_from_db()
        self.assertEqual((journey.user_id, application.user_id), (user.pk, user.pk))  # linked now, so export and erasure find them
        self.assertTrue(any(a.pk == application.pk for a in GoldApplication.objects.filter(user=user)))

    def test_a_verified_customer_becomes_unverified_and_the_verified_count_stays_one(self):
        user_services.verify_email(tokens.make_verify_token(self.customer))
        before = MetricCounter.objects.get(key="email_verified").value
        self.change("david@example.com")
        user = User.objects.get(pk=self.customer.pk)
        self.assertIsNone(user.email_verified_at)
        self.assertEqual(MetricCounter.objects.get(key="email_verified").value, before - 1)
        user_services.verify_email(tokens.make_verify_token(user))
        self.assertEqual(MetricCounter.objects.get(key="email_verified").value, before)

    def test_resend_confirm_is_for_admin_and_only_while_not_verified(self):
        mail.outbox.clear()
        self.assertEqual(post_to(self.admin, f"/people/{self.customer.pk}/resend-verify/").status_code, 302)
        self.assertEqual(len([m for m in mail.outbox if "onfirm" in m.subject]), 1)
        self.assertTrue(PersonEdit.objects.filter(what=PersonEdit.RESENT, after="Resent the confirm email", by=self.admin).exists())
        self.assertEqual(post_to(make_team_member("o@example.test", levels.OFFICE), f"/people/{self.customer.pk}/resend-verify/").status_code, 403)
        user_services.verify_email(tokens.make_verify_token(self.customer))
        mail.outbox.clear()
        post_to(self.admin, f"/people/{self.customer.pk}/resend-verify/")
        self.assertEqual(mail.outbox, [])  # already verified: refused

    def test_timeline_resend_builds_a_fresh_link_or_resends_a_plain_email_and_refuses_the_wrong_ones(self):
        user_services.verify_email(tokens.make_verify_token(self.customer))
        welcome = EmailLog.objects.filter(to=self.customer.email, template="welcome").first()
        self.assertIsNotNone(welcome)
        reset = EmailLog.objects.create(to=self.customer.email, subject="Reset", template="password_reset", status="sent", subject_email=self.customer.email)
        notice = EmailLog.objects.create(to=self.customer.email, subject="Changed", template="password_changed", status="sent", subject_email=self.customer.email)
        verify_log = EmailLog.objects.filter(to=self.customer.email, template="verify").first()
        client = Client(HTTP_HOST=OFFICE)
        client.force_login(self.admin)
        page = client.get(f"/people/{self.customer.pk}/").content.decode()
        self.assertIn(f"/people/{self.customer.pk}/emails/{reset.pk}/resend/", page)
        self.assertIn(f"/people/{self.customer.pk}/emails/{welcome.pk}/resend/", page)
        self.assertNotIn(f"/emails/{notice.pk}/resend/", page)  # a security notice about a past event
        self.assertNotIn(f"/emails/{verify_log.pk}/resend/", page)  # he is verified now
        mail.outbox.clear()
        client.post(f"/people/{self.customer.pk}/emails/{reset.pk}/resend/")
        link = re.search(r"/reset/([^/\s]+)/([^/\s]+)/", mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, [self.customer.email])
        self.assertTrue(link)  # built now by the normal sender, not copied
        client.post(f"/people/{self.customer.pk}/emails/{welcome.pk}/resend/")
        self.assertEqual(len(mail.outbox), 2)
        mail.outbox.clear()
        client.post(f"/people/{self.customer.pk}/emails/{notice.pk}/resend/")
        client.post(f"/people/{self.customer.pk}/emails/{verify_log.pk}/resend/")
        self.assertEqual(mail.outbox, [])
        self.assertEqual(PersonEdit.objects.filter(what=PersonEdit.RESENT).count(), 2)

    def test_timeline_resend_refuses_a_suppressed_address_and_below_admin(self):
        user_services.verify_email(tokens.make_verify_token(self.customer))
        welcome = EmailLog.objects.filter(to=self.customer.email, template="welcome").first()
        office = make_team_member("o2@example.test", levels.OFFICE)
        mail.outbox.clear()
        self.assertEqual(post_to(office, f"/people/{self.customer.pk}/emails/{welcome.pk}/resend/").status_code, 403)
        EmailSuppression.objects.create(email=self.customer.email, reason=EmailSuppression.HARD_BOUNCE, first_seen=timezone.now(), last_seen=timezone.now())
        post_to(self.admin, f"/people/{self.customer.pk}/emails/{welcome.pk}/resend/")
        self.assertEqual(mail.outbox, [])
        self.assertFalse(PersonEdit.objects.filter(what=PersonEdit.RESENT).exists())

    def test_only_admin_and_up_may_and_the_button_follows(self):
        for level, status in ((levels.OFFICE, 403), (levels.VIEWER, 403)):
            actor = make_team_member(f"{level}@example.test", level)
            self.assertEqual(post(actor, self.customer.pk, "x@example.com").status_code, status)
            with self.assertRaises(ChangeRefused):
                team_account.change_customer_email(actor, self.customer, "x@example.com")
        self.assertEqual(User.objects.get(pk=self.customer.pk).email, "david@thegrapevine.co.um")
        client = Client(HTTP_HOST=OFFICE)
        client.force_login(make_team_member("office@example.test", levels.OFFICE))
        self.assertNotContains(client.get(f"/people/{self.customer.pk}/"), "data-change-email")
        client.force_login(self.admin)
        self.assertContains(client.get(f"/people/{self.customer.pk}/"), "data-change-email")

    def test_refused_when_another_account_or_a_lead_has_the_address_or_it_is_not_valid(self):
        User.objects.create_user("taken@example.com", "x")
        lead("hugo@example.com")
        mail.outbox.clear()
        for typed in ("Taken@Example.com", "hugo@example.com", "not an email"):
            with self.subTest(typed=typed):
                self.change(typed)
                self.assertEqual(User.objects.get(pk=self.customer.pk).email, "david@thegrapevine.co.um")
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(PersonEdit.objects.filter(what=PersonEdit.EMAIL).exists())

    def test_the_same_address_changes_nothing(self):
        self.assertFalse(team_account.change_customer_email(self.admin, self.customer, "DAVID@thegrapevine.co.um"))
        self.assertFalse(PersonEdit.objects.exists())

    def test_a_team_member_is_refused(self):
        member = make_team_member("olive@example.test", levels.OFFICE)
        with self.assertRaises(ChangeRefused):
            team_account.change_customer_email(self.admin, member, "new@example.com")
        self.assertEqual(User.objects.get(pk=member.pk).email, "olive@example.test")


class ReconfirmTests(OfficeTestCase):
    """Confirming again after an Office change does not repeat emails he already had; a first confirm still sends them."""
    def setUp(self):
        self.admin = make_team_member("admin@example.test", levels.ADMIN)
        self.customer = user_services.register_interest(cleaned(email="david@thegrapevine.co.um", plan="tier-2", mobile="07911120001")).user

    def change(self, new):
        with self.captureOnCommitCallbacks(execute=True):
            return post(self.admin, self.customer.pk, new)

    def test_welcome_is_sent_once_and_the_dialog_warns(self):
        mail.outbox.clear()
        user_services.verify_email(tokens.make_verify_token(self.customer))  # first confirm
        self.assertEqual(len([m for m in mail.outbox if "Welcome" in m.subject]), 1)
        self.change("david@example.com")
        mail.outbox.clear()
        user_services.verify_email(tokens.make_verify_token(User.objects.get(pk=self.customer.pk)))  # confirms the new address
        self.assertEqual([m for m in mail.outbox if "Welcome" in m.subject], [])
        client = Client(HTTP_HOST=OFFICE)
        client.force_login(self.admin)
        self.assertContains(client.get(f"/people/{self.customer.pk}/"), "Change his login email?")


class AfterChangeTests(OfficeTestCase):
    def setUp(self):
        self.admin = make_team_member("admin@example.test", levels.ADMIN)
        self.admin.first_name, self.admin.last_name = "Barry", "Staffer"
        self.admin.save()
        self.customer = user_services.register_interest(cleaned(email="david@thegrapevine.co.um", plan="tier-2", mobile="07911120001")).user
        user_services.verify_email(tokens.make_verify_token(self.customer))

    def test_erasure_before_he_confirms_still_finds_everything_and_the_notices_never_name_staff(self):
        old = "david@thegrapevine.co.um"
        application = gold_services.submit_application(application_data(email=old))[0]
        outreach_services.add_note(old, self.admin, "a note")
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            post(self.admin, self.customer.pk, "david@example.com")
        notices = [m for m in mail.outbox if "login email was changed" in m.subject]
        self.assertEqual(len(notices), 2)
        for message in notices:
            self.assertNotIn("Barry", message.body)
            self.assertIn("the Spa 99 team", message.body)
        user = User.objects.get(pk=self.customer.pk)
        self.assertIsNone(user.email_verified_at)
        self.assertTrue(user_services.proven_before(user))
        self.assertTrue(EmailLog.objects.filter(to="david@example.com").exists())
        user_services.delete_user_data(user)
        self.assertFalse(GoldApplication.objects.filter(pk=application.pk).exists())
        self.assertFalse(EmailLog.objects.filter(to__iexact="david@example.com").exists())
        self.assertFalse(StickyNote.objects.exists())

    def test_a_reminder_with_no_window_date_is_refused_by_the_resend_and_the_batch_rule(self):
        reg = InterestRegistration.objects.get(user=self.customer)
        InterestRegistration.objects.filter(pk=reg.pk).update(payment_status=InterestRegistration.INVITED, payment_due_at=None)
        reg.refresh_from_db()
        self.assertEqual(payments.window_email_open(reg, kind=PaymentNotice.REMINDER), "No window")
        self.assertEqual(payments.window_email_open(reg, kind=PaymentNotice.INVITE), "")
