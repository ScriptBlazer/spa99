"""Write side of the stored figures. Services call these inside the same transaction as the event they describe, so a
rolled-back event leaves no trace. This module imports no other project app at module level (users, journey and gold
import it), and takes plain values (slugs, dates, strings), never models.

Each event bumps the all-time MetricCounter and the DailyMetric row of the entity's own date (a session's start date, a
registration's date, ...), so `rebuild_metrics` can recompute exactly the same rows from the source tables."""
import logging

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from .models import DailyMetric, MetricCounter

logger = logging.getLogger("spa99.metrics")


class K:
    """Metric keys. Event keys (rebuilt from source) first, then visitor keys (no source: counted live only), then
    derived keys (written by the roll-up)."""

    REGISTRATIONS = "registrations"
    REGISTRATIONS_BY_PLAN = "registrations_by_plan"          # dimension: plan slug ("none" when no plan)
    REGISTRATIONS_BY_SOURCE = "registrations_by_source"      # dimension: journey | direct
    EMAIL_VERIFIED = "email_verified"
    MARKETING_OPT_IN = "marketing_opt_in"
    JOURNEYS_STARTED = "journeys_started"
    JOURNEYS_COMPLETED = "journeys_completed"
    JOURNEY_SCREEN = "journey_screen"                        # dimension: screen number reached
    SUGGESTED_PLAN = "suggested_plan"                        # dimension: plan slug
    JOURNEY_GOLD_POTENTIAL = "journey_gold_potential"        # dimension: high | medium | low
    JOURNEY_ANSWER = "journey_answer"                        # dimension: "question:option" (completed journeys)
    GOLD_APPLICATIONS = "gold_applications"
    GOLD_BY_POTENTIAL = "gold_by_potential"                  # dimension: high | medium | low | unrated
    GOLD_BY_STATUS = "gold_by_status"                        # counter only (current state): new | contacted | approved | declined
    GOLD_APPROVED = "gold_approved"
    GOLD_INVITES_SENT = "gold_invites_sent"
    GOLD_INVITES_USED = "gold_invites_used"

    VISITORS = "visitors"                                    # daily unique visitors (one per anonymous hash per day)
    PAGE_VIEWS = "page_views"                                # dimension "" = all pages, else path group
    REFERRERS = "referrers"                                  # dimension: referring site host

    RATE_JOURNEY_START = "rate_journey_start"                # journeys started / visitors, basis points
    RATE_JOURNEY_FINISH = "rate_journey_finish"              # journeys completed / started
    RATE_REGISTER = "rate_register"                          # registrations / visitors


# Rebuilt from the source tables by `rebuild_metrics`.
EVENT_KEYS = (
    K.REGISTRATIONS, K.REGISTRATIONS_BY_PLAN, K.REGISTRATIONS_BY_SOURCE, K.EMAIL_VERIFIED, K.MARKETING_OPT_IN,
    K.JOURNEYS_STARTED, K.JOURNEYS_COMPLETED, K.JOURNEY_SCREEN, K.SUGGESTED_PLAN, K.JOURNEY_GOLD_POTENTIAL,
    K.JOURNEY_ANSWER, K.GOLD_APPLICATIONS, K.GOLD_BY_POTENTIAL, K.GOLD_BY_STATUS, K.GOLD_APPROVED,
    K.GOLD_INVITES_SENT, K.GOLD_INVITES_USED,
)
RATE_KEYS = (K.RATE_JOURNEY_START, K.RATE_JOURNEY_FINISH, K.RATE_REGISTER)
NO_DAILY = (K.GOLD_BY_STATUS,)  # current-state counters have no daily row


def day(when=None):
    """London calendar day of a datetime (or today)."""
    return timezone.localdate(when) if when is not None else timezone.localdate()


def _bump(model, lookup, amount):
    if model.objects.filter(**lookup).update(value=F("value") + amount):
        return
    try:
        with transaction.atomic():  # savepoint: a lost race must not poison the caller's transaction
            model.objects.create(value=amount, **lookup)
    except IntegrityError:
        model.objects.filter(**lookup).update(value=F("value") + amount)


def _refresh_after_commit():
    """Queue one debounced snapshot refresh once the surrounding transaction commits (a rolled-back event queues nothing)."""
    from office import snapshots

    snapshots.request_refresh()


def count(key, dimension="", amount=1, on=None, counter=True, daily=True):
    """Add `amount` (negative to take back) to the all-time counter and to the day's row (`on` = the day, default today)."""
    if not amount:
        return
    dimension = (dimension or "")[:100]
    if counter:
        _bump(MetricCounter, {"key": key, "dimension": dimension}, amount)
        _refresh_after_commit()  # a counted event: the stored snapshots are refreshed in the background
    if daily and key not in NO_DAILY:
        _bump(DailyMetric, {"date": on or day(), "key": key, "dimension": dimension}, amount)


# ---------- registrations ----------

def registered(plan_slug, source, created_at, verified_at=None, marketing=False, amount=1):
    """A person's interest registration was created (`amount` -1 when erased)."""
    on = day(created_at)
    count(K.REGISTRATIONS, "", amount, on)
    count(K.REGISTRATIONS_BY_PLAN, plan_slug or "none", amount, on)
    count(K.REGISTRATIONS_BY_SOURCE, source, amount, on)
    if marketing:
        count(K.MARKETING_OPT_IN, "", amount, on)


def interest_plan_changed(old_slug, new_slug, created_at):
    """The plan a person is interested in changed. The registration keeps its day; the plan split moves."""
    if (old_slug or "none") == (new_slug or "none"):
        return
    on = day(created_at)
    count(K.REGISTRATIONS_BY_PLAN, old_slug or "none", -1, on)
    count(K.REGISTRATIONS_BY_PLAN, new_slug or "none", 1, on)


def email_verified(verified_at, amount=1):
    count(K.EMAIL_VERIFIED, "", amount, day(verified_at))


# ---------- journey ----------

def journey_started(created_at, screens):
    """A non-bot journey session began. `screens` = the screen numbers reached at the start (screen 1)."""
    on = day(created_at)
    count(K.JOURNEYS_STARTED, "", 1, on)
    for number in screens:
        count(K.JOURNEY_SCREEN, str(number), 1, on)


def journey_screens_reached(created_at, screens):
    """The journey moved on and reached these screens for the first time."""
    on = day(created_at)
    for number in screens:
        count(K.JOURNEY_SCREEN, str(number), 1, on)


def journey_completed(completed_at, plan_slug, gold_level, answers, first=True,
                      old_plan_slug=None, old_gold_level=None, old_answers=()):
    """A journey was finished (first=True) or re-finished with a different result (first=False: the old suggestion,
    Gold level and answers are taken back first). `answers` is a list of "question:option"."""
    on = day(completed_at)
    if first:
        count(K.JOURNEYS_COMPLETED, "", 1, on)
    else:
        if old_plan_slug:
            count(K.SUGGESTED_PLAN, old_plan_slug, -1, on)
        if old_gold_level:
            count(K.JOURNEY_GOLD_POTENTIAL, old_gold_level, -1, on)
        for item in old_answers:
            count(K.JOURNEY_ANSWER, item, -1, on)
    if plan_slug:
        count(K.SUGGESTED_PLAN, plan_slug, 1, on)
    if gold_level:
        count(K.JOURNEY_GOLD_POTENTIAL, gold_level, 1, on)
    for item in answers:
        count(K.JOURNEY_ANSWER, item, 1, on)


# ---------- gold ----------

def gold_application(created_at, potential, status, amount=1):
    on = day(created_at)
    count(K.GOLD_APPLICATIONS, "", amount, on)
    count(K.GOLD_BY_POTENTIAL, potential or "unrated", amount, on)
    count(K.GOLD_BY_STATUS, status, amount)


def gold_status_changed(old_status, new_status, approved_at=None):
    count(K.GOLD_BY_STATUS, old_status, -1)
    count(K.GOLD_BY_STATUS, new_status, 1)
    if new_status == "approved":
        count(K.GOLD_APPROVED, "", 1, day(approved_at))
    elif old_status == "approved":
        count(K.GOLD_APPROVED, "", -1, day(approved_at))


def gold_potential_changed(old, new, created_at):
    if (old or "unrated") != (new or "unrated"):
        on = day(created_at)
        count(K.GOLD_BY_POTENTIAL, old or "unrated", -1, on)
        count(K.GOLD_BY_POTENTIAL, new or "unrated", 1, on)


def gold_invite(key, when, amount=1):
    count(key, "", amount, day(when))
