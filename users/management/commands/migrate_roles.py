"""One-off data move from the old roles to the team levels (docs/features/user-rules.md). Never a migration.

  Owner -> Admin     Manager -> Admin     Viewer -> Office     System -> Developer
  Approver stays Approver (and gets Office if they would have no level)

Each person ends at the highest level they map to. Superusers are untouched. Old group memberships are left in place;
`setup_roles` then removes the retired groups (everyone in them now holds a level). `--dry-run` prints what would change and saves nothing.
Safe to run again.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction

from common import levels

OLD_TO_LEVEL = {"Owner": levels.ADMIN, "Manager": levels.ADMIN, "Viewer": levels.OFFICE, "System": levels.DEVELOPER}


class Command(BaseCommand):
    help = "Map the old Owner/Manager/Viewer/Approver/System groups to Office/Admin/Developer + Approver."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show the mapping; change nothing.")

    def handle(self, *args, **options):
        User = get_user_model()
        with transaction.atomic():
            groups = {name: Group.objects.get_or_create(name=name)[0] for name in (*levels.LEVEL_GROUPS, levels.APPROVER_GROUP)}
            people = (User.objects.filter(groups__name__in=[*OLD_TO_LEVEL, levels.APPROVER_GROUP]).distinct().order_by("email"))
            changed = 0
            for user in people:
                names = set(user.groups.values_list("name", flat=True))
                before = levels.held(user)
                target = max((OLD_TO_LEVEL[n] for n in names if n in OLD_TO_LEVEL), key=levels.rank, default=levels.NONE)
                if levels.rank(before[0]) > levels.rank(target) and before[0] != levels.SUPERUSER:
                    target = before[0]  # already higher than the old roles gave (run before): never lowered
                if target == levels.NONE and levels.APPROVER_GROUP in names and before[0] == levels.NONE:
                    target = levels.OFFICE
                if target in levels.GROUP_FOR:
                    user.groups.add(groups[levels.GROUP_FOR[target]])
                if not user.is_staff and (target != levels.NONE or before[0] != levels.NONE):
                    user.is_staff = True
                    user.save(update_fields=["is_staff", "updated_at"])
                after = levels.held(user)
                changed += before != after
                self.stdout.write(f"{user.email}: {sorted(names)} -> {levels.LABELS[after[0]]}{' + Approver' if after[1] else ''}")
            self.stdout.write(f"{changed} of {len(people)} people changed.")
            if options["dry_run"]:
                transaction.set_rollback(True)
                self.stdout.write("Dry run: nothing was saved.")
