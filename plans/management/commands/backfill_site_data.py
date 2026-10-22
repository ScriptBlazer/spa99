"""One-off update for an EXISTING install after the "data, not code" review fixes (2026-10-22). New installs get all
of this from `seed_phase1`. This command fills the gaps in rows that already exist and changes nothing that was
written by hand:

- site copy that still says "January 2027" gets the {opening} placeholder (the date then lives in Site settings)
- facilities with no picture description get the starting one
- Gold perks with no short phrase get the starting one
- the Shabbos / Yom Tov hours line is written onto the opening rule

Not a migration, on purpose. `--dry-run` shows what would change and saves nothing. Safe to run twice."""
from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

from content.models import Page, Section
from plans import seed as plans_seed
from plans.models import Facility, OpeningRule, Plan

OLD_OPENING = "January 2027"


def _swap(text):
    return text.replace(OLD_OPENING, "{opening}") if text and OLD_OPENING in text else text


def backfill():
    """Apply the updates. Returns Counter of 'what' -> rows changed."""
    changed = Counter()
    for section in Section.objects.all():
        new = {f: _swap(getattr(section, f)) for f in ("heading", "body", "cta_label")}
        if any(new[f] != getattr(section, f) for f in new):
            for field, value in new.items():
                setattr(section, field, value)
            section.save()
            changed["content.Section (opening placeholder)"] += 1
    for page in Page.objects.all():
        if _swap(page.meta_description) != page.meta_description:
            page.meta_description = _swap(page.meta_description)
            page.save()
            changed["content.Page (opening placeholder)"] += 1

    alts = {row[0]: row[4] for row in plans_seed.FACILITIES}
    for facility in Facility.objects.filter(image_alt=""):
        if facility.slug in alts:
            facility.image_alt = alts[facility.slug]
            facility.save()
            changed["plans.Facility (picture description)"] += 1

    gold = Plan.objects.filter(slug="gold").first()
    phrases = {p["key"]: p["phrase"] for data in plans_seed.PLANS if data["slug"] == "gold" for p in data["perks"] if p.get("phrase")}
    if gold is not None:
        perks, touched = [dict(p) for p in gold.perks or []], False
        for perk in perks:
            if not perk.get("phrase") and perk.get("key") in phrases:
                perk["phrase"], touched = phrases[perk["key"]], True
        if touched:
            gold.perks = perks
            gold.save()
            changed["plans.Plan (Gold perk phrases)"] += 1

    for rule in OpeningRule.objects.filter(kind=OpeningRule.CLOSE_BEFORE_CANDLES, public_note=""):
        rule.public_title = rule.public_title or plans_seed.SHABBOS_TITLE
        rule.public_note = plans_seed.SHABBOS_NOTE
        rule.save()
        changed["plans.OpeningRule (Shabbos line)"] += 1
    return changed


class Command(BaseCommand):
    help = "Fill gaps in existing rows after the data-not-code fixes. Use --dry-run to preview."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show what would change; save nothing.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        with transaction.atomic():
            changed = backfill()
            if dry_run:
                transaction.set_rollback(True)
        prefix = "Would change" if dry_run else "Changed"
        if not changed:
            self.stdout.write("Nothing to change.")
        for name, count in sorted(changed.items()):
            self.stdout.write(f"{prefix} {count} x {name}")
        if dry_run:
            self.stdout.write("Dry run: nothing was saved.")
