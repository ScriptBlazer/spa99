"""Sales: the live sale, prices, the kept-price snapshot, End now, the public bar and the preview link.

Everything about "which sale is on" is one indexed query (`live_sale`); a request asks at most once (`sale_for_request`). Locking:
saving or ending a sale takes a row lock on the SiteSettings singleton (`lock`), so two saves cannot both pass the overlap check.
SQLite ignores select_for_update (it serialises writers anyway); nothing here is Postgres-only."""
import time
from decimal import ROUND_HALF_UP, Decimal

from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Sale, SiteSettings

PENNY = Decimal("0.01")
PREVIEW_SALT = "plans.sale-preview"
PREVIEW_SECONDS = 3600  # the link works for an hour; once opened, that browser sees the bar for an hour
PREVIEW_KEY = "sale_preview"
PREVIEW_PARAM = "sale_preview"
EMPTY_SNAPSHOT = {"sale": None, "sale_name": "", "sale_percent_off": None, "sale_months": None, "sale_locked_at": None}


# ---------- which sale is on ----------

def live_sale(now=None):
    """The sale live at `now` (starts_at inclusive, end exclusive; End now counts), or None. One query."""
    now = now or timezone.now()
    queryset = Sale.objects.filter(starts_at__lte=now, ends_at__gt=now).exclude(ended_early_at__lte=now)
    return queryset.order_by("-starts_at").first()


def plans_in(sale):
    return list(sale.plans.all())  # ordered by Plan.Meta (order, price)


def covers(sale, plan):
    return sale is not None and plan is not None and any(p.pk == plan.pk for p in sale.plans.all())


def plans_text(sale):
    """'Tier 2', 'Tier 2 and Tier 3', 'Tier 1, Tier 2 and Tier 3'."""
    names = [p.name for p in sale.plans.all()]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1] if names else ""


# ---------- prices ----------

def sale_price(plan, sale_or_percent, vat_rate=None):
    """The plan's ex-VAT price with the sale taken off, rounded to whole pence. `sale_or_percent` is a Sale or a percent
    (a person's kept percent). Pass `vat_rate` to get the price including VAT instead."""
    percent = getattr(sale_or_percent, "percent_off", sale_or_percent)
    price = (Decimal(plan.price_ex_vat) * (Decimal(100) - Decimal(percent)) / Decimal(100)).quantize(PENNY, rounding=ROUND_HALF_UP)
    if vat_rate is None:
        return price
    return (price * (Decimal(100) + Decimal(vat_rate)) / Decimal(100)).quantize(PENNY, rounding=ROUND_HALF_UP)


def price_lines(plan, percent, vat_rate):
    """Full and sale price, ex and inc VAT, as pounds text ('299.00')."""
    from .services import price_inc_vat

    return {"price_ex_vat": f"{Decimal(plan.price_ex_vat):.2f}", "price_inc_vat": f"{price_inc_vat(plan.price_ex_vat, vat_rate):.2f}",
            "sale_price_ex_vat": f"{sale_price(plan, percent):.2f}", "sale_price_inc_vat": f"{sale_price(plan, percent, vat_rate):.2f}"}


# ---------- the kept price on a registration ----------

def snapshot_fields(plan, held=None, now=None):
    """The sale fields an InterestRegistration should have for `plan`.

    - a person who holds a snapshot keeps it when the new plan is covered by that same sale (even if it has ended since);
    - otherwise a live sale that covers the plan is copied (name, percent, months) and time-stamped;
    - otherwise none: moving to a plan no sale covers clears it (history keeps the old one).
    Never adds a snapshot once the sale has ended. `held` is the current InterestRegistration (None for a new one)."""
    if plan is None:
        return dict(EMPTY_SNAPSHOT)
    if held is not None and held.sale_percent_off and held.sale_id and covers(held.sale, plan):
        return {name: getattr(held, name) for name in EMPTY_SNAPSHOT}
    sale = live_sale(now)
    if covers(sale, plan):
        return {"sale": sale, "sale_name": sale.name, "sale_percent_off": sale.percent_off, "sale_months": sale.months_at_price,
                "sale_locked_at": now or timezone.now()}
    return dict(EMPTY_SNAPSHOT)


def kept_price(interest, vat_rate=None):
    """What a person keeps, for the member screens: None without a snapshot or plan, else a plain dict with a ready sentence."""
    if interest is None or not interest.sale_percent_off or interest.plan is None:
        return None
    plan, percent, months = interest.plan, interest.sale_percent_off, interest.sale_months
    vat = SiteSettings.load().vat_rate if vat_rate is None else vat_rate
    unit = "month" if months == 1 else "months"
    return {
        "name": interest.sale_name, "percent": percent, "months": months, "plan_name": plan.name, "locked_at": interest.sale_locked_at,
        **price_lines(plan, percent, vat),
        "text": f"You keep {percent}% off {plan.name} for {months} {unit} from your first payment.",
    }


# ---------- saving and ending (the lock lives here) ----------

def lock():
    """Serialise sale writers: a row lock on the SiteSettings singleton (inside a transaction)."""
    SiteSettings.objects.select_for_update().filter(pk=SiteSettings.load().pk).first()


@transaction.atomic
def save_sale(form, user):
    """Save a valid SaleForm: the row through the change log (overlap and live-edit locks are checked by Sale.clean under the lock),
    then the plans (a logged change of its own). Returns True when something was written. A stale form raises ValidationError."""
    from system import services as system_services

    lock()
    sale = form.instance
    adding = sale._state.adding
    if not adding and hasattr(form, "ensure_current"):
        form.ensure_current(lock=True)
    old_plans = [] if adding else [p.name for p in sale.plans.all()]
    new_plans = list(form.cleaned_data["plans"])
    plans_changed = adding or {p.pk for p in new_plans} != set(sale.plans.values_list("pk", flat=True))
    if not adding and not form.changed_data and not plans_changed:
        return False
    if adding:
        sale.created_by = user
        system_services.save_logged(sale, user)
    elif [f for f in form.changed_data if f != "plans"]:
        system_services.save_logged(sale, user, fields=[f for f in form.changed_data if f != "plans"])
    if plans_changed:
        sale.plans.set(new_plans)
        after = [p.name for p in sale.plans.all()]
        system_services.record_direct(
            user, "sales", "plans.sale", sale, "plans", old_plans, after,
            sentence=f"Set the plans for {sale.name}: {', '.join(after)}" if adding else
            f"Changed {sale.name} · Plans from {', '.join(old_plans) or 'none'} to {', '.join(after)}")
    return True


@transaction.atomic
def end_now(sale, user):
    """End a live sale now (an upcoming one is cancelled: it never runs). Logged and undoable from the change log while its original
    end is still in the future. Refused for a sale that has already ended."""
    from system import services as system_services

    lock()
    sale = Sale.objects.select_for_update().get(pk=sale.pk)
    now = timezone.now()
    status = sale.status(now)
    if status == "ended":
        raise ValidationError("This sale has already ended.")
    sale.ended_early_at = max(now, sale.starts_at)
    system_services.save_logged(sale, user, fields=["ended_early_at"])
    return sale


def register_offer(vat_rate=None):
    """For the register and choose-a-tier screens: the live sale (never a preview: nothing is promised for a sale that is not on) with
    each covered plan's price lines, or None. `text` is the factual sentence; `prices` is keyed by plan slug."""
    sale = live_sale()
    if sale is None:
        return None
    vat = SiteSettings.load().vat_rate if vat_rate is None else vat_rate
    unit = "month" if sale.months_at_price == 1 else "months"
    return {**bar(sale), "prices": {p.slug: price_lines(p, sale.percent_off, vat) for p in sale.plans.all()},
            "text": f"Register during the {sale.name} and keep {sale.percent_off}% off {plans_text(sale)} for {sale.months_at_price} {unit} from your first payment."}


# ---------- the public bar ----------

def bar(sale, preview=False):
    """The data for the bar on public pages."""
    return {
        "id": str(sale.pk), "name": sale.name, "percent": sale.percent_off, "plans_text": plans_text(sale),
        "plan_slugs": [p.slug for p in sale.plans.all()], "months": sale.months_at_price,
        "starts_at": sale.starts_at.isoformat(), "ends_at": sale.window_end.isoformat(), "preview": preview,
    }


def preview_token(sale):
    return signing.dumps({"sale": str(sale.pk)}, salt=PREVIEW_SALT)


def preview_url(sale):
    from django.conf import settings

    return f"{settings.SITE_URL}/?{PREVIEW_PARAM}={preview_token(sale)}"


def sale_from_token(token, max_age=PREVIEW_SECONDS):
    """The sale a preview link is for, or None (bad signature, expired, sale gone or already ended)."""
    try:
        data = signing.loads(token, salt=PREVIEW_SALT, max_age=max_age)
        sale = Sale.objects.filter(pk=data["sale"]).first()
    except (signing.BadSignature, KeyError, ValueError, TypeError, ValidationError):
        return None
    return sale if sale is not None and sale.status() != "ended" else None


def start_preview(request):
    """A valid `?sale_preview=` token on a public page puts the sale in this browser's session for an hour (called by
    plans.middleware.SalePreviewMiddleware, so it works whether or not the page reads the bar)."""
    sale = sale_from_token(request.GET.get(PREVIEW_PARAM, ""))
    if sale is not None and getattr(request, "session", None) is not None:
        request.session[PREVIEW_KEY] = {"sale": str(sale.pk), "until": time.time() + PREVIEW_SECONDS}


def _preview_sale(request):
    """The sale this browser is previewing (from the session), or None once the hour is up or the sale has ended."""
    session = getattr(request, "session", None)
    if session is None:
        return None
    held = session.get(PREVIEW_KEY)
    if held and held.get("until", 0) > time.time():
        sale = Sale.objects.filter(pk=held["sale"]).first()
        if sale is not None and sale.status() != "ended":
            return sale
    return None


def is_public_host(request):
    """The public website only: not office, control or system (HostRoutingMiddleware sets request.urlconf for those)."""
    return getattr(request, "urlconf", "config.urls") == "config.urls"


def sale_bar_for_request(request):
    """`sale_bar` for a public page: the previewed sale (this browser only), else the live sale, else None. Cached on the request."""
    if hasattr(request, "_sale_bar"):
        return request._sale_bar
    result = None
    if is_public_host(request):
        previewed = _preview_sale(request)
        sale = previewed or live_sale()
        result = bar(sale, preview=previewed is not None) if sale is not None else None
    request._sale_bar = result
    return result
