"""Gold JSON endpoints. Public on purpose: applying creates no account. CSRF protected, rate limited, honeypot."""
import json

from django.contrib.auth.decorators import login_not_required
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from common.audit import client_ip
from common.ratelimit import hit, rate_limited_json, too_many_response
from journey import engine as journey_engine
from journey import services as journey_services
from journey.models import Question

from . import services
from .forms import GoldApplicationForm
from . import rating
from .models import BML, PROPERTY_LINK, SIZE, WHERE

HONEYPOT_FIELD = "website"
APPLY_SCOPE, APPLY_LIMIT, APPLY_WINDOW = "gold-apply", 10, 3600


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


def _question_text(key, default):
    question = Question.objects.filter(key=key).first()
    return question.text if question else default


def _industry_question_text():
    return _question_text(rating.INDUSTRY_QUESTION, "What do you do?")


def _industry_other_text():
    return _question_text(rating.INDUSTRY_OTHER_QUESTION, "In a few words")


@login_not_required  # PUBLIC: Gold applications need no account (CSRF cookie set here, rate limited)
@ensure_csrf_cookie
@require_GET
@rate_limited_json("gold-options", 60, 60)
def options(request):
    """Choices for the form plus anything already known (journey answers, signed-in details) so nothing is asked twice."""
    session = journey_services.session_from_cookies(request.COOKIES, request.user)
    prefill = {}
    if session is not None:
        answers = journey_services.effective_answers(session)
        industry = answers.get(rating.INDUSTRY_QUESTION)
        if industry is not None and industry.values():
            prefill["industry"] = industry.values()[0]
        other = answers.get(rating.INDUSTRY_OTHER_QUESTION)
        if other is not None and other.text_value and prefill.get("industry") == rating.OTHER_INDUSTRY:
            prefill["industry_other"] = other.text_value
        if prefill.get("industry") == rating.PROPERTY_INDUSTRY:  # the property questions are only for Property
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
        "industry": {
            "question": _industry_question_text(), "options": _choices(rating.industry_choices()),
            "other_value": rating.OTHER_INDUSTRY, "other_label": _industry_other_text(),
        },
        # Show property_link and size_range only while the industry answer is one of these (the server enforces it).
        "property_when": {"question": "industry", "any_of": [rating.PROPERTY_INDUSTRY]},
        "property_link": _choices(rating.choices(PROPERTY_LINK)), "size_range": _choices(rating.choices(SIZE)),
        "location": _choices(rating.choices(WHERE)), "bml_relationship": _choices(rating.choices(BML)),
        "prefill": prefill, "spa_interest": services.interest_snapshot(session),
    })


@login_not_required  # PUBLIC: see options()
@require_POST
@rate_limited_json("gold-apply-any", 120, 3600)  # generous cap on all posts; the real limit below counts valid ones only
def apply(request):
    """Submit an application. 201 with the reference, or 400 {"errors": {field: [messages]}}.
    Ten valid applications an hour per IP: mistakes while filling in the form do not use them up."""
    data = _payload(request)
    if data is None:
        return JsonResponse({"error": "Send JSON."}, status=400)
    if data.get(HONEYPOT_FIELD):  # a bot: pretend it worked, save nothing
        return JsonResponse({"reference": "GC-OK"}, status=201)
    form = GoldApplicationForm(data)
    if not form.is_valid():
        return JsonResponse({"errors": {k: [str(m) for m in v] for k, v in form.errors.items()}}, status=400)
    if not hit(APPLY_SCOPE, client_ip(request) or "unknown", APPLY_LIMIT, APPLY_WINDOW):
        return too_many_response(APPLY_WINDOW)
    session = journey_services.session_from_cookies(request.COOKIES, request.user)
    try:
        application, _ = services.submit_application(form.cleaned_data, session=session)
    except services.ApplicationsClosed:
        return JsonResponse({"error": "Applications are not open yet."}, status=403)
    return JsonResponse({"reference": application.reference, "message": "Thank you. We'll be in touch."}, status=201)
