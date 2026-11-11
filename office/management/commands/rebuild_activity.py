"""Rebuild the Activity page's stored daily totals (office.ActivityDay) from the source tables, for the whole history. `--dry-run` shows exactly what would change, row by row, and writes nothing.
Run it once after deploying the page, and any time an old row was added, changed or erased (the hourly job only recounts today and yesterday). Safe to run again. Never run from a migration.
`--summary` prints only the totals."""
import re
from collections import defaultdict

from django.core.management.base import BaseCommand

from office import activity_store


def day_text(day):
    return f"{day.day} {day:%b %Y}"


def staff_name(label):
    """The staff member without his email: "Name (a@b)" becomes "Name", a bare "a@b" becomes "a"."""
    name = re.sub(r"\s*\(.*\)\s*$", "", (label or "").strip()).strip().split("@")[0]
    return name or "(no name)"


def build_report(create, update, delete, have):
    """(rows, totals, by_type, by_staff, first_day, last_day) from activity_store.differences(). Rows are (day, group, staff, before, after) sorted by day, type, staff."""
    stored = {row.pk: row for row in have.values()}
    rows = []
    for (day, group, key), (n, label) in create.items():
        rows.append((day, group, staff_name(label), None, n))
    for (day, group, key), (n, label) in update.items():
        rows.append((day, group, staff_name(label), have[(day, group, key)].count, n))
    for pk in delete:
        row = stored[pk]
        rows.append((row.day, row.group, staff_name(row.staff_label or row.staff_key), row.count, None))
    rows.sort(key=lambda r: (r[0], r[1], r[2].lower()))
    kept = len(have) - len(update) - len(delete)
    by_type, by_staff = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for row in have.values():
        by_type[row.group][0] += row.count
        by_type[row.group][1] += row.count
        by_staff[staff_name(row.staff_label or row.staff_key)][0] += row.count
        by_staff[staff_name(row.staff_label or row.staff_key)][1] += row.count
    for day, group, staff, before, after in rows:
        delta = (after or 0) - (before or 0)
        by_type[group][1] += delta
        by_staff[staff][1] += delta
    totals = {"add": len(create), "change": len(update), "remove": len(delete), "same": kept}
    days = [r[0] for r in rows]
    return rows, totals, dict(by_type), dict(by_staff), (min(days) if days else None), (max(days) if days else None)


def row_line(day, group, staff, before, after):
    return f"{day_text(day)} · {group.capitalize()} · {staff}: {'none' if before is None else before} → {'removed' if after is None else after}"


def render(rows, totals, by_type, by_staff, first, last, done, summary):
    out = ["Rebuild of the Activity daily totals (office_activityday)",
           ("DONE: the stored totals were rebuilt from the source tables. What it did is below." if done else
            "DRY RUN: this only reads. Nothing will be changed. It recounts every staff action in the source tables and shows how the stored daily totals would end up.")]
    verbs = ("added", "changed", "removed", "left as they were") if done else ("to add", "to change", "to remove", "to leave as they are")
    out += ["", "TOTALS", f"   Rows {verbs[0]}: {totals['add']:,}", f"   Rows {verbs[1]}: {totals['change']:,}", f"   Rows {verbs[2]}: {totals['remove']:,}", f"   Rows {verbs[3]}: {totals['same']:,}"]
    changed = totals["add"] + totals["change"] + totals["remove"]
    if not changed:
        out += ["", "Nothing changed: the stored totals already match the source tables." if done else "Nothing would change: the stored totals already match the source tables."]
    elif not summary:
        out += ["", f"DAYS COVERED: {day_text(first)} to {day_text(last)}", "", f"EVERY ROW ({'day · type · staff: before → after'})"]
        out += [f"   {row_line(*row)}" for row in rows]
        out += ["", "BY TYPE (actions stored, old total → new total)"]
        out += [f"   {group.capitalize()}: {old:,} → {new:,}" for group, (old, new) in sorted(by_type.items())]
        out += ["", "BY STAFF (actions stored, old total → new total)"]
        out += [f"   {name}: {old:,} → {new:,}" for name, (old, new) in sorted(by_staff.items(), key=lambda i: i[0].lower())]
    out += ["", "COMMAND TO RUN FOR REAL" if not done else "TO CHECK", "   python manage.py rebuild_activity" + ("" if not done else "   (a second run should say nothing changed)")]
    return "\n".join(out)


class Command(BaseCommand):
    help = "Recount every Activity daily total from the source tables. --dry-run changes nothing; --summary prints only the totals."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Say exactly what would change; write nothing.")
        parser.add_argument("--summary", action="store_true", help="Print only the totals.")
        parser.add_argument("--allow-empty", action="store_true", help="Let a rebuild that finds no actions at all clear the stored totals (the safeguard otherwise deletes nothing).")

    def handle(self, *args, **options):
        create, update, delete, have = activity_store.differences()
        guarded = bool(not options["allow_empty"] and delete and not create and not update and len(delete) == len(have))  # the same test activity_store.apply makes
        report = build_report(create, update, [] if guarded else delete, have)
        if not options["dry_run"]:
            activity_store.apply(allow_empty=options["allow_empty"])
        text = render(*report, done=not options["dry_run"], summary=options["summary"])
        if guarded:
            text += (f"\n\nSAFEGUARD: the sources hold no actions at all but {len(delete):,} stored rows exist, so nothing {'was' if not options['dry_run'] else 'will be'} deleted. "
                     "If every staff action really was erased, run it with --allow-empty.")
        self.stdout.write(text)
