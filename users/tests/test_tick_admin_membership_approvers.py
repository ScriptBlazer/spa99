"""The one-off script that ticks Membership approver for today's Admins (2026-11-19): dry run changes nothing, Admins only, safe to repeat."""
from io import StringIO

from django.contrib.auth.models import Group
from django.core.management import CommandError, call_command
from django.test import TestCase

from common import levels
from plans.tests.helpers import make_team_member
from system.models import SystemChange, SystemEvent


def run(*args):
    out = StringIO()
    call_command("tick_admin_membership_approvers", *args, stdout=out)
    return out.getvalue()


class TickAdminTests(TestCase):
    def setUp(self):
        self.barry = make_team_member("barry@example.com", levels.ADMIN, approver=True)
        self.office = make_team_member("office@example.com", levels.OFFICE)
        self.dev = make_team_member("dev@example.com", levels.DEVELOPER)
        self.root = make_team_member("root@example.com", levels.SUPERUSER)
        self.viewer = make_team_member("viewer@example.com", levels.VIEWER)
        self.gone = make_team_member("gone@example.com", levels.ADMIN, is_active=False)

    def ticked(self):
        return {u.email for u in (self.barry, self.office, self.dev, self.root, self.viewer, self.gone)
                if levels.holds_membership_group(type(u).objects.get(pk=u.pk))}

    def test_dry_run_changes_nothing_the_real_run_ticks_active_admins_only_and_a_second_run_is_a_no_op(self):
        text = run("--dry-run")
        self.assertIn("1 would be ticked", text)
        self.assertNotIn("barry@", text)  # emails are masked
        self.assertEqual((self.ticked(), SystemChange.objects.count(), SystemEvent.objects.filter(kind=SystemEvent.ROLE_CHANGED).count()), (set(), 0, 0))
        self.assertIn("Done: 1 ticked", run())
        self.assertEqual(self.ticked(), {"barry@example.com"})
        self.assertTrue(levels.can_approve_memberships(type(self.barry).objects.get(pk=self.barry.pk)))
        self.assertEqual(SystemEvent.objects.filter(kind=SystemEvent.ROLE_CHANGED).count(), 1)
        self.assertIn("Done: 0 ticked, 1 already ticked", run())
        self.assertEqual((self.ticked(), SystemEvent.objects.filter(kind=SystemEvent.ROLE_CHANGED).count()), ({"barry@example.com"}, 1))

    def test_a_deactivated_admin_is_reported_masked_and_a_missing_group_stops_a_real_run_only(self):
        self.assertIn("g***@example.com: deactivated Admin, skipped", run("--dry-run"))
        Group.objects.filter(name=levels.MEMBERSHIP_APPROVER_GROUP).delete()
        self.assertIn("1 would be ticked", run("--dry-run"))
        with self.assertRaises(CommandError):
            run()
