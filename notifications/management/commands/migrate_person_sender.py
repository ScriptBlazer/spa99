"""Move the old "person sender" onto the new per-email Sender (Office 2). A SCRIPT, never a migration (it reads and changes data).

Before: one address for all automatic emails (System > Emails, `auto_email_from_address`), and each email either Site or Person. After: each automatic email stores the staff member it goes out
as (`NotificationTemplate.sender_user`), hello@ when none. Until this has run, emails keep behaving as they did (the old person sender still works), so running it is a tidy-up, not a rescue.

For every email that uses the person sender (its own setting, or its built-in default: the next-morning email): the staff member whose login or sending address is that address becomes its
sender, and its old Site/Person setting is cleared. An email whose address matches nobody is left exactly as it is and listed, so nothing changes silently. Safe to run twice (a second run
finds nothing to do). The old address setting and the old Site/Person column stay in the database until a later release removes them.

    manage.py migrate_person_sender --dry-run     then without --dry-run."""
from django.core.management.base import BaseCommand
from django.db import transaction

from notifications import emailbody, sender as sender_mod
from notifications.models import NotificationTemplate
from plans.models import SiteSettings


class Command(BaseCommand):
    help = "Give each email that used the person sender the matching staff member as its Sender. --dry-run writes nothing."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show what would change; write nothing.")

    def handle(self, *args, dry_run=False, **options):
        address = (SiteSettings.load().auto_email_from_address or "").strip().lower()
        candidates = {sender.address: user for user, sender in sender_mod.staff_candidates()}
        match = candidates.get(address)
        moved = unmatched = 0
        for row in NotificationTemplate.objects.order_by("key"):
            spec = emailbody.spec_for(row.key)
            uses_person = (row.sender or (spec.default_sender if spec else "site")) == "person"
            if row.sender_user_id or not uses_person:
                continue
            if match is None:
                unmatched += 1
                self.stdout.write(f"LEFT   {row.key}: uses the person sender but {address or 'no address'} is not a staff member's address, so it stays as it is")
                continue
            self.stdout.write(f"{'WOULD SET' if dry_run else 'SET'}  {row.key}: sender becomes {match.get_full_name() or match.email} <{address}>")
            moved += 1
            if not dry_run:
                with transaction.atomic():
                    row.sender_user, row.sender = match, ""
                    row._history_user = None
                    row.save(update_fields=["sender_user", "sender", "updated_at"])
        self.stdout.write(f"{moved} email(s) {'would be moved' if dry_run else 'moved'}, {unmatched} left. The old address setting stays until a later release removes it.")
