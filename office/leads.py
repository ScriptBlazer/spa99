"""Leads: people who gave their email at the journey gate. One lead = one lower-cased address (docs/features/office-leads.md).
The list is one row per address, driven by that address's latest journey session; every query is DB-side with plain
Lower/Exists/Subquery (SQLite and Postgres alike), paged 25 at a time with one extra row fetched instead of a count.
Figures (tiles, totals, top answers) are NOT here: they live in the stored snapshots (office.selectors.lead_block/build_leads).
The short lists (hot leads, recent activity) are LIMIT reads."""
import csv
import logging
from datetime import datetime, time, timedelta

from django.db.models import Count, Exists, F, OuterRef, Q, Subquery
from django.db.models.functions import Lower
from django.http import HttpResponse
from django.utils import timezone

from gold.models import ApplicationEvent, GoldApplication
from insights import reader
from journey.models import JourneySession, Option
from users.models import InterestRegistration, User

from . import lists, profile

logger = logging.getLogger("spa99.office")

PAGE_SIZE = 25
SHOWS = ("lead", "registered", "all")
SORTS = ("last_seen", "first_seen", "potential", "visits")
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


def lead_queryset(show="lead", range_name="all", today=None):
    """One session per address (its latest), annotated with `has_account`, `has_application` and `journeys_n`. `show`:
    lead (no account, the default), registered (former leads who now have an account) or all. Staff addresses never appear
    (counting rule C2). `range_name` is by last seen (7d, 30d, 90d, all)."""
    newer = (_gate_sessions().filter(email_key=OuterRef("email_key"))
             .filter(Q(created_at__gt=OuterRef("created_at")) | Q(created_at=OuterRef("created_at"), id__gt=OuterRef("id"))))
    same = _gate_sessions().filter(email_key=OuterRef("email_key")).order_by().values("email_key").annotate(n=Count("id")).values("n")
    queryset = (_gate_sessions().filter(~Exists(newer)).filter(~Exists(_accounts(staff=True)))
                .annotate(has_account=Exists(_accounts()), has_application=Exists(_applications()), journeys_n=Subquery(same)))
    if show == "lead":
        queryset = queryset.filter(has_account=False)
    elif show == "registered":
        queryset = queryset.filter(has_account=True)
    start, _ = reader.range_dates(range_name if range_name in RANGES else "all", today)
    if start is not None:
        queryset = queryset.filter(last_seen_at__gte=timezone.make_aware(datetime.combine(start, time.min)))
    return queryset


def hot_leads_queryset():
    """High Gold potential, no account, no Gold application (declined or not: he has applied)."""
    return lead_queryset(show="lead").filter(gold_potential="high", has_application=False)


def filters_from(request):
    get = request.GET
    show, sort, range_name = get.get("show", "lead"), get.get("sort", "last_seen"), get.get("range", "30d")
    return {"q": get.get("q", "").strip(), "range": range_name if range_name in RANGES else "30d", "show": show if show in SHOWS else "lead",
            "tier": get.get("tier", ""), "potential": get.get("potential", "") if get.get("potential") in POTENTIALS else "",
            "industry": get.get("industry", ""), "gold": "yes" if get.get("gold") in ("yes", "1", "on") else "", "hot": "1" if get.get("hot") == "1" else "",
            "sort": sort if sort in SORTS else "last_seen"}


def is_filtered(filters):
    """True when anything narrows the list beyond the defaults. The page shows no count then (counting rule C5)."""
    return bool(filters["q"] or filters["tier"] or filters["potential"] or filters["industry"] or filters["gold"] or filters["hot"]
                or filters["show"] != "lead" or filters["range"] != "30d")


def filtered_queryset(filters):
    queryset = lead_queryset(filters["show"], filters["range"])
    for word in filters["q"].lower().split():
        queryset = queryset.filter(email_key__contains=word)
    if filters["tier"]:
        queryset = queryset.filter(suggested_plan__slug=filters["tier"])
    if filters["potential"]:
        queryset = queryset.filter(gold_potential=filters["potential"])
    if filters["industry"]:
        queryset = queryset.filter(answers__question__key="industry", answers__options__value=filters["industry"])
    if filters["gold"]:
        queryset = queryset.filter(has_application=True)
    if filters["hot"]:  # exactly the Hot leads count: High potential, no account, no Gold application
        queryset = queryset.filter(gold_potential="high", has_account=False, has_application=False)
    order = {"last_seen": [F("last_seen_at").desc()], "first_seen": [F("lead_at").desc(nulls_last=True)],
             "potential": [F("gold_score").desc(nulls_last=True), F("last_seen_at").desc()],
             "visits": [F("journeys_n").desc(nulls_last=True), F("last_seen_at").desc()]}[filters["sort"]]
    return queryset.order_by(*order, "-created_at", "-id")


def filter_choices():
    """Plans and industry options for the filter controls."""
    from plans.models import Plan

    return {"tiers": list(Plan.objects.filter(kind=Plan.MONTHLY).order_by("order").values("slug", "name")),
            "industries": list(Option.objects.filter(question__key="industry", active=True).order_by("order").values("value", "label"))}


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
    firsts = {}
    for key, referrer, utm, medium, campaign, device in (_gate_sessions().filter(email_key__in=emails).order_by("-created_at")
                                                         .values_list("email_key", "referrer", "utm_source", "utm_medium", "utm_campaign", "device_type")):
        firsts[key] = (referrer, utm, medium, campaign, device)  # oldest wins: iterated newest first
    out = []
    for page_row in page_sessions:
        session = loaded[page_row.pk]
        labels = profile.answer_labels(session)
        referrer, utm, medium, campaign, device = firsts.get(page_row.email_key, ("", "", "", "", ""))
        host = profile.referrer_host(referrer)
        out.append({
            "id": str(session.pk), "email": page_row.email_key, "first_seen": lists_iso(session.lead_at or session.created_at),
            "last_seen": lists_iso(session.last_seen_at), "journeys": page_row.journeys_n or 1, "finished": session.completed,
            "tier": session.suggested_plan.name if session.suggested_plan_id else "", "tier_slug": session.suggested_plan.slug if session.suggested_plan_id else "",
            "potential": session.gold_potential, "score": session.gold_score, "industries": labels.get("industry", []),
            "answers": labels, "summary": summary_lines(labels),
            "source": {"host": host, "utm_source": utm, "utm_medium": medium, "utm_campaign": campaign, "device": device,
                       "label": utm or host or "Direct", "campaign": campaign},
            "registered": page_row.has_account, "account_id": str(accounts[page_row.email_key]) if page_row.email_key in accounts else "",
            "gold_applied": page_row.has_application, "status": status_of(page_row.has_account, statuses.get(page_row.email_key, [])),
            "href": _url("office_lead", session.pk),
        })
    return out


def lists_iso(value):
    return value.isoformat() if value else ""


def page(filters, number):
    """(rows, has_next) for one page, DB-side."""
    start = (number - 1) * PAGE_SIZE
    found = list(filtered_queryset(filters)[start:start + PAGE_SIZE + 1])
    return build_rows(found[:PAGE_SIZE]), len(found) > PAGE_SIZE


def hot_leads(limit=5):
    """The short Hot leads list (newest first): LIMIT read, one query."""
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
    writer.writerow(["email", "status", "first_seen", "last_seen", "journeys", "suggested_tier", "gold_potential", "gold_score", "industries",
                     "when", "how_often", "facilities", "company", "source", "campaign", "device", "applied_for_gold",
                     "consent_given_at", "consent_privacy_version"])
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
                row["email"], row["status"], row["first_seen"], row["last_seen"], row["journeys"], row["tier"], row["potential"], row["score"] or "",
                "; ".join(row["industries"]), "; ".join(a.get("time", [])), "; ".join(a.get("frequency", [])), "; ".join(a.get("facilities", [])),
                "; ".join(a.get("company", [])), row["source"]["label"], row["source"]["campaign"], row["source"]["device"],
                "yes" if row["gold_applied"] else "no", lists_iso(s.lead_at), s.lead_privacy_version)])
    return response


# ---------- recent activity (the latest events across people) ----------

def _who(user=None, email=""):
    if user is not None:
        first = (user.first_name or "").strip()
        last = (user.last_name or "").strip()
        return f"{first} {last[:1]}." if first and last else (first or user.email)
    return email or "A visitor"


def activity(limit=10):
    """The latest `limit` events: email given, registered, verified, journey finished, Gold applied, Gold decided. Six LIMIT
    reads over the existing timestamps, merged: [{kind, at, who, label, detail, href}] newest first."""
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


TIMELINE_PAGE = 20


def timeline_page(timeline, number):
    """A page of the timeline (newest first, 20 events), grouped by day: ([{day, items}], has_more)."""
    start = (number - 1) * TIMELINE_PAGE
    chunk = timeline[start:start + TIMELINE_PAGE]
    days = []
    for item in chunk:
        day = timezone.localtime(datetime.fromisoformat(item["at"])).date().isoformat() if item["at"] else ""
        if not days or days[-1]["day"] != day:
            days.append({"day": day, "items": []})
        days[-1]["items"].append(item)
    return days, len(timeline) > start + TIMELINE_PAGE
