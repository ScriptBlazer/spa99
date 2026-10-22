"""Gold JSON endpoints. Public on purpose: applying creates no account. CSRF protected, rate limited, honeypot."""
import json

from django.contrib.auth.decorators import login_not_required
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from common.ratelimit import rate_limited_json
from journey import engine as journey_engine
from journey import services as journey_services

from . import services
from .forms import GoldApplicationForm
from .models import BML_CHOICES, PROPERTY_LINKS, SIZE_RANGES, WHERE_CHOICES

HONEYPOT_FIELD = "website"


def _choices(pairs):
    return [{"value": value, "label": label} for value, label in pairs]


def _payload(request):
    """JSON body, or an ordinary form post."""
    if (request.content_type or "").startswith("application/json"):
        try:
            data = json.loads(request.body or b"{}")
        except (ValueError, UnicodeDecodeError):
            return None
        return data if isinstance(data, dict) else None
    return request.POST.dict()


@login_not_required  # PUBLIC: Gold applications need no account (CSRF cookie set here, rate limited)
@ensure_csrf_cookie
@require_GET
@rate_limited_json("gold-options", 60, 60)
def options(request):
    """Choices for the form plus anything already known (journey answers, signed-in details) so nothing is asked twice."""
    session = journey_services.session_from_cookies(request.COOKIES)
    prefill = {}
    if session is not None:
        signals, _ = journey_engine.gold_signals(session)
        if signals.get("property_link"):
            prefill["property_link"] = signals["property_link"]
        if signals.get("size"):
            prefill["size_range"] = signals["size"]
    if request.user.is_authenticated:
        prefill.update(
            first_name=request.user.first_name, last_name=request.user.last_name,
            email=request.user.email, mobile=request.user.mobile or "",
        )
    return JsonResponse({
        "property_link": _choices(PROPERTY_LINKS), "size_range": _choices(SIZE_RANGES),
        "location": _choices(WHERE_CHOICES), "bml_relationship": _choices(BML_CHOICES),
        "prefill": prefill, "spa_interest": services.interest_snapshot(session),
    })


@login_not_required  # PUBLIC: see options()
@require_POST
@rate_limited_json("gold-apply", 10, 3600)
def apply(request):
    """Submit an application. 201 with the reference, or 400 {"errors": {field: [messages]}}."""
    data = _payload(request)
    if data is None:
        return JsonResponse({"error": "Send JSON."}, status=400)
    if data.get(HONEYPOT_FIELD):  # a bot: pretend it worked, save nothing
        return JsonResponse({"reference": "GC-OK"}, status=201)
    form = GoldApplicationForm(data)
    if not form.is_valid():
        return JsonResponse({"errors": {k: [str(m) for m in v] for k, v in form.errors.items()}}, status=400)
    session = journey_services.session_from_cookies(request.COOKIES)
    try:
        application, _ = services.submit_application(form.cleaned_data, session=session)
    except services.ApplicationsClosed:
        return JsonResponse({"error": "Applications are not open yet."}, status=403)
    return JsonResponse({"reference": application.reference, "message": "Thank you. We'll be in touch."}, status=201)
