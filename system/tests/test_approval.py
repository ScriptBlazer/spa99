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

    def test_the_switch_and_the_ticked_potentials_are_saved_and_logged(self):
        from system.models import SystemChange

        token = self.client.get("/approval/").context["form"].initial["row_token"]
        response = self.client.post("/approval/", {"final_approval_on": "on", "final_approval_potentials": ["medium", "low"], "row_token": token})
        self.assertEqual(response.status_code, 302)
        site = SiteSettings.load()
        self.assertEqual((site.final_approval_on, site.final_approval_potentials), (True, "low,medium"))
        self.assertTrue(SystemChange.objects.filter(section="approval", field="final_approval_on").exists())
        page = self.client.get("/approval/")
        self.assertFalse(page.context["final_nothing_ticked"])
        self.client.post("/approval/", {"final_approval_on": "on", "row_token": page.context["form"].initial["row_token"]})
        self.assertEqual(SiteSettings.load().final_approval_potentials, "")
        self.assertTrue(self.client.get("/approval/").context["final_nothing_ticked"])

    def test_only_developers_see_the_page_and_it_gives_the_frontend_its_context(self):
        for user in (self.office, self.admin):
            client, _ = sign_in(user)
            self.assertEqual(client.get("/approval/").status_code, 404)
        page = self.client.get("/approval/")
        self.assertEqual(page.status_code, 200)
        context = page.context
        self.assertEqual(sorted(c["email"] for c in context["approver_candidates"]), ["admin@example.com", "office@example.com"])
        self.assertEqual([c["email"] for c in context["final_candidates"]], ["admin@example.com"])  # Office level is never offered
        self.assertFalse(context["final_approver_missing"])  # the switch is off by default
        SiteSettings.objects.filter(singleton_key="site").update(final_approval_on=True)
        self.assertTrue(self.client.get("/approval/").context["final_approver_missing"])
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


class ApprovalReviewTests(TestCase):
    def setUp(self):
        from gold import services as gold_services
        from gold.models import GoldApplication
        from gold.tests.test_gold import application_data
        from plans.management.commands.seed_phase1 import seed_all

        seed_all()
        SiteSettings.objects.filter(singleton_key="site").update(final_approval_on=True)  # final approval is off by default
        self.GoldApplication = GoldApplication
        self.dev = dev()
        self.approver = make_team_member("approver@example.com", levels.OFFICE, approver=True)
        self.final = make_team_member("final@example.com", levels.ADMIN, final=True)
        self.client = unlocked_client(self.dev)
        self.application, _ = gold_services.submit_application(application_data())
        GoldApplication.objects.filter(pk=self.application.pk).update(potential_level="low", status="contacted")
        self.application.refresh_from_db()

    def test_the_last_final_approver_cannot_leave_while_applications_wait_and_a_new_one_is_emailed_them(self):
        from django.core import mail

        approval.approve(self.application, self.approver)
        with self.assertRaises(ChangeRefused) as caught:
            service.remove(self.dev, service.FINAL, self.final.pk)
        self.assertIn("1 application wait", str(caught.exception))
        self.assertTrue(levels.held_roles(self.final)[1])
        newcomer = make_team_member("second@example.com", levels.ADMIN)
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            service.add(self.dev, service.FINAL, [newcomer.pk])
        self.assertEqual([m.to for m in mail.outbox], [["second@example.com"]])  # only the new person, for the waiting application
        self.assertIn("/final/", mail.outbox[0].body)
        self.assertTrue(service.remove(self.dev, service.FINAL, self.final.pk))  # no longer the last

    def test_the_django_admin_action_sends_low_potential_for_final_approval(self):
        from gold.admin import GoldApplicationAdmin
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory

        request = RequestFactory().post("/")
        request.user = self.approver
        request._messages = mock_messages()
        GoldApplicationAdmin(self.GoldApplication, AdminSite()).approve_and_invite(request, self.GoldApplication.objects.all())
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, "awaiting_final")

    def test_adding_nobody_new_or_a_missing_id_is_refused_cleanly(self):
        import uuid

        service.add(self.dev, service.APPROVER, [self.approver.pk])
        self.assertIs(service.add(self.dev, service.APPROVER, [self.approver.pk]), False)
        with self.assertRaises(ChangeRefused):
            service.add(self.dev, service.APPROVER, [self.final.pk, uuid.uuid4()])
        self.assertFalse(levels.held_roles(User.objects.get(pk=self.final.pk))[0])  # all or nothing
        page = self.client.post("/approval/approvers/add/", {"user": [str(self.approver.pk)]}, follow=True)
        self.assertContains(page, "Nobody new to add.")

    def test_a_send_back_restores_the_status_it_had(self):
        approval.approve(self.application, self.approver)
        approval.send_back(self.application, self.final)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, "contacted")


def mock_messages():
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.test import RequestFactory

    request = RequestFactory().get("/")
    request.session = {}
    return FallbackStorage(request)
