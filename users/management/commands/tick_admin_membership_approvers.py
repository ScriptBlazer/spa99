"""One-off (2026-11-19): give the Membership approver group to every active account at exactly Admin level.
Never a migration. Until now Admin approved memberships without the tick; from now on Admin needs it, so this keeps today's Admins working.
Developers and superusers always can approve and are left alone. Running it twice changes nothing.

  manage.py tick_admin_membership_approvers --dry-run   # list what it would do; change nothing
  manage.py tick_admin_membership_approvers             # do it
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from common import levels
from system import audit
from system.models import SystemEvent
from system.services import record_direct


def _masked(email):
    name, _, domain = email.partition("@")
    return f"{name[:1]}***@{domain}"


class Command(BaseCommand):
    help = "Add the Membership approver group to every active Admin (exactly Admin level). Use --dry-run first."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Print what would be done; change nothing.")

    def handle(self, *args, **options):
        dry, done, already = options["dry_run"], 0, 0
        group = Group.objects.filter(name=levels.MEMBERSHIP_APPROVER_GROUP).first()
        if group is None and not dry:
            raise CommandError("The Membership approver group does not exist yet. Run: manage.py setup_roles")
        for user in get_user_model().objects.filter(is_active=False).prefetch_related("groups").order_by("email"):
            if levels.held_level(user) == levels.ADMIN:
                self.stdout.write(f"{_masked(user.email)}: deactivated Admin, skipped.")
        admins = [u for u in get_user_model().objects.filter(is_active=True, is_staff=True).prefetch_related("groups").order_by("email")
                  if levels.level_of(u) == levels.ADMIN]
        with transaction.atomic():
            for user in admins:
                if levels.holds_membership_group(user):
                    already += 1
                    self.stdout.write(f"{_masked(user.email)}: already ticked.")
                    continue
                done += 1
                self.stdout.write(f"{_masked(user.email)}: {'would be ticked' if dry else 'ticked'} as Membership approver.")
                if not dry:
                    user.groups.add(group)
                    sentence = f"Made {user.email} a membership approver (Admin now needs the tick; tick_admin_membership_approvers)"
                    record_direct(None, "approval", "users.user", user, levels.MEMBERSHIP_APPROVER_GROUP, False, True, sentence=sentence)
                    audit.log_event(SystemEvent.ROLE_CHANGED, detail={"person": user.email, "via": "tick_admin_membership_approvers"},
                                    email="command line", sentence=sentence)
        self.stdout.write(f"Dry run: {done} would be ticked, {already} already ticked, nothing was saved." if dry
                          else f"Done: {done} ticked, {already} already ticked.")
