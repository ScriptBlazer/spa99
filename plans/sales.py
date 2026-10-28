"""Sales: the live sale, prices, the kept-price snapshot, End now, the public bar and the preview link.

Everything about "which sale is on" is one indexed query (`live_sale`); a request asks at most once (`sale_for_request`). Locking:
saving or ending a sale takes a row lock on the SiteSettings singleton (`lock`), so two saves cannot both pass the overlap check.
SQLite ignores select_for_update (it serialises writers anyway); nothing here is Postgres-only."""
import time
import uuid
from decimal import ROUND_HALF_UP, Decimal

from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Plan, Sale, SiteSettings

PENNY = Decimal("0.01")
PREVIEW_SALT = "plans.sale-preview"
PREVIEW_SECONDS = 3600  # the link works once, within an hour; the browser that opens it sees the bar for an hour
PREVIEW_KEY = "sale_preview"
PREVIEW_PARAM = "sale_preview"
EMPTY_SNAPSHOT = {"sale": None, "sale_name": "", "sale_percent_off": None, "sale_months": None, "sale_locked_at": None}


# ---------- which sale is on ----------

def live_sale(now=None):
    """The sale live at `now` (starts_at inclusive, end exclusive; End now counts), or None, with its plans loaded (two queries)."""
    now = now or timezone.now()
    queryset = Sale.objects.filter(starts_at__lte=now, ends_at__gt=now).exclude(ended_early_at__lte=now)
    return queryset.prefetch_related("plans").order_by("-starts_at").first()


def live_sale_for_request(request):
    """The live sale, asked once per request (the bar and the register offer share it)."""
    if not hasattr(request, "_live_sale"):
        request._live_sale = live_sale()
    return request._live_sale


def plans_in(sale):
    return list(sale.plans.all())  # ordered by Plan.Meta (order, price)


def covers(sale, plan):
    return sale is not None and plan is not None and any(p.pk == plan.pk for p in sale.plans.all())


def plans_text(sale):
    """'Tier 2', 'Tier 2 and Tier 3'; every membership: 'all memberships' (plus the single visit: 'all memberships and single visits');
    the single visit alone: 'single visits'. A single visit inside a longer list is lower case ('Tier 2 and single visit')."""
    if hasattr(sale, "_plans_text"):
        return sale._plans_text
    chosen = list(sale.plans.all())
    monthly = set(Plan.objects.filter(kind=Plan.MONTHLY).values_list("pk", flat=True))
    one_off = {p.pk for p in chosen if p.kind == Plan.ONE_OFF}
    picked = {p.pk for p in chosen}
    if monthly and picked == monthly:
        text = "all memberships"
    elif monthly and one_off and picked == monthly | one_off:
        text = "all memberships and single visits"
    elif picked and picked == one_off:
        text = "single visits"
    else:
        names = [p.name.lower() if p.kind == Plan.ONE_OFF and i else p.name for i, p in enumerate(chosen)]
        text = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1] if names else ""
    sale._plans_text = text
    return text


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
        "name": interest.sale_name, "percent": percent, "months": months, "plan_name": plan.name,
        "plan_slugs": [p.slug for p in interest.sale.plans.all()] if interest.sale_id else [plan.slug],  # plans that keep the price
        "locked_at": interest.sale_locked_at,
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


def register_offer(vat_rate=None, request=None):
    """For the register and choose-a-tier screens: the live sale (never a preview: nothing is promised for a sale that is not on) with
    each covered plan's price lines, or None. `text` is the factual sentence; `prices` is keyed by plan slug."""
    sale = live_sale_for_request(request) if request is not None else live_sale()
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
    """Signed and single-use: it carries a random nonce, spent by the first browser that opens the link (start_preview)."""
    return signing.dumps({"sale": str(sale.pk), "n": uuid.uuid4().hex}, salt=PREVIEW_SALT)


def preview_url(sale):
    from django.conf import settings

    return f"{settings.SITE_URL}/?{PREVIEW_PARAM}={preview_token(sale)}"


def sale_from_token(token, max_age=PREVIEW_SECONDS, spend=False):
    """The sale a preview link is for, or None (bad signature, expired, sale gone or already ended). With `spend=True` the link's
    nonce is used up (an atomic cache add: DatabaseCache, same on SQLite and Postgres): a second open gets None."""
    try:
        data = signing.loads(token, salt=PREVIEW_SALT, max_age=max_age)
        sale = Sale.objects.filter(pk=data["sale"]).prefetch_related("plans").first()
    except (signing.BadSignature, KeyError, ValueError, TypeError, ValidationError):
        return None
    if sale is None or sale.status() == "ended":
        return None
    if spend and not cache.add(f"sale-preview-used:{data.get('n', '')}", 1, timeout=max_age + 60):
        return None
    return sale


def end_preview(request):
    """`?sale_preview=end` (the "End preview" link in the bar) drops this browser's preview."""
    if getattr(request, "session", None) is not None:
        request.session.pop(PREVIEW_KEY, None)


def preview_offer(request):
    """A preview link opened with GET does NOT start anything (chat and email link scanners GET links, and would use up the single use):
    the page shows a "Start preview" notice instead. Returns {token, name} for a valid, unspent link on a public page, else None.
    Nothing is shown when this browser is already previewing that sale."""
    token = request.GET.get(PREVIEW_PARAM, "") if request.method == "GET" and is_public_host(request) else ""
    if not token or token == "end":
        return None
    sale = sale_from_token(token)  # not spent
    if sale is None:
        return None
    nonce = signing.loads(token, salt=PREVIEW_SALT).get("n", "")
    if cache.get(f"sale-preview-used:{nonce}"):
        return None
    current = _preview_sale(request)
    if current is not None and current.pk == sale.pk:
        return None
    return {"token": token, "name": sale.name}


def start_preview(request, token):
    """POST from the "Start preview" button: spends the single-use link and puts the sale in this browser's session for an hour.
    Returns True when it started. A second browser, an expired or spent link, or an ended sale does nothing."""
    if getattr(request, "session", None) is None:
        return False
    sale = sale_from_token(token or "", spend=True)
    if sale is None:
        return False
    request.session[PREVIEW_KEY] = {"sale": str(sale.pk), "until": time.time() + PREVIEW_SECONDS}
    return True


def _preview_sale(request):
    """The sale this browser is previewing (from the session), or None once the hour is up or the sale has ended."""
    session = getattr(request, "session", None)
    if session is None:
        return None
    held = session.get(PREVIEW_KEY)
    if held and held.get("until", 0) > time.time():
        sale = Sale.objects.filter(pk=held["sale"]).prefetch_related("plans").first()
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
        sale = previewed or live_sale_for_request(request)
        result = bar(sale, preview=previewed is not None) if sale is not None else None
    request._sale_bar = result
    return result
