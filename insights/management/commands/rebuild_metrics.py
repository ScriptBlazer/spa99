"""Recompute the stored Office figures from the source tables. `--dry-run` only lists the differences. Run it once to
backfill existing data, and any time a figure looks wrong. Safe to run again. Never run from a migration."""
from django.core.management.base import BaseCommand

from insights import rebuild


class Command(BaseCommand):
    help = "Recompute the stored metrics (counters, daily rows, rates, weeks, months, sentences) from source."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show the differences; change nothing.")
        parser.add_argument("--limit", type=int, default=40, help="Most differences to print (default 40).")

    def handle(self, *args, **options):
        diffs = rebuild.differences()
        self.stdout.write(f"{len(diffs)} difference(s) between the stored figures and the source tables.")
        for kind, ident, stored, wanted in diffs[: options["limit"]]:
            self.stdout.write(f"  {kind} {ident}: stored {stored}, source says {wanted}")
        if len(diffs) > options["limit"]:
            self.stdout.write(f"  ... and {len(diffs) - options['limit']} more")
        if options["dry_run"]:
            self.stdout.write("Dry run: nothing changed. (Visitor and page-view figures have no source and are never rebuilt.)")
            return
        summary = rebuild.apply()
        self.stdout.write(self.style.SUCCESS(f"Rebuilt. Roll-up: {summary}"))
