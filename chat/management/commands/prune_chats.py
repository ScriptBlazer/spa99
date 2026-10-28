from django.conf import settings
from django.core.management.base import BaseCommand

from chat import services


class Command(BaseCommand):
    help = "Delete Ask us chats older than the retention (90 days, settings.CHAT_RETENTION_DAYS). Also runs daily as a scheduled job."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Only report how many would be deleted.")
        parser.add_argument("--days", type=int, default=None, help=f"Override the retention for this run (default {settings.CHAT_RETENTION_DAYS}).")

    def handle(self, *args, **options):
        count = services.prune(options["days"], dry_run=options["dry_run"])
        self.stdout.write(f"{'Would delete' if options['dry_run'] else 'Deleted'} {count} chat(s).")
