"""One-off backfill for Office counting rule C1: give every older journey session a person_key (its own key), so each
becomes its own anonymous person. New sessions get it when created. Never run from a migration. `--dry-run` only counts.
Safe to run again (only sessions with no person_key are touched)."""
from django.core.management.base import BaseCommand
from django.db.models import F

from journey.models import JourneySession


class Command(BaseCommand):
    help = "Set person_key = key on journey sessions that have none (counting rule C1)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Say how many sessions would change; change nothing.")

    def handle(self, *args, **options):
        missing = JourneySession.objects.filter(person_key="")
        count = missing.count()
        self.stdout.write(f"{count} journey session(s) have no person_key.")
        if options["dry_run"]:
            self.stdout.write("Dry run: nothing changed.")
            return
        missing.update(person_key=F("key"))  # queryset update: no history rows
        self.stdout.write(self.style.SUCCESS(f"Set person_key on {count} session(s)."))
