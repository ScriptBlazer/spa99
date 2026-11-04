"""Copy the old Office emails (outreach.PersonMessage) into email threads, one thread per address, so they show in the new Email tab.
A separate script, never a migration. Safe to run again: a message already copied (Message.legacy_person_message) is skipped.
    python manage.py backfill_email_threads --dry-run     (shows what it would do, changes nothing)
    python manage.py backfill_email_threads"""
from django.core.management.base import BaseCommand
from django.db import transaction

from emailchat import services
from emailchat.models import Message, Thread
from outreach.models import PersonMessage

SUBJECT = "A message from Spa 99"  # the old Message email's subject (PersonMessage did not keep one)


class Command(BaseCommand):
    help = "Copy old PersonMessage rows into email threads (idempotent). --dry-run changes nothing."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Count what would be copied; change nothing.")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        done = set(Message.objects.exclude(legacy_person_message=None).values_list("legacy_person_message", flat=True))
        todo = [m for m in PersonMessage.objects.order_by("sent_at") if m.pk not in done]
        addresses = sorted({m.email for m in todo})
        self.stdout.write(f"{'DRY RUN: ' if dry else ''}{len(todo)} old message(s) to copy into {len(addresses)} thread(s); {len(done)} already copied.")
        if dry:
            return
        for address in addresses:
            rows = [m for m in todo if m.email == address]
            with transaction.atomic():
                thread = Thread.objects.filter(email=address, subject=SUBJECT).order_by("created_at").first()
                if thread is None:
                    thread = Thread(email=address, subject=SUBJECT)
                    services.resolve_links(thread, save=False)
                    thread.save()
                for row in rows:
                    text = row.text or ""
                    message = Message.objects.create(
                        thread=thread, direction=Message.OUT, subject=SUBJECT, shows_subject=not thread.messages.exists(), body_text=text, body_html="", status=Message.SENT,
                        author=row.author, author_label=row.author_label, created_at=row.sent_at, updated_at=row.sent_at, sent_at=row.sent_at, legacy_person_message=row.pk)
                    services._touch_thread(thread, message) if (thread.last_message_at is None or row.sent_at >= thread.last_message_at) else None
        self.stdout.write(self.style.SUCCESS("Done."))
