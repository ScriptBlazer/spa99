"""Leads: people who gave their email at the journey gate. One lead = one lower-cased address (docs/features/office-leads.md).
The list is one row per address, driven by that address's latest journey session; every query is DB-side with plain
Lower/Exists/Subquery (SQLite and Postgres alike), paged 25 at a time with one extra row fetched instead of a count.
Figures (tiles, totals, top answers) are NOT here: they live in the stored snapshots (office.selectors.lead_block/build_leads).
The short lists (hot leads, recent activity) are LIMIT reads."""
import csv
import logging
from datetime import datetime, time, timedelta

from django.db.models import Case, Count, Exists, F, IntegerField, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Lower
from django.http import HttpResponse
from django.utils import timezone

from common import sorting
from common.sorting import Column
from gold.models import ApplicationEvent, GoldApplication
from insights import reader
from journey.models import JourneySession, Option
from mailings.models import EmailOptOut
from outreach.models import ArchivedLead
from users.models import InterestRegistration, User

from system import defaults

from . import lists, profile

logger = logging.getLogger("spa99.office")

# The sortable headers (R1). Keys are also the System default `leads_sort` values (last_seen, first_seen, potential, visits).
# Source, Wants, Industry and Heard via are built from several values (or from the address's first journey, not this row's), so
# they are plain headers.
COLUMNS = [
    Column("email", "Lead", "email_key"),
    Column("wants", "Wants"),
    Column("best_fit", "Best fit", ("suggested_plan__order", "suggested_plan__name")),
    Column("potential", "Potential", "gold_score", first=sorting.DESC),
    Column("industry", "Industry", css="o-wide-xl"),
    Column("source", "Source"),
    Column("heard_via", "Heard via", css="o-wide-xl"),
    Column("visits", "Visits", "journeys_n", first=sorting.DESC, css="num o-wide-xl"),
    Column("status", "Status", "status_rank", first=sorting.DESC),
    Column("last_seen", "Last seen", "last_seen_at", first=sorting.DESC, css="num"),
    Column("first_seen", "First seen", "lead_at", first=sorting.DESC, hidden=True),
]
ARCHIVED_COLUMN = Column("archived", "Archived", "archived_at", first=sorting.DESC, css="num")
SORTS = tuple(c.key for c in COLUMNS if c.sortable)
VIEWS = ("", "archived")
TIEBREAK = ("-last_seen_at", "-created_at", "-id")
RANGES = ("7d", "30d", "90d", "all")
POTENTIALS = ("high", "medium", "low")
CSV_CHUNK = 200
OPEN_GOLD = (GoldApplication.NEW, GoldApplication.CONTACTED, GoldApplication.AWAITING_FINAL)


def _url(name, *args):
    """A link into the Office (its own URL configuration, whichever host the code runs under)."""
    from django.urls import reverse

    return reverse(name, args=args, urlconf="config.urls_office")


# ---------- the queries ----------

def _gate_sessions():
    """Every non-bot session that left an address, with its lower-cased address as `email_key`."""
    return JourneySession.objects.filter(is_bot=False).exclude(lead_email="").annotate(email_key=Lower("lead_email"))


def _accounts(staff=None):
    users = User.objects.annotate(account_key=Lower("email")).filter(account_key=OuterRef("email_key"))
    # staff addresses are never leads; any other account takes the lead over only once its address is verified (an
    # unverified account may carry someone else's address)
    return users.filter(is_staff=True) if staff else users.filter(email_verified_at__isnull=False)


def _applications():
    return GoldApplication.objects.annotate(application_key=Lower("email")).filter(application_key=OuterRef("email_key"))


def _chats_with_email():
    """Real (not staff test) conversations whose lead_email matches the row's address, any case."""
    from chat.models import Conversation

    return Conversation.objects.filter(staff_test=False).exclude(lead_email="").annotate(chat_key=Lower("lead_email")).filter(chat_key=OuterRef("email_key"))


def _heard_answers():
    from journey.models import Answer

    return (Answer.objects.filter(question__key="heard_via", skipped=False, options__isnull=False, session__is_bot=False)
            .exclude(session__lead_email="").annotate(ak=Lower("session__lead_email")))


def _newer_heard():
    """A later journey of the same address that also answered heard_via (so the older answer is no longer his)."""
    return _heard_answers().filter(ak=OuterRef("ak"), session__created_at__gt=OuterRef("session__created_at"))


def _archived():
    """The archive row of the address (ArchivedLead.email is lower case, like email_key)."""
    return ArchivedLead.objects.filter(email=OuterRef("email_key"))


def lead_queryset(range_name="all", today=None, archived=False):
    """One session per address (its latest), annotated with `has_account`, `has_application` and `journeys_n`. Only addresses
    with NO account: a registered person is not a lead (they are in People). Staff addresses never appear either (counting
    rule C2). `range_name` is by last seen (7d, 30d, 90d, all). Archived addresses are left out (they are in the Archived view:
    `archived=True` lists only them); everything that counts leads (list, CSV, tiles, hot leads, snapshots) goes through here."""
    newer = (_gate_sessions().filter(email_key=OuterRef("email_key"))
             .filter(Q(created_at__gt=OuterRef("created_at")) | Q(created_at=OuterRef("created_at"), id__gt=OuterRef("id"))))
    same = _gate_sessions().filter(email_key=OuterRef("email_key")).order_by().values("email_key").annotate(n=Count("id")).values("n")
    queryset = (_gate_sessions().filter(~Exists(newer)).filter(~Exists(_accounts(staff=True)))
                .annotate(has_account=Exists(_accounts()), has_application=Exists(_applications()), journeys_n=Subquery(same))
                .filter(has_account=False).filter(Exists(_archived()) if archived else ~Exists(_archived())))
    start, _ = reader.range_dates(range_name if range_name in RANGES else "all", today)
    if start is not None:
        queryset = queryset.filter(last_seen_at__gte=timezone.make_aware(datetime.combine(start, time.min)))
    return queryset


def hot_leads_queryset():
    """High Gold potential, no account, no Gold application (declined or not: he has applied)."""
    return lead_queryset().filter(gold_potential="high", has_application=False)


def filters_from(request):
    """The list's filters from the request. `sort` is always a valid key (the System default when none asked), `dir` its direction
    (default descending), `view` is "" or "archived"."""
    get, d = request.GET, defaults.get(request)
    range_name = get.get("range", d.leads_range)
    view = "archived" if get.get("view") == "archived" else ""
    default_key = "archived" if view else (d.leads_sort if d.leads_sort in SORTS else "last_seen")   # the archive reads newest put away first
    sort, direction, _ = sorting.resolve(_columns(view), get, default_key, sorting.DESC)
    return {"q": get.get("q", "").strip(), "range": range_name if range_name in RANGES else d.leads_range, "tier": get.get("tier", ""), "potential": get.get("potential", "") if get.get("potential") in POTENTIALS else "",
            "industry": get.get("industry", ""), "heard": get.get("heard", ""), "chat": "1" if get.get("chat") == "1" else "", "gold": "yes" if get.get("gold") in ("yes", "1", "on") else "", "hot": "1" if get.get("hot") == "1" else "",
            "view": view, "sort": sort, "dir": direction}


def _columns(view):
    return COLUMNS + ([ARCHIVED_COLUMN] if view == "archived" else [])


def columns_for(filters, request):
    """The `columns` context for the table header (see common.sorting): one dict per column with key, label, sortable, active, dir,
    aria_sort and url. The Archived view adds an Archived column."""
    return sorting.header_columns(_columns(filters["view"]), filters["sort"], filters["dir"], request.path, request.GET)


def is_filtered(filters, request=None):
    """True when anything narrows the list beyond the defaults (System > Defaults). The page shows no count then (counting rule C5).
    Reads the same values as filters_from."""
    d = defaults.get(request)
    return bool(filters["q"] or filters["tier"] or filters["potential"] or filters["industry"] or filters["heard"] or filters["chat"] or filters["gold"] or filters["hot"]
                or filters.get("view") or filters["range"] != d.leads_range)


def _status_rank():
    """0 lead, 1 applied (an open Gold application), 2 gold (an approved one): the order of the Status column."""
    return Case(When(Exists(_applications().filter(status=GoldApplication.APPROVED)), then=Value(2)),
                When(Exists(_applications().filter(status__in=OPEN_GOLD)), then=Value(1)), default=Value(0), output_field=IntegerField())


def filtered_queryset(filters):
    archived = filters.get("view") == "archived"
    columns = _columns(filters.get("view", ""))
    queryset = lead_queryset("all" if archived else filters["range"], archived=archived)  # the archive is everyone put away, whenever last seen
    if archived:
        queryset = queryset.annotate(archived_at=Subquery(_archived().values("archived_at")[:1]))
    if filters.get("sort") == "status":
        queryset = queryset.annotate(status_rank=_status_rank())
    queryset = queryset.annotate(name_key=Lower("lead_first_name")) if filters["q"] else queryset
    for word in filters["q"].lower().split():  # each word is part of the address, the first name or the mobile (digits, a leading 0 ignored)
        digits = "".join(ch for ch in word if ch.isdigit()).lstrip("0")
        match = Q(email_key__contains=word) | Q(name_key__contains=word)
        queryset = queryset.filter(match | (Q(lead_mobile__contains=digits) if len(digits) >= 3 else Q(pk__in=[])))
    if filters["tier"]:
        queryset = queryset.filter(suggested_plan__slug=filters["tier"])
    if filters["potential"]:
        queryset = queryset.filter(gold_potential=filters["potential"])
    if filters["industry"]:
        queryset = queryset.filter(answers__question__key="industry", answers__options__value=filters["industry"])
    if filters["heard"]:  # "How did you hear about us?" (journey answer heard_via), the newest journey of that address that answered it
        queryset = queryset.filter(Exists(_heard_answers().filter(ak=OuterRef("email_key"), options__value=filters["heard"]).filter(~Exists(_newer_heard()))))
    if filters["chat"]:  # the address was given to the assistant in a chat (Conversation.lead_email)
        queryset = queryset.filter(Exists(_chats_with_email()))
    if filters["gold"]:
        queryset = queryset.filter(has_application=True)
    if filters["hot"]:  # exactly the Hot leads count: High potential, no account, no Gold application
        queryset = queryset.filter(gold_potential="high", has_application=False)
    key = filters.get("sort") if filters.get("sort") in {c.key for c in columns if c.sortable} else "last_seen"
    return queryset.order_by(*sorting.order_by(columns, key, filters.get("dir") or sorting.DESC, TIEBREAK))


def filter_choices():
    """Plans and industry options for the filter controls."""
    from plans.models import Plan

    return {"tiers": list(Plan.objects.filter(kind=Plan.MONTHLY).order_by("order").values("slug", "name")),
            "industries": list(Option.objects.filter(question__key="industry", active=True).order_by("order").values("value", "label")),
            "heard": list(Option.objects.filter(question__key="heard_via", active=True).order_by("order").values("value", "label"))}


# ---------- rows ----------

def status_of(has_account, applications):
    """The furthest he has gone: gold (an approved application), applied (an open one), registered, lead."""
    if GoldApplication.APPROVED in applications:
        return "gold"
    if any(s in OPEN_GOLD for s in applications):
        return "applied"
    return "registered" if has_account else "lead"


def summary_lines(answers):
    """The two short lines of key answers, from {question key: [labels]} (time and frequency; facilities and company)."""
    def short(labels):
        return ", ".join(labels)

    first = " · ".join(short(answers[k]) for k in ("time", "frequency") if k in answers)
    shown = answers.get("facilities", [])
    second = short(shown[:3]) + (f" +{len(shown) - 3}" if len(shown) > 3 else "") if shown else ""
    second = " · ".join(x for x in (second, short(answers["company"]) if "company" in answers else "") if x)
    return [first, second] if (first or second) else ["No answers yet"]


def build_rows(page_sessions):
    """Rows (dicts) in the order of `page_sessions`, using the annotations of `lead_queryset`."""
    loaded = {s.pk: s for s in profile.sessions_with_answers(JourneySession.objects.filter(pk__in=[s.pk for s in page_sessions]))}
    emails = [s.email_key for s in page_sessions]
    statuses = {}
    for key, status in GoldApplication.objects.annotate(k=Lower("email")).filter(k__in=emails).values_list("k", "status"):
        statuses.setdefault(key, []).append(status)
    accounts = dict(User.objects.filter(email_verified_at__isnull=False).annotate(k=Lower("email")).filter(k__in=emails).values_list("k", "pk"))
    unsubscribed = set(EmailOptOut.objects.filter(email__in=emails).values_list("email", flat=True))
    unsubscribed |= set(User.objects.filter(marketing_consent=False).annotate(k=Lower("email")).filter(k__in=emails).values_list("k", flat=True))  # an account that turned news off
    firsts = {}
    for key, referrer, utm, medium, campaign, device in (_gate_sessions().filter(email_key__in=emails).order_by("-created_at")
                                                         .values_list("email_key", "referrer", "utm_source", "utm_medium", "utm_campaign", "device_type")):
        firsts[key] = (referrer, utm, medium, campaign, device)  # oldest wins: iterated newest first
    from chat.models import Conversation

    chatted = {k for k in Conversation.objects.filter(staff_test=False).annotate(k=Lower("lead_email")).filter(k__in=emails).values_list("k", flat=True)}
    heard = {}
    for key, label in _heard_answers().filter(ak__in=emails).order_by("session__created_at").values_list("ak", "options__label"):
        heard[key] = label  # the newest answering journey wins
    archived = {a.email: a for a in ArchivedLead.objects.filter(email__in=emails)}
    from outreach.services import bounced_set

    bounced = bounced_set(emails)  # Possible fake: a permanent bounce on the suppression list (one query for the page)
    out = []
    for page_row in page_sessions:
        session = loaded[page_row.pk]
        put_away = archived.get(page_row.email_key)
        labels = profile.answer_labels(session)
        referrer, utm, medium, campaign, device = firsts.get(page_row.email_key, ("", "", "", "", ""))
        host = profile.referrer_host(referrer)
        out.append({
            "id": str(session.pk), "email": page_row.email_key, "name": session.lead_first_name, "mobile": session.lead_mobile, "first_seen": lists_iso(session.lead_at or session.created_at),
            "last_seen": lists_iso(session.last_seen_at), "journeys": page_row.journeys_n or 1, "finished": session.completed,
            "tier": session.suggested_plan.name if session.suggested_plan_id else "", "tier_slug": session.suggested_plan.slug if session.suggested_plan_id else "",
            "potential": session.gold_potential, "score": session.gold_score, "industries": labels.get("industry", []),
            "answers": labels, "summary": summary_lines(labels), "heard_via": heard.get(page_row.email_key, ""),
            "via_chat": page_row.email_key in chatted, "bounced": page_row.email_key in bounced,
            "source": {"host": host, "utm_source": utm, "utm_medium": medium, "utm_campaign": campaign, "device": device,
                       "label": utm or host or "Direct", "campaign": campaign},
            "registered": page_row.has_account, "account_id": str(accounts[page_row.email_key]) if page_row.email_key in accounts else "",
            "gold_applied": page_row.has_application, "status": status_of(page_row.has_account, statuses.get(page_row.email_key, [])),
            "href": _url("office_lead", session.pk), "unsubscribed": page_row.email_key in unsubscribed,
            "archived": {"at": lists_iso(put_away.archived_at), "by": put_away.archived_by_label, "reason": put_away.reason} if put_away else None,
            "archive_url": _url("office_lead_archive", session.pk), "unarchive_url": _url("office_lead_unarchive", session.pk),
        })
    return out


def lists_iso(value):
    return value.isoformat() if value else ""


def page(filters, number, size=None):
    """(rows, has_next) for one page, DB-side. `size` defaults to System > Defaults > Leads rows per page."""
    size = size or defaults.get().leads_page_size
    start = (number - 1) * size
    found = list(filtered_queryset(filters)[start:start + size + 1])
    return build_rows(found[:size]), len(found) > size


def hot_leads(limit=None):
    """The short Hot leads list (newest first): LIMIT read, one query. Default length: System > Defaults."""
    limit = limit or defaults.get().dashboard_hot_leads
    found = hot_leads_queryset().select_related("suggested_plan").order_by("-lead_at", "-id")[:limit]
    return [{"id": str(s.pk), "email": s.email_key, "tier": s.suggested_plan.name if s.suggested_plan_id else "", "potential": s.gold_potential,
             "score": s.gold_score, "last_seen": lists_iso(s.last_seen_at), "first_seen": lists_iso(s.lead_at or s.created_at),
             "href": _url("office_lead", s.pk)} for s in found]


# ---------- CSV ----------

def csv_response(filters, user_id=None):
    """Every filtered row, answers as separate columns, consent version and timestamps. Admin and up (the view guards it)."""
    logger.info("Leads CSV exported by account %s", user_id)  # who and when; never the addresses
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="spa99-leads.csv"'
    writer = csv.writer(response)
    writer.writerow(["email", "first_name", "mobile", "status", "first_seen", "last_seen", "journeys", "best_fit", "gold_potential", "gold_score", "industries",
                     "when", "how_often", "facilities", "company", "heard_via", "gave_email_in_chat", "source", "campaign", "device", "applied_for_gold",
                     "consent_given_at", "consent_privacy_version", "consent_wording_version"])
    queryset = filtered_queryset(filters)
    offset = 0
    while True:
        chunk = list(queryset[offset:offset + CSV_CHUNK])
        if not chunk:
            break
        offset += CSV_CHUNK
        consent = {s.email_key: s for s in chunk}
        for row in build_rows(chunk):
            a, s = row["answers"], consent[row["email"]]
            writer.writerow([lists.safe_cell(x) for x in (
                row["email"], row["name"], row["mobile"], row["status"], row["first_seen"], row["last_seen"], row["journeys"], row["tier"], row["potential"], row["score"] or "",
                "; ".join(row["industries"]), "; ".join(a.get("time", [])), "; ".join(a.get("frequency", [])), "; ".join(a.get("facilities", [])),
                "; ".join(a.get("company", [])), row["heard_via"], "yes" if row["via_chat"] else "no", row["source"]["label"], row["source"]["campaign"], row["source"]["device"],
                "yes" if row["gold_applied"] else "no", lists_iso(s.lead_at), s.lead_privacy_version, s.lead_consent_version)])
    return response


# ---------- recent activity (the latest events across people) ----------

def _who(user=None, email=""):
    if user is not None:
        first = (user.first_name or "").strip()
        last = (user.last_name or "").strip()
        return f"{first} {last[:1]}." if first and last else (first or user.email)
    return email or "A visitor"


def activity(limit=None):
    """The latest `limit` events: email given, registered, verified, journey finished, Gold applied, Gold decided. Six LIMIT
    reads over the existing timestamps, merged: [{kind, at, who, label, detail, href}] newest first."""
    limit = limit or defaults.get().dashboard_activity
    out = []

    def add(at, kind, who, label, detail="", href=""):
        out.append({"at": at, "kind": kind, "who": who, "label": label, "detail": detail, "href": href})

    seen = set()
    sessions = (_gate_sessions().filter(lead_at__isnull=False).filter(~Exists(_accounts(staff=True)))
                .filter(Q(user__isnull=True) | Q(user__is_staff=False)).select_related("suggested_plan").order_by("-lead_at")[:limit * 2])
    for s in sessions:
        if (s.lead_email.lower(), s.lead_at) in seen:  # a restart copies the address and time
            continue
        seen.add((s.lead_email.lower(), s.lead_at))
        add(s.lead_at, "lead", s.lead_email.lower(), "gave his email", f"Suggested {s.suggested_plan.name}" if s.suggested_plan_id else "",
            _url("office_lead", s.pk))
    for i in InterestRegistration.objects.filter(user__is_staff=False).select_related("user", "plan").order_by("-created_at")[:limit]:
        add(i.created_at, "registered", _who(i.user), "registered", i.plan.name if i.plan_id else "", _url("office_person", i.user_id))
    for u in User.objects.filter(email_verified_at__isnull=False, is_staff=False, interest__isnull=False).order_by("-email_verified_at")[:limit]:
        add(u.email_verified_at, "verified", _who(u), "confirmed his email", "", _url("office_person", u.pk))
    for s in (JourneySession.objects.filter(is_bot=False, completed=True, completed_at__isnull=False).filter(Q(user__isnull=True) | Q(user__is_staff=False))
              .select_related("user", "suggested_plan").order_by("-completed_at")[:limit]):
        href = _url("office_person", s.user_id) if s.user_id else (_url("office_lead", s.pk) if s.lead_email else "")
        add(s.completed_at, "journey_finished", _who(s.user, s.lead_email.lower()), "finished the journey",
            f"Suggested {s.suggested_plan.name}" if s.suggested_plan_id else "", href)
    for a in GoldApplication.objects.order_by("-created_at")[:limit]:
        add(a.created_at, "gold_applied", a.full_name, "applied for Gold", f"{a.potential_level.title()} potential" if a.potential_level else "",
            _url("office_gold_application", a.pk))
    decided = {ApplicationEvent.APPROVED: "was approved for Gold", ApplicationEvent.FINAL_CONFIRMED: "was approved for Gold", ApplicationEvent.DECLINED: "was declined for Gold"}
    for e in ApplicationEvent.objects.filter(action__in=list(decided)).select_related("application").order_by("-at")[:limit]:
        add(e.at, "gold_decided", e.application.full_name, decided[e.action], f"by {e.actor_label}" if e.actor_label else "",
            _url("office_gold_application", e.application_id))
    out.sort(key=lambda e: e["at"], reverse=True)
    out = out[:limit]
    for e in out:
        e["at"] = e["at"].isoformat()
    return out


# ---------- one lead ----------

def lead_for(session):
    """The lead profile for any of his sessions, or ('account', user) when the address has an account now (the page
    redirects), or None. Staff addresses are never leads."""
    email = (session.lead_email or "").strip().lower()
    if not email or session.is_bot:
        return None
    account = User.objects.filter(email__iexact=email, email_verified_at__isnull=False).first()
    if account is not None:
        return "account", account
    return "lead", profile.lead_profile(email, session.pk)


def timeline_page(timeline, number, size=None):
    """A page of the timeline (newest first; System > Defaults > events per page), grouped by day: ([{day, items}], has_more)."""
    size = size or defaults.get().timeline_page_size
    start = (number - 1) * size
    chunk = timeline[start:start + size]
    days = []
    for item in chunk:
        day = timezone.localtime(datetime.fromisoformat(item["at"])).date().isoformat() if item["at"] else ""
        if not days or days[-1]["day"] != day:
            days.append({"day": day, "items": []})
        days[-1]["items"].append(item)
    return days, len(timeline) > start + size
