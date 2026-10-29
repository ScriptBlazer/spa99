"""Chat logic: guards (cap, limits), the price rule, history, the streamed reply and storage. Views stay thin.

The server decides what the model may know: prices are in the knowledge only when `prices_allowed` (the site's own price rule,
pages.access.memberships_visible, or a lead email given in this chat). A stray "£" from the model is cut off in code too."""
import hashlib
import json
import logging
import re
from datetime import timedelta
from decimal import Decimal

import anthropic
from django.conf import settings
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from common.audit import client_ip
from common.ratelimit import hit
from insights import visitors
from journey import services as journey_services
from pages.access import memberships_visible
from pages.links import short_url
from plans.models import SiteSettings
from system import defaults as system_defaults

from . import config, knowledge, llm
from .models import Conversation, FaqItem, Message
from .prompt import KNOWLEDGE_HEADER, MESSAGES, personality, system_rules

logger = logging.getLogger("spa99.chat")
abuse_logger = logging.getLogger("spa99.chat.abuse")

NEXT_STEPS = {"journey": ("Tailor your membership", "/journey/"), "register": ("Register", "/register/")}


# ---------- config the panel needs ----------

def handoff_links(reason=""):
    site = SiteSettings.load()
    email = site.contact_address
    return {"reason": reason, "whatsapp_url": short_url("chat", site, msg="rates"), "email": email,
            "mailto": f"mailto:{email}?subject=A%20question%20for%20Spa%2099" if email else ""}


def assistant_card(request=None):
    """What the panel shows about the assistant: {name, welcome_heading, welcome_line}."""
    cfg = config.get(request)
    return {"name": cfg.name, "welcome_heading": cfg.welcome_heading, "welcome_line": cfg.welcome_line}


def suggested_questions(limit=4):
    return list(FaqItem.objects.filter(visible=True, suggested=True).values_list("question", flat=True)[:limit])


# ---------- the cap and the limits ----------

def month_start(now=None):
    local = timezone.localtime(now or timezone.now())
    return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def spent_this_month_pence():
    total = Message.objects.filter(created_at__gte=month_start()).aggregate(total=Sum("cost_pence"))["total"]
    return Decimal(total or 0)


def cap_reached(request=None):
    cap = system_defaults.get(request).chat_monthly_cap_gbp
    return spent_this_month_pence() >= Decimal(cap) * 100


def daily_cap_reached(request=None):
    """Soft daily cap: a share of the monthly cap (System > Assistant > Limits, 5% by default), counted from midnight London. Hand-off only until tomorrow."""
    cap = system_defaults.get(request).chat_monthly_cap_gbp
    midnight = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    spent = Message.objects.filter(created_at__gte=midnight).aggregate(total=Sum("cost_pence"))["total"]
    return Decimal(spent or 0) >= Decimal(cap) * config.get(request).daily_cap_percent


def too_busy():
    """Too many new conversations this hour, whole site."""
    since = timezone.now() - timedelta(hours=1)
    return Conversation.objects.filter(created_at__gte=since, message_count__gte=1).count() >= settings.CHAT_MAX_CONVERSATIONS_PER_HOUR


def abuse(event, request, **detail):
    """An abuse signal in the log. The IP is hashed with the day's random salt (the visitor counter's), which is deleted the next
    day, so the log never holds an address and the hash cannot be recomputed. Nothing is stored in the database."""
    try:
        today = timezone.localdate()
        digest = hashlib.sha256(f"{visitors.todays_salt(today)}|{client_ip(request) or ''}".encode()).hexdigest()[:12]
    except Exception:  # noqa: BLE001 - logging must never break the chat
        digest = "unknown"
    abuse_logger.warning("chat abuse: %s visitor=%s %s", event, digest, " ".join(f"{k}={v}" for k, v in detail.items()))


def within_rate_limits(request, token):
    """Per browser (the page's chat cookie) and per IP: messages per 10 minutes and per day (System > Assistant > Limits)."""
    ip = client_ip(request) or "unknown"
    cfg = config.get(request)
    windows = ((cfg.rate_per_10_minutes, 600), (cfg.rate_per_day, 86400))
    for scope, who in (("browser", token or "none"), ("ip", ip)):
        for number, (limit, seconds) in enumerate(windows):
            if not hit(f"chat-{scope}-{number}", who, limit, seconds):
                abuse("rate_limited", request, scope=scope, window=seconds)
                return False
    return True


# ---------- what is not worth a model call ----------

CODE_CHARS = set("{}<>;[]$\\`|")
INJECTION = re.compile(
    r"ignore (all |any |the |your )?(previous|prior|above|earlier)|disregard (all |any |the |your )?(previous|prior|above|instructions)|"
    r"(system|developer|hidden|initial) (prompt|message|instructions)|your (instructions|rules|prompt)|jailbreak|developer mode|"
    r"act as|pretend (to be|you)|you are now|repeat (everything|the above|your)|reveal (your|the)", re.I)


def looks_like_code(text):
    """Pasted code or markup: a code fence, many code characters, or more lines than a question needs."""
    return "```" in text or sum(1 for c in text if c in CODE_CHARS) >= 6 or text.count("\n") >= settings.CHAT_MAX_LINES


def looks_like_injection(text):
    return bool(INJECTION.search(text))


# ---------- conversations ----------

def journey_session(request):
    return journey_services.session_from_cookies(request.COOKIES, getattr(request, "user", None))


def browser_hash(token):
    """What a conversation stores of the page cookie: a hash, so the id alone cannot continue someone else's chat."""
    return hashlib.sha256(f"chat-browser|{token}".encode()).hexdigest() if token else ""


def find_conversation(request, conversation_id, token=None):
    """The visitor's own conversation, or None (unknown id, or it belongs to someone else's account or browser)."""
    if not conversation_id:
        return None
    try:
        conversation = Conversation.objects.filter(pk=conversation_id).first()
    except (ValueError, TypeError):
        return None
    except Exception:  # noqa: BLE001 - a malformed id (ValidationError)
        return None
    if conversation is None:
        return None
    if conversation.browser_hash and conversation.browser_hash != browser_hash(token):
        return None
    user = request.user if request.user.is_authenticated else None
    if conversation.user_id and (user is None or user.pk != conversation.user_id):
        return None
    if conversation.session_id:
        session = journey_session(request)
        if session is None or session.pk != conversation.session_id:
            return None
    return conversation


def attach(conversation, request, session=None):
    """Link what is known about this browser (journey session, account); never replaces an existing link."""
    session = session or journey_session(request)
    changed = []
    if session is not None and conversation.session_id is None:
        conversation.session = session
        changed.append("session")
    if request.user.is_authenticated and conversation.user_id is None:
        conversation.user = request.user
        changed.append("user")
    if changed:
        conversation.save(update_fields=changed + ["updated_at"])


def prices_allowed(request, conversation):
    if hasattr(conversation, "_force_prices"):  # the System test console picks with or without prices
        return conversation._force_prices
    return bool(memberships_visible(request) or conversation.lead_email)


def pending_question(conversation):
    """True when the last thing in the chat is a price question that was answered with the email offer."""
    last = conversation.messages.order_by("-created_at", "-id").first()
    return bool(last and last.role == Message.ASSISTANT and last.offered_email)


DECLINED_STOPS = ("cap", "unavailable", "refusal", "off_topic", "closed")


def api_history(conversation):
    """The turns sent to Claude: plain text only, the last CHAT_HISTORY_MESSAGES, starting with a visitor message. Left out: the
    email-offer replies (the question is answered again after the email), declined (off-topic) turns with their canned replies, so
    pasted code or an injection phrase never reaches the model on a later turn, and our own hand-off lines."""
    rows = conversation.messages.filter(offered_email=False, off_topic=False).exclude(role=Message.ASSISTANT, stop_reason__in=DECLINED_STOPS)
    rows = list(rows.order_by("-created_at", "-id").values_list("role", "text")[:settings.CHAT_HISTORY_MESSAGES])
    rows.reverse()
    while rows and rows[0][0] != Message.USER:
        rows.pop(0)
    return [{"role": role, "content": text} for role, text in rows]


def lead_saved(conversation, session, email, consent, token=None):
    """The email given in the chat becomes a lead exactly as at the journey gate (journey.services.save_lead). The conversation is
    made only now (None = a new one), so a failed attempt leaves nothing behind. Returns the conversation.
    Raises journey_services.LeadError."""
    clean = journey_services.save_lead(session, email, consent)
    if conversation is None:
        conversation = Conversation.objects.create(session=session, browser_hash=browser_hash(token))
    conversation.lead_email = clean
    conversation.session = conversation.session or session
    conversation.save(update_fields=["lead_email", "session", "updated_at"])
    return conversation


# ---------- the streamed reply ----------

def sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _store(conversation, text, usage=None, stop_reason="", handoff=False, offered=False, off_topic=False):
    usage = usage or {}
    pence = llm.cost_pence(usage.get("input", 0), usage.get("output", 0), usage.get("cache_read", 0), usage.get("cache_write", 0))
    with transaction.atomic():
        Message.objects.create(conversation=conversation, role=Message.ASSISTANT, text=text, input_tokens=usage.get("input", 0),
                               output_tokens=usage.get("output", 0), cache_read_tokens=usage.get("cache_read", 0),
                               cache_write_tokens=usage.get("cache_write", 0), cost_pence=pence, stop_reason=stop_reason[:30],
                               flagged_handoff=handoff, offered_email=offered, off_topic=off_topic)
        conversation.total_cost_pence = Decimal(conversation.total_cost_pence) + pence
        conversation.last_at = timezone.now()
        conversation.save(update_fields=["total_cost_pence", "last_at", "updated_at"])
    conversation._reply_stored = True  # reply_events checks it when the visitor's connection drops
    return pence


def _done(conversation, ok, stop_reason="", **extra):
    left = max(getattr(conversation, "_max_messages", config.get().max_messages) - conversation.message_count, 0)
    return sse("done", {"conversation_id": str(conversation.pk), "ok": ok, "stop_reason": stop_reason, "messages_left": left, **extra})


def estimate_usage(chars):
    """A conservative bill for a model call whose usage never arrived (cut stream, timeout, closed connection): the request's size
    at 3 characters a token, uncached, plus the whole output cap. Caps can then never be outrun by dropping connections."""
    return {"input": chars // 3 + 1, "output": settings.CHAT_MAX_TOKENS}


def _ended(conversation, reason, message_key, error=False, usage=None):
    """A reply the server ends itself (cap, Anthropic down, refusal): the words, the hand-off buttons, done."""
    text = MESSAGES[message_key]
    _store(conversation, text, usage, stop_reason=reason, handoff=True)
    yield sse("error", {"reason": reason, "message": text}) if error else sse("delta", {"text": text})
    yield sse("handoff", handoff_links(reason))
    yield _done(conversation, False, reason)


def _off_topic_turn(conversation, text, usage=None, stop_reason="off_topic", handoff=False):
    """Record a declined turn. After CHAT_OFF_TOPIC_LIMIT of them the conversation is closed (flagged in the Office list).
    Returns True when it was closed. The visitor message just stored is marked too."""
    conversation.off_topic_count += 1
    closed = conversation.off_topic_count >= settings.CHAT_OFF_TOPIC_LIMIT
    conversation.ended_off_topic = closed or conversation.ended_off_topic
    conversation.save(update_fields=["off_topic_count", "ended_off_topic", "updated_at"])
    last_user = conversation.messages.filter(role=Message.USER).order_by("-created_at", "-id").first()
    if last_user:
        Message.objects.filter(pk=last_user.pk).update(off_topic=True)
    _store(conversation, text, usage, stop_reason, handoff=closed or handoff, off_topic=True)
    return closed


def _declined(request, conversation, why):
    """Off-topic without a model call (pasted code, an injection phrase): one polite line, counted, never sent to Claude."""
    abuse(why, request)
    closed = _off_topic_turn(conversation, MESSAGES["off_topic"])
    yield sse("delta", {"text": MESSAGES["off_topic"]})
    yield from _after_decline(conversation, closed)


def _after_decline(conversation, closed):
    if closed:
        yield sse("handoff", handoff_links("off_topic_limit"))
        yield _done(conversation, False, "off_topic", off_topic=True, ended=True)
    else:
        yield _done(conversation, True, "off_topic", off_topic=True, ended=False, suggested=suggested_questions())


def reply_events(request, conversation):
    """SSE strings for one reply. Never raises: any failure becomes an error or hand-off event. If the visitor's connection drops
    (the generator is closed) after the model was called, the reply is still stored and billed (known usage or an estimate)."""
    conversation._reply_stored, conversation._billing = False, None
    conversation._max_messages = config.get(request).max_messages
    try:
        yield from _reply(request, conversation)
    except GeneratorExit:
        billing = conversation._billing
        if billing and not conversation._reply_stored:
            text = "".join(billing["emitted"]).strip() or MESSAGES["unavailable"]
            _store(conversation, text, billing["usage"] or estimate_usage(billing["chars"]), "aborted", handoff=False)
        raise


def _reply(request, conversation):
    if conversation.ended_off_topic:  # closed: no model call, buttons only
        yield sse("delta", {"text": MESSAGES["closed"]})
        yield sse("handoff", handoff_links("off_topic_limit"))
        yield _done(conversation, False, "closed", ended=True)
        return
    if cap_reached(request) or daily_cap_reached(request):
        conversation.ended_by_cap = True
        conversation.save(update_fields=["ended_by_cap", "updated_at"])
        abuse("cap", request)
        yield from _ended(conversation, "cap", "cap")
        return
    last = conversation.messages.filter(role=Message.USER).order_by("-created_at", "-id").first()
    if last and looks_like_code(last.text):
        yield from _declined(request, conversation, "code")
        return
    if last and looks_like_injection(last.text):
        yield from _declined(request, conversation, "injection")
        return
    prices = prices_allowed(request, conversation)
    text, _digest = knowledge.build(prices)
    emitted, suppressed, final = [], False, None
    history = api_history(conversation)
    voice = personality(config.get(request))
    chars = len(system_rules()) + len(voice) + len(KNOWLEDGE_HEADER) + len(text) + sum(len(m["content"]) for m in history)
    conversation._billing = {"emitted": emitted, "usage": None, "chars": chars}  # from here the model call is billed, whatever happens
    try:
        for kind, payload in llm.stream_reply(system_rules(), KNOWLEDGE_HEADER + text, history, voice):
            if kind == "final":
                final = payload
                conversation._billing["usage"] = payload["usage"]
                continue
            if suppressed:
                continue
            if not prices and "£" in payload:  # hard rule: no price before an email, whatever the model wrote
                payload, suppressed = payload.split("£")[0], True
            if payload:
                emitted.append(payload)
                yield sse("delta", {"text": payload})
    except (anthropic.RateLimitError, anthropic.APIStatusError, anthropic.APIConnectionError, TimeoutError) as error:
        logger.warning("Chat reply failed: %s", type(error).__name__)
        # A refusal to connect costs nothing; a stream cut part-way, or a timeout, was billed
        billed = bool(emitted) or isinstance(error, TimeoutError) or (isinstance(error, anthropic.APIStatusError) and bool(emitted))
        yield from _ended(conversation, "unavailable", "unavailable", error=True, usage=estimate_usage(chars) if billed else None)
        return
    except Exception:  # noqa: BLE001 - the visitor must never meet an error page
        logger.exception("Chat reply failed")
        yield from _ended(conversation, "unavailable", "unavailable", error=True, usage=estimate_usage(chars))
        return
    if final is None or final["stop_reason"] == "refusal":
        closed = _off_topic_turn(conversation, MESSAGES["refusal"], (final or {}).get("usage"), "refusal", handoff=True)
        yield sse("error", {"reason": "refusal", "message": MESSAGES["refusal"]})
        yield sse("handoff", handoff_links("refusal"))
        yield _done(conversation, False, "refusal", ended=closed)
        return
    names = [name for name, _ in final["tools"]]
    handoff = "show_handoff" in names
    offer = (not prices) and ("offer_email" in names or suppressed)
    steps = [s for name, args in final["tools"] if name == "suggest_next_steps" for s in args.get("steps", []) if s in NEXT_STEPS][:2]
    reply = "".join(emitted).strip()
    if "off_topic" in names:
        extra = "" if reply else MESSAGES["off_topic"]
        if extra:
            yield sse("delta", {"text": extra})
        closed = _off_topic_turn(conversation, reply + extra, final["usage"], final["stop_reason"])
        yield from _after_decline(conversation, closed)
        return
    extra = ""
    if suppressed:
        extra = ("\n\n" if reply else "") + MESSAGES["prices"]
    elif final["stop_reason"] == "max_tokens":  # cut at the output cap: end cleanly, never continue
        extra = "..." if reply else MESSAGES["too_long"]
        handoff = True
    elif not reply:
        extra = MESSAGES["prices"] if offer else MESSAGES["handoff"] if handoff else MESSAGES["empty"]
        handoff = handoff or not offer
    if extra:
        yield sse("delta", {"text": extra})
    reply += extra
    _store(conversation, reply, final["usage"], final["stop_reason"], handoff=handoff, offered=offer)
    if steps:
        yield sse("next_steps", {"steps": [{"key": key, "label": NEXT_STEPS[key][0], "url": NEXT_STEPS[key][1]} for key in dict.fromkeys(steps)]})
    if handoff:
        yield sse("handoff", handoff_links("too_long" if final["stop_reason"] == "max_tokens" else "asked"))
    if offer:
        yield sse("offer_email", {"pending": True})
    yield _done(conversation, True, final["stop_reason"])


# ---------- deleting and exporting (UK GDPR, 90 days) ----------

def prune(days=None, dry_run=False, now=None):
    """Delete conversations (and their messages) not touched for `days` (default CHAT_RETENTION_DAYS). Returns the number."""
    days = settings.CHAT_RETENTION_DAYS if days is None else days
    old = Conversation.objects.filter(last_at__lt=(now or timezone.now()) - timedelta(days=days))
    count = old.count()
    if count and not dry_run:
        old.delete()
        logger.info("Chat: deleted %s conversation(s) older than %s days", count, days)
    return count


def _person_filter(user=None, email=None):
    query = Q(pk__in=[])
    if user is not None:
        query |= Q(user=user) | Q(session__user=user)
    if email:
        query |= Q(lead_email__iexact=email)
    return query


def export_conversations(user=None, email=None):
    rows = []
    for conversation in Conversation.objects.filter(_person_filter(user, email)).order_by("created_at"):
        rows.append({"started_at": conversation.created_at.isoformat(), "lead_email": conversation.lead_email,
                     "messages": [{"role": m.role, "text": m.text, "at": m.created_at.isoformat()} for m in conversation.messages.all()]})
    return rows


def erase_conversations(user=None, email=None):
    """Delete a person's chats (by account, journey session of the account, or the email given in the chat). Returns the number."""
    return Conversation.objects.filter(_person_filter(user, email)).delete()[1].get("chat.Conversation", 0)
