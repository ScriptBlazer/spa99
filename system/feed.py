"""The audit read model: ONE feed of changes and security events, newest first, paginated by group.

Shape (what the page gets from `audit_feed`):

    {"days": [{"date": date, "groups": [group, ...]}, ...],      # newest day first
     "page": {"number", "num_pages", "total", "has_next", "has_previous", "next_number", "previous_number"}}

    group = {"type": "batch" | "event", "key", "time", "user_label", "sections": [labels], "section_label", "count",
             "summary" (one line: who, what, N fields, section), "category" (change | security | undo | failure),
             "ip_address", "user_agent", "path", "batch_id", "outcome", "open_count", "undo_all_url" (or ""),
             "items": [SystemChange or SystemEvent rows]}

A batch group is one save (all changes sharing a batch id, or a lone change); each event is its own group. Items carry
`.can_undo`, `.undone_label` ('' unless undone) and, for changes, `.sentence`. Filters apply to items: a group lists only
the items that match. The number of queries does not depend on how many groups there are (tested)."""
import csv
import heapq
from datetime import date, timedelta, timezone as dt_timezone
from urllib.parse import urlencode

from django.db.models import Count, Max, Q, UUIDField
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone

from . import audit
from .changes import SECTION_LABELS
from .models import SystemChange, SystemEvent

PAGE_SIZE = 25
PARAMS = ("section", "user", "category", "kind", "q", "range", "date_from", "date_to")
CHANGE_KINDS = {"created", "updated", "deleted", "direct"}


def params_from(get):
    return {key: (get.get(key, "") or "").strip() for key in PARAMS}


def query_string(params):
    return urlencode({k: v for k, v in params.items() if v})


def section_choices():
    return [*SECTION_LABELS.items(), *audit.EVENT_SECTION_LABELS.items()]


def section_label(key):
    return SECTION_LABELS.get(key) or audit.EVENT_SECTION_LABELS.get(key) or key


def people():
    """Everyone who appears in the log (for the person filter): two small queries."""
    names = set(SystemChange.objects.exclude(user_label="").order_by().values_list("user_label", flat=True).distinct())
    names |= set(SystemEvent.objects.exclude(user_label="").order_by().values_list("user_label", flat=True).distinct())
    return sorted(names)


def filtered(params):
    """(changes queryset, events queryset) with the filters applied."""
    changes, events = SystemChange.objects.all(), SystemEvent.objects.all()
    category, kind = params.get("category"), params.get("kind")
    if category == "change":
        changes, events = changes.filter(undo_of__isnull=True), events.none()
    elif category == "undo":
        changes, events = changes.filter(undo_of__isnull=False), events.filter(kind__in=audit.kinds_in("undo"))
    elif category in ("security", "failure"):
        changes, events = changes.none(), events.filter(kind__in=audit.kinds_in(category))
    if kind:
        if kind in CHANGE_KINDS:
            changes, events = changes.filter(kind=kind), events.none()
        else:
            changes, events = changes.none(), events.filter(kind=kind)
    if params.get("section"):
        changes, events = changes.filter(section=params["section"]), events.filter(section=params["section"])
    if params.get("user"):
        changes, events = changes.filter(user_label__icontains=params["user"]), events.filter(user_label__icontains=params["user"])
    if params.get("q"):
        text = params["q"]
        changes = changes.filter(Q(sentence__icontains=text) | Q(user_label__icontains=text) | Q(ip_address__icontains=text)
                                 | Q(object_repr__icontains=text) | Q(field__icontains=text))
        events = events.filter(Q(sentence__icontains=text) | Q(user_label__icontains=text) | Q(ip_address__icontains=text) | Q(path__icontains=text))
    start, end = params.get("date_from"), params.get("date_to")
    if params.get("range") in ("1", "7", "30"):
        start, end = (timezone.localdate() - timedelta(days=int(params["range"]) - 1)).isoformat(), ""
    for value, lookup in ((start, "created_at__date__gte"), (end, "created_at__date__lte")):
        if value:
            try:
                day = date.fromisoformat(value)
            except ValueError:
                continue
            changes, events = changes.filter(**{lookup: day}), events.filter(**{lookup: day})
    return changes, events


def _group_key():
    return Coalesce("batch_id", "id", output_field=UUIDField())


def _page_number(raw):
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 1


def audit_feed(params, page=1):
    """One page of the feed (see the module doc for the shape). Queries: 2 counts, 2 group heads, 2 item loads, 1 undone."""
    changes, events = filtered(params)
    number = _page_number(page)
    group_count = changes.annotate(gk=_group_key()).order_by().values("gk").distinct().count()
    total = group_count + events.count()
    num_pages = max(1, -(-total // PAGE_SIZE))
    number = min(number, num_pages)
    want = number * PAGE_SIZE
    change_heads = list(changes.annotate(gk=_group_key()).order_by().values("gk").annotate(latest=Max("created_at")).order_by("-latest", "-gk")[:want])
    event_heads = list(events.order_by("-created_at", "-id").values("id", "created_at")[:want])
    merged = [(h["latest"], str(h["gk"]), "batch") for h in change_heads] + [(h["created_at"], str(h["id"]), "event") for h in event_heads]
    merged.sort(reverse=True)
    chosen = merged[(number - 1) * PAGE_SIZE: want]
    batch_keys = [key for _t, key, kind in chosen if kind == "batch"]
    event_ids = [key for _t, key, kind in chosen if kind == "event"]

    items = {}
    if batch_keys:
        rows = changes.annotate(gk=_group_key()).filter(gk__in=batch_keys).order_by("created_at", "seq")
        for row in rows:
            items.setdefault(str(row.gk), []).append(row)
    event_rows = {str(e.pk): e for e in events.filter(pk__in=event_ids)} if event_ids else {}
    undone = {}
    ids = [c.pk for rows in items.values() for c in rows if c.undoable]
    if ids:
        for original, label, when in SystemChange.objects.filter(undo_of_id__in=ids).order_by("created_at").values_list("undo_of_id", "user_label", "created_at"):
            undone.setdefault(original, (label or "a script", when))

    groups = []
    for latest, key, kind in chosen:
        if kind == "event":
            event = event_rows.get(key)
            if event is None:
                continue
            event.can_undo, event.undone_label = False, ""
            groups.append(_event_group(event))
        elif key in items:
            groups.append(_batch_group(key, latest, items[key], undone))
    return {"days": _by_day(groups), "page": {
        "number": number, "num_pages": num_pages, "total": total, "has_next": number < num_pages, "has_previous": number > 1,
        "next_number": number + 1, "previous_number": number - 1}}


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def _event_group(event):
    return {"type": "event", "key": str(event.pk), "time": event.created_at, "user_label": event.user_label,
            "sections": [section_label(event.section)], "section_label": section_label(event.section), "count": 1,
            "summary": event.sentence or event.get_kind_display(), "category": audit.category_of_event(event.kind),
            "ip_address": event.ip_address, "user_agent": event.user_agent, "path": event.path,
            "batch_id": event.batch_id, "outcome": event.outcome, "open_count": 0, "undo_all_url": "", "items": [event]}


def _batch_group(key, latest, rows, undone):
    for row in rows:
        stamp = undone.get(row.pk)
        row.undone_label = stamp[0] if stamp else ""
        row.can_undo = row.undoable and not row.undo_of_id and not stamp
    first = rows[0]
    sections = list(dict.fromkeys(section_label(r.section) for r in rows))
    who = first.user_label or "A script"
    where = sections[0] if len(sections) == 1 else "several sections"
    undoing = all(r.undo_of_id for r in rows)
    only_edits = all(r.kind in ("updated", "direct") for r in rows)
    if undoing:
        summary = f"{who} put back {_plural(len(rows), 'field')} in {where}"
    elif only_edits:
        summary = f"{who} changed {_plural(len(rows), 'field')} in {where}"
    else:
        summary = f"{who} made {_plural(len(rows), 'change')} in {where}"
    open_rows = [r for r in rows if r.can_undo]
    batch_id = first.batch_id
    return {"type": "batch", "key": key, "time": latest, "user_label": first.user_label, "sections": sections, "section_label": where,
            "count": len(rows), "summary": summary, "category": "undo" if undoing else "change", "ip_address": first.ip_address,
            "user_agent": first.user_agent, "path": first.path, "batch_id": batch_id, "outcome": "ok", "open_count": len(open_rows),
            "undo_all_url": reverse("system_undo_batch", args=[batch_id]) if batch_id and len(open_rows) > 1 else "", "items": rows}


def _by_day(groups):
    days = []
    for group in groups:
        day = timezone.localtime(group["time"]).date()
        if not days or days[-1]["date"] != day:
            days.append({"date": day, "groups": []})
        days[-1]["groups"].append(group)
    return days


# ---------- CSV ----------

HEADER = ["time_utc", "number", "type", "kind", "outcome", "who", "ip", "browser", "section", "path", "what happened", "old", "new", "request_id", "hash"]


def _safe(value):
    """A cell that starts with = + - @ would run as a formula in a spreadsheet: prefix an apostrophe."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def _row(item):
    is_change = isinstance(item, SystemChange)
    return [item.created_at.astimezone(dt_timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), item.seq, "change" if is_change else "event", item.kind,
            "ok" if is_change else item.outcome, item.user_label, item.ip_address, item.user_agent, item.section, item.path, item.sentence,
            _json(item.old_value) if is_change else "", _json(item.new_value) if is_change else "", item.batch_id or "", item.hash]


def _json(value):
    import json

    return "" if value is None else json.dumps(value, ensure_ascii=False)


def export_count(params):
    changes, events = filtered(params)
    return changes.count() + events.count()


class _Echo:
    def write(self, value):
        return value


def export_rows(params):
    """Generator of CSV lines for the filtered feed, newest first, read with iterator() so memory stays flat."""
    changes, events = filtered(params)
    streams = [changes.order_by("-created_at", "-id").iterator(), events.order_by("-created_at", "-id").iterator()]
    writer = csv.writer(_Echo())
    yield writer.writerow(HEADER)
    for item in heapq.merge(*streams, key=lambda r: (r.created_at, str(r.pk)), reverse=True):
        yield writer.writerow([_safe(cell) for cell in _row(item)])
