"""System > Approval: who may hold each role, who may change whom, delivery addresses, the audit rows, and the one-off import."""
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from common import levels
from gold import approval
from gold.models import ApproverDelivery
from plans.models import SiteSettings
from plans.tests.helpers import make_team_member
from system import approval as service
from system.models import SystemChange, SystemEvent
from system.services import ChangeRefused
from system.tests.test_system import PASSWORD, make_user, sign_in, unlocked_client

User = get_user_model()


def dev(email="dev@example.com"):
    user = make_user(email)
    return user


class ApprovalTests(TestCase):
    def setUp(self):
        self.dev = dev()
        self.office = make_team_member("office@example.com", levels.OFFICE)
        self.admin = make_team_member("admin@example.com", levels.ADMIN)
        self.client = unlocked_client(self.dev)

    def test_only_developers_see_the_page_and_it_gives_the_frontend_its_context(self):
        for user in (self.office, self.admin):
            client, _ = sign_in(user)
            self.assertEqual(client.get("/approval/").status_code, 404)
        page = self.client.get("/approval/")
        self.assertEqual(page.status_code, 200)
        context = page.context
        self.assertEqual(sorted(c["email"] for c in context["approver_candidates"]), ["admin@example.com", "office@example.com"])
        self.assertEqual([c["email"] for c in context["final_candidates"]], ["admin@example.com"])  # Office level is never offered
        self.assertTrue(context["final_approver_missing"])
        self.assertEqual(set(context["approver_candidates"][0]), {"id", "name", "email", "level", "level_label"})
        self.assertEqual(context["cc"], [])

    def test_eligibility_is_checked_on_the_server_office_is_never_a_final_approver(self):
        self.assertFalse(levels.can_hold_final_approver(self.office))
        self.assertTrue(levels.can_hold_final_approver(self.admin))
        with self.assertRaises(ChangeRefused):
            service.add(self.dev, service.FINAL, [self.office.pk])
        self.client.post("/approval/final/add/", {"user": [str(self.office.pk)]})  # the same refusal through the endpoint
        self.assertFalse(levels.held_roles(self.office)[1])
        self.client.post("/approval/final/add/", {"user": [str(self.admin.pk)]})
        self.assertEqual(levels.held_roles(self.admin), (False, True))
        self.assertTrue(approval.final_approver_exists())

    def test_every_change_is_in_the_change_list_and_the_audit_log_with_a_sentence(self):
        self.client.post("/approval/approvers/add/", {"user": [str(self.office.pk), str(self.admin.pk)]})
        self.assertEqual(sorted(a.email for a in approval.approvers()), ["admin@example.com", "office@example.com"])
        self.client.post(f"/approval/delivery/{self.office.pk}/", {"other_email": "Barry@Example.com"})  # unticked: another address
        self.assertEqual(approval.address_for(User.objects.get(pk=self.office.pk)), "barry@example.com")
        self.client.post(f"/approval/delivery/{self.office.pk}/", {"use_account_email": "1", "other_email": ""})
        self.assertEqual(approval.address_for(User.objects.get(pk=self.office.pk)), "office@example.com")
        self.client.post(f"/approval/approvers/{self.admin.pk}/remove/")
        sentences = set(SystemChange.objects.filter(section="approval").values_list("sentence", flat=True))
        self.assertIn("Made office@example.com an approver", sentences)
        self.assertIn("office@example.com's approval emails now go to barry@example.com", sentences)
        self.assertIn("office@example.com's approval emails now go to their account email", sentences)
        self.assertIn("Removed admin@example.com as approver", sentences)
        self.assertEqual(SystemEvent.objects.filter(kind="role_changed", sentence__contains="an approver").count(), 2)
        page = self.client.get("/approval/")  # the list rows render, with the delivery form and the remove button
        self.assertEqual([a["email"] for a in page.context["approvers"]], ["office@example.com"])
        self.assertContains(page, "Send to their account email")

    def test_delivery_is_validated_and_only_for_people_who_hold_a_role(self):
        service.add(self.dev, service.APPROVER, [self.office.pk])
        for bad in ("not-an-email", ""):
            with self.assertRaises(ChangeRefused):
                service.set_delivery(self.dev, self.office.pk, False, bad)
        with self.assertRaises(ChangeRefused):
            service.set_delivery(self.dev, self.admin.pk, False, "x@example.com")  # not an approver
        self.assertFalse(ApproverDelivery.objects.exists())
        service.remove(self.dev, service.APPROVER, self.office.pk)
        self.assertFalse(ApproverDelivery.objects.filter(user=self.office).exists())

    def test_nobody_changes_themselves_or_their_betters_but_a_superuser_may_set_their_own_roles(self):
        other_dev, root = make_team_member("dev2@example.com", levels.DEVELOPER), make_team_member("root@example.com", levels.SUPERUSER)
        for target in (self.dev, other_dev, root):
            with self.assertRaises(ChangeRefused):
                service.add(self.dev, service.APPROVER, [target.pk])
        self.assertEqual(service.add(root, service.FINAL, [root.pk, other_dev.pk]), 2)  # a superuser: themselves and a developer
        self.assertEqual({u.email for u in approval.final_approvers()}, {"root@example.com", "dev2@example.com"})
        self.assertTrue(levels.is_final_approver(root))  # a superuser may always act; they are emailed only because they hold the group

    def test_a_superuser_only_gets_emails_when_they_hold_the_group(self):
        make_team_member("root@example.com", levels.SUPERUSER)
        self.assertEqual(approval.approver_addresses(), [])
        self.assertEqual(approval.final_approver_addresses(), [])

    def test_team_changes_keep_the_roles_and_drop_what_the_new_level_cannot_hold(self):
        from system import team

        user = make_team_member("both@example.com", levels.ADMIN, approver=True, final=True)
        team.set_access(self.dev, user, "office")
        self.assertEqual((levels.held_level(user), levels.held_roles(user)), ("office", (True, False)))  # Approver stays, Final goes
        rows = {r["user"].email: r for r in team.rows(self.dev)}
        self.assertEqual(rows["both@example.com"]["role_labels"], ["Approver"])


class ImportApproversTests(TestCase):
    def run_command(self, *args):
        out = StringIO()
        call_command("import_approvers_from_emails", *args, stdout=out)
        return out.getvalue()

    def test_dry_run_changes_nothing_and_the_real_run_maps_addresses_to_accounts(self):
        office = make_team_member("Barry@example.com", levels.OFFICE)
        no_level = User.objects.create_user("plain@example.com", PASSWORD)
        site = SiteSettings.load()
        site.gold_approver_emails = "barry@EXAMPLE.com, plain@example.com, ghost@example.com"
        site.save()
        out = self.run_command("--dry-run")
        self.assertIn("would be made an approver", out)
        self.assertEqual(levels.held_roles(office), (False, False))
        self.assertFalse(SystemChange.objects.filter(section="approval").exists())
        out = self.run_command()
        self.assertEqual(levels.held_roles(User.objects.get(pk=office.pk)), (True, False))
        self.assertIn("no team level", out)
        self.assertIn("no account", out)
        self.assertEqual(levels.held_roles(no_level), (False, False))
        self.assertIn("Nothing to do", self.run_command())  # safe to run twice
