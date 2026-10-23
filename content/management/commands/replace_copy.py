"""Replace a phrase in site copy (page titles, section headings, bodies and button labels).

For one-off wording changes on an existing database; new installs get the wording from the seed.
Run with --dry-run first. Saves through the model, so history is kept.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from content.models import Page, Section

FIELDS = {Page: ["title", "meta_description"], Section: ["heading", "body", "cta_label"]}


class Command(BaseCommand):
    help = "Replace a phrase in site copy. Use --dry-run to preview."

    def add_arguments(self, parser):
        parser.add_argument("find")
        parser.add_argument("replace")
        parser.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, find, replace, dry_run=False, **options):
        changed = 0
        for model, fields in FIELDS.items():
            for obj in model.objects.all():
                hits = [f for f in fields if find in (getattr(obj, f) or "")]
                if not hits:
                    continue
                for f in hits:
                    setattr(obj, f, getattr(obj, f).replace(find, replace))
                    self.stdout.write(f"{model.__name__} {obj.pk} {f}: {getattr(obj, f)[:80]}")
                if not dry_run:
                    obj.save()
                changed += 1
        verb = "Would change" if dry_run else "Changed"
        self.stdout.write(self.style.SUCCESS(f"{verb} {changed} row(s)."))
