"""The one service for every approval and revenue figure the Office shows (docs/features/office-counting-rules.md, "Office 2"). Home's three cards, the Approvals tabs, the Leads and
Registered tiles and the Revenue page all read this, so they always agree.

WHAT THE WORDS MEAN
  Membership people   every registration that is not on the Gold plan (a person on a Tier). Gold-plan members are the Gold table of Registered; they are never in the approval lists.
  waiting / approved / declined (membership)   Barry's review of the registration (office.MembershipReview). No row = waiting.
  waiting / approved / declined (Gold)         the Gold application's own status. Waiting = new, contacted or awaiting final approval (the same rows as the Gold Waiting list).
  Registered total    every registration, Gold-plan members included: the true total.
  Leads total         the Leads list: no account, not archived, not on the approach list.
A Tier member who also applied for Gold counts in both Waiting figures (two different decisions), but Revenue counts him once, at the plan he is on.

REVENUE ("approved" and "waiting" are the same two words as above; declined counts in neither)
  Gold         the number of Gold applications x Plan.annual_fee of the Gold plan (never a typed 199), excluding VAT. An applicant who holds a non-declined Tier registration is not counted
               here: he is counted at his Tier.
  Memberships  each member's own monthly price x 12, excluding VAT: an active subscription's agreed price when it has one, else the kept sale price (while it is held), else the plan's price.
  Left out      declined people, a staff member's own registration or Gold application (a test), and a registration whose subscription is cancelled (and not active again).
  Possible     the same sums for the people still waiting. Never added to the approved figures.
Everything is kept in whole pence (integers), excluding VAT, in the stored snapshot; VAT is added when it is shown, from the VAT setting, and nothing is rounded until display.

WHERE THE NUMBERS LIVE
  One stored snapshot (OfficeSnapshot page "counts"), written by the hourly roll-up and the debounced refresh like every other Office figure, and by `refresh_approvals()` right after Barry
  approves, declines or undoes, so the tabs and cards are right when the page loads. Nothing is summed while a page loads: a missing row is an empty state (`updating`) and asks for a
  refresh (`read()`). Plain ORM, the same on SQLite and Postgres."""
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from gold.models import GoldApplication
from insights.models import OfficeSnapshot
from plans.models import Plan, SiteSettings, Subscription
from plans.sales import sale_price
from users.models import InterestRegistration

from .models import MembershipReview

WAITING, APPROVED, DECLINED = MembershipReview.WAITING, MembershipReview.APPROVED, MembershipReview.DECLINED
GOLD_SLUG = "gold"
GOLD_WAITING = (GoldApplication.NEW, GoldApplication.CONTACTED, GoldApplication.AWAITING_FINAL)
PAGE, RANGE = OfficeSnapshot.COUNTS, "all"
PENCE = Decimal(100)


def to_pence(amount):
    """A price in pounds (Decimal or text) as whole pence."""
    return int((Decimal(amount) * PENCE).quantize(Decimal(1), rounding=ROUND_HALF_UP))


# ---------- who is in which list ----------

def membership_people():
    """Registrations on a Tier (not Gold-plan members, not people with no plan left)."""
    return InterestRegistration.objects.exclude(plan__slug=GOLD_SLUG)


def with_review(queryset):
    """Annotate `review_status`: the review's status, or waiting when there is no row."""
    return queryset.annotate(review_status=Coalesce("review__status", Value(WAITING)))


def _by_status(queryset):
    counts = dict(with_review(queryset).order_by().values_list("review_status").annotate(n=Count("pk")).values_list("review_status", "n"))
    approved, declined = counts.get(APPROVED, 0), counts.get(DECLINED, 0)
    total = sum(counts.values())
    return {"total": total, "waiting": total - approved - declined, "approved": approved, "declined": declined}


def gold_counts():
    counts = dict(GoldApplication.objects.order_by().values_list("status").annotate(n=Count("pk")).values_list("status", "n"))
    approved, declined = counts.get(GoldApplication.APPROVED, 0), counts.get(GoldApplication.DECLINED, 0)
    waiting = sum(counts.get(status, 0) for status in GOLD_WAITING)
    return {"total": sum(counts.values()), "waiting": waiting, "approved": approved, "declined": declined}


# ---------- revenue (whole pence, excluding VAT) ----------

def agreed_subquery():
    """Annotation for a registration queryset: the agreed price of his active subscription (None when he has none). Used as `.annotate(agreed=agreed_subquery())`."""
    return Subquery(Subscription.objects.filter(registration=OuterRef("pk"), status=Subscription.ACTIVE).order_by("-created_at").values("agreed_price_ex_vat")[:1])


def agreed_price(reg):
    """The same figure for one registration: the annotation when the queryset carried it, else one query."""
    if hasattr(reg, "agreed"):
        return reg.agreed
    return Subscription.objects.filter(registration=reg, status=Subscription.ACTIVE).order_by("-created_at").values_list("agreed_price_ex_vat", flat=True).first()


def month_pence(reg):
    """THE price rule, used by Revenue and by the Approvals rows: one member's monthly price in pence, excluding VAT, and whether it is a kept sale price.
    His active subscription's agreed price, else the kept sale price (while held), else the plan's price. (None, False) when he has no plan."""
    if reg.plan is None:
        return None, False
    agreed = agreed_price(reg)
    if agreed is not None:
        return to_pence(agreed), False
    if reg.sale_percent_off and not reg.sale_expired_at:
        return to_pence(sale_price(reg.plan, reg.sale_percent_off)), True
    return to_pence(reg.plan.price_ex_vat), False


def _blank(bucket_plans):
    return {"count": 0, "year_pence": 0, "by_plan": [{"slug": p["slug"], "name": p["name"], "kind": p["kind"], "count": 0, "year_pence": 0} for p in bucket_plans]}


def revenue():
    """{"gold_fee_pence", "approved": {...}, "waiting": {...}} in whole pence a year, excluding VAT. Each bucket: count, year_pence and `by_plan` (the Tiers in plan order, Gold last):
    [{slug, name, kind, count, year_pence}]. See the module text for what counts."""
    gold_plan = Plan.objects.filter(slug=GOLD_SLUG).first()
    fee = to_pence(gold_plan.annual_fee) if gold_plan is not None and gold_plan.annual_fee is not None else 0
    tiers = list(Plan.objects.filter(kind=Plan.MONTHLY).order_by("order", "price_ex_vat"))
    layout = [{"slug": p.slug, "name": p.name, "kind": "tier"} for p in tiers] + [{"slug": GOLD_SLUG, "name": gold_plan.name if gold_plan else "Gold Card", "kind": "gold"}]
    buckets = {APPROVED: _blank(layout), WAITING: _blank(layout)}
    rows_by_slug = {bucket: {row["slug"]: row for row in data["by_plan"]} for bucket, data in buckets.items()}
    cancelled = Exists(Subscription.objects.filter(registration=OuterRef("pk"), status=Subscription.CANCELLED))
    active = Exists(Subscription.objects.filter(registration=OuterRef("pk"), status=Subscription.ACTIVE))
    held = []  # (user id, lower email) of everyone holding a non-declined Tier registration: his Gold application is not added on top
    for reg in with_review(InterestRegistration.objects.filter(plan__kind=Plan.MONTHLY).select_related("plan", "user")).annotate(agreed=agreed_subquery(), has_cancelled=cancelled, has_active=active).iterator():
        if reg.review_status == DECLINED or reg.user.is_staff or (reg.has_cancelled and not reg.has_active):
            continue  # not revenue: declined, a staff member's own (test) registration, or a membership whose subscription was cancelled
        held.append((reg.user_id, (reg.user.email or "").strip().lower()))
        row = rows_by_slug[reg.review_status].get(reg.plan.slug)
        if row is None:
            continue
        pence = month_pence(reg)[0] * 12
        row["count"] += 1
        row["year_pence"] += pence
    users, emails = {u for u, _ in held}, {e for _, e in held if e}
    for application in GoldApplication.objects.filter(status__in=(GoldApplication.APPROVED, *GOLD_WAITING)).select_related("user").only("status", "user_id", "email", "user__is_staff"):
        if application.user is not None and application.user.is_staff:
            continue  # a staff member's own application
        if application.user_id in users or (application.email or "").strip().lower() in emails:
            continue  # he is on a Tier: counted once, there
        bucket = APPROVED if application.status == GoldApplication.APPROVED else WAITING
        row = rows_by_slug[bucket][GOLD_SLUG]
        row["count"] += 1
        row["year_pence"] += fee
    for bucket, data in buckets.items():
        data["count"] = sum(row["count"] for row in data["by_plan"])
        data["year_pence"] = sum(row["year_pence"] for row in data["by_plan"])
    return {"gold_fee_pence": fee, "approved": buckets[APPROVED], "waiting": buckets[WAITING]}


def with_vat(pence, vat_rate):
    """Pence including VAT, exact (a Decimal: not rounded here)."""
    return Decimal(pence) * (Decimal(100) + Decimal(vat_rate)) / Decimal(100)


def revenue_view(data=None, vat_rate=None):
    """The Revenue page's figures from the stored ones: every bucket and plan row gets month and year, excluding and including VAT (Decimal pence, exact), and the average for a member.
    Rounding is for display only (the `pounds` filter): totals are never added up from rounded figures."""
    data = data if data is not None else read()["revenue"]
    vat = Decimal(SiteSettings.load().vat_rate if vat_rate is None else vat_rate)

    def figures(count, year):
        return {"count": count, "year_ex": Decimal(year), "month_ex": Decimal(year) / 12, "year_inc": with_vat(year, vat), "month_inc": with_vat(year, vat) / 12,
                "avg_year_ex": Decimal(year) / count if count else None, "avg_year_inc": with_vat(year, vat) / count if count else None}

    out = {"vat_rate": vat, "gold_fee_pence": data["gold_fee_pence"], "gold_fee_inc_pence": with_vat(data["gold_fee_pence"], vat)}
    for bucket in (APPROVED, WAITING):
        source = data[bucket]
        out[bucket] = {**figures(source["count"], source["year_pence"]), "by_plan": [{**row, **figures(row["count"], row["year_pence"])} for row in source["by_plan"]]}
    return out


# ---------- the snapshot ----------

def compute_approvals():
    """Everything cheap: memberships, Gold, the registered total and Revenue."""
    return {"memberships": _by_status(membership_people()), "gold": gold_counts(), "registered_total": InterestRegistration.objects.count(),
            "gold_members": InterestRegistration.objects.filter(plan__slug=GOLD_SLUG).count(), "revenue": revenue()}


def compute_leads():
    """The Leads total (the list's own query, so the two always agree). The heavy part: only the job and the first read build it."""
    from . import leads

    return {"leads_total": leads.lead_queryset("all").count()}


def compute_all():
    return {**compute_approvals(), **compute_leads()}


def _write(payload):
    now = timezone.now()
    row, created = OfficeSnapshot.objects.get_or_create(page=PAGE, range=RANGE, defaults={"payload": payload, "built_at": now})
    if not created:
        OfficeSnapshot.objects.filter(pk=row.pk).update(payload=payload, built_at=now, updated_at=now)
    return payload


def refresh_approvals():
    """Barry decided something (or a registration was removed): recompute the cheap figures now and keep the stored Leads total. Never raises past the decision: a failure is logged and the
    hourly roll-up catches up."""
    import logging

    try:
        with transaction.atomic():
            stored = OfficeSnapshot.objects.filter(page=PAGE, range=RANGE).values_list("payload", flat=True).first() or {}
            payload = {**compute_approvals(), "leads_total": stored.get("leads_total") if "leads_total" in stored else compute_leads()["leads_total"]}
            _write(payload)
    except Exception:  # noqa: BLE001
        logging.getLogger("spa99.office").exception("Could not refresh the approval counts")


def empty():
    """What a page shows before the first snapshot exists (a fresh database): zeros and `updating`, never worked out while the page loads."""
    zero = {"total": 0, "waiting": 0, "approved": 0, "declined": 0}
    bucket = {"count": 0, "year_pence": 0, "by_plan": []}
    return {"memberships": dict(zero), "gold": dict(zero), "registered_total": 0, "gold_members": 0, "leads_total": 0, "updating": True,
            "revenue": {"gold_fee_pence": 0, "approved": dict(bucket), "waiting": dict(bucket)}}


def read():
    """The stored figures, one row. A missing row is an empty state and a refresh is asked for in the background (the same rule as every other Office figure: nothing is worked out while a
    page loads)."""
    payload = OfficeSnapshot.objects.filter(page=PAGE, range=RANGE).values_list("payload", flat=True).first()
    if payload:
        return payload
    from . import snapshots

    snapshots.request_refresh()
    return empty()


def cards(vat_rate=None):
    """For Home's three cards: {"waiting": {gold, memberships}, "approved": {...}, "revenue": {...}} from one stored row. Each ring has `value` and `of` (its total):
    people rings are x of y applied / registered; the Revenue rings are pence, with `of` = the estimate plus what those waiting would add."""
    data = read()
    gold, members = data["gold"], data["memberships"]
    rev = data["revenue"]

    def money(gold):
        have, wait = (sum(r["year_pence"] for r in rev[bucket]["by_plan"] if (r["slug"] == GOLD_SLUG) == gold) for bucket in ("approved", "waiting"))
        return {"value": have, "possible": wait, "of": have + wait}

    return {"waiting": {"gold": {"value": gold["waiting"], "of": gold["total"]}, "memberships": {"value": members["waiting"], "of": members["total"]}},
            "approved": {"gold": {"value": gold["approved"], "of": gold["total"]}, "memberships": {"value": members["approved"], "of": members["total"]}},
            "revenue": {"gold": money(True), "memberships": money(False)}, "registered_total": data["registered_total"], "leads_total": data.get("leads_total", 0)}
