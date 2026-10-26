"""One-off backfill for the multi-select "What do you do?": copy the single `industry` of older Gold applications into the
new `industries` list. Never run from a migration. `--dry-run` only counts. Safe to run again (only applications whose list
is empty and that have an industry are touched). Reading code does not need it (GoldApplication.industry_values falls back
to `industry`); it only makes the admin export show the list for old rows too."""
from django.core.management.base import BaseCommand

from gold.models import GoldApplication


class Command(BaseCommand):
    help = "Set industries = [industry] on Gold applications made before the multi-select."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Say how many applications would change; change nothing.")

    def handle(self, *args, **options):
        todo = [a for a in GoldApplication.objects.exclude(industry="") if not a.industries]
        self.stdout.write(f"{len(todo)} Gold application(s) have an industry but no industries list.")
        if options["dry_run"]:
            self.stdout.write("Dry run: nothing changed.")
            return
        for application in todo:
            GoldApplication.objects.filter(pk=application.pk).update(industries=[application.industry])  # no history rows
        self.stdout.write(self.style.SUCCESS(f"Updated {len(todo)} application(s)."))
