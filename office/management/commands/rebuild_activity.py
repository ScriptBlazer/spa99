"""Rebuild the Activity page's stored daily totals (office.ActivityDay) and its time-of-day totals (office.ActivityTimeOfDay, the "By time" card) from the source tables, for the whole history. `--dry-run` shows exactly what would change, row by row, and writes nothing.
Run it once after deploying the page, and any time an old row was added, changed or erased (the hourly job only recounts today and yesterday). Safe to run again. Never run from a migration.
`--summary` prints only the totals."""
import re
from collections import defaultdict

from django.core.management.base import BaseCommand

from office import activity, activity_store


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


PART_ORDER = [key for key, *_rest in activity.PARTS]
PART_NAMES = {key: label for key, label, *_rest in activity.PARTS}


def build_time_report(create, update, delete, have, names=None):
    """(rows, totals, by_part) from activity_store.differences_time(). Rows are (day, part, group, staff, before, after) sorted by day, part of the day, type, staff. Only the counts are
    stored, so a staff name comes from the counting (create, update) or, for a row to remove, from `names` (stored ActivityDay labels by staff key)."""
    names = names or {}
    stored = {row.pk: row for row in have.values()}
    rows = []
    for (day, part, group, key), (n, label) in create.items():
        rows.append((day, part, group, staff_name(label), None, n))
    for (day, part, group, key), (n, label) in update.items():
        rows.append((day, part, group, staff_name(label), have[(day, part, group, key)].count, n))
    for pk in delete:
        row = stored[pk]
        rows.append((row.day, row.part, row.group, staff_name(names.get(row.staff_key) or row.staff_key), row.count, None))
    rows.sort(key=lambda r: (r[0], PART_ORDER.index(r[1]), r[2], r[3].lower()))
    by_part = {part: [0, 0] for part in PART_ORDER}
    for row in have.values():
        by_part[row.part][0] += row.count
        by_part[row.part][1] += row.count
    for day, part, group, staff, before, after in rows:
        by_part[part][1] += (after or 0) - (before or 0)
    kept = len(have) - len(update) - len(delete)
    return rows, {"add": len(create), "change": len(update), "remove": len(delete), "same": kept}, by_part


def time_row_line(day, part, group, staff, before, after):
    return f"{day_text(day)} · {PART_NAMES[part]} · {group.capitalize()} · {staff}: {'none' if before is None else before} → {'removed' if after is None else after}"


def row_line(day, group, staff, before, after):
    return f"{day_text(day)} · {group.capitalize()} · {staff}: {'none' if before is None else before} → {'removed' if after is None else after}"


def render(rows, totals, by_type, by_staff, first, last, done, summary, time=None):
    """`time` is build_time_report()'s (rows, totals, by_part), or None for the days only."""
    out = ["Rebuild of the Activity daily totals (office_activityday)" + (" and time-of-day totals (office_activitytimeofday)" if time else ""),
           ("DONE: the stored totals were rebuilt from the source tables. What it did is below." if done else
            "DRY RUN: this only reads. Nothing will be changed. It recounts every staff action in the source tables and shows how the stored daily totals would end up.")]
    verbs = ("added", "changed", "removed", "left as they were") if done else ("to add", "to change", "to remove", "to leave as they are")
    out += ["", "TOTALS", f"   Rows {verbs[0]}: {totals['add']:,}", f"   Rows {verbs[1]}: {totals['change']:,}", f"   Rows {verbs[2]}: {totals['remove']:,}", f"   Rows {verbs[3]}: {totals['same']:,}"]
    changed = totals["add"] + totals["change"] + totals["remove"]
    time_changed = bool(time and time[1]["add"] + time[1]["change"] + time[1]["remove"])
    if time:
        t = time[1]
        out += ["", "TOTALS BY TIME", f"   Rows {verbs[0]}: {t['add']:,}", f"   Rows {verbs[1]}: {t['change']:,}", f"   Rows {verbs[2]}: {t['remove']:,}", f"   Rows {verbs[3]}: {t['same']:,}"]
    if not changed and not time_changed:
        out += ["", "Nothing changed: the stored totals already match the source tables." if done else "Nothing would change: the stored totals already match the source tables."]
    elif not summary:
        if changed:
            out += ["", f"DAYS COVERED: {day_text(first)} to {day_text(last)}", "", f"EVERY ROW ({'day · type · staff: before → after'})"]
            out += [f"   {row_line(*row)}" for row in rows]
            out += ["", "BY TYPE (actions stored, old total → new total)"]
            out += [f"   {group.capitalize()}: {old:,} → {new:,}" for group, (old, new) in sorted(by_type.items())]
            out += ["", "BY STAFF (actions stored, old total → new total)"]
            out += [f"   {name}: {old:,} → {new:,}" for name, (old, new) in sorted(by_staff.items(), key=lambda i: i[0].lower())]
        if time_changed:
            out += ["", f"EVERY ROW BY TIME ({'day · part · type · staff: before → after'})"]
            out += [f"   {time_row_line(*row)}" for row in time[0]]
            out += ["", "BY TIME (actions stored, old total → new total)"]
            out += [f"   {PART_NAMES[part]}: {old:,} → {new:,}" for part, (old, new) in time[2].items()]
    out += ["", "COMMAND TO RUN FOR REAL" if not done else "TO CHECK", "   python manage.py rebuild_activity" + ("" if not done else "   (a second run should say nothing changed)")]
    return "\n".join(out)


class Command(BaseCommand):
    help = "Recount every Activity daily total from the source tables. --dry-run changes nothing; --summary prints only the totals."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Say exactly what would change; write nothing.")
        parser.add_argument("--summary", action="store_true", help="Print only the totals.")
        parser.add_argument("--allow-empty", action="store_true", help="Let a rebuild that finds no actions at all clear the stored totals (the safeguard otherwise deletes nothing).")

    def handle(self, *args, **options):
        plan, time_plan = activity_store.differences(), activity_store.differences_time()
        create, update, delete, have = plan
        t_create, t_update, t_delete, t_have = time_plan
        allow = options["allow_empty"]
        guarded, t_guarded = activity_store.guarded(plan, allow_empty=allow), activity_store.guarded(time_plan, allow_empty=allow)  # the same test activity_store.apply_both makes
        names = {key: row.staff_label for (_d, _g, key), row in have.items() if row.staff_label}   # stored labels by staff key, for the rows the time table removes
        names.update({key: label for (_d, _g, key), (_n, label) in {**create, **update}.items()})
        report = build_report(create, update, [] if guarded else delete, have)
        time_report = build_time_report(t_create, t_update, [] if t_guarded else t_delete, t_have, names)
        if not options["dry_run"]:
            activity_store.apply_both(allow_empty=allow)
        text = render(*report, done=not options["dry_run"], summary=options["summary"], time=time_report)
        verb = "was" if not options["dry_run"] else "will be"
        if guarded:
            text += (f"\n\nSAFEGUARD: the sources hold no actions at all but {len(delete):,} stored rows exist, so nothing {verb} deleted. "
                     "If every staff action really was erased, run it with --allow-empty.")
        if t_guarded:
            text += (f"\n\nSAFEGUARD (by time): the sources hold no actions at all but {len(t_delete):,} stored time-of-day rows exist, so nothing {verb} deleted. "
                     "If every staff action really was erased, run it with --allow-empty.")
        self.stdout.write(text)
