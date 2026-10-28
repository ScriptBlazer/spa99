"""Chat endpoints (public site only: they are in config/urls.py, not in the staff hosts). Short views; logic in services.py.
CSRF is Django's middleware (the token comes from GET /chat/state/ or any page with a form). The reply is a streamed
text/event-stream: a sync gunicorn worker is busy for the seconds the reply takes (max_tokens and a wall-clock timeout bound it)."""
import json
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth.decorators import login_not_required
from django.core import signing
from django.http import Http404, JsonResponse, StreamingHttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.crypto import get_random_string
from django.views.decorators.http import require_GET, require_POST

from common.ratelimit import rate_limited_json
from common.useragent import device_type
from journey import services as journey_services
from journey import views as journey_views
from pages.access import memberships_visible

from . import llm, services
from .models import Conversation, Message

HONEYPOT_FIELD = journey_views.HONEYPOT_FIELD


def _json(request):
    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _refuse(code, message, status, **extra):
    return JsonResponse({"error": message, "code": code, "handoff": services.handoff_links(code), **extra}, status=status)


def _page_cookie(request):
    """The chat cookie value if it is ours and fresh (set by GET /chat/state/ when the panel opens), else None. It proves the
    request comes from the page, and names the browser for the rate limit."""
    try:
        return signing.TimestampSigner(salt="chat-page").unsign(request.COOKIES.get(settings.CHAT_COOKIE, ""), max_age=settings.CHAT_COOKIE_SECONDS)
    except signing.BadSignature:
        return None


def _same_origin(request):
    origin = request.META.get("HTTP_ORIGIN")
    if origin:
        return urlparse(origin).netloc == request.get_host()
    return request.META.get("HTTP_SEC_FETCH_SITE", "") in ("", "same-origin", "same-site", "none")


def _gate(request):
    """None when the request may go on; else the refusal. Bots, other sites and requests that never opened the panel get no answer
    and, above all, no model call."""
    if device_type(request.META.get("HTTP_USER_AGENT", "")) == "bot":
        services.abuse("bot", request)
        return JsonResponse({"error": "Not available."}, status=403)
    if not _same_origin(request):
        services.abuse("cross_origin", request)
        return JsonResponse({"error": "Not available."}, status=403)
    if _page_cookie(request) is None:
        services.abuse("no_page_cookie", request)
        return JsonResponse({"error": "Open the chat first.", "code": "no_session"}, status=403)
    return None


def config(request):
    """What the panel needs, as plain data (also used by the state endpoint)."""
    return {"enabled": llm.enabled(), "max_message_chars": settings.CHAT_MAX_MESSAGE_CHARS, "honeypot_field": HONEYPOT_FIELD, "max_messages": settings.CHAT_MAX_MESSAGES,
            "suggested": services.suggested_questions(), "handoff": services.handoff_links(), "prices_visible": memberships_visible(request),
            "capped": services.cap_reached(request) if llm.enabled() else False, "privacy_url": "/privacy/"}


@login_not_required  # PUBLIC: visitors have no account. Sets the CSRF cookie the POST endpoints need.
@ensure_csrf_cookie
@require_GET
@never_cache
@rate_limited_json("chat-state", 120, 60)
def state(request):
    if not llm.enabled():
        raise Http404
    response = JsonResponse(config(request))
    if _page_cookie(request) is None:
        value = signing.TimestampSigner(salt="chat-page").sign(get_random_string(24))
        response.set_cookie(settings.CHAT_COOKIE, value, max_age=settings.CHAT_COOKIE_SECONDS, httponly=True, samesite="Lax",
                            secure=settings.SESSION_COOKIE_SECURE, path="/chat/")
    return response


@login_not_required  # PUBLIC: see state(). CSRF protected, rate limited per browser and per IP, bots refused, capped by length and count.
@require_POST
def message(request):
    """{"conversation_id"?, "message"} or {"conversation_id", "retry": true} (answer the pending question again after the email)."""
    if not llm.enabled():
        raise Http404
    refused = _gate(request)
    if refused:
        return refused
    data = _json(request)
    if data is None:
        return JsonResponse({"error": "Send JSON."}, status=400)
    if data.get(HONEYPOT_FIELD):  # a bot filled the hidden field: pretend, no model call
        services.abuse("honeypot", request)
        return JsonResponse({"error": "Not available."}, status=403)
    if not services.within_rate_limits(request, _page_cookie(request)):
        return _refuse("rate_limited", "Too many messages. Please wait a few minutes.", 429)
    token = _page_cookie(request)
    conversation = services.find_conversation(request, data.get("conversation_id"), token)
    retry = data.get("retry") is True
    if retry:
        if conversation is None or not services.pending_question(conversation):
            return JsonResponse({"error": "Nothing to answer again.", "code": "nothing_pending"}, status=400)
        if not services.prices_allowed(request, conversation):  # no email yet: answering again would only loop on the model
            services.abuse("retry_without_email", request)
            return JsonResponse({"error": "Leave your email to see prices.", "code": "needs_email"}, status=403)
        if conversation.message_count >= settings.CHAT_MAX_MESSAGES:  # a retry is a message too
            return _refuse("conversation_full", "This conversation is full.", 409)
        conversation.message_count += 1
        conversation.save(update_fields=["message_count", "updated_at"])
    else:
        text = data.get("message")
        text = text.strip() if isinstance(text, str) else ""
        if not text:
            return JsonResponse({"error": "Write a question first.", "code": "empty"}, status=400)
        if len(text) > settings.CHAT_MAX_MESSAGE_CHARS:
            return JsonResponse({"error": "That is the limit for one message.", "code": "too_long", "max_length": settings.CHAT_MAX_MESSAGE_CHARS}, status=400)
        if conversation is not None and conversation.message_count >= settings.CHAT_MAX_MESSAGES:
            return _refuse("conversation_full", "This conversation is full.", 409)
        if conversation is None:
            if services.too_busy():
                services.abuse("busy", request)
                return _refuse("busy", "Our assistant is busy just now.", 503)
            conversation = Conversation.objects.create(browser_hash=services.browser_hash(token))
        Message.objects.create(conversation=conversation, role=Message.USER, text=text)
        conversation.message_count += 1
        conversation.save(update_fields=["message_count", "updated_at"])
    services.attach(conversation, request)
    response = StreamingHttpResponse(services.reply_events(request, conversation), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache, no-transform"
    response["X-Accel-Buffering"] = "no"  # a proxy must not hold the stream back
    response["X-Chat-Conversation"] = str(conversation.pk)
    return response


@login_not_required  # PUBLIC: see state(). The email for prices: a lead exactly as at the journey gate.
@require_POST
@rate_limited_json("chat-email", 20, 60)
def email(request):
    """{"conversation_id"?, "email", "consent": true}. 200 {"saved", "conversation_id", "retry"}; 400 {"errors": {"email", "consent"}}.
    `retry` true: send POST /chat/message/ {conversation_id, retry: true} and the pending price question is answered, with prices."""
    if not llm.enabled():
        raise Http404
    refused = _gate(request)
    if refused:
        return refused
    data = _json(request)
    if data is None:
        return JsonResponse({"error": "Send JSON."}, status=400)
    if data.get(HONEYPOT_FIELD):
        services.abuse("honeypot", request)
        return JsonResponse({"saved": True, "retry": False})  # a bot: pretend, store nothing
    token = _page_cookie(request)
    conversation = services.find_conversation(request, data.get("conversation_id"), token)
    if request.user.is_authenticated:  # signed in: his account is his address and prices are already shown
        return JsonResponse({"saved": True, "conversation_id": str(conversation.pk) if conversation else None,
                             "retry": bool(conversation and services.pending_question(conversation))})
    session, _ = journey_views._session_for(request)  # the journey session of this browser (made if there is none), as at the gate
    try:  # a conversation is only made once the lead is saved: a failed attempt leaves nothing behind
        conversation = services.lead_saved(conversation, session, data.get("email"), data.get("consent"), token)
    except journey_services.LeadError as error:
        return journey_views._with_cookie(JsonResponse({"errors": error.errors}, status=400), session)
    body = {"saved": True, "conversation_id": str(conversation.pk), "retry": services.pending_question(conversation)}
    return journey_views._with_cookie(JsonResponse(body), session)
