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
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from . import audit
from .changes import SECTION_LABELS
from .models import SystemChange, SystemEvent

PAGE_SIZE = 25
PARAMS = ("section", "user", "category", "kind", "q", "range", "date_from", "date_to")
CHANGE_KINDS = {"created", "updated", "deleted", "direct"}


def categories(params):
    """The chosen categories (the `category` value is one or several, comma separated)."""
    valid = [key for key, _label in audit.CATEGORIES]
    return [c for c in (params.get("category") or "").split(",") if c in valid]


def chips(params):
    """The type chips: [{key, label, pressed, value}]. `value` is the `category` the chip sets when pressed (toggles it)."""
    chosen = categories(params)
    out = [{"key": "", "label": "All", "pressed": not chosen, "value": ""}]
    for key, label in (("change", "Changes"), ("security", "Security"), ("undo", "Undo"), ("failure", "Failures")):
        now = [c for c in chosen if c != key] if key in chosen else [*chosen, key]
        out.append({"key": key, "label": label, "pressed": key in chosen, "value": ",".join(now)})
    return out


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
    # typed emails of failed sign-ins are not people, so they are left out
    names |= set(SystemEvent.objects.exclude(user_label="").exclude(kind=SystemEvent.SIGN_IN_FAILED).order_by().values_list("user_label", flat=True).distinct())
    return sorted(names)


def filtered(params):
    """(changes queryset, events queryset) with the filters applied."""
    changes, events = SystemChange.objects.all(), SystemEvent.objects.all()
    kind, cats = params.get("kind"), categories(params)
    if cats:
        edits = Q()
        if "change" in cats:
            edits |= Q(undo_of__isnull=True)
        if "undo" in cats:
            edits |= Q(undo_of__isnull=False)
        kinds = [k for c in cats for k in audit.kinds_in(c)]  # "change" adds the events that are edits (code_edit)
        changes = changes.filter(edits) if edits else changes.none()
        events = events.filter(kind__in=kinds) if kinds else events.none()
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
        rows = changes.annotate(gk=_group_key()).filter(gk__in=batch_keys).select_related("undo_of").order_by("created_at", "seq")
        for row in rows:
            items.setdefault(str(row.gk), []).append(row)
    event_rows = {str(e.pk): e for e in events.filter(pk__in=event_ids)} if event_ids else {}
    _decorate([c for rows in items.values() for c in rows])

    groups = []
    for latest, key, kind in chosen:
        if kind == "event":
            event = event_rows.get(key)
            if event is None:
                continue
            event.can_undo, event.undone_label = False, ""
            groups.append(_event_group(event))
        elif key in items:
            groups.append(_batch_group(key, latest, items[key]))
    days = _by_day(groups)
    totals = _day_totals(changes, events, [d["date"] for d in days])
    for day in days:
        day["entries"] = totals.get(day["date"], 0)
    return {"days": days, "page": {
        "number": number, "num_pages": num_pages, "total": total, "has_next": number < num_pages, "has_previous": number > 1,
        "next_number": number + 1, "previous_number": number - 1, "size": PAGE_SIZE,
        "remaining": max(0, total - number * PAGE_SIZE)}}


def _day_totals(changes, events, dates):
    """{date: entries logged that day (with the filters)}: two small queries, whatever the number of groups."""
    out = {}
    if not dates:
        return out
    for queryset in (changes, events):
        for row in queryset.filter(created_at__date__in=dates).order_by().values("created_at__date").annotate(n=Count("id")):
            out[row["created_at__date"]] = out.get(row["created_at__date"], 0) + row["n"]
    return out


def _key_of(change):
    return str(change.batch_id or change.pk)


def _decorate(rows):
    """Give changes the facts the page needs, in two queries for any number of rows: `undone_label`, `undone_at`,
    `undone_key`, `undone_pk` (who put it back, when, and where to jump), `blocked_at`, `blocked_key`, `blocked_pk` (a newer
    change to the same field: Undo would be refused) and `can_undo`."""
    for row in rows:
        row.undone_at = row.undone_key = row.undone_pk = row.blocked_at = row.blocked_key = row.blocked_pk = None
        row.undone_label = ""
    candidates = [c for c in rows if c.undoable and not c.undo_of_id]
    undone = {}
    if candidates:
        for undo in SystemChange.objects.filter(undo_of_id__in=[c.pk for c in candidates]).order_by("created_at").only("pk", "undo_of_id", "user_label", "created_at", "batch_id"):
            undone.setdefault(undo.undo_of_id, undo)
        for row in candidates:
            undo = undone.get(row.pk)
            if undo:
                row.undone_label, row.undone_at, row.undone_key, row.undone_pk = undo.user_label or "a script", undo.created_at, _key_of(undo), undo.pk
        open_rows = [c for c in candidates if c.pk not in undone]
        if open_rows:
            newer = {}
            later = SystemChange.objects.filter(
                field__in={c.field for c in open_rows}, object_pk__in={c.object_pk for c in open_rows}, model_label__in={c.model_label for c in open_rows},
                created_at__gt=min(c.created_at for c in open_rows)).order_by("created_at").only("pk", "model_label", "object_pk", "field", "created_at", "batch_id")
            for row in later:
                newer.setdefault((row.model_label, row.object_pk, row.field), []).append(row)
            for row in open_rows:
                nxt = next((n for n in newer.get((row.model_label, row.object_pk, row.field), []) if n.created_at > row.created_at and n.pk != row.pk), None)
                if nxt:
                    row.blocked_at, row.blocked_key, row.blocked_pk = nxt.created_at, _key_of(nxt), nxt.pk
    for row in rows:
        row.can_undo = bool(row.undoable and not row.undo_of_id and not row.undone_label and not row.blocked_at)


def person(label):
    """'moishe.berko@x.com' -> 'Moishe Berko' (the short name shown in the log; the drawer has the full email)."""
    name = (label or "").split("@")[0].replace(".", " ").replace("_", " ").strip()
    return name.title() if name else ""


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


EVENT_ICONS = {
    SystemEvent.SIGN_IN: "sign-in", SystemEvent.UNLOCK: "lock-key-open", SystemEvent.LOCK_MANUAL: "lock-key", SystemEvent.LOCK_IDLE: "timer",
    SystemEvent.SIGN_OUT: "sign-out", SystemEvent.SESSION_EXPIRED: "timer", SystemEvent.EXPORT: "download-simple",
    SystemEvent.PASSWORD_CHANGED: "lock-key", SystemEvent.ROLE_CHANGED: "user-gear", SystemEvent.USER_DEACTIVATED: "user-gear", SystemEvent.USER_REACTIVATED: "user-gear",
    SystemEvent.UNDO: "arrow-counter-clockwise", SystemEvent.UNDO_ALL: "arrow-counter-clockwise", SystemEvent.AUDIT_PRUNED: "minus",
    SystemEvent.CODE_EDIT: "code",
}
CATEGORY_WORDS = {"change": "Change", "security": "Security", "undo": "Undo", "failure": "Failure"}
OUTCOME_WORDS = {SystemEvent.SIGN_IN_FAILED: "wrong password", SystemEvent.UNLOCK_FAILED: "wrong password",
                 SystemEvent.UNLOCK_RATE_LIMITED: "rate limited", SystemEvent.ACCESS_DENIED: "denied"}


def _meta(group_ip, ua, tail):
    from .templatetags.system_ui import browser

    return [part for part in (group_ip, browser(ua), tail) if part]


def _event_group(event):
    detail = event.detail if isinstance(event.detail, dict) else {}
    word = OUTCOME_WORDS.get(event.kind, "") if event.outcome != SystemEvent.OK else ""
    if event.outcome == SystemEvent.BLOCKED and event.kind == SystemEvent.SIGN_IN_FAILED:
        word = "rate limited"
    summary = event.sentence or event.get_kind_display()
    who = person(event.user_label)
    rest = ""
    for lead in (event.user_label, who):
        if lead and summary.startswith(lead):
            who, rest = (person(event.user_label), summary[len(lead):])
            break
    else:
        who = ""
    try:
        denied = int(detail.get("count", 0))
    except (TypeError, ValueError):
        denied = 0
    category = audit.category_of_event(event.kind)
    roles = ([", ".join(detail.get("old") or []) or "none", ", ".join(detail.get("new") or []) or "none"]
             if event.kind == SystemEvent.ROLE_CHANGED and isinstance(detail.get("old"), list) and isinstance(detail.get("new"), list) else None)
    return {"type": "event", "key": str(event.pk), "time": event.created_at, "user_label": event.user_label, "who": who, "rest": rest,
            "icon": "warning-octagon" if category == "failure" else EVENT_ICONS.get(event.kind, "sign-in"), "category_word": CATEGORY_WORDS[category],
            "roles": roles, "changed_fields": detail.get("changed_fields", 0) if event.kind == SystemEvent.CODE_EDIT else 0, "meta": _meta(event.ip_address, event.user_agent, event.path),
            "sections": [section_label(event.section)], "section_label": section_label(event.section), "count": 1,
            "summary": summary, "category": category,
            "ip_address": event.ip_address, "user_agent": event.user_agent, "path": event.path, "kind": event.kind,
            "batch_id": event.batch_id, "outcome": event.outcome, "outcome_word": word, "denied_count": denied if denied > 1 else 0,
            "open_count": 0, "undo_total": 0, "undo_all_url": "", "items": [event]}


def _batch_group(key, latest, rows):
    first = rows[0]
    sections = list(dict.fromkeys(section_label(r.section) for r in rows))
    who = first.user_label or "A script"
    where = sections[0] if len(sections) == 1 else "several sections"
    undoing = all(r.undo_of_id for r in rows)
    only_edits = all(r.kind in ("updated", "direct") for r in rows)
    if undoing:
        summary, verb = f"{who} put back {_plural(len(rows), 'field')} in {where}", "put back"
    elif only_edits:
        summary, verb = f"{who} changed {_plural(len(rows), 'field')} in {where}", "changed"
    else:
        summary, verb = f"{who} made {_plural(len(rows), 'change')} in {where}", "made"
    if len(rows) == 1:
        from .templatetags.system_ui import what as what_of

        row = rows[0]
        what = what_of(row)
        if row.kind == SystemChange.CREATED:
            verb, what = "added", row.object_repr or "a row"
        elif row.kind == SystemChange.DELETED:
            verb, what = "removed", row.object_repr or "a row"
    elif verb == "made":
        what = _plural(len(rows), "change")
    else:
        what = _plural(len(rows), "field")
    open_rows = [r for r in rows if r.can_undo]
    waiting = [r for r in rows if r.undoable and not r.undo_of_id and not r.undone_label]
    batch_id = first.batch_id
    origin = None
    if undoing and first.undo_of_id and first.undo_of:
        original = first.undo_of
        origin = {"time": original.created_at, "key": _key_of(original), "pk": original.pk}
    category = "undo" if undoing else "change"
    request_id = f"req {str(first.batch_id)[:6]}" if first.batch_id else ""
    icon = "arrow-counter-clockwise" if undoing else "plus" if verb == "added" else "minus" if verb == "removed" else "pencil-simple"
    return {"type": "batch", "key": key, "time": latest, "icon": icon, "category_word": CATEGORY_WORDS[category], "meta": _meta(first.ip_address, first.user_agent, request_id), "user_label": first.user_label, "who": person(first.user_label) or "A script",
            "verb": verb, "what": what, "sections": sections, "section_label": where, "count": len(rows), "summary": summary,
            "category": category, "ip_address": first.ip_address, "user_agent": first.user_agent, "path": first.path,
            "batch_id": batch_id, "outcome": "ok", "outcome_word": "", "open_count": len(open_rows), "undo_total": len(waiting), "origin": origin,
            "undo_all_url": reverse("system_undo_batch", args=[batch_id]) if batch_id and len(open_rows) > 1 else "", "items": rows}


def _by_day(groups):
    days = []
    today = timezone.localdate()
    for group in groups:
        day = timezone.localtime(group["time"]).date()
        if not days or days[-1]["date"] != day:
            name = "Today" if day == today else "Yesterday" if day == today - timedelta(days=1) else f"{day:%A}"
            days.append({"date": day, "name": name, "groups": []})
        days[-1]["groups"].append(group)
    return days


def page_of(params, entry_id):
    """The page of the feed that holds this entry's group (1 when unknown): groups newer than it, divided by the page size."""
    import uuid

    try:
        entry_id = uuid.UUID(str(entry_id))
    except ValueError:
        return 1
    changes, events = filtered(params)
    row = SystemChange.objects.filter(pk=entry_id).first()
    if row is not None:
        moment = SystemChange.objects.filter(batch_id=row.batch_id).aggregate(m=Max("created_at"))["m"] if row.batch_id else row.created_at
    else:
        row = SystemEvent.objects.filter(pk=entry_id).first()
        if row is None:
            return 1
        moment = row.created_at
    ahead = (changes.annotate(gk=_group_key()).order_by().values("gk").annotate(latest=Max("created_at")).filter(latest__gt=moment).count()
             + events.filter(created_at__gt=moment).count())
    return ahead // PAGE_SIZE + 1


def entry_detail(raw_id):
    """Everything the detail drawer shows for one entry (a change or a security event), or None. Reads one row (plus its
    undo links); the hash check recomputes this row's own hash, it does not walk the chain."""
    import json
    import uuid

    from .templatetags.system_ui import shown, what as what_of

    try:
        entry_id = uuid.UUID(str(raw_id))
    except (TypeError, ValueError):
        return None
    row = SystemChange.objects.select_related("undo_of").filter(pk=entry_id).first()
    is_change = row is not None
    if row is None:
        row = SystemEvent.objects.filter(pk=entry_id).first()
        if row is None:
            return None
    if row.seq is None:
        status = "legacy"
    else:
        from .audit import digest

        status = "ok" if digest(row.prev_hash, row.hash_payload()) == row.hash else "bad"
    pretty = lambda value: json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, default=str)  # noqa: E731
    try:
        section_url = reverse(f"system_{row.section}") if row.section in SECTION_LABELS else ""
    except NoReverseMatch:  # a section without its own page
        section_url = ""
    info = {"section_url": section_url, "is_change": is_change, "row": row, "title": row.sentence or str(row), "section_label": section_label(row.section), "hash_status": status,
            "who": person(row.user_label), "key": _key_of(row) if is_change else str(row.pk)}
    if is_change:
        _decorate([row])
        info.update(what=what_of(row), old_shown=shown(row.old_value, row.field), new_shown=shown(row.new_value, row.field),
                    old_json=pretty(row.old_value), new_json=pretty(row.new_value),
                    has_values=row.kind in ("updated", "direct"), undo_of=row.undo_of if row.undo_of_id else None,
                    undo_of_key=_key_of(row.undo_of) if row.undo_of_id and row.undo_of else "",
                    batch_url_ok=bool(row.batch_id))
        if not row.undoable:
            info["why_not"] = ("Removals are permanent." if row.kind == SystemChange.DELETED else "Created rows are not undone here." if row.kind == SystemChange.CREATED
                               else "This entry cannot be undone." if not row.undo_of_id else "")
    else:
        info.update(detail_json=pretty(row.detail), outcome_word=OUTCOME_WORDS.get(row.kind, ""))
        if row.kind == SystemEvent.CODE_EDIT and isinstance(row.detail, dict):  # the code as typed: tinted rows in the drawer
            from .codeview.service import diff_lines

            info.update(diff_lines=diff_lines(row.detail.get("diff", "")), diff_truncated=bool(row.detail.get("diff_truncated")),
                        changed_fields=row.detail.get("changed_fields", 0))
    return info


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
