"""Recompute the event figures from the source tables (the repair tool behind `rebuild_metrics`, also the one-off
backfill). Never run from a migration. Visitor and page-view figures have no source table (anonymous hashes are wiped daily), so they are left alone. The people figures, answers, insights and snapshots are rewritten from the journey and registration tables by the roll-up that runs at the end."""
from collections import defaultdict

from django.db import transaction

from . import metrics, rollup
from .metrics import EVENT_KEYS, K, NO_DAILY
from .models import DailyMetric, MetricCounter


def expected():
    """(counters, daily) the source tables imply: {(key, dim): n} and {(date, key, dim): n}. Same definitions as the
    live calls in insights.metrics (a row's own date, bots never counted)."""
    from gold.models import GoldApplication, GoldInvite
    from journey import engine
    from journey.models import JourneySession, Question
    from users.models import InterestRegistration, User

    counters, daily = defaultdict(int), defaultdict(int)

    def add(key, dim="", on=None, n=1):
        counters[(key, dim)] += n
        if on is not None and key not in NO_DAILY:
            daily[(on, key, dim)] += n

    for interest in InterestRegistration.objects.select_related("plan", "user"):
        on = metrics.day(interest.created_at)
        add(K.REGISTRATIONS, "", on)
        add(K.REGISTRATIONS_BY_PLAN, interest.plan.slug if interest.plan_id else "none", on)
        add(K.REGISTRATIONS_BY_SOURCE, interest.source, on)
        if interest.user.marketing_consent:
            add(K.MARKETING_OPT_IN, "", on)
    for verified_at in User.objects.filter(email_verified_at__isnull=False).values_list("email_verified_at", flat=True):
        add(K.EMAIL_VERIFIED, "", metrics.day(verified_at))

    screens = sorted(set(Question.objects.filter(active=True).values_list("screen", flat=True)))
    sessions = JourneySession.objects.filter(is_bot=False).select_related("suggested_plan")
    for session in sessions.iterator():
        on = metrics.day(session.created_at)
        add(K.JOURNEYS_STARTED, "", on)
        for number in screens:
            if number <= session.furthest_step:
                add(K.JOURNEY_SCREEN, str(number), on)
        if not session.completed:
            continue
        done = metrics.day(session.completed_at or session.updated_at)
        add(K.JOURNEYS_COMPLETED, "", done)
        if session.suggested_plan_id:
            add(K.SUGGESTED_PLAN, session.suggested_plan.slug, done)
        if session.gold_potential:
            add(K.JOURNEY_GOLD_POTENTIAL, session.gold_potential, done)
        counted = session.suggestion_detail.get("counted_answers")
        for item in (counted if counted is not None else engine.counted_answers(session)):
            add(K.JOURNEY_ANSWER, item, done)

    for application in GoldApplication.objects.all():
        on = metrics.day(application.created_at)
        add(K.GOLD_APPLICATIONS, "", on)
        add(K.GOLD_BY_POTENTIAL, application.potential_level or "unrated", on)
        add(K.GOLD_BY_STATUS, application.status)
        if application.status == GoldApplication.APPROVED:
            add(K.GOLD_APPROVED, "", metrics.day(application.approved_at or application.updated_at))
    for sent_at, used_at in GoldInvite.objects.values_list("sent_at", "used_at"):
        if sent_at:
            add(K.GOLD_INVITES_SENT, "", metrics.day(sent_at))
        if used_at:
            add(K.GOLD_INVITES_USED, "", metrics.day(used_at))
    return ({k: v for k, v in counters.items() if v}, {k: v for k, v in daily.items() if v})


def stored():
    counters = {(c.key, c.dimension): c.value for c in MetricCounter.objects.filter(key__in=EVENT_KEYS) if c.value}
    daily = {(d.date, d.key, d.dimension): d.value for d in DailyMetric.objects.filter(key__in=EVENT_KEYS) if d.value}
    return counters, daily


def differences():
    """[(kind, identity, stored value, expected value)], sorted; empty when stored and source agree."""
    want_counters, want_daily = expected()
    have_counters, have_daily = stored()
    diffs = []
    for kind, have, want in (("counter", have_counters, want_counters), ("daily", have_daily, want_daily)):
        for ident in sorted(set(have) | set(want), key=str):
            if have.get(ident, 0) != want.get(ident, 0):
                diffs.append((kind, ident, have.get(ident, 0), want.get(ident, 0)))
    return diffs


def apply():
    """Make the stored event figures equal to the source, then re-run the whole roll-up (rates, weeks, months, text).
    Returns (number of differences fixed, roll-up summary)."""
    with transaction.atomic():
        want_counters, want_daily = expected()
        OBSOLETE = ("people_started", "people_finished", "people_registered")  # the old per-day hash flags (counting rules C3)
        DailyMetric.objects.filter(key__in=OBSOLETE).delete()
        MetricCounter.objects.filter(key__in=OBSOLETE).delete()
        MetricCounter.objects.filter(key__in=EVENT_KEYS).delete()
        DailyMetric.objects.filter(key__in=EVENT_KEYS).delete()
        MetricCounter.objects.bulk_create([MetricCounter(key=k, dimension=d, value=v) for (k, d), v in want_counters.items()])
        DailyMetric.objects.bulk_create([DailyMetric(date=day, key=k, dimension=d, value=v) for (day, k, d), v in want_daily.items()])
        summary = rollup.run(since=None)
    return summary
