"""One-off backfill: store `suggestion_detail["counted_answers"]` on completed journeys that finished before it was
recorded, so the Office answer votes (counting rule C3) include them. Never run from a migration. `--dry-run` only counts.
Safe to run again (only sessions missing the field are touched). Going forward `engine.complete` is the only place a
journey is finished and it always stores the field (also on a re-finish)."""
from django.core.management.base import BaseCommand

from journey import engine
from journey.models import JourneySession

BATCH = 500


class Command(BaseCommand):
    help = "Add counted_answers to completed, non-bot journeys that lack it."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Say how many sessions would change; change nothing.")

    def handle(self, *args, **options):
        pending = [pk for pk, detail in JourneySession.objects.filter(completed=True, is_bot=False).values_list("pk", "suggestion_detail")
                   if "counted_answers" not in (detail or {})]
        self.stdout.write(f"{len(pending)} completed journey(s) have no counted_answers.")
        if options["dry_run"]:
            self.stdout.write("Dry run: nothing changed.")
            return
        for i in range(0, len(pending), BATCH):
            for session in JourneySession.objects.filter(pk__in=pending[i:i + BATCH]):
                detail = dict(session.suggestion_detail or {})
                detail["counted_answers"] = engine.counted_answers(session)
                JourneySession.objects.filter(pk=session.pk).update(suggestion_detail=detail)  # queryset update: no history row
        self.stdout.write(self.style.SUCCESS(f"Filled counted_answers on {len(pending)} journey(s)."))
