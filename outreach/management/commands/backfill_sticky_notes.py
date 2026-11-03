"""Copy the Gold NOTE_ADDED history events into sticky notes, once. Never part of a migration (docs/features/office-outreach.md).
Each note keeps the id of the event it came from, so a re-run copies nothing. The old events stay in the audit table; the Office
no longer shows them as history lines.   Usage: manage.py backfill_sticky_notes --dry-run   then without --dry-run."""
from django.core.management.base import BaseCommand
from django.db import transaction

from gold.models import ApplicationEvent
from outreach.models import StickyNote


class Command(BaseCommand):
    help = "Copy Gold NOTE_ADDED events into sticky notes (idempotent). Use --dry-run first."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="List what would be copied and change nothing.")

    def handle(self, *args, dry_run=False, **options):
        done = set(StickyNote.objects.filter(source_event__isnull=False).values_list("source_event", flat=True))
        events = ApplicationEvent.objects.filter(action=ApplicationEvent.NOTE_ADDED).select_related("application").order_by("at")
        todo = [e for e in events if e.pk not in done and e.message.strip() and e.application.email.strip()]
        for e in todo:
            self.stdout.write(f"{'WOULD COPY' if dry_run else 'COPY'} {e.application.reference} {e.at:%Y-%m-%d %H:%M} by {e.actor_label or '-'}: {e.message[:60]}")
        if not dry_run:
            with transaction.atomic():
                for e in todo:
                    StickyNote.objects.create(
                        email=e.application.email.strip().lower(), text=e.message.strip(), author=e.actor, author_label=e.actor_label,
                        created_at=e.at, source_event=e.pk)
        self.stdout.write(f"{len(todo)} note(s) {'would be copied' if dry_run else 'copied'}; {len(done)} already copied.")
