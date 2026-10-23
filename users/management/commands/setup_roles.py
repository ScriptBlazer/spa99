"""Create (or refresh) the team groups: Office, Admin, Developer and the extra permission Approver (docs/features/user-rules.md).
The groups hold no model permissions: the level IS the membership, checked by common.levels (the hidden Django admin is
superuser only). Safe to run again; `--dry-run` only prints.

The retired groups (Owner, Manager, Viewer, System) are removed only once everyone in them already holds a new level. Run
`migrate_roles` first to map people across; until then they are kept and the unmapped people are listed.
"""
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction

from common import levels

NEW_GROUPS = (*levels.LEVEL_GROUPS, levels.APPROVER_GROUP)
RETIRED_GROUPS = ("Owner", "Manager", "Viewer", "System")


class Command(BaseCommand):
    help = "Create or refresh the Office, Admin, Developer and Approver groups; remove the retired ones once empty."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show what would happen; change nothing.")

    def handle(self, *args, **options):
        with transaction.atomic():
            for name in NEW_GROUPS:
                group, created = Group.objects.get_or_create(name=name)
                group.permissions.clear()
                self.stdout.write(f"{name}: {'created' if created else 'refreshed'}")
            for name in RETIRED_GROUPS:
                group = Group.objects.filter(name=name).first()
                if group is None:
                    continue
                left = [u.email for u in group.user_set.all() if levels.held_level(u) == levels.NONE]
                if left:
                    self.stdout.write(self.style.WARNING(f"{name}: kept, {len(left)} not mapped yet ({', '.join(left)}). Run migrate_roles first."))
                else:
                    group.delete()
                    self.stdout.write(f"{name}: retired group removed")
            if options["dry_run"]:
                transaction.set_rollback(True)
                self.stdout.write("Dry run: nothing was saved.")
