"""System > Team > a person: the login email, the password, the reset link and the approval ticks. Mocked: mail goes to the test outbox, nothing real is called."""
import json

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core import mail
from django.core.management import call_command
from django.test import Client, TestCase
from django.utils import timezone
from io import StringIO

from common import levels
from gold import services as gold_services
from gold.models import GoldApplication
from gold.tests.test_gold import application_data
from journey.models import JourneySession
from notifications.models import EmailLog, StaffSender
from plans.tests.helpers import make_team_member
from system import approval as approval_service
from system import team_account
from system.models import SystemChange, SystemEvent
from system.services import ChangeRefused
from system.tests.test_system import PASSWORD, SYSTEM, make_user, unlocked_client
from system.tests.test_team import at

User = get_user_model()
GOOD = "Marble-Eucalyptus-2027!"


def sessions_of(user):
    return sum(1 for s in Session.objects.all() if s.get_decoded().get("_auth_user_id") == str(user.pk))


def signed_in(user):
    client = Client()
    client.force_login(user)  # a real database session, on any level (Office people never reach System)
    return client


class PersonBase(TestCase):
    def setUp(self):
        call_command("setup_roles", stdout=StringIO())
        self.dev = at("developer", "dev@example.com")
        self.office = at("office", "olive@example.com")
        self.client = unlocked_client(self.dev)


class GuardTests(PersonBase):
    def test_nobody_changes_themselves_or_anyone_at_or_above_their_level(self):
        peer, boss = at("developer", "peer@example.com"), at("developer", "boss@example.com", superuser=True)
        actions = (lambda a, t: team_account.change_email(a, t, "new@example.com"), lambda a, t: team_account.set_password(a, t, GOOD, GOOD),
                   lambda a, t: team_account.send_reset_link(a, t), lambda a, t: approval_service.set_for_person(a, t, {"final": True}))
        for target in (self.dev, peer, boss):
            for action in actions:
                with self.subTest(target=target.email), self.assertRaises(ChangeRefused):
                    action(self.dev, target)
        self.assertEqual(User.objects.get(pk=peer.pk).email, "peer@example.com")
        # a superuser may change another superuser (U4), never themselves
        other = at("developer", "super2@example.com", superuser=True)
        self.assertTrue(team_account.change_email(boss, other, "renamed@example.com"))
        with self.assertRaises(ChangeRefused):
            team_account.change_email(boss, boss, "mine@example.com")

    def test_the_routes_are_404_below_developer_and_for_non_team_accounts(self):
        at("admin", "admin@example.com")
        admin_client = Client(HTTP_HOST=SYSTEM)
        admin_client.post("/dev-login/", {"username": "admin@example.com", "password": PASSWORD})
        member = User.objects.create_user("member@example.com", PASSWORD)
        for path in (f"/team/{self.office.pk}/", f"/team/{self.office.pk}/change-email/", f"/team/{self.office.pk}/set-password/"):
            self.assertEqual(admin_client.get(path).status_code, 404, path)
        self.assertEqual(self.client.get(f"/team/{member.pk}/").status_code, 404)
        self.assertEqual(self.client.post(f"/team/{member.pk}/set-password/", {"new_password": GOOD, "new_password_again": GOOD}).status_code, 404)
        page = self.client.get(f"/team/{self.office.pk}/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(self.client.get("/team/"), f'href="/team/{self.office.pk}/"')  # each Team row links to the page
        self.assertContains(self.client.get(f"/team/{self.dev.pk}/"), "You cannot change your own email here")


class ChangeEmailTests(PersonBase):
    def test_the_same_account_keeps_its_data_and_everything_that_should_follows(self):
        target = User.objects.get(pk=self.office.pk)
        target.email_verified_at, target.first_name = timezone.now(), "Olive"
        target.save()
        StaffSender.objects.create(user=target, sending_address="olive.sender@example.com")
        journey = JourneySession.objects.create(user=target, lead_email="olive@example.com")
        application = gold_services.submit_application(application_data(email="olive@example.com"))[0]
        EmailLog.objects.create(to="olive@example.com", subject="Hi", template="welcome", subject_email="olive@example.com")
        old_pk, public_id = target.pk, target.public_id
        stay = signed_in(target)
        self.assertEqual(sessions_of(target), 1)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f"/team/{target.pk}/change-email/", {"new_email": "  Olive.New@Example.COM "})
        self.assertRedirects(response, f"/team/{target.pk}/", fetch_redirect_response=False)
        target.refresh_from_db()
        self.assertEqual((target.pk, target.public_id, target.email, target.first_name), (old_pk, public_id, "olive.new@example.com", "Olive"))
        self.assertEqual(User.objects.filter(email__iexact="olive@example.com").count(), 0)
        self.assertEqual(levels.held_level(target), "office")  # level, groups and sending address stay
        self.assertEqual(StaffSender.objects.get(user=target).sending_address, "olive.sender@example.com")
        journey.refresh_from_db(), application.refresh_from_db()
        self.assertEqual((journey.lead_email, application.email, application.user_id), ("olive.new@example.com", "olive.new@example.com", target.pk))
        self.assertEqual(EmailLog.objects.get(template="welcome").subject_email, "olive.new@example.com")
        self.assertEqual(EmailLog.objects.get(template="welcome").to, "olive.new@example.com")  # the sent emails follow the address (the timeline reads them by address)
        # both addresses are told, the sessions are gone
        notices = [m for m in mail.outbox if "login email was changed" in m.subject]
        self.assertEqual(sorted(m.to[0] for m in notices), ["olive.new@example.com", "olive@example.com"])
        by_address = {m.to[0]: m for m in notices}
        self.assertNotIn("olive.new@example.com", by_address["olive@example.com"].body)  # the old address is told, but never where to
        self.assertIn("olive@example.com to olive.new@example.com", by_address["olive.new@example.com"].body)
        self.assertEqual(sessions_of(target), 0)
        self.assertNotIn("_auth_user_id", stay.session)
        # change list and audit: old to new
        change = SystemChange.objects.get(section="team", field="email")
        self.assertEqual((change.old_value, change.new_value, change.user), ("olive@example.com", "olive.new@example.com", self.dev))
        self.assertTrue(SystemEvent.objects.filter(kind="role_changed", detail__old="olive@example.com", detail__new="olive.new@example.com").exists())

    def test_an_address_another_account_has_is_refused_in_any_case_and_points_to_merge(self):
        User.objects.create_user("taken@example.com", "x")
        StaffSender.objects.create(user=self.dev, sending_address="boxed@example.com")
        for typed, needle in (("Taken@Example.com", "Merge two accounts"), ("boxed@example.com", "sending address"), ("not an email", "valid email")):
            with self.subTest(typed=typed), self.assertRaises(ChangeRefused) as caught:
                team_account.change_email(self.dev, self.office, typed)
            self.assertIn(needle, str(caught.exception))
        self.assertEqual(User.objects.get(pk=self.office.pk).email, "olive@example.com")
        self.assertFalse(team_account.change_email(self.dev, self.office, "OLIVE@example.com"))  # the same address: nothing to do
        self.assertFalse(SystemChange.objects.filter(field="email").exists())
        self.assertEqual(len(mail.outbox), 0)


class OfficeDataTests(PersonBase):
    def test_notes_messages_and_timeline_follow_the_change_and_erasure_finds_them(self):
        from outreach import people
        from outreach.models import PersonEdit, PersonMessage, StickyNote
        from users import services as user_services

        target = User.objects.get(pk=self.office.pk)
        target.email_verified_at = timezone.now()
        target.save()
        StickyNote.objects.create(email="olive@example.com", text="Likes the sauna", author=self.dev)
        PersonMessage.objects.create(email="olive@example.com", text="Hello", subject="Hi", author=self.dev)
        self.assertTrue(team_account.change_email(self.dev, target, "olive.new@example.com"))
        target.refresh_from_db()
        main, addresses, _ = people.resolve(user=target)
        self.assertEqual(main, "olive.new@example.com")
        self.assertEqual(StickyNote.objects.get().email, "olive.new@example.com")
        self.assertEqual(PersonMessage.objects.get().email, "olive.new@example.com")
        self.assertTrue(PersonEdit.objects.filter(email="olive.new@example.com", what=PersonEdit.EMAIL, before="olive@example.com").exists())  # the timeline line
        user_services.delete_user_data(target)
        self.assertFalse(StickyNote.objects.exists() or PersonMessage.objects.exists() or PersonEdit.objects.exists())

    def test_an_address_a_lead_or_gold_applicant_or_archived_lead_holds_is_refused(self):
        from outreach.models import ArchivedLead

        JourneySession.objects.create(lead_email="lead@example.com")
        gold_services.submit_application(application_data(email="gold@example.com"))
        ArchivedLead.objects.create(email="gone@example.com")
        for address, words in (("lead@example.com", "a lead"), ("gold@example.com", "a Gold applicant"), ("gone@example.com", "an archived lead")):
            with self.subTest(address=address), self.assertRaises(ChangeRefused) as caught:
                team_account.change_email(self.dev, self.office, address)
            self.assertIn(f"belongs to {words} (", str(caught.exception))
        self.assertEqual(User.objects.get(pk=self.office.pk).email, "olive@example.com")
        # his own journey already on the new address is not someone else's
        JourneySession.objects.create(user=self.office, lead_email="olive.mine@example.com")
        self.assertTrue(team_account.change_email(self.dev, self.office, "olive.mine@example.com"))

    def test_a_bounced_old_address_keeps_his_email_history(self):
        from notifications.models import EmailSuppression

        EmailSuppression.objects.create(email="olive@example.com", reason=EmailSuppression.HARD_BOUNCE, first_seen=timezone.now(), last_seen=timezone.now())
        EmailLog.objects.create(to="olive@example.com", subject="Invite", template="team_invite", subject_email="olive@example.com")
        self.assertTrue(team_account.change_email(self.dev, self.office, "olive.new@example.com"))
        self.assertEqual(EmailLog.objects.get(template="team_invite").to, "olive.new@example.com")


class PasswordTests(PersonBase):
    def test_set_password_runs_the_validators_and_never_records_the_password(self):
        target = self.office
        for bad in ("short", "password1234", "olive@example.com", ""):
            with self.subTest(bad=bad), self.assertRaises(ChangeRefused):
                team_account.set_password(self.dev, target, bad, bad)
        with self.assertRaises(ChangeRefused):
            team_account.set_password(self.dev, target, GOOD, GOOD + "x")  # not the same twice
        target.refresh_from_db()
        self.assertTrue(target.check_password(PASSWORD))  # every refusal left it alone
        stay = signed_in(target)
        self.assertEqual(sessions_of(target), 1)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f"/team/{target.pk}/set-password/", {"new_password": GOOD, "new_password_again": GOOD})
        self.assertRedirects(response, f"/team/{target.pk}/", fetch_redirect_response=False)
        target.refresh_from_db()
        self.assertTrue(target.check_password(GOOD))
        self.assertEqual(sessions_of(target), 0)
        self.assertNotIn("_auth_user_id", stay.session)  # that browser is signed out
        sent = [m for m in mail.outbox if m.to == ["olive@example.com"]]
        self.assertEqual(len(sent), 1)
        self.assertIn("was changed by dev@example.com", sent[0].body)
        self.assertNotIn(GOOD, sent[0].body)
        event = SystemEvent.objects.get(kind="password_changed")
        self.assertEqual((event.sentence, event.user), ("Password set by dev@example.com for olive@example.com", self.dev))
        change = SystemChange.objects.get(field="password")
        everything = json.dumps([event.sentence, event.detail, change.sentence, change.old_value, change.new_value]) + target.password
        self.assertNotIn(GOOD, everything.replace(target.password, ""))
        self.assertNotIn(GOOD, "".join(str(h.__dict__) for h in User.history.filter(id=target.pk)))

    def test_you_cannot_set_your_own_password_here_and_an_inactive_account_waits(self):
        with self.assertRaises(ChangeRefused) as caught:
            team_account.set_password(self.dev, self.dev, GOOD, GOOD)
        self.assertIn("Change password", str(caught.exception))
        self.office.is_active = False
        self.office.save()
        with self.assertRaises(ChangeRefused):
            team_account.set_password(self.dev, self.office, GOOD, GOOD)
        self.dev.refresh_from_db()
        self.assertTrue(self.dev.check_password(PASSWORD))

    def test_the_reset_link_is_the_invite_for_a_new_account_and_the_reset_email_otherwise(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(f"/team/{self.office.pk}/reset-link/")
        reset = mail.outbox[-1]
        self.assertEqual((reset.to, reset.subject), (["olive@example.com"], "Reset your Spa 99 password"))
        self.assertIn("/reset/", reset.body)
        self.assertIn("one hour", reset.body)
        pending = User.objects.create_user("pending@example.com", None, is_staff=True)
        pending.groups.add(*self.office.groups.all())
        team_account.send_reset_link(self.dev, pending)
        self.assertIn("added to the Spa 99 team", mail.outbox[-1].subject)
        self.assertEqual(SystemEvent.objects.filter(kind="password_changed", detail__kind="reset_link").count(), 2)
        with self.assertRaises(ChangeRefused):
            team_account.send_reset_link(self.dev, self.dev)


class TickTests(PersonBase):
    def test_ticks_set_on_the_person_page_obey_the_rules_of_system_approval(self):
        admin = at("admin", "admin@example.com")
        url = f"/team/{self.office.pk}/roles/"
        # Gold and Membership approver for an Office person; the Approval page sees the same
        self.client.post(url, {"approver": "1", "membership": "1"})
        self.assertEqual((levels.held(User.objects.get(pk=self.office.pk))[1], levels.holds_membership_group(User.objects.get(pk=self.office.pk))), (True, True))
        ids = {r["id"] for r in self.client.get("/approval/").context["approvers"]}
        self.assertIn(str(self.office.pk), ids)
        self.assertEqual(SystemChange.objects.filter(section="approval", object_pk=str(self.office.pk)).count(), 2)
        # Final approver is refused for Office, and the whole save is undone (all or nothing)
        self.client.post(url, {"approver": "1", "membership": "1", "final": "1"})
        self.assertFalse(levels.held_roles(User.objects.get(pk=self.office.pk))[1])
        # Admin: Membership approver allowed (Admin needs the tick); Final approver allowed; where the emails go is set with it
        self.client.post(f"/team/{admin.pk}/roles/", {"membership": "1"})
        self.assertTrue(levels.holds_membership_group(User.objects.get(pk=admin.pk)))
        from gold import approval
        self.client.post(f"/team/{admin.pk}/roles/", {"final": "1", "delivery": "1", "other_email": "boss@example.org"})
        self.assertTrue(approval_service.person(self.dev, admin)["roles"][2]["held"])
        self.assertContains(self.client.get(f"/team/{admin.pk}/"), "boss@example.org")  # the page shows the email setting once they hold a role
        self.assertEqual(approval.address_for(User.objects.get(pk=admin.pk)), "boss@example.org")
        self.client.post(f"/team/{admin.pk}/roles/", {"final": "1", "delivery": "1"})  # no account box and no other address: refused, nothing changes
        self.assertEqual(approval.address_for(User.objects.get(pk=admin.pk)), "boss@example.org")
        self.client.post(f"/team/{admin.pk}/roles/", {"delivery": "1", "other_email": "boss@example.org"})  # Final unticked: removed, and the email setting goes with it
        self.assertFalse(levels.held_roles(User.objects.get(pk=admin.pk))[1])
        # you cannot tick yourself, a superuser can
        with self.assertRaises(ChangeRefused):
            approval_service.set_for_person(self.dev, self.dev, {"approver": True})
        root = at("developer", "root@example.com", superuser=True)
        self.assertTrue(approval_service.set_for_person(root, root, {"approver": True}))
