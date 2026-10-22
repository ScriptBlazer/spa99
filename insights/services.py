"""Read-only statistics for the Control dashboard. Live queries on saved answers; no third-party analytics.
Every function takes the session queryset from `sessions()` so all cards share the same filters.
Sessions flagged as bots are always excluded."""
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Count, F, Q
from django.db.models.functions import TruncDate

from gold.models import GoldApplication, GoldRule
from journey.models import Answer, JourneySession, Option, Question
from plans.models import Plan
from plans.services import price_inc_vat
from users.models import InterestRegistration

TIME_QUESTION, FREQUENCY_QUESTION = "time", "frequency"


# ---------- filters ----------

def parse_range(date_from=None, date_to=None):
    """(start, end) aware datetimes, end exclusive. Dates are London calendar days; either may be None."""
    zone = ZoneInfo(settings.TIME_ZONE)
    start = datetime.combine(date_from, time.min, tzinfo=zone) if date_from else None
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=zone) if date_to else None
    return start, end


def sessions(start=None, end=None, source=None, completed=None):
    """Non-bot journey sessions in the range. `completed` True/False filters finished vs unfinished."""
    qs = JourneySession.objects.filter(is_bot=False)
    if start:
        qs = qs.filter(created_at__gte=start)
    if end:
        qs = qs.filter(created_at__lt=end)
    if source:
        qs = qs.filter(Q(utm_source__iexact=source) | Q(referrer__icontains=source))
    if completed is not None:
        qs = qs.filter(completed=completed)
    return qs


def _in_range(qs, start, end, field="created_at"):
    if start:
        qs = qs.filter(**{f"{field}__gte": start})
    if end:
        qs = qs.filter(**{f"{field}__lt": end})
    return qs


# ---------- helpers ----------

def _option_counts(session_qs, question_key):
    """[{'value','label','count','percent'}] for one question, in option order. Percent is of sessions that answered."""
    answered = Answer.objects.filter(session__in=session_qs, question__key=question_key, skipped=False)
    base = answered.count()
    counts = {
        row["options__value"]: row["n"]
        for row in answered.filter(options__isnull=False).values("options__value").annotate(n=Count("pk"))
    }
    options = Option.objects.filter(question__key=question_key).order_by("order", "value")
    result = []
    for option in options:
        n = counts.get(option.value, 0)
        if n or option.active:
            result.append({
                "value": option.value, "label": option.label, "count": n,
                "percent": round(100 * n / base, 1) if base else 0.0,
            })
    return {"answered": base, "options": result}


def _values_by_session(session_qs, question_key):
    """{session id: [option values]} for one question."""
    rows = Answer.objects.filter(
        session__in=session_qs, question__key=question_key, skipped=False, options__isnull=False
    ).values_list("session_id", "options__value")
    found = defaultdict(list)
    for session_id, value in rows:
        found[session_id].append(value)
    return found


# ---------- cards ----------

def funnel(session_qs):
    """Started -> reached each screen -> result -> registered / applied for Gold, with drop-off per screen."""
    started = session_qs.count()
    screens = sorted(set(Question.objects.filter(active=True).values_list("screen", flat=True)))
    steps, previous = [], started
    for number in screens:
        reached = session_qs.filter(furthest_step__gte=number).count()
        steps.append({"screen": number, "reached": reached, "drop_off": previous - reached})
        previous = reached
    result = session_qs.filter(completed=True).count()
    return {
        "started": started,
        "steps": steps,
        "result": result,
        "result_drop_off": previous - result,
        "registered": session_qs.filter(Q(user__isnull=False) | Q(registrations__isnull=False)).distinct().count(),
        "gold": session_qs.filter(gold_applications__isnull=False).distinct().count(),
    }


def demand_by_time(session_qs):
    """Time band x frequency counts, and expected visits a week per band (frequency weight shared between the
    bands a person picked). Weights come from Option.weight, editable in Control."""
    times = _values_by_session(session_qs, TIME_QUESTION)
    freqs = _values_by_session(session_qs, FREQUENCY_QUESTION)
    freq_options = list(Option.objects.filter(question__key=FREQUENCY_QUESTION).order_by("order"))
    weights = {o.value: (o.weight or Decimal("0")) for o in freq_options}
    bands = []
    for band in Option.objects.filter(question__key=TIME_QUESTION).order_by("order", "value"):
        by_frequency, expected = Counter(), Decimal("0")
        for session_id, picked in times.items():
            if band.value not in picked:
                continue
            freq = (freqs.get(session_id) or [None])[0]
            if freq is None:
                continue
            by_frequency[freq] += 1
            expected += weights.get(freq, Decimal("0")) / len(picked)
        bands.append({
            "value": band.value, "label": band.label, "sessions": sum(1 for p in times.values() if band.value in p),
            "by_frequency": {o.value: by_frequency.get(o.value, 0) for o in freq_options},
            "expected_weekly_visits": float(round(expected, 2)),
        })
    return {"bands": bands, "frequencies": [{"value": o.value, "label": o.label} for o in freq_options]}


def facilities(session_qs):
    return _option_counts(session_qs, "facilities")


def company(session_qs):
    return _option_counts(session_qs, "company")


def tier_mix(session_qs, start=None, end=None):
    """Suggested vs chosen plans, how often people choose differently, and monthly revenue from current prices."""
    plans = list(Plan.objects.filter(kind=Plan.MONTHLY).order_by("order"))
    suggested = Counter(session_qs.filter(completed=True, suggested_plan__isnull=False).values_list("suggested_plan__slug", flat=True))
    registrations = _in_range(InterestRegistration.objects.filter(plan__isnull=False), start, end)
    chosen = Counter(registrations.values_list("plan__slug", flat=True))
    comparable = registrations.filter(journey_session__suggested_plan__isnull=False)
    total_comparable = comparable.count()
    agreed = comparable.filter(plan=F("journey_session__suggested_plan")).count()

    def revenue(counter):
        ex = sum((Decimal(counter.get(p.slug, 0)) * p.price_ex_vat for p in plans), Decimal("0"))
        inc = sum((Decimal(counter.get(p.slug, 0)) * price_inc_vat(p.price_ex_vat) for p in plans), Decimal("0"))
        return {"ex_vat": str(ex), "inc_vat": str(inc)}

    return {
        "plans": [
            {"slug": p.slug, "name": p.name, "price_ex_vat": str(p.price_ex_vat),
             "suggested": suggested.get(p.slug, 0), "chosen": chosen.get(p.slug, 0)}
            for p in plans
        ],
        "chose_differently": {
            "compared": total_comparable, "different": total_comparable - agreed,
            "percent": round(100 * (total_comparable - agreed) / total_comparable, 1) if total_comparable else 0.0,
        },
        "projected_monthly_revenue_chosen": revenue(chosen),
        "projected_monthly_revenue_suggested": revenue(suggested),
    }


def industries(session_qs):
    """Industry breakdown, property share (editable via GoldRule.is_property) and Gold potential spread."""
    industry = _option_counts(session_qs, "industry")
    industry_by_session = _values_by_session(session_qs, "industry")
    link_by_session = _values_by_session(session_qs, "property_link")
    law_by_session = _values_by_session(session_qs, "property_law")
    property_values = set(
        GoldRule.objects.filter(group=GoldRule.PROPERTY_LINK, is_property=True, active=True).values_list("match_value", flat=True)
    )
    property_sessions = 0
    for session_id, picked in industry_by_session.items():
        links = set(link_by_session.get(session_id, []))
        is_property = (
            bool(links & property_values)
            or ("property" in picked and not links)
            or ("law" in picked and "yes" in law_by_session.get(session_id, []))
        )
        property_sessions += is_property
    answered = industry["answered"]
    spread = Counter(session_qs.filter(completed=True).exclude(gold_potential="").values_list("gold_potential", flat=True))
    return {
        "industries": industry["options"],
        "answered": answered,
        "property_sessions": property_sessions,
        "property_percent": round(100 * property_sessions / answered, 1) if answered else 0.0,
        "gold_potential": {level: spread.get(level, 0) for level in ("high", "medium", "low")},
    }


def sources(session_qs):
    hosts = Counter()
    for referrer in session_qs.exclude(referrer="").values_list("referrer", flat=True):
        host = urlparse(referrer if "//" in referrer else f"//{referrer}").hostname
        if host:
            hosts[host.lower()] += 1
    utm = Counter(session_qs.exclude(utm_source="").values_list("utm_source", flat=True))
    return {
        "heard_via": _option_counts(session_qs, "heard_via")["options"],
        "referrers": [{"host": h, "count": n} for h, n in hosts.most_common(10)],
        "utm_sources": [{"source": s, "count": n} for s, n in utm.most_common(10)],
    }


def trend(start=None, end=None):
    """Registrations and Gold applications per London day."""
    def per_day(qs):
        rows = _in_range(qs, start, end).annotate(day=TruncDate("created_at")).values("day").annotate(n=Count("pk"))
        return {row["day"]: row["n"] for row in rows}

    registrations = per_day(InterestRegistration.objects.all())
    gold = per_day(GoldApplication.objects.all())
    return [
        {"date": day.isoformat(), "registrations": registrations.get(day, 0), "gold": gold.get(day, 0)}
        for day in sorted(set(registrations) | set(gold))
    ]


def summary(date_from=None, date_to=None, source=None, completed=None):
    """All cards in one dict (the dashboard endpoint)."""
    start, end = parse_range(date_from, date_to)
    qs = sessions(start, end, source=source, completed=completed)
    return {
        "range": {"from": date_from.isoformat() if date_from else None, "to": date_to.isoformat() if date_to else None},
        "funnel": funnel(qs),
        "demand": demand_by_time(qs),
        "facilities": facilities(qs),
        "tier_mix": tier_mix(qs, start, end),
        "company": company(qs),
        "industries": industries(qs),
        "sources": sources(qs),
        "trend": trend(start, end),
    }
