"""Remove audit rows older than SYSTEM_AUDIT_RETENTION_DAYS (0 = keep forever) and re-anchor the hash chain."""
from django.conf import settings
from django.core.management.base import BaseCommand

from system import audit


class Command(BaseCommand):
    help = "Prune old System audit rows (retention setting SYSTEM_AUDIT_RETENTION_DAYS; 0 keeps everything)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Only report what would be removed.")
        parser.add_argument("--days", type=int, default=None, help="Override the setting for this run.")

    def handle(self, *args, **options):
        days = settings.SYSTEM_AUDIT_RETENTION_DAYS if options["days"] is None else options["days"]
        if not days:
            self.stdout.write("Retention is 0 (keep forever): nothing to do.")
            return
        result = audit.prune(days, dry_run=options["dry_run"])
        verb = "Would remove" if options["dry_run"] else "Removed"
        self.stdout.write(f"{verb} {result['changes']} change(s) and {result['events']} event(s) older than {days} days.")
