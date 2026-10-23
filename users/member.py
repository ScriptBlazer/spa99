"""Context for the member dashboard screens (My Spa 99). Stored data only: nothing here calls out or changes data.
Used by the short views in views.py; the screens are described in docs/design/MEMBER.md and docs/features/member-dashboard.md."""
from gold import invites as gold_invites
from pages import services as pages_services
from plans import services as plan_services
from plans.models import SiteSettings

from . import services
from .models import InterestRegistration

STATUS_GOLD, STATUS_REGISTERED, STATUS_NONE = "gold", "registered", "none"


def can_open(user):
    """May this person open the member area (/account/)? Only with a membership (interest and/or Gold); a superuser always
    can (an empty membership is shown). Being on the team never gives member access (user rule book U1)."""
    if not user.is_authenticated or not user.is_active:
        return False
    return user.is_superuser or InterestRegistration.objects.filter(user=user).exists()


def _card(plan, vat, ranges):
    return pages_services.plan_card(plan, vat, ranges) if plan is not None else None


def _suggested_plan(user):
    """The plan from this person's latest finished journey, if it is still one they can register interest in."""
    session = (user.journey_sessions.filter(completed=True, suggested_plan__isnull=False)
               .select_related("suggested_plan").order_by("-completed_at", "-pk").first())
    plan = session.suggested_plan if session else None
    return plan if plan is not None and services.interest_plans().filter(pk=plan.pk).exists() else None


def base_context(user):
    """Shared by every screen: who they are and where they stand."""
    site = SiteSettings.load()
    interest = getattr(user, "interest", None)
    plan = interest.plan if interest is not None else None
    is_gold = plan is not None and plan.slug == "gold"
    return {
        "greeting": pages_services.greeting(user), "site": site, "opening": site.opening_label, "opening_date": site.opening_date,
        "verified": bool(user.email_verified_at), "email": user.email, "account_id": user.public_id_display,
        "interest": interest, "interest_plan": plan, "is_gold": is_gold,
        "gold_since": gold_invites.gold_since(user) if is_gold else None,
        "status": STATUS_GOLD if is_gold else STATUS_REGISTERED if plan is not None else STATUS_NONE,
        "status_name": "Gold member" if is_gold else plan.name if plan is not None else "",
    }


def home_context(user):
    return base_context(user)


def book_context(user):
    """Book a visit: the booking line(s) for their plan, the opening hours, the Stay pills (same source as The spa)."""
    context = base_context(user)
    cards = pages_services.purchasable_plans()
    own = [c for c in cards if context["interest_plan"] is not None and c["slug"] == context["interest_plan"].slug]
    shown = own if own and not context["is_gold"] else cards  # Gold or no plan: every plan's line
    context.update({
        "booking_lines": pages_services.booking_lines(shown),
        "hours": pages_services.opening_hours(), "hours_summary": pages_services.hours_summary(),
        "closure": pages_services.closure_title(), "stay_pills": pages_services.visit_pills()["stay"],
        "notify_booking_open": context["site"].notify_booking_open,
    })
    return context


def membership_context(user):
    """Membership: Gold card facts, or the registered plan, price ex/inc VAT, the choice tiles and the journey suggestion."""
    context = base_context(user)
    site, ranges = context["site"], plan_services.hours_ranges()
    tiles = [_card(p, site.vat_rate, ranges) for p in services.interest_plans()]  # visible + interest_allowed
    current = context["interest_plan"]
    suggested = _suggested_plan(user)
    context.update({
        "plan_tiles": tiles, "current_plan": next((t for t in tiles if current is not None and t["slug"] == current.slug), None),
        "vat_rate": site.vat_rate.normalize(),
        "suggested_plan": _card(suggested, site.vat_rate, ranges),
        "suggestion_differs": suggested is not None and (current is None or current.pk != suggested.pk) and not context["is_gold"],
    })
    return context


def you_context(user):
    context = base_context(user)
    context.update({"marketing_consent": user.marketing_consent, "mobile": user.mobile or "", "full_name": user.get_full_name()})
    return context


def set_marketing_consent(user, on):
    """Turn marketing emails on or off. Saves (and so writes a history row) only when it changes; the time is when they chose."""
    from django.utils import timezone

    on = bool(on)
    if user.marketing_consent == on:
        return False
    user.marketing_consent = on
    user.marketing_consent_at = timezone.now()
    user.save(update_fields=["marketing_consent", "marketing_consent_at", "updated_at"])
    return True
