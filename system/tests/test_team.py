"""Team management in System, host access by level, and merging duplicate accounts. Mocked: no real email, no real clock."""
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.management import call_command
from django.test import Client, TestCase

from common import levels
from gold import services as gold_services
from gold.models import GoldApplication
from gold.tests.test_gold import application_data
from journey.models import JourneySession
from plans.management.commands.seed_phase1 import seed_all
from plans.models import Plan
from system import team
from system.models import SystemChange, SystemEvent
from system.services import ChangeRefused
from system.tests.test_system import PASSWORD, SYSTEM, make_user, sign_in, unlocked_client
from django.db.models import Q
from users.models import InterestRegistration

User = get_user_model()


def at(level, email, approver=False, superuser=False):
    user = User.objects.create_user(email, PASSWORD, is_staff=True, is_superuser=superuser)
    if level:
        user.groups.add(Group.objects.get_or_create(name=levels.GROUP_FOR[level])[0])
    if approver:
        user.groups.add(Group.objects.get_or_create(name="Approver")[0])
    return user


class HostAccessTests(TestCase):
    def test_system_is_404_below_developer_and_open_to_developer(self):
        for level in ("office", "admin"):
            client, _ = sign_in(at(level, f"{level}@example.com"))
            self.assertEqual(client.get("/team/").status_code, 404, level)
        self.assertEqual(unlocked_client(at("developer", "dev@example.com")).get("/team/").status_code, 200)

    def test_control_is_404_for_office_level_and_open_to_admin(self):
        for level, status in (("office", 404), ("admin", 200)):
            client = Client(HTTP_HOST="control.localhost")
            client.force_login(at(level, f"{level}@example.com"))
            self.assertEqual(client.get("/").status_code, status, level)


class TeamManagementTests(TestCase):
    def setUp(self):
        call_command("setup_roles", stdout=StringIO())
        self.dev = at("developer", "dev@example.com")

    def test_a_new_email_gets_an_account_without_a_password_and_an_invite(self):
        with self.captureOnCommitCallbacks(execute=True):
            user, created = team.add_member(self.dev, "New.Person@Example.com", "office")
        self.assertTrue(created)
        self.assertEqual((user.email, user.is_staff, user.has_usable_password()), ("new.person@example.com", True, False))
        self.assertEqual(levels.held(user), ("office", False))  # approval roles are set in System > Approval, never here
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("added to the Spa 99 team", mail.outbox[0].subject)
        self.assertIn("/reset/", mail.outbox[0].body)
        self.assertTrue(SystemChange.objects.filter(section="team", sentence__contains="Added new.person@example.com").exists())
        self.assertTrue(SystemEvent.objects.filter(kind="role_changed").exists())

    def test_an_existing_account_just_gains_the_level_and_keeps_its_password(self):
        member = User.objects.create_user("member@example.com", "keep-this-password-1")
        mail.outbox.clear()
        user, created = team.add_member(self.dev, "member@example.com", "admin")
        self.assertFalse(created)
        self.assertEqual((levels.held_level(user), user.check_password("keep-this-password-1")), ("admin", True))
        self.assertEqual(len(mail.outbox), 0)

    def test_the_guards_hold_on_the_server(self):
        other_dev, admin, root = at("developer", "dev2@example.com"), at("admin", "admin@example.com"), at(None, "root@example.com", superuser=True)
        for call in (lambda: team.set_access(self.dev, other_dev, "office"), lambda: team.set_access(self.dev, self.dev, "office"),
                     lambda: team.set_active(self.dev, self.dev, False), lambda: team.remove_from_team(self.dev, self.dev),
                     lambda: team.set_access(self.dev, root, "office"), lambda: team.set_access(self.dev, admin, "developer"),
                     lambda: team.add_member(self.dev, "x@example.com", "developer"),
                     lambda: team.set_access(admin, self.dev, "office")):
            with self.assertRaises(ChangeRefused):
                call()
        self.assertEqual(levels.held_level(other_dev), "developer")
        self.assertTrue(team.set_access(root, other_dev, "admin"))  # a superuser may change a developer ...
        self.assertTrue(team.remove_from_team(at(None, "root2@example.com", superuser=True), root))  # ... and another superuser
        root.refresh_from_db()
        self.assertEqual(levels.level_of(root), "none")

    def test_remove_from_team_keeps_the_account_and_the_membership(self):
        user = at("admin", "gone@example.com", approver=True)
        InterestRegistration.objects.create(user=user)
        team.remove_from_team(self.dev, user)
        user.refresh_from_db()
        self.assertEqual((levels.held(user), user.is_staff, user.is_active, InterestRegistration.objects.filter(user=user).exists()), (("none", False), False, True, True))

    def test_the_team_screen_posts_use_the_same_guards(self):
        client = unlocked_client(self.dev)
        other = at("admin", "other@example.com", approver=True)
        client.post(f"/team/{other.pk}/access/", {"level": "office", "approver": "0"})  # the old Approver toggle is gone: ignored
        self.assertEqual(levels.held(other), ("office", True))  # level changed, the Approver role is untouched
        page = client.get("/team/")
        self.assertNotContains(page, 'name="approver"')
        self.assertContains(page, 'data-system-role="Approver"')
        client.post("/team/add/", {"email": "fresh@example.com", "level": "admin"})
        self.assertTrue(User.objects.filter(email="fresh@example.com", is_staff=True).exists())
        client.post("/team/add/", {"email": "bad@example.com", "level": "developer"})  # not above your own level
        self.assertFalse(User.objects.filter(email="bad@example.com").exists())
        self.assertContains(client.get("/team/"), "Add team member")


class MergeTests(TestCase):
    def setUp(self):
        seed_all()
        call_command("setup_roles", stdout=StringIO())
        self.dev = at("developer", "dev@example.com")
        self.keep = User.objects.create_user("keep@example.com", "x")
        self.gone = User.objects.create_user("gone@example.com", "x", first_name="Dan", mobile="+447123456789")

    def test_a_merge_moves_membership_sessions_and_gold_then_deletes_the_other(self):
        InterestRegistration.objects.create(user=self.gone, plan=Plan.objects.get(slug="tier-2"))
        session = JourneySession.objects.create(user=self.gone)
        application = gold_services.submit_application(application_data())[0]
        GoldApplication.objects.filter(pk=application.pk).update(user=self.gone)
        keep, moved = team.merge_accounts(self.dev, "keep@example.com", "gone@example.com")
        self.assertEqual(moved["sessions"], 1)
        session.refresh_from_db()
        self.keep.refresh_from_db()
        self.assertEqual((session.user_id, self.keep.interest.plan.slug, self.keep.first_name, self.keep.mobile), (self.keep.pk, "tier-2", "Dan", "+447123456789"))
        application.refresh_from_db()
        self.assertEqual(application.user_id, self.keep.pk)
        self.assertFalse(User.objects.filter(email="gone@example.com").exists())
        self.assertTrue(SystemChange.objects.filter(field="merged").exists())

    def test_the_merge_screen_previews_then_merges_on_confirm(self):
        client = unlocked_client(self.dev)
        page = client.post("/team/merge/", {"keep": "keep@example.com", "remove": "gone@example.com"})
        self.assertContains(page, "data-system-merge-preview")
        self.assertTrue(User.objects.filter(email="gone@example.com").exists())  # a preview changes nothing
        client.post("/team/merge/", {"keep": "keep@example.com", "remove": "gone@example.com", "confirm": "1"})
        self.assertFalse(User.objects.filter(email="gone@example.com").exists())

    def test_refusals(self):
        InterestRegistration.objects.create(user=self.keep, plan=Plan.objects.get(slug="tier-1"))
        InterestRegistration.objects.create(user=self.gone, plan=Plan.objects.get(slug="gold"))
        with self.assertRaisesMessage(ChangeRefused, "different"):
            team.merge_preview(self.dev, "keep@example.com", "gone@example.com")
        root = at(None, "root@example.com", superuser=True)
        with self.assertRaisesMessage(ChangeRefused, "superuser"):
            team.merge_accounts(self.dev, "keep@example.com", "root@example.com")
        with self.assertRaises(ChangeRefused):
            team.merge_accounts(self.dev, "keep@example.com", "keep@example.com")
        self.assertTrue(User.objects.filter(email="gone@example.com").exists())


class MigrateRolesTests(TestCase):
    def test_dry_run_changes_nothing_then_the_real_run_maps_the_old_groups(self):
        old = {name: Group.objects.create(name=name) for name in ("Owner", "Manager", "Viewer", "Approver", "System")}
        owner, viewer, approver, dev = (User.objects.create_user(f"{n}@example.com", "x", is_staff=True) for n in ("owner", "viewer", "approver", "dev"))
        owner.groups.add(old["Owner"], old["Viewer"])
        viewer.groups.add(old["Viewer"])
        approver.groups.add(old["Approver"])
        dev.groups.add(old["System"], old["Manager"])
        out = StringIO()
        call_command("migrate_roles", "--dry-run", stdout=out)
        self.assertIn("Dry run", out.getvalue())
        self.assertEqual(levels.held_level(owner), "none")
        self.assertFalse(Group.objects.filter(name="Office").exists())
        call_command("migrate_roles", stdout=StringIO())
        self.assertEqual([levels.held(u) for u in (owner, viewer, approver, dev)], [("admin", False), ("office", False), ("office", True), ("developer", False)])
        call_command("setup_roles", stdout=StringIO())
        self.assertEqual(set(Group.objects.values_list("name", flat=True)), {"Office", "Admin", "Developer", "Approver", "Final approver"})
        self.assertEqual(levels.held(dev), ("developer", False))


class SystemPasswordTests(TestCase):
    def test_a_developer_changes_their_password_behind_the_unlock(self):
        dev = at("developer", "dev@example.com")
        locked, _ = sign_in(dev)
        self.assertEqual(locked.get("/password/").status_code, 302)  # to the unlock page
        client = unlocked_client(dev)
        self.assertEqual(client.get("/password/").status_code, 200)
        response = client.post("/password/", {"old_password": PASSWORD, "new_password1": "another-long-password-2", "new_password2": "another-long-password-2"})
        self.assertEqual((response.status_code, response["Location"]), (302, "/password/"))
        dev.refresh_from_db()
        self.assertTrue(dev.check_password("another-long-password-2"))
        admin_client, _ = sign_in(at("admin", "a@example.com"))
        self.assertEqual(admin_client.get("/password/").status_code, 404)


class ReviewFixTests(TestCase):
    def setUp(self):
        seed_all()
        call_command("setup_roles", stdout=StringIO())
        self.dev = at("developer", "dev@example.com")

    def test_after_a_merge_an_erasure_of_the_kept_account_leaves_nothing_of_either_person(self):
        from common.models import LoginEvent
        from notifications.models import EmailLog
        from users import services as user_services

        keep = User.objects.create_user("keep@example.com", "x", first_name="Kay")
        gone = User.objects.create_user("gone@example.com", "x", first_name="Gil")
        application = gold_services.submit_application(application_data(email="gone@example.com"))[0]
        EmailLog.objects.create(to="gone@example.com", subject="Hello", template="welcome", subject_email="gone@example.com")
        LoginEvent.objects.create(attempted_email="gone@example.com", event="failed")
        gone.save()
        team.merge_accounts(self.dev, "keep@example.com", "gone@example.com")
        user_services.delete_user_data(keep)
        for email in ("keep@example.com", "gone@example.com"):
            self.assertFalse(GoldApplication.objects.filter(email__iexact=email).exists(), email)
            self.assertFalse(EmailLog.objects.filter(Q(to__iexact=email) | Q(subject_email__iexact=email)).exists(), email)
            self.assertFalse(LoginEvent.objects.filter(attempted_email__iexact=email).exists(), email)
        self.assertFalse(GoldApplication.history.model.objects.filter(id=application.pk).exists())
        self.assertFalse(User.history.model.objects.filter(email__in=["gone@example.com", "keep@example.com"]).exists())

    def test_a_developer_cannot_merge_into_themselves_or_a_peer(self):
        peer, other = at("developer", "peer@example.com"), User.objects.create_user("other@example.com", "x")
        for keep in (self.dev, peer):
            with self.assertRaises(ChangeRefused):
                team.merge_accounts(self.dev, keep.email, "other@example.com")
        root = at(None, "root@example.com", superuser=True)
        team.merge_accounts(root, "peer@example.com", "other@example.com")  # a superuser may
        self.assertFalse(User.objects.filter(email="other@example.com").exists())

    def test_old_groups_on_a_non_staff_account_are_not_promoted(self):
        member = User.objects.create_user("member@example.com", "x")
        member.groups.add(Group.objects.create(name="Owner"))
        out = StringIO()
        call_command("migrate_roles", stdout=out)
        member.refresh_from_db()
        self.assertEqual((levels.held_level(member), member.is_staff), ("none", False))
        self.assertIn("SKIPPED", out.getvalue())

    def test_team_actions_only_reach_team_members(self):
        member = User.objects.create_user("plain@example.com", "x")
        client = unlocked_client(self.dev)
        self.assertEqual(client.post(f"/team/{member.pk}/active/", {"active": "0"}).status_code, 404)
        member.refresh_from_db()
        self.assertTrue(member.is_active)
        with self.assertRaises(ChangeRefused):
            team.set_active(self.dev, member, False)

    def test_create_team_member_is_written_to_the_audit_log(self):
        call_command("create_team_member", email="cli@example.com", level="admin", invite=True, stdout=StringIO())
        self.assertTrue(SystemEvent.objects.filter(kind="role_changed", sentence__contains="cli@example.com").exists())
