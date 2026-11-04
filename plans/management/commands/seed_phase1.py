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


INITIAL_STAFF_ALERT_EMAIL = "moishe@spa99.uk"  # the ONE place this address lives: first value of System > Defaults > Payment alert emails


def _seed_staff_alert_email():
    """Fill the payment alert address only while the field is empty, so an edit (even to a different address) is never overwritten."""
    from system.models import SiteDefaults

    row = SiteDefaults.load()
    if row.staff_alert_seeded:  # only ever the first time: clearing the field later is respected (use the on/off switch to stop the emails)
        return
    if not row.staff_alert_emails:
        SiteDefaults.objects.filter(pk=row.pk).update(staff_alert_emails=INITIAL_STAFF_ALERT_EMAIL)
    SiteDefaults.objects.filter(pk=row.pk).update(staff_alert_seeded=True)


INITIAL_GROUP_COPY_EMAIL = "staff@spa99.uk"  # the ONE place this address lives: first value of System > Defaults > "Copy of replies to the Office goes to"


def _seed_group_copy_email():
    """Same pattern as the payment alert address: fill it only the first time and only while empty, so an edit (or clearing it to switch the copy off) is never overwritten."""
    from system.models import SiteDefaults

    row = SiteDefaults.load()
    if row.office_copy_seeded:
        return
    if not row.office_copy_email:
        SiteDefaults.objects.filter(pk=row.pk).update(office_copy_email=INITIAL_GROUP_COPY_EMAIL)
    SiteDefaults.objects.filter(pk=row.pk).update(office_copy_seeded=True)


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
    _seed_staff_alert_email()
    _seed_group_copy_email()
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
