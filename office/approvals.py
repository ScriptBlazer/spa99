"""Barry's membership approval list (docs/features/office-2.md). Waiting, Approved and Declined lists of the people on a Tier, and the three decisions: Approve, Decline and Undo.

THE RULE: a decision here changes nothing for the member. No email, no change to his membership, plan, price or payment, and no member-facing page reads it (office.models). The list is for
Barry only, so he can choose who he wants for special prices. No row means waiting, so every registration starts waiting with no backfill.

Who is in the list: registrations that are not on the Gold plan (Gold-plan members are approved through Gold and show in Registered > Gold). Everything is plain ORM, the same on SQLite and
Postgres. Counts come from office.counts (stored); the lists below are LIMIT-style pages (one extra row fetched instead of a count)."""
from django.db import transaction
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone

from gold import audit
from plans.sales import sale_price
from users.models import InterestRegistration

from . import counts
from .models import MembershipReview, MembershipReviewEvent

WAITING, APPROVED, DECLINED = counts.WAITING, counts.APPROVED, counts.DECLINED
STATUSES = (WAITING, APPROVED, DECLINED)
LABELS = {WAITING: "Waiting", APPROVED: "Approved", DECLINED: "Declined"}
DONE, UNCHANGED, MISSING = "done", "unchanged", "missing"
NOTE = "For Barry's eyes. Nothing here changes anything for the member: his membership and emails stay as they are."


def status_from(get):
    return get.get("status") if get.get("status") in STATUSES else WAITING


def queryset(status, q="", plan=""):
    """The people in one list, newest first (waiting: by when they registered; approved and declined: by when Barry decided)."""
    found = counts.with_review(counts.membership_people()).filter(review_status=status).select_related("user", "plan", "review")
    for word in (q or "").split():
        found = found.filter(Q(user__email__icontains=word) | Q(user__first_name__icontains=word) | Q(user__last_name__icontains=word))
    if plan:
        found = found.filter(plan__slug=plan)
    if status == WAITING:
        return found.order_by("-created_at", "-pk")
    return found.annotate(decided_at=Coalesce("review__at", "created_at")).order_by("-decided_at", "-pk")


def price_of(reg):
    """His own price, a month, in pence excluding VAT, and whether it is a kept sale price (the Waiting row reads "Tier 2, £249 a month (sale price)"). The list price when he holds no sale."""
    if reg.plan is None:
        return None, False
    if reg.sale_percent_off and not reg.sale_expired_at:
        return counts.to_pence(sale_price(reg.plan, reg.sale_percent_off)), True
    return counts.to_pence(reg.plan.price_ex_vat), False


def row(reg):
    user = reg.user
    try:
        review = reg.review
    except MembershipReview.DoesNotExist:
        review = None
    pence, sale = price_of(reg)
    status = getattr(reg, "review_status", WAITING)
    return {"id": str(user.pk), "name": user.get_full_name() or user.email, "email": user.email, "plan": reg.plan.name if reg.plan_id else "", "plan_slug": reg.plan.slug if reg.plan_id else "",
            "month_pence": pence, "sale": sale, "registered": reg.created_at.isoformat(), "status": status,
            "decided_at": review.at.isoformat() if review and review.at else "", "decided_by": review.by_label if review else "",
            "href": reverse("office_person", args=[user.pk]), "approve_url": reverse("office_approval_approve", args=[user.pk]),
            "decline_url": reverse("office_approval_decline", args=[user.pk]), "undo_url": reverse("office_approval_undo", args=[user.pk])}


def page(status, number, size, q="", plan=""):
    """(rows, has_next) for one page of one list."""
    start = (number - 1) * size
    found = list(queryset(status, q, plan)[start:start + size + 1])
    return [row(r) for r in found[:size]], len(found) > size


def line(members):
    """The line at the top of Registered, from the stored membership counts: {approved, waiting, declined, text, status} or None when nobody has registered. "32 approved, 16 left to approve,
    2 declined"; "All 48 approved" when none are left; the link goes to Approvals (Waiting, or Approved when none wait)."""
    if not members["total"]:
        return None
    parts = [f"{members['approved']} approved"]
    if members["waiting"]:
        parts.append(f"{members['waiting']} left to approve")
    if members["declined"]:
        parts.append(f"{members['declined']} declined")
    text = f"All {members['approved']} approved" if not members["waiting"] and not members["declined"] else ", ".join(parts)
    return {"approved": members["approved"], "waiting": members["waiting"], "declined": members["declined"], "text": text, "status": WAITING if members["waiting"] else APPROVED,
            "url": f"{reverse('office_approvals')}?status={WAITING if members['waiting'] else APPROVED}"}


def decide(user_pk, to_status, actor):
    """Move one person to `to_status` (approved, declined, or waiting for Undo). Audited: a MembershipReviewEvent with who and when. Returns (DONE | UNCHANGED | MISSING, row dict or None).
    Never touches the membership. Refreshes the stored counts (and Revenue) right away."""
    if to_status not in STATUSES:
        return MISSING, None
    with transaction.atomic():
        reg = (InterestRegistration.objects.select_for_update(of=("self",)).select_related("user", "plan").filter(user_id=user_pk).exclude(plan__slug=counts.GOLD_SLUG).first())
        if reg is None:
            return MISSING, None
        review, _ = MembershipReview.objects.get_or_create(registration=reg)
        before = review.status
        if before == to_status:
            reg.review_status = to_status
            return UNCHANGED, row(reg)
        waiting = to_status == WAITING
        review.status, review.by, review.by_label, review.at = to_status, None if waiting else (actor if getattr(actor, "pk", None) else None), "" if waiting else audit.label_for(actor), None if waiting else timezone.now()
        review.save(update_fields=["status", "by", "by_label", "at"])
        MembershipReviewEvent.objects.create(registration=reg, from_status=before, to_status=to_status, by=actor if getattr(actor, "pk", None) else None, by_label=audit.label_for(actor))
        reg.review_status = to_status
        reg.review = review
    counts.refresh_approvals()
    from . import snapshots

    snapshots.request_refresh()  # the hourly figures follow within moments (the Home cards read the stored row refreshed above)
    return DONE, row(reg)


def export_for(user):
    """UK GDPR: Barry's review of this person (his status, who decided and when, and each change), for the person export. {} when there is none."""
    reg = InterestRegistration.objects.filter(user=user).first()
    if reg is None:
        return {}
    review = MembershipReview.objects.filter(registration=reg).first()
    return {"status": review.status if review else WAITING, "decided_by": review.by_label if review else "", "decided_at": review.at.isoformat() if review and review.at else None,
            "changes": [{"from": e.from_status, "to": e.to_status, "by": e.by_label, "at": e.at.isoformat()} for e in MembershipReviewEvent.objects.filter(registration=reg).order_by("at", "id")]}
