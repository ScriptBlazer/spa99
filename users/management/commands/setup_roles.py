"""Create (or refresh) the staff roles as Django Groups: Owner, Manager, Viewer, Approver, System. PROPOSED permissions per
docs/features/admin.md, to be approved by Moishe. Safe to run again; `--dry-run` only prints.

  Owner   everything, including Team (users, groups) and Gold status
  Manager everything on the project apps except Team and Gold status (people and Gold applications are view only here;
          Control does the field-level edits)
  Approver Gold only (Office): sees and decides Gold applications (approve, decline, resend); nothing else. Whoever
          is listed under System > Emails usually holds this role.
  System  developers only: may use the System host (system.spa99.uk) with a staff account. The group holds no model
          permissions (System is its own app); membership is the permission.
  Viewer  read-only: dashboard (insights), people, Gold applications, journey sessions
Superusers bypass groups entirely.
"""
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction

PROJECT_APPS = ["users", "plans", "content", "journey", "gold", "notifications"]
PEOPLE = ("users", "user")  # People and Team share this model; Manager may only read it (Control decides edits)
GOLD_STATUS = ("gold", "goldapplication")
VIEWER_MODELS = {
    PEOPLE, ("users", "interestregistration"), GOLD_STATUS, ("journey", "journeysession"), ("journey", "answer"),
}


def permissions_for(role):
    """Set of (app_label, codename) for a role."""
    perms = Permission.objects.select_related("content_type").filter(
        content_type__app_label__in=PROJECT_APPS + ["auth"]
    )
    chosen = set()
    for perm in perms:
        key = (perm.content_type.app_label, perm.content_type.model)
        action = perm.codename.split("_", 1)[0]
        if role == "Owner":
            ok = True
        elif role == "Manager":
            ok = key[0] != "auth"  # no groups / permissions (Team)
            if key in (PEOPLE, GOLD_STATUS):
                ok = ok and action == "view"
        elif role == "Approver":
            ok = key == GOLD_STATUS and action == "view"   # decisions only through the Office (locked service, invite); never edited in the admin
        elif role == "System":
            ok = False  # access to System is the group membership itself (system.services.may_use_system)
        else:  # Viewer
            ok = action == "view" and key in VIEWER_MODELS
        if ok:
            chosen.add((perm.content_type.app_label, perm.codename))
    return chosen


class Command(BaseCommand):
    help = "Create or refresh the Owner, Manager, Viewer, Approver and System groups."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show the permission counts; change nothing.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        with transaction.atomic():
            for role in ("Owner", "Manager", "Viewer", "Approver", "System"):
                wanted = permissions_for(role)
                group, created = Group.objects.get_or_create(name=role)
                lookup = {(p.content_type.app_label, p.codename): p for p in Permission.objects.select_related("content_type")}
                group.permissions.set([lookup[key] for key in wanted])
                self.stdout.write(f"{role}: {len(wanted)} permissions ({'created' if created else 'refreshed'})")
            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write("Dry run: nothing was saved.")
