"""Gold JSON endpoints. Public on purpose: applying creates no account. CSRF protected, rate limited, honeypot."""
import json

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_not_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from common.audit import client_ip
from common.ratelimit import hit, rate_limited_json, too_many_response
from journey import engine as journey_engine
from journey import services as journey_services
from journey.models import Question

from . import services
from . import invites
from .forms import GoldApplicationForm, GoldSetupForm
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


# ---------- account setup from the invite ----------

SETUP_SCOPE, SETUP_LIMIT, SETUP_WINDOW = "gold-invite", 20, 3600


def _invalid_link(request, status=410):
    return render(request, "gold/invite_invalid.html", status=status)


@login_not_required  # PUBLIC: the link in the approval email (signed, 14 days, single use, rate limited)
@require_http_methods(["GET", "POST"])
def invite_setup(request, token):
    """GET shows the setup form (nothing is used up by opening it); POST creates the account and signs him in."""
    if not hit(SETUP_SCOPE, client_ip(request) or "unknown", SETUP_LIMIT, SETUP_WINDOW):
        return render(request, "gold/invite_invalid.html", {"throttled": True}, status=429)
    status, invite = invites.read_invite(token)
    if status != invites.OK:
        return _invalid_link(request)
    application = invite.application
    form = GoldSetupForm(request.POST or None, application=application, initial={"marketing_opt_in": application.marketing_consent})
    if request.method == "POST" and form.is_valid():
        try:
            user = invites.accept_invite(token, form.cleaned_data)
        except invites.InviteError as error:
            return render(request, "gold/invite_invalid.html", {"text": error.text}, status=410)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, "Welcome to Spa 99. Your Gold Card is active.")
        return redirect("account")
    return render(request, "gold/invite_setup.html", {"form": form, "application": application},
                  status=400 if request.method == "POST" else 200)
