"""Load the Phase 1 starting data: plans and prices, site settings, hours, facilities, site copy, journey
questions and suggestion rules, Gold rules. Safe to run again: it only creates what is missing and never
overwrites what has been edited. `--dry-run` shows what would be created and saves nothing.

Lives in `plans` (the base data app). Not a migration, on purpose (backfills and seeds never go in migrations)."""
from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

from chat import seed as chat_seed
from content import seed as content_seed
from gold import seed as gold_seed
from journey import seed as journey_seed
from mailings import seed as mailings_seed
from notifications import seed as notifications_seed
from plans import seed as plans_seed

SEEDS = [("plans", plans_seed), ("content", content_seed), ("journey", journey_seed), ("gold", gold_seed), ("notifications", notifications_seed), ("mailings", mailings_seed), ("chat", chat_seed)]


def seed_all():
    """Run every seed. Returns Counter of 'app.Model' -> rows created."""
    created = Counter()

    def ensure(model, lookup, defaults=None):
        obj, was_created = model.objects.get_or_create(**lookup, defaults=defaults or {})
        if was_created:
            created[f"{model._meta.app_label}.{model.__name__}"] += 1
        return obj, was_created

    for _, module in SEEDS:
        module.run(ensure)
    return created


class Command(BaseCommand):
    help = "Load the Phase 1 starting data (idempotent). Use --dry-run to preview."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show what would be created; save nothing.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        with transaction.atomic():
            created = seed_all()
            if dry_run:
                transaction.set_rollback(True)
        prefix = "Would create" if dry_run else "Created"
        if not created:
            self.stdout.write("Nothing to create: everything is already there.")
        for name, count in sorted(created.items()):
            self.stdout.write(f"{prefix} {count} x {name}")
        if dry_run:
            self.stdout.write("Dry run: nothing was saved.")
