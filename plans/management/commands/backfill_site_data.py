"""One-off update for an EXISTING install after the "data, not code" review fixes (2026-10-22). New installs get all
of this from `seed_phase1`. This command fills the gaps in rows that already exist and changes nothing that was
written by hand:

- site copy that still says "January 2027" gets the {opening} placeholder (the date then lives in Site settings)
- facilities with no picture description get the starting one
- Gold perks with no short phrase get the starting one
- the Shabbos / Yom Tov hours line is written onto the opening rule
- (memberships page, 2026-10-22) plans with no tagline / render get the starting ones, perks with no `pill` get the
  starting one, and the "Not sure?" row gets the new wording only if it still has the exact old wording
- (The spa page, 2026-10-22) facilities get display, image name, focus and soft facts into empty slots only (the
  display is set only on a row that has no facts and no image name yet, so a later edit is never undone); missing
  `spa` copy rows are created; the exact old wording "Eight spaces, one quiet visit.", "Explore your membership" (spa
  closing button) and the massage line "by appointment" (OPS-06) are replaced

- (2026-10-23) facts are filled only on a never-touched row (cleared facts stay cleared); the three picture
  descriptions that no longer match the new photos (cold plunge, showers, massage room) are replaced only while they
  still have the exact old wording; the kitchenette goes from companion to tile only while it still has its seeded
  image and facts; the kitchenette moves after the showers only while all eight orders are still the old seeded ones

- (2026-10-23, round 3) missing rows for the opener lines, amenity moments and kit (`spa`), Gold page notes (`gold`), the
  Memberships "every visit" row and the whole `signin` page are created (never overwritten, never re-created for pages
  you did not ask about); step 2 pills lose "Towel, robe and slippers" only while exactly the old wording; Gold perks
  without a `note` get the starting one; the gym gets its bottle picture name only while it has no small picture at all.
  The last two run only on the first round 3 run (while the `signin` page does not exist), so clearing the gym's picture
  name or removing a note by hand stays cleared

Not a migration, on purpose. `--dry-run` shows what would change and saves nothing. Safe to run twice."""
from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

from content import seed as content_seed
from content.models import Page, Section
from plans import seed as plans_seed
from plans.models import Facility, OpeningRule, Plan

OLD_OPENING = "January 2027"
# Seeded picture descriptions that no longer match the realistic photos (2026-10-23): replaced only while exactly this.
OLD_FACILITY_ALTS = {
    "cold-plunge": "Cold plunge pool set into a travertine floor",
    "showers": "Rain showers behind walnut slatted screens",
    "massage-room": "Massage room with a walnut table",
}


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
    for facility in Facility.objects.all():
        if facility.slug not in alts:
            continue
        if facility.image_alt == "" or OLD_FACILITY_ALTS.get(facility.slug) == facility.image_alt:  # exact old wording only
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

    for data in plans_seed.PLANS:  # memberships page: tagline, render, perk chips (only into empty slots)
        plan = Plan.objects.filter(slug=data["slug"]).first()
        if plan is None:
            continue
        touched = False
        for field in ("tagline", "render"):
            if data.get(field) and not getattr(plan, field):
                setattr(plan, field, data[field])
                touched = True
        pills = {p["key"]: p["pill"] for p in data["perks"] if p.get("pill")}
        perks = [dict(p) for p in plan.perks or []]
        for perk in perks:
            if not perk.get("pill") and perk.get("key") in pills:
                perk["pill"], touched = pills[perk["key"]], True
        if touched:
            plan.perks = perks
            plan.save()
            changed["plans.Plan (memberships page: tagline, render, pills)"] += 1

    not_sure = Section.objects.filter(page__key="memberships", key="not_sure", heading="Not sure? Find yours.").first()
    if not_sure is not None:
        not_sure.heading = "Not sure?"
        if not_sure.cta_label == "Explore your membership":
            not_sure.cta_label = "Tailor your membership"
        not_sure.save()
        changed["content.Section (memberships: Not sure?)"] += 1

    changed.update(_spa_page())
    changed.update(_round_3())
    return changed


OLD_STEP_2_PILLS = "Towel, robe and slippers\nYour own locker\nPhones stay in the locker"
# page key -> the rows added in round 3 (None = every row of the page, creating the page too)
ROUND_3_ROWS = {
    "spa": ["opener_1", "opener_2", "opener_3", "opener_4", "opener_image", "moment_towel", "moment_shower",
            "moment_slippers", "moment_tote", "arrive_kit"],
    "gold": ["holds_lead", "apply_note"],
    "memberships": ["every_visit"],
    "signin": None,
}


def _round_3():
    """Round 3 data (2026-10-23): fills missing rows only; the one wording change needs the exact old text."""
    changed = Counter()
    pages = list(content_seed.PAGES)
    # The record that round 3 has run is the `signin` page (new in round 3). Perk notes and the gym picture name can be
    # emptied by hand, and empty looks the same as "never set", so they are only set while that page does not exist yet.
    first_run = not Page.objects.filter(key="signin").exists()
    for page_key, wanted in ROUND_3_ROWS.items():
        title, description, sections = content_seed.PAGES[page_key]
        page = Page.objects.filter(key=page_key).first()
        if page is None and wanted is None:
            page = Page.objects.create(key=page_key, title=title, meta_description=description, order=pages.index(page_key) + 1)
            changed["content.Page (round 3)"] += 1
        if page is None:
            continue
        for order, (key, heading, body, cta_label, cta_url) in enumerate(sections, start=1):
            if wanted is not None and key not in wanted:
                continue
            _, made = Section.objects.get_or_create(page=page, key=key, defaults={
                "heading": heading, "body": body, "cta_label": cta_label, "cta_url": cta_url, "order": order})
            if made:
                changed["content.Section (round 3 rows)"] += 1
    pills = Section.objects.filter(page__key="spa", key="step_2_pills", body=OLD_STEP_2_PILLS).first()
    if pills is not None:
        pills.body = content_seed.STEP_2_PILLS
        pills.save()
        changed["content.Section (spa step 2 pills)"] += 1

    gold = Plan.objects.filter(slug="gold").first()
    if gold is not None and first_run:
        perks, touched = [dict(p) for p in gold.perks or []], False
        for perk in perks:
            note = plans_seed.GOLD_PERK_NOTES.get(perk.get("key"))
            if note and "note" not in perk:
                perk["note"], touched = note, True
        if touched:
            gold.perks = perks
            gold.save()
            changed["plans.Plan (Gold perk notes)"] += 1

    gym = Facility.objects.filter(slug="gym").first()
    if gym is not None and first_run and not gym.detail_image and not gym.detail_image_name:
        gym.detail_image_name = plans_seed.GYM_DETAIL["detail_image_name"]
        gym.detail_alt = gym.detail_alt or plans_seed.GYM_DETAIL["detail_alt"]
        gym.save()
        changed["plans.Facility (gym small picture)"] += 1
    return changed


OLD_MASSAGE_LINE = "A quiet room for a massage, by appointment."
OLD_SPA_INTRO = "Eight spaces, one quiet visit."
# Stand-in images replaced by the realistic fal set (2026-10-22): swapped only while the old name is still set.
OLD_FACILITY_IMAGES = {"cold-plunge": "cold-tub", "kitchenette": "lounge"}


# The seeded order before 2026-10-23 (kitchenette last). Reordered only while the rows still have exactly these.
OLD_FACILITY_ORDER = {"dry-sauna": 1, "wet-sauna": 2, "cold-plunge": 3, "showers": 4, "relaxing-zone": 5,
                      "massage-room": 6, "gym": 7, "kitchenette": 8}


def _reorder_facilities():
    """Kitchenette goes right after the showers so the four tiles share one row. Never touches a rearranged set."""
    facilities = list(Facility.objects.all())
    if {f.slug: f.order for f in facilities} != OLD_FACILITY_ORDER:
        return 0
    new = {row[0]: order for order, row in enumerate(plans_seed.FACILITIES, start=1)}
    for facility in facilities:
        if facility.order != new[facility.slug]:
            facility.order = new[facility.slug]
            facility.save()
    return 1


def _spa_page():
    """The spa page data: facility fields, missing copy rows and three exact-wording fixes. Fills empty only."""
    changed = Counter()
    if _reorder_facilities():
        changed["plans.Facility (order: kitchenette after showers)"] += 1
    for facility in Facility.objects.all():
        seed = plans_seed.FACILITY_SPA_PAGE.get(facility.slug)
        touched = False
        if seed is not None:
            untouched = not facility.facts and not facility.image_name  # never backfilled or edited
            if untouched and facility.display != seed["display"]:
                facility.display, touched = seed["display"], True
            elif (facility.slug == "kitchenette" and facility.display == Facility.COMPANION and seed["display"] == Facility.TILE
                  and facility.image_name == seed["image_name"] and facility.facts == seed["facts"]):
                facility.display, touched = Facility.TILE, True  # 2026-10-23: kitchenette is a normal tile now
            if seed["image_name"] and not facility.image_name:
                facility.image_name, touched = seed["image_name"], True
            elif OLD_FACILITY_IMAGES.get(facility.slug) == facility.image_name:
                facility.image_name, touched = seed["image_name"], True
            if seed["image_focus"] != "50% 50%" and facility.image_focus in ("", "50% 50%"):
                facility.image_focus, touched = seed["image_focus"], True
            if untouched:  # empty facts can mean "show none" after an admin cleared them
                facility.facts, touched = list(seed["facts"]), True
        if facility.short_line == OLD_MASSAGE_LINE:
            facility.short_line, touched = "A quiet room for massage, part of your visit.", True
        if touched:
            facility.save()
            changed["plans.Facility (the spa page fields)"] += 1

    page = Page.objects.filter(key="spa").first()
    if page is not None:
        _, _, sections = content_seed.PAGES["spa"]
        for order, (key, heading, body, cta_label, cta_url) in enumerate(sections, start=1):
            _, made = Section.objects.get_or_create(page=page, key=key, defaults={
                "heading": heading, "body": body, "cta_label": cta_label, "cta_url": cta_url, "order": order})
            if made:
                changed["content.Section (spa page rows)"] += 1
        fixed = 0
        for section in Section.objects.filter(page=page):  # saved one by one so the change is in the history
            if section.key == "intro" and section.body == OLD_SPA_INTRO:
                section.body = "{rooms} spaces, one quiet visit."
            elif section.key == "next" and section.cta_label == "Explore your membership":
                section.cta_label = "Tailor your membership"
            else:
                continue
            section.save()
            fixed += 1
        if fixed:
            changed["content.Section (spa page wording)"] += fixed
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
