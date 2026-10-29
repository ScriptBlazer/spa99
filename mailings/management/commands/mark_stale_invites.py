"""One-off: invites still waiting (queued or sending) from the retired Invites batch sending can never be sent now. Mark them skipped so
they stop counting as "invited and waiting". Invites made by a group send (batch_id = a Mailing id) are left alone.
Never run by a migration. `--dry-run` shows the count and changes nothing."""
from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef
from django.utils import timezone

from mailings.models import Invite, Mailing

REASON = "old batch, sending retired"


class Command(BaseCommand):
    help = "Mark old queued invites (from the retired Invites batches) as skipped."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Only say how many would change.")

    def handle(self, *args, dry_run=False, **options):
        old = Invite.objects.filter(status__in=(Invite.QUEUED, Invite.SENDING)).exclude(Exists(Mailing.objects.filter(pk=OuterRef("batch_id"))))
        count = old.count()
        if dry_run:
            self.stdout.write(f"Dry run: {count} old queued invite(s) would be marked skipped ({REASON}). Nothing changed.")
            return
        old.update(status=Invite.SKIPPED, reason=REASON, updated_at=timezone.now())
        self.stdout.write(f"Marked {count} old queued invite(s) skipped ({REASON}).")
