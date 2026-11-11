"""Office > Activity: a mini dashboard and one list of every staff action (docs/features/office-activity.md). Read only.

The figures (tiles, change lines, columns, who did what, by type, the staff list, the day counts) are read from the stored daily totals (`office.ActivityDay`, written by
office.activity_store), never counted from the sources while a page loads. The list is live: one source is one table, the newest rows of a page are limited in the database
(`-when, -pk`) with the same filter (`_scope`) that fills the stored totals (`_by_day`), so the list and the figures agree. The rows of a page are merged from the sources and sorted by
(at, source, pk), which is the order each source has in the database, so pages join up even when times are equal. A row is a plain dict. Text of notes and of
messages is never read into a row. Automatic actions (the group email, a bounce, his own link, the system) are not staff and are left out.
"""
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Callable

from django.db.models import Count, Q, Sum
from django.db.models.functions import Lower, TruncDate
from django.utils import dateformat, timezone

from gold.audit import label_for
from gold.models import ApplicationEvent
from journey.models import JourneySession
from office.models import MembershipReview, MembershipReviewEvent
from outreach import services as outreach_services
from outreach.models import LeadArchiveEvent, NoteEvent, OutreachEntry, PersonEdit, PersonMessage, StickyNote
from plans.models import Plan
from system.models import SystemEvent
from users.models import User

from . import profile
from .models import ActivityDay
from .selectors import ACTIVITY_RANGES

NO_FILTER = {"staff": "", "group": ""}
PAGE_SIZE = 50
MAX_STAFF_BARS = 8
TOP = 8  # the list shows this many while closed (a preview); "See all" opens the whole list, a page at a time
OPEN_PAGE_SIZE = 10  # rows on each page once opened: page 1 is rows 1 to 10 (a fixed number, not a setting)
AUTOMATIC = (outreach_services.GROUP_EMAIL_LABEL, "Bounce", outreach_services.SELF_LABEL)  # labels the system writes when no staff member acted
GROUPS = [("approvals", "Approvals"), ("leads", "Leads and people"), ("notes", "Notes"), ("emails", "Emails"), ("gold", "Gold"), ("memberships", "Memberships")]
GROUP_LABELS = dict(GROUPS)
HUES = {"approvals": "clay", "leads": "teal", "notes": "sage", "emails": "slate", "gold": "ochre", "memberships": "plum"}  # one colour per type, everywhere on the page
ICONS = {"approvals": "check", "leads": "address-book", "notes": "note", "emails": "envelope", "gold": "gold", "memberships": "coin"}
SYSTEM_KINDS = (SystemEvent.SETUP_MANUAL, SystemEvent.SETUP_EDITED, SystemEvent.SETUP_CANCELLED, SystemEvent.SALE_RESTORED)
GOLD_WORDS = {
    ApplicationEvent.APPROVED: "Approved a Gold application", ApplicationEvent.SENT_FOR_FINAL: "Sent a Gold application for final approval",
    ApplicationEvent.FINAL_CONFIRMED: "Confirmed final approval", ApplicationEvent.SENT_BACK: "Sent a Gold application back for review",
    ApplicationEvent.DECLINED: "Declined a Gold application", ApplicationEvent.RESPONDED: "Responded to a Gold applicant",
    ApplicationEvent.INVITE_SENT: "Sent a Gold invite", ApplicationEvent.INVITE_RESENT: "Sent a Gold invite again",
    ApplicationEvent.STATUS_CHANGED_ADMIN: "Changed a Gold status in the admin", ApplicationEvent.GUIDE_SENT: "Sent the Gold guide",
}
# A Gold application's own notes come from the copied sticky notes and its emails are automatic, so neither is read from the Gold events.
GOLD_NOT_STAFF = (ApplicationEvent.SUBMITTED, ApplicationEvent.EMAIL_SENT, ApplicationEvent.EMAIL_FAILED, ApplicationEvent.NOTE_ADDED,
                  ApplicationEvent.NOTE_EDITED, ApplicationEvent.NOTE_DELETED, ApplicationEvent.NOTE_RESTORED)

# `what` (a stable name) -> the sentence round the person: "{staff} {before}{person}{after}". {title} is the approach list's name in lower case.
WORDING = {
    "Note added": ("added a note on ", ""), "Note edited": ("edited a note on ", ""), "Note deleted": ("deleted a note on ", ""), "Note restored": ("restored a note on ", ""),
    "Archived": ("archived ", ""), "Moved back to Leads": ("moved ", " back to Leads"), "Marked as genuine": ("marked ", " as genuine"),
    "Genuine mark undone": ("undid the genuine mark on ", ""),
    "Added to the approach list": ("added ", " to the {title}"), "Marked done on the approach list": ("marked ", " done on the {title}"),
    "Email sent": ("emailed ", ""), "Email failed": ("tried to email ", ""),
    "Approved": ("approved ", ""), "Declined": ("declined ", ""), "Undid a decision": ("undid the decision on ", ""),
    GOLD_WORDS[ApplicationEvent.APPROVED]: ("approved ", " for Gold"), GOLD_WORDS[ApplicationEvent.SENT_FOR_FINAL]: ("sent ", " for final Gold approval"),
    GOLD_WORDS[ApplicationEvent.FINAL_CONFIRMED]: ("confirmed ", " for Gold"), GOLD_WORDS[ApplicationEvent.SENT_BACK]: ("sent ", " back for Gold review"),
    GOLD_WORDS[ApplicationEvent.DECLINED]: ("declined ", " for Gold"), GOLD_WORDS[ApplicationEvent.RESPONDED]: ("replied to ", " about Gold"),
    "Marked Contacted": ("marked ", " as contacted"), GOLD_WORDS[ApplicationEvent.INVITE_SENT]: ("sent ", " a Gold invite"),
    GOLD_WORDS[ApplicationEvent.INVITE_RESENT]: ("sent ", " the Gold invite again"), GOLD_WORDS[ApplicationEvent.STATUS_CHANGED_ADMIN]: ("changed the Gold status of ", " in the admin"),
    GOLD_WORDS[ApplicationEvent.GUIDE_SENT]: ("sent ", " the Gold guide"),
    "Set up membership manually": ("set up a membership for ", " by hand"), "Edited a manual membership": ("changed the membership of ", ""),
    "Cancelled a manual membership": ("cancelled the membership of ", ""), "Restored a sale price": ("restored the sale price for ", ""),
}
for _noun, _a in (("Mobile", "a mobile"), ("Email", "an email"), ("First name", "a first name")):
    WORDING[f"{_noun} added"] = (f"added {_a} for ", "")
    WORDING[f"{_noun} changed"] = (f"changed the {_noun.lower()} of ", "")
    WORDING[f"{_noun} removed"] = (f"removed the {_noun.lower()} of ", "")


# ---------- filters and the period ----------

def _iso(text):
    try:
        return date.fromisoformat((text or "").strip())
    except ValueError:
        return None


def filters_from(request, range_name="week"):
    """{staff, group, from, to, range, error}. `range` is the range picked (or remembered); dates, when set, win over it. A backwards range is refused, garbage is empty."""
    start, end = _iso(request.GET.get("from")), _iso(request.GET.get("to"))
    error = ""
    if start and end and end < start:
        start = end = None
        error = "The end date can't be before the start date."
    group = request.GET.get("group", "")
    return {"staff": request.GET.get("staff", "").strip()[:254].lower(), "group": group if group in GROUP_LABELS else "", "from": start, "to": end,
            "range": range_name if range_name in ACTIVITY_RANGES else "week", "error": error}


def is_filtered(filters):
    """Staff, type or dates (the range is shown by the range bar itself)."""
    return bool(filters["staff"] or filters["group"] or filters["from"] or filters["to"])


def _local(day, add=0):
    return timezone.make_aware(datetime.combine(day + timedelta(days=add), time.min))


@dataclass
class Period:
    """The window shown and the window just before it, of the same length, for the change lines. `start` and `end` (start inclusive, end exclusive, None = open) bound the live list;
    the stored figures are whole London days: `day_from` to `day_to` (inclusive) and `prev_from` to `prev_to`."""
    name: str            # week, month, 30d, all or custom (dates picked)
    start: datetime = None
    end: datetime = None
    day_from: date = None
    day_to: date = None
    prev_from: date = None
    prev_to: date = None
    granularity: str = "day"
    first_day: date = None   # the first and last day of the columns (None: from the first action)
    last_day: date = None

    @property
    def has_previous(self):
        return self.prev_from is not None and self.prev_to is not None


def _span(name, start_day, end_day, today, prev_from, prev_to, granularity="day"):
    """A window of whole days start_day..end_day (inclusive; None = open): the list stops at now."""
    return Period(name, _local(start_day) if start_day else None, _local(end_day, 1) if end_day else None, start_day, end_day, prev_from, prev_to, granularity)


def period(filters, now=None):
    """The window for `filters` at `now` (London), in whole days. This week starts Monday and is compared with last week up to the same weekday; this month with last month up to the
    same day of the month; 30 days (today and the 29 before) with the 30 days before; dates with the same number of days just before them. Today counts as a whole day on both sides."""
    now = timezone.localtime(now or timezone.now())
    today = now.date()
    start_date, end_date = filters.get("from"), filters.get("to")
    if start_date or end_date:
        last = end_date or today
        p = _span("custom", start_date, last, today, None, None)
        p.first_day, p.last_day = start_date, last
        if end_date is None:
            p.end = now
        if start_date and start_date <= last:
            days = (last - start_date).days + 1
            p.prev_from, p.prev_to = start_date - timedelta(days=days), min(last, today) - timedelta(days=days)
        p.granularity = "day" if p.first_day and (p.last_day - p.first_day).days < 31 else "week"
        return p
    name = filters.get("range") or "all"
    if name == "week":
        monday = today - timedelta(days=today.weekday())
        p = _span(name, monday, today, today, monday - timedelta(days=7), today - timedelta(days=7))
        p.end, p.first_day, p.last_day = now, monday, monday + timedelta(days=6)
        return p
    if name == "month":
        first = today.replace(day=1)
        before = (first - timedelta(days=1)).replace(day=1)
        p = _span(name, first, today, today, before, min(first - timedelta(days=1), before + timedelta(days=today.day - 1)))
        p.end, p.first_day, p.last_day = now, first, today
        return p
    if name == "30d":
        first = today - timedelta(days=29)
        p = _span(name, first, today, today, first - timedelta(days=30), first - timedelta(days=1))
        p.end, p.first_day, p.last_day = now, first, today
        return p
    return Period("all", granularity="week", last_day=today)


# ---------- staff: one person, however his label was stored ----------

_EMAIL_IN_LABEL = re.compile(r"\(([^()\s]+@[^()\s]+)\)\s*$")


def staff_key(label):
    """One person, one key: the email inside "Name (email)", a bare email, or (an old plain label) the name, all lower case."""
    label = (label or "").strip()
    found = _EMAIL_IN_LABEL.search(label)
    return (found.group(1) if found else label).lower()


def _name_part(label):
    label = (label or "").strip()
    found = _EMAIL_IN_LABEL.search(label)
    if found:
        return label[: found.start()].strip()
    return "" if "@" in label else label


def _staff_q(label, key):
    if "@" in key:
        return Q(**{f"{label}__iexact": key}) | Q(**{f"{label}__iendswith": f"({key})"})
    return Q(**{f"{label}__iexact": key})


def _identities(labels):
    """{key: (first name or email, full label)} for stored labels. The full label is the account's own ("Name (email)") while it exists, else the best one stored.
    Two people who share a first name (among these and the team) show their full labels instead."""
    by_key = defaultdict(set)
    for label in labels:
        if (label or "").strip():
            by_key[staff_key(label)].add(label.strip())
    emails = [key for key in by_key if "@" in key]
    users = {u.e: u for u in User.objects.annotate(e=Lower("email")).filter(e__in=emails)} if emails else {}
    out, firsts = {}, defaultdict(set)
    for key, stored in by_key.items():
        best = max(stored, key=lambda text: (("(" in text), len(text)))
        user = users.get(key)
        full = label_for(user) if user else best
        first = (user.first_name.strip() if user and user.first_name.strip() else "") or (_name_part(best).split() or [""])[0]
        if not first:  # no first name anywhere: his email
            found = _EMAIL_IN_LABEL.search(best)
            first = user.email if user else (found.group(1) if found else best)
        out[key] = (first, full)
        firsts[first.lower()].add(key)
    for email, name in User.objects.filter(is_staff=True).values_list("email", "first_name"):
        if (name or "").strip():
            firsts[name.strip().split()[0].lower()].add(email.lower())
    return {key: ((full if len(firsts[first.lower()]) > 1 else first), full) for key, (first, full) in out.items()}


def staff_choices():
    """[(key, label)] for everyone who appears in the stored totals, A to Z: one entry for one person (a bare email and "Name (email)" are the same person), a deleted account
    stays by its stored label. Light queries only: one read of the distinct stored labels, one or two of the accounts. Nothing is counted from the sources."""
    people = _identities([label for label in ActivityDay.objects.order_by().values_list("staff_label", flat=True).distinct()])
    return sorted(((key, full) for key, (_who, full) in people.items()), key=lambda pair: pair[1].lower())


# ---------- the sources ----------

@dataclass
class Source:
    index: int                 # its place in the sort key (so equal times keep one fixed order)
    group: str
    when: str                  # the time field
    label: str                 # the staff label field
    base: Callable             # () -> the queryset, before any filter
    row: Callable              # (obj, ctx) -> {label, what, detail, email, user, pid, application}
    related: tuple = ()
    defer: tuple = ()


def _r(label, what, detail="", email="", user=None, pid="", application=None):
    return {"label": label, "what": what, "detail": detail, "email": (email or "").strip().lower(), "user": user, "pid": pid, "application": application}


def _plans(ctx):
    if "plans" not in ctx:
        ctx["plans"] = dict(Plan.objects.values_list("slug", "name"))
    return ctx["plans"]


def _row_note(n, ctx):
    return _r(n.author_label, "Note added", email=n.email)


def _row_note_event(e, ctx):
    return _r(e.by_label, {NoteEvent.DELETED: "Note deleted", NoteEvent.RESTORED: "Note restored", NoteEvent.EDITED: "Note edited"}[e.kind], email=e.note.email)  # never the text


def _row_edit(e, ctx):
    noun = {PersonEdit.MOBILE: "Mobile", PersonEdit.EMAIL: "Email"}.get(e.what, "First name")
    verb = "added" if not e.before else ("removed" if not e.after else "changed")
    detail = f"{e.before} to {e.after}" if e.before and e.after else (e.after or e.before)
    return _r(e.by_label, f"{noun} {verb}", detail, email=e.email)


def _row_archive(e, ctx):
    words = {LeadArchiveEvent.ARCHIVED: "Archived", LeadArchiveEvent.RESTORED: "Moved back to Leads", LeadArchiveEvent.GENUINE: "Marked as genuine", LeadArchiveEvent.UNGENUINE: "Genuine mark undone"}
    return _r(e.by_label, words.get(e.kind, "Moved back to Leads"), e.reason if e.kind == LeadArchiveEvent.ARCHIVED else "", email=e.email)


def _approach_row(what, label):
    def row(e, ctx):
        app = e.gold_application
        return _r(getattr(e, label), what, email=e.lead_email or (app.email if app else ""), user=e.user, application=app)
    return row


def _row_message(m, ctx):
    failed = m.status == PersonMessage.FAILED
    return _r(m.author_label, "Email failed" if failed else "Email sent", "Did not send" if failed else "", email=m.email)  # the body is never read


def _row_membership(e, ctx):
    if e.to_status == MembershipReview.WAITING:
        what, detail = "Undid a decision", f"Was {e.from_status}"
    else:
        what, detail = ("Approved" if e.to_status == MembershipReview.APPROVED else "Declined"), ""
    return _r(e.by_label, what, detail, user=e.registration.user)


def _row_gold(e, ctx):
    meta = e.meta or {}
    what = "Marked Contacted" if e.action == ApplicationEvent.RESPONDED and (meta.get("whatsapp") or meta.get("email")) else GOLD_WORDS.get(e.action, e.get_action_display())
    detail = f"{e.from_status.replace('_', ' ').capitalize()} to {e.to_status.replace('_', ' ')}" if e.from_status and e.to_status else ""
    return _r(e.actor_label, what, detail, email=e.application.email, application=e.application)


def _row_system(e, ctx):
    plans, d = _plans(ctx), e.detail or {}
    detail = ""
    if e.kind == SystemEvent.SETUP_MANUAL:
        what, detail = "Set up membership manually", plans.get(d.get("plan"), "")
    elif e.kind == SystemEvent.SETUP_EDITED:
        what, old, new = "Edited a manual membership", (d.get("old") or {}).get("plan"), (d.get("new") or {}).get("plan")
        detail = f"{plans.get(old, old)} to {plans.get(new, new)}" if old and new and old != new else ""
    elif e.kind == SystemEvent.SETUP_CANCELLED:
        what = "Cancelled a manual membership"
    else:
        what = "Restored a sale price"
    return _r(e.user_label, what, detail, pid=d.get("member", ""))


SOURCES = [
    Source(0, "notes", "created_at", "author_label", lambda: StickyNote.objects.all(), _row_note),  # a copied Gold note is a note added, too: its Gold event is left out below
    Source(1, "notes", "at", "by_label", lambda: NoteEvent.objects.all(), _row_note_event, related=("note",)),
    Source(2, "leads", "at", "by_label", lambda: PersonEdit.objects.all(), _row_edit),
    Source(3, "leads", "at", "by_label", lambda: LeadArchiveEvent.objects.all(), _row_archive),
    Source(4, "leads", "added_at", "added_by_label", lambda: OutreachEntry.objects.all(), _approach_row("Added to the approach list", "added_by_label"), related=("user", "gold_application")),
    Source(5, "leads", "done_at", "done_by_label", lambda: OutreachEntry.objects.all(), _approach_row("Marked done on the approach list", "done_by_label"), related=("user", "gold_application")),
    Source(6, "emails", "sent_at", "author_label", lambda: PersonMessage.objects.all(), _row_message, defer=("text",)),
    Source(7, "approvals", "at", "by_label", lambda: MembershipReviewEvent.objects.all(), _row_membership, related=("registration__user",)),
    Source(8, "gold", "at", "actor_label", lambda: ApplicationEvent.objects.exclude(action__in=GOLD_NOT_STAFF), _row_gold, related=("application",)),
    Source(9, "memberships", "created_at", "user_label", lambda: SystemEvent.objects.filter(kind__in=SYSTEM_KINDS), _row_system),
]


def _clean(queryset, source):
    """Not automatic, not without a staff label, and with a time."""
    return queryset.exclude(**{f"{source.label}__in": ("", *AUTOMATIC)}).filter(**{f"{source.when}__isnull": False})


def _scope(source, f, start, end):
    """The one shared filter, for the list and for the counts: staff member, and the window."""
    queryset = _clean(source.base(), source)
    if f["staff"]:
        queryset = queryset.filter(_staff_q(source.label, f["staff"]))
    if start:
        queryset = queryset.filter(**{f"{source.when}__gte": start})
    if end:
        queryset = queryset.filter(**{f"{source.when}__lt": end})
    return queryset


def _sources(f):
    return [s for s in SOURCES if not f["group"] or s.group == f["group"]]


def _fetch(source, f, start, end, limit):
    """[(time, source index, pk, object)] for the newest `limit` rows of one source that match, in the database's own order (-time, -pk). Rows are built later, for the page only."""
    queryset = _scope(source, f, start, end).order_by(f"-{source.when}", "-pk")
    if source.related:
        queryset = queryset.select_related(*source.related)
    if source.defer:
        queryset = queryset.defer(*source.defer)
    return [(getattr(obj, source.when), source.index, obj.pk, obj) for obj in queryset[:limit]]


# ---------- counts: the same filter, grouped ----------

def _by_day(f, start, end):
    """[(group, label, day, n)] for the window: counts by staff label and London day, one grouped query per source."""
    zone = timezone.get_current_timezone()
    out = []
    for source in _sources(f):
        grouped = (_scope(source, f, start, end).order_by().annotate(day=TruncDate(source.when, tzinfo=zone)).values(source.label, "day").annotate(n=Count("pk")))
        out.extend((source.group, row[source.label], row["day"], row["n"]) for row in grouped)
    return out


def _stored(f, first, last):
    """The stored daily rows for the whole days first..last (None = open), with the staff and type filter: one query."""
    rows = ActivityDay.objects.all()
    if first:
        rows = rows.filter(day__gte=first)
    if last:
        rows = rows.filter(day__lte=last)
    if f["staff"]:
        rows = rows.filter(staff_key=staff_key(f["staff"]))
    if f["group"]:
        rows = rows.filter(group=f["group"])
    return rows


def _stored_by_day(f, first, last):
    """[(group, label, day, n)] from the stored totals, the shape `_by_day` counts."""
    return [(r.group, r.staff_label, r.day, r.count) for r in _stored(f, first, last).order_by("day")]


def _stored_totals(f, first, last):
    """{group: n} for a window (the period before: only the counts are needed): one grouped query over the stored rows."""
    return Counter({row["group"]: row["n"] for row in _stored(f, first, last).order_by().values("group").annotate(n=Sum("count"))})


def _bucket(day, granularity):
    return day if granularity == "day" else day - timedelta(days=day.weekday())


def _phrase(name):
    return {"week": "this week", "month": "this month", "30d": "in the last 30 days", "all": "in all", "custom": "in these dates"}[name]


def _plural(n, word):
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def dashboard(filters, now=None):
    """Everything above the list, from the stored daily totals with the same filter as the list: totals and the change on the period before, the columns, who did what and by type.
    Keys: range (the window's name: week, month, 30d, all or custom), granularity, labels (ISO dates of the columns), series {all and each type: total, previous_total, values},
    types, summaries, plus (for the template, not the chart script) kpis, staff, more_staff, day_counts, total, empty."""
    p = period(filters, now)
    rows = _stored_by_day(filters, p.day_from, p.day_to)
    previous = _stored_totals(filters, p.prev_from, p.prev_to) if p.has_previous else None
    by_type, by_staff_type, by_day, by_bucket, stored = Counter(), defaultdict(Counter), Counter(), defaultdict(Counter), defaultdict(set)
    for group, label, day, n in rows:
        key = staff_key(label)
        by_type[group] += n
        by_staff_type[key][group] += n
        by_day[day] += n
        by_bucket[_bucket(day, p.granularity)][group] += n
        stored[key].add(label)
    total = sum(by_type.values())
    first = p.first_day or min(by_day, default=timezone.localdate())
    last = max(p.last_day or timezone.localdate(), first)
    buckets, cursor = [], _bucket(first, p.granularity)
    while cursor <= _bucket(last, p.granularity):
        buckets.append(cursor)
        cursor += timedelta(days=1 if p.granularity == "day" else 7)
    series = {"all": {"total": total, "previous_total": sum(previous.values()) if previous is not None else None, "values": [sum(by_bucket[b].values()) for b in buckets]}}
    for group, _label in GROUPS:
        series[group] = {"total": by_type[group], "previous_total": previous[group] if previous is not None else None, "values": [by_bucket[b][group] for b in buckets]}
    order = sorted(GROUPS, key=lambda g: (-by_type[g[0]], [x[0] for x in GROUPS].index(g[0])))  # busiest first, the rest in table order
    kpis = [{"key": "all", "label": "Actions", "hue": "slate", "anchor": "days"}] + [{"key": g, "label": label, "hue": HUES[g], "anchor": "list"} for g, label in order[:3]]
    types = [{"key": g, "label": label, "value": by_type[g], "share_bp": round(by_type[g] * 10000 / total) if total else 0, "hue": HUES[g], "icon": ICONS[g]} for g, label in GROUPS]
    people = _identities([label for labels in stored.values() for label in labels])
    ranked = sorted(by_staff_type.items(), key=lambda item: (-sum(item[1].values()), people[item[0]][1].lower()))
    top = sum(ranked[0][1].values()) if ranked else 0
    staff = []
    for key, counts in ranked:
        n = sum(counts.values())
        share, run, stops = n / top, 0, []
        for g, label in GROUPS:
            if counts[g]:
                a, b = run / n * share * 100, (run + counts[g]) / n * share * 100
                stops.append(f"var(--office-{HUES[g]}) {a:.2f}% {b:.2f}%")
                run += counts[g]
        staff.append({"key": key, "name": people[key][0], "full": people[key][1], "total": n, "share": f"{share:.4f}", "stack": f"linear-gradient(to right, {', '.join(stops)})",
                      "says": ", ".join(f"{counts[g]} {label.lower()}" for g, label in GROUPS if counts[g])})
    weekly = p.granularity == "week"
    busiest = max(range(len(buckets)), key=lambda i: series["all"]["values"][i], default=-1)
    if not total:
        summaries = {"days": "No staff actions in this range.", "staff": "No staff actions in this range.", "types": "No staff actions in this range."}
    else:
        peak = buckets[busiest]
        days_line = f"{_plural(total, 'action')} {_phrase(p.name)}. " + (f"Busiest week: w/c {dateformat.format(peak, 'j M')}, with {series['all']['values'][busiest]:,}." if weekly
                                                                         else f"Busiest day: {dateformat.format(peak, 'l')}, with {series['all']['values'][busiest]:,}.")
        lead = max(types, key=lambda t: t["value"])
        summaries = {"days": days_line, "staff": f"{staff[0]['name']} did the most: {staff[0]['total']:,} of {total:,}.",
                     "types": f"Most were {lead['label'].lower()}: {lead['value']:,} of {total:,}."}
    return {"range": p.name, "granularity": p.granularity, "labels": [b.isoformat() for b in buckets], "series": series, "types": types, "summaries": summaries,
            "kpis": kpis, "staff": staff[:MAX_STAFF_BARS], "more_staff": max(len(staff) - MAX_STAFF_BARS, 0), "day_counts": {d.isoformat(): n for d, n in by_day.items()},
            "total": total, "empty": not total, "peak": busiest, "days": [{"iso": b.isoformat(), "count": series["all"]["values"][i]} for i, b in enumerate(buckets)]}


def chart_data(data):
    """The part of `dashboard()` the chart script reads (no staff names, no per-day map)."""
    return {key: data[key] for key in ("range", "granularity", "labels", "series", "types", "summaries")}


# ---------- the list ----------

def _people(rows):
    """Name and link for the rows of one page: by account (verified), by lead address (his newest journey) or by Gold application. Three small queries at most."""
    emails = {r["email"] for r in rows if r["email"] and not r["user"] and not r["application"]}
    pids = {r["pid"] for r in rows if r["pid"]}
    accounts = {u.email: u for u in User.objects.filter(email__in=emails, email_verified_at__isnull=False)} if emails else {}
    by_pid = {u.public_id: u for u in User.objects.filter(public_id__in=pids)} if pids else {}
    leads = {}
    for s in (JourneySession.objects.filter(lead_email__in=emails - set(accounts), is_bot=False).order_by("created_at") if emails - set(accounts) else []):
        leads[s.lead_email.lower()] = s  # the newest wins
    for r in rows:
        user = r["user"] or accounts.get(r["email"]) or by_pid.get(r["pid"])
        if user is not None:
            r.update(name=user.get_full_name() or user.email, sub=user.email if user.get_full_name() else "", href=profile._href("office_person", user.pk))
        elif r["application"] is not None:
            a = r["application"]
            r.update(name=a.full_name or a.email, sub=a.email if a.full_name else "", href=profile._href("office_gold_application", a.pk))
        elif r["email"]:
            s = leads.get(r["email"])
            r.update(name=r["email"], sub="", href=profile._href("office_lead", s.pk) if s else "")
        else:
            r.update(name="", sub="", href="")  # a person who has been erased: the row stays, there is no one to name
    return rows


def day_heading(day, today):
    """Today, Yesterday, else Mon 9 Nov (with the year when it is not this one)."""
    if day == today:
        return "Today"
    if day == today - timedelta(days=1):
        return "Yesterday"
    return dateformat.format(day, "D j M" if day.year == today.year else "D j M Y")


def _day_counts(f, p, first, last):
    """Counts for days `first` to `last` (a caller that did not build the whole dashboard), from the stored totals."""
    first = max(first, p.day_from) if p.day_from else first
    last = min(last, p.day_to) if p.day_to else last
    counts = Counter()
    for _group, _label, day, n in _stored_by_day(f, first, last):
        counts[day.isoformat()] += n
    return counts


def page(filters, offset=0, size=PAGE_SIZE, now=None, day_counts=None, after_day="", title="Approach list"):
    """(rows of this page, has_more). The merged list is newest first by (at, source, pk), the order each source has in the database, so a page never repeats a row within one load. Numbered
    pages are an offset over the merge: each source gives its newest `offset + size + 1` rows, they are merged and the page is the slice `offset:offset + size` (the cost grows with
    the page, which is fine at this size; the caller keeps the page number inside the real page count). Rows are built for the slice only. Each row also
    has who (first name), staff (full label), time, day, sentence parts (before, after) and `heading` ({label, count}) on the first row of a day not already shown (`after_day`: the day just above)."""
    filters = {"range": "all", "from": None, "to": None, "staff": "", "group": "", **filters}
    p = period(filters, now)
    want, ctx = max(int(offset), 0) + size, {}
    merged = [hit for source in _sources(filters) for hit in _fetch(source, filters, p.start, p.end, want + 1)]
    merged.sort(key=lambda hit: hit[:3], reverse=True)
    chunk = merged[want - size:want]
    page_rows = []
    for at, index, pk, obj in chunk:
        source = SOURCES[index]
        row = source.row(obj, ctx)
        row.update(at=at, pk=pk, source=index, group=source.group)
        page_rows.append(row)
    rows = _people(page_rows)
    people = _identities([r["label"] for r in rows])
    today = timezone.localdate()
    for r in rows:
        who, full = people[staff_key(r["label"])]
        local = timezone.localtime(r["at"])
        before, after = WORDING.get(r["what"], ("", ""))
        known = r["what"] in WORDING
        r.update(who=who, staff=full, group_label=GROUP_LABELS[r["group"]], hue=HUES[r["group"]], icon=ICONS[r["group"]], day=local.date().isoformat(), time=dateformat.format(local, "H:i"),
                 before=before.replace("{title}", title.lower()) if known else f"· {r['what']} · ", after=after.replace("{title}", title.lower()))
    if rows and day_counts is None:
        days = [date.fromisoformat(r["day"]) for r in rows]
        day_counts = _day_counts(filters, p, min(days), max(days))
    shown = after_day
    for r in rows:
        if r["day"] != shown:
            shown = r["day"]
            r["heading"] = {"label": day_heading(date.fromisoformat(shown), today), "count": day_counts.get(shown, 0), "iso": shown}
        else:
            r["heading"] = None
    return rows, len(merged) > want
