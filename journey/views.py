"""Journey JSON endpoints. Public on purpose: visitors have no account yet. Protected by CSRF (Django's
middleware), a per-IP rate limit and a honeypot field. Logic lives in services.py and engine.py."""
import json

from django.conf import settings
from django.contrib.auth.decorators import login_not_required
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from common.ratelimit import rate_limited_json
from insights import visitors

from . import engine, services

COOKIE_NAME = services.COOKIE_NAME
COOKIE_MAX_AGE = 365 * 24 * 60 * 60  # one year
HONEYPOT_FIELD = "website"  # real people never see or fill this


def _session_for(request):
    """The visitor's session from the cookie, or a fresh one. Returns (session, created)."""
    referrer = request.GET.get("ref") or request.META.get("HTTP_REFERER", "")
    utm = {name: request.GET.get(name, "") for name in services.UTM_FIELDS}
    session, created = services.get_or_create_session(
        request.COOKIES.get(COOKIE_NAME),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        referrer=referrer,
        utm=utm,
        user=request.user,
    )
    if created:
        visitors.record_step(request, "started")  # one person once a day, however many sessions they open
    return session, created


def _with_cookie(response, session):
    response.set_cookie(
        COOKIE_NAME, session.key, max_age=COOKIE_MAX_AGE, httponly=True, samesite="Lax",
        secure=settings.SESSION_COOKIE_SECURE, path="/",
    )
    return response


def _body(request):
    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _bad(message, status=400, missing=None):
    body = {"error": message}
    if missing:
        body["missing"] = missing  # question keys that still need a choice
    return JsonResponse(body, status=status)


def _progress(session):
    return {
        "current_step": session.current_step,
        "furthest_step": session.furthest_step,
        "completed": session.completed,
        "next_step": services.next_screen(session),
    }


@login_not_required  # PUBLIC: visitors have no account yet (rate limited, CSRF cookie set here)
@ensure_csrf_cookie
@require_GET
@rate_limited_json("journey-state", 120, 60)
def state(request):
    """Session, screens with questions and options, saved answers and the current step (resume)."""
    session, _ = _session_for(request)
    return _with_cookie(JsonResponse(services.build_state(session)), session)


def _save_one(session, item):
    answer, changed = services.save_answer(
        session, item.get("question"), options=item.get("options"), text=item.get("text", ""),
        skipped=bool(item.get("skipped")),
    )
    return {"question": answer.question.key, "changed": changed}


@login_not_required  # PUBLIC: see state(). CSRF protected, rate limited, honeypot.
@require_POST
@rate_limited_json("journey-answer", 240, 60)
def answer(request):
    """Save one answer: {"question", "options": [...], "text", "skipped"}. Or {"answers": [...]} in one go
    (for browsers that block the cookie and post at the end). Repeating a request changes nothing."""
    data = _body(request)
    if data is None:
        return _bad("Send JSON.")
    session, _ = _session_for(request)
    if data.get(HONEYPOT_FIELD):  # a bot: pretend it worked, keep it out of the statistics
        type(session).objects.filter(pk=session.pk).update(is_bot=True)
        return _with_cookie(JsonResponse({"saved": True}), session)
    items = data["answers"] if isinstance(data.get("answers"), list) else [data]
    try:
        saved = [_save_one(session, item) for item in items if isinstance(item, dict)]
    except services.AnswerError as error:
        return _bad(str(error))
    state_now = services.build_state(session)
    visible = {q["key"]: q["visible"] for screen in state_now["screens"] for q in screen["questions"]}
    return _with_cookie(JsonResponse({"saved": True, "answers": saved, "visible": visible, **_progress(session)}), session)


@login_not_required  # PUBLIC: see state()
@require_POST
@rate_limited_json("journey-step", 240, 60)
def step(request):
    """Move: {"step": 2} or {"direction": "next" | "back"}. Remembered so a refresh resumes here."""
    data = _body(request)
    if data is None:
        return _bad("Send JSON.")
    session, _ = _session_for(request)
    try:
        services.set_step(session, step=data.get("step"), direction=data.get("direction"))
    except services.AnswerError as error:
        return _bad(str(error), missing=error.missing)
    return _with_cookie(JsonResponse(_progress(session)), session)


@login_not_required  # PUBLIC: see state()
@require_http_methods(["GET", "POST"])
@rate_limited_json("journey-result", 60, 60)
def result(request):
    """The suggested plan with reasons, the other plans and the Gold nudge.
    GET only reads (a link preview or a refresh changes nothing); POST also stores the suggestion and marks the
    journey as finished, which is what the page does when he reaches the result."""
    if request.method == "GET":
        session = services.session_from_cookies(request.COOKIES, request.user)
        if session is None:
            return _bad("No journey yet.", status=404)
        return JsonResponse(engine.preview(session))
    session, _ = _session_for(request)
    try:
        data = engine.complete(session)
        visitors.record_step(request, "finished")
        return _with_cookie(JsonResponse(data), session)
    except services.AnswerError as error:
        return _bad(str(error), missing=error.missing)


@login_not_required  # PUBLIC: see state()
@require_POST
@rate_limited_json("journey-restart", 20, 60)
def restart(request):
    """'Start again': a new empty session on the same device (new cookie), so the old answers, suggestion, statistics
    and any Gold application linked to it stay intact. Returns the fresh state: screen 1, no answers, no last suggestion."""
    old, _ = _session_for(request)
    fresh = services.create_session(
        request.META.get("HTTP_USER_AGENT", ""), referrer=old.referrer,
        utm={name: getattr(old, name) for name in services.UTM_FIELDS}, user=request.user,
    )
    visitors.record_step(request, "started")
    return _with_cookie(JsonResponse(services.build_state(fresh)), fresh)
