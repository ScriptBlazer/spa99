"""One-off: turn the old typed approver addresses (SiteSettings.gold_approver_emails) into Approver roles on team accounts.
Never a migration. Each address is matched to an account by exact email (case-insensitive) and that person gets the
Approver group if their team level allows it (Office or higher). Addresses with no account, or an account with no team level,
are listed and skipped (add them in System > Team first, then run this again). Running it twice changes nothing.

  manage.py import_approvers_from_emails --dry-run   # print what it would do; change nothing
  manage.py import_approvers_from_emails             # do it

The typed list itself is left as it is (the column stays for now, no longer used for sending).
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction

from common import levels
from common.validators import split_emails
from plans.models import SiteSettings
from system import audit
from system.models import SystemEvent
from system.services import record_direct


class Command(BaseCommand):
    help = "Give the Approver role to the accounts whose email is in the old typed approver list. Use --dry-run first."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Print what would be done; change nothing.")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        addresses = split_emails(SiteSettings.load().gold_approver_emails)
        if not addresses:
            self.stdout.write("The old approver list is empty: nothing to import.")
            return
        User, done = get_user_model(), 0
        with transaction.atomic():
            group = Group.objects.get_or_create(name=levels.APPROVER_GROUP)[0] if not dry else Group.objects.filter(name=levels.APPROVER_GROUP).first()
            for address in dict.fromkeys(a.lower() for a in addresses):
                user = User.objects.filter(email__iexact=address).first()
                if user is None:
                    self.stdout.write(f"{address}: no account with this email. Skipped.")
                elif not levels.can_hold_approver(user):
                    self.stdout.write(f"{address}: the account has no team level (Office or higher is needed). Skipped.")
                elif not user.is_active:
                    self.stdout.write(f"{address}: the account is deactivated. Skipped.")
                elif levels.held_roles(user)[0]:
                    self.stdout.write(f"{address}: already an approver. Nothing to do.")
                else:
                    self.stdout.write(f"{address}: {'would be made' if dry else 'made'} an approver ({levels.LABELS[levels.held_level(user)]}).")
                    done += 1
                    if not dry:
                        user.groups.add(group)
                        sentence = f"Made {user.email} an approver (imported from the old approver list)"
                        record_direct(None, "approval", "users.user", user, levels.APPROVER_GROUP, False, True, sentence=sentence)
                        audit.log_event(SystemEvent.ROLE_CHANGED, detail={"person": user.email, "via": "import_approvers_from_emails"},
                                        email="command line", sentence=sentence)
        self.stdout.write(f"Dry run: {done} would change, nothing was saved." if dry else f"Done: {done} made approvers.")
