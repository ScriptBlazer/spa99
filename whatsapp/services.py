"""WhatsApp logic: contacts and who they are, the 24-hour window, sending (queued), inbound messages, delivery ticks, templates, what the
Office pages need, the timeline lines, and export / erasure. The views stay thin and call these. Twilio itself is `twilio_api`."""
import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone

import phonenumbers
from django.conf import settings
from django.core import signing
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, F, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from django.utils.safestring import mark_safe

from common.tasks import enqueue

from . import errors, formatting, imagesize, twilio_api
from .models import TEMPLATE_PREFIX, Contact, ContactRead, Message, Template

logger = logging.getLogger("spa99.whatsapp")

WINDOW = timedelta(hours=24)
EPOCH = datetime(1970, 1, 1, tzinfo=dt_timezone.utc)
DUPLICATE_WINDOW = timedelta(seconds=10)
STOP_WORDS = {"STOP", "STOPALL", "UNSUBSCRIBE", "END", "QUIT", "CANCEL"}  # Twilio's own list; a whole message, any case
START_WORDS = {"START", "UNSTOP"}  # a clear restart word, nothing vaguer: "yes" or a normal reply does NOT clear a STOP
RANK = {Message.QUEUED: 0, Message.SENT: 1, Message.DELIVERED: 2, Message.READ: 3}
TWILIO_STATUS = {"accepted": "queued", "scheduled": "queued", "queued": "queued", "sending": "queued", "sent": "sent", "delivered": "delivered",
                 "read": "read", "failed": "failed", "undelivered": "undelivered"}
SEND_TYPES = {"image/jpeg": (Message.IMAGE, b"\xff\xd8\xff", ".jpg"), "image/png": (Message.IMAGE, b"\x89PNG", ".png"), "application/pdf": (Message.DOCUMENT, b"%PDF-", ".pdf")}
DEFAULT_LABELS = {"spa99_lead_follow_up": {"1": "First name"}}  # what each variable of a template is called in the form (kept across syncs)

DONE, EMPTY, TOO_LONG, WINDOW_CLOSED, OPTED_OUT, DUPLICATE = "done", "empty", "too_long", "window_closed", "opted_out", "duplicate"
NOT_CONFIGURED, BAD_FILE, TOO_BIG, BAD_TEMPLATE, MISSING_VARIABLES, NOT_RETRYABLE = "not_configured", "bad_file", "too_big", "bad_template", "missing_variables", "not_retryable"
WORDS = {EMPTY: "Write a message first.", TOO_LONG: "That message is too long.", WINDOW_CLOSED: "The 24-hour window has closed. Send a template to reopen it.",
         OPTED_OUT: "He replied STOP, so he gets no more messages.", DUPLICATE: "That message was just sent.", NOT_CONFIGURED: "WhatsApp is not set up yet.",
         BAD_FILE: "Photos or PDFs only.", TOO_BIG: "Photos up to 5 MB, PDFs up to 16 MB.", BAD_TEMPLATE: "That template cannot be sent.",
         MISSING_VARIABLES: "Fill in every field of the template.", NOT_RETRYABLE: "That message cannot be sent again."}


# ---------- numbers ----------

def to_e164(value):
    """'whatsapp:+447700900123', '+44 7700 900123' or '07700 900123' -> '+447700900123'; '' when it is not a valid number."""
    raw = (value or "").strip()
    if raw.lower().startswith("whatsapp:"):
        raw = raw[9:].strip()
    try:
        number = phonenumbers.parse(raw, "GB")
    except phonenumbers.NumberParseException:
        return ""
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164) if phonenumbers.is_valid_number(number) else ""


def sender():
    return to_e164(settings.TWILIO_WHATSAPP_FROM)


def configured():
    return twilio_api.configured()


def now():
    return timezone.now()


# ---------- contacts and who they are ----------

def resolve_links(contact, save=True):
    """Find who owns this number: an account (User.mobile), a lead (the mobile given at the email step or typed by staff), a Gold
    application. The name staff, the lead or the account gave wins over his WhatsApp profile name."""
    from gold.models import GoldApplication
    from journey.models import JourneySession
    from users.models import User

    user = User.objects.filter(mobile=contact.phone).first()
    session = JourneySession.objects.filter(lead_mobile=contact.phone, is_bot=False).exclude(lead_email="").order_by("-created_at").first()
    application = GoldApplication.objects.filter(mobile=contact.phone).order_by("-created_at").first()
    lead_email = (session.lead_email or "").lower() if session is not None and user is None else ""
    name = ""
    if user is not None:
        name = (user.get_full_name() or "").strip()
    if not name and session is not None:
        named = JourneySession.objects.filter(lead_email__iexact=session.lead_email, is_bot=False).exclude(lead_first_name="").order_by("-created_at").first()
        name = named.lead_first_name if named else ""
    if not name and application is not None:
        name = application.full_name
    contact.user, contact.lead_email, contact.application, contact.name = user, lead_email, application, name[:100]
    if save:
        contact.save(update_fields=["user", "lead_email", "application", "name"])
    return contact


def relink(*phones):
    """A mobile was added or changed: refresh the links and names of the chats on those numbers."""
    for contact in Contact.objects.filter(phone__in=[p for p in phones if p]):
        resolve_links(contact)


def get_or_create_contact(phone, profile_name=""):
    contact, created = Contact.objects.get_or_create(phone=phone)
    changed = False
    if profile_name and contact.profile_name != profile_name[:100]:
        contact.profile_name, changed = profile_name[:100], True
    if created:
        resolve_links(contact, save=False)
        changed = True
    if changed:
        contact.save()
    return contact


def owner_of_phone(phone, exclude_email="", exclude_user=None):
    """Who already has this number ({name, url}), or None. Used to refuse the same number on two people (two people would share one chat)."""
    from journey.models import JourneySession
    from users.models import User

    if not phone:
        return None
    users = User.objects.filter(mobile=phone)
    if exclude_user is not None:
        users = users.exclude(pk=exclude_user.pk)
    other = users.filter(interest__isnull=False).first() or users.first()
    if other is not None:
        return {"name": other.get_full_name() or other.email, "url": _office("office_person", other.pk) if hasattr(other, "interest") else ""}
    sessions = JourneySession.objects.filter(lead_mobile=phone, is_bot=False).exclude(lead_email="")
    if exclude_email:
        sessions = sessions.exclude(lead_email__iexact=exclude_email)
    if exclude_user is not None and exclude_user.email:
        sessions = sessions.exclude(lead_email__iexact=exclude_user.email)
    found = sessions.order_by("-created_at").first()
    if found is not None:
        return {"name": found.lead_first_name or found.lead_email.lower(), "url": _office("office_lead", found.pk)}
    return None


def _office(name, *args):
    return reverse(name, args=args, urlconf="config.urls_office")


# ---------- the 24-hour window ----------

def window_ends_at(contact):
    return contact.last_inbound_at + WINDOW if contact.last_inbound_at else None


def window_open(contact, at=None):
    ends = window_ends_at(contact)
    return bool(ends and ends > (at or now()))


def window_state(contact, at=None):
    """open | closed | opted_out | empty (nothing yet) | template_waiting (a template went out and he has not replied)."""
    if contact.opted_out:
        return "opted_out"
    if window_open(contact, at):
        return "open"
    if not contact.last_message_at:
        return "empty"
    if contact.last_inbound_at is None:
        return "template_waiting"
    return "closed"


# ---------- unread (per staff member) ----------

def _read_after(user, contact_ref):
    return Coalesce(Subquery(ContactRead.objects.filter(contact=OuterRef(contact_ref), user=user).values("read_at")[:1]), Value(EPOCH))


def unread_counts(user, contact_ids):
    """{contact id: unread inbound messages} for the chats on screen: one query."""
    rows = (Message.objects.filter(contact_id__in=list(contact_ids), direction=Message.IN).annotate(ra=_read_after(user, "contact_id"))
            .filter(created_at__gt=F("ra")).values("contact_id").annotate(n=Count("id")))
    return {r["contact_id"]: r["n"] for r in rows}


def unread_total(user):
    """How many chats have unread messages (the navigation badge counts chats, like WhatsApp)."""
    return (Contact.objects.annotate(ra=_read_after(user, "pk"))
            .filter(Exists(Message.objects.filter(contact=OuterRef("pk"), direction=Message.IN, created_at__gt=OuterRef("ra")))).count())


def first_unread(user, contact):
    """(count, id of the first unread message or None) for the thread's unread divider."""
    after = ContactRead.objects.filter(contact=contact, user=user).values_list("read_at", flat=True).first() or EPOCH
    rows = list(Message.objects.filter(contact=contact, direction=Message.IN, created_at__gt=after).order_by("id").values_list("id", flat=True))
    return len(rows), (rows[0] if rows else None)


def mark_read(contact, user):
    ContactRead.objects.update_or_create(contact=contact, user=user, defaults={"read_at": now()})


# ---------- sending ----------

def _clean_variable(value):
    return " ".join(str(value or "").replace("\x00", "").split())[:200]  # WhatsApp refuses newlines, tabs and long runs of spaces in variables


def fill_body(body, variables):
    """The template text with its {{1}} style variables filled in (what goes in the chat)."""
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: str(variables.get(m.group(1), "")), body or "")


def template_html(template):
    """The template text as safe, formatted HTML with every variable as <span data-var="1" data-label="First name">[First name]</span>.
    The page only sets each span's textContent as he types, so it needs no formatter of its own."""
    spans = {}

    def hold(match):
        key = match.group(1)
        spans[key] = f'<span data-var="{escape(key)}" data-label="{escape(label_for(template, key))}">[{escape(label_for(template, key))}]</span>'
        return f"{key}"

    body = re.sub(r"\{\{\s*(\w+)\s*\}\}", hold, template.body or "")
    out = str(formatting.render(body))
    return mark_safe(re.sub("(\\w+)", lambda m: spans[m.group(1)], out))


def label_for(template, key):
    return (template.variable_labels or {}).get(str(key)) or f"Detail {key}"


def _queue(contact, actor, kind, body="", **fields):
    """Record a queued outgoing message and hand it to the worker. Returns (DONE, message) or (DUPLICATE, None)."""
    since = now() - DUPLICATE_WINDOW
    recent = Message.objects.filter(contact=contact, direction=Message.OUT, kind=kind, body=body, created_at__gte=since, media_key=fields.get("media_key", ""))
    recent = recent.filter(author=actor) if getattr(actor, "pk", None) else recent.filter(author__isnull=True)
    if recent.exists():
        return DUPLICATE, None
    from gold import audit  # label_for: "Name (email)"

    with transaction.atomic():
        message = Message.objects.create(contact=contact, direction=Message.OUT, kind=kind, body=body, status=Message.QUEUED,
                                         author=actor if getattr(actor, "pk", None) else None, author_label=audit.label_for(actor), **fields)
        Contact.objects.filter(pk=contact.pk).update(last_message_at=message.created_at, last_preview=_preview(message), last_kind=kind, last_direction=Message.OUT)
    _enqueue_send(message)
    return DONE, message


def _enqueue_send(message):
    try:
        enqueue("whatsapp.tasks.send_message", message.pk)
    except Exception:  # noqa: BLE001 - recorded as queued; the "Try again" button resends
        logger.exception("Could not queue WhatsApp message %s", message.pk)


def _blocked(contact, needs_window):
    if not configured():
        return NOT_CONFIGURED
    if contact.opted_out:
        return OPTED_OUT
    if needs_window and not window_open(contact):
        return WINDOW_CLOSED
    return None


def send_text(contact, actor, body):
    """Free text inside the 24-hour window. Returns (result, message)."""
    body = (body or "").replace("\x00", "").strip()
    if not body:
        return EMPTY, None
    if len(body) > settings.WHATSAPP_MAX_BODY:
        return TOO_LONG, None
    blocked = _blocked(contact, needs_window=True)
    return (blocked, None) if blocked else _queue(contact, actor, Message.TEXT, body)


def send_media(contact, actor, upload, caption=""):
    """A photo (JPEG or PNG, 5 MB) or a PDF (16 MB) inside the window, with an optional caption. The file goes to the default storage
    (S3 on live); Twilio fetches it from a signed, expiring link. Returns (result, message)."""
    caption = (caption or "").replace("\x00", "").strip()
    if len(caption) > settings.WHATSAPP_MAX_BODY:
        return TOO_LONG, None
    blocked = _blocked(contact, needs_window=True)
    if blocked:
        return blocked, None
    data = upload.read(settings.WHATSAPP_MAX_FILE_BYTES + 1)
    kind = None
    for content_type, (found, magic, extension) in SEND_TYPES.items():  # the file's own first bytes decide, not its name or declared type
        if data.startswith(magic):
            kind, media_type, ext = found, content_type, extension
    if kind is None:
        return BAD_FILE, None
    if len(data) > (settings.WHATSAPP_MAX_IMAGE_BYTES if kind == Message.IMAGE else settings.WHATSAPP_MAX_FILE_BYTES):
        return TOO_BIG, None
    width, height = imagesize.size_of(data) if kind == Message.IMAGE else (None, None)
    key = default_storage.save(f"whatsapp/{contact.pk}/{uuid.uuid4().hex}{ext}", ContentFile(data))
    name = re.sub(r"[^\w .()-]", "_", (getattr(upload, "name", "") or f"file{ext}").rsplit("/", 1)[-1])[:200] or f"file{ext}"
    result, message = _queue(contact, actor, kind, caption, media_key=key, media_type=media_type, media_filename=name, media_size=len(data), media_width=width, media_height=height)
    if result != DONE:
        default_storage.delete(key)
    return result, message


def send_template(contact, actor, template_id, variables):
    """An approved `spa99_` template, any time (not after STOP). `variables` is {key: text}. Returns (result, message); MISSING_VARIABLES
    puts the empty keys in the message's place as a list: (MISSING_VARIABLES, [keys])."""
    blocked = _blocked(contact, needs_window=False)
    if blocked:
        return blocked, None
    template = Template.objects.filter(pk=template_id).first()
    if template is None or not template.sendable:  # enforced here, whatever a page posted: BML templates never go from Spa 99
        return BAD_TEMPLATE, None
    values = {str(k): _clean_variable(variables.get(str(k))) for k in template.variables}
    empty = [k for k, v in values.items() if not v]
    if empty:
        return MISSING_VARIABLES, empty
    return _queue(contact, actor, Message.TEMPLATE, fill_body(template.body, values), template=template, template_variables=values)


def retry(message, actor):
    """Send a failed message again (the same bubble). Returns (result, message)."""
    if message.direction != Message.OUT or message.status not in Message.BAD + (Message.QUEUED,):
        return NOT_RETRYABLE, None
    if message.status == Message.QUEUED and message.claimed_at is None:
        return NOT_RETRYABLE, None  # still waiting for the worker
    blocked = _blocked(message.contact, needs_window=message.kind != Message.TEMPLATE)
    if blocked:
        return blocked, None
    Message.objects.filter(pk=message.pk).update(status=Message.QUEUED, error_code="", error_message="", twilio_sid=None, claimed_at=None, updated_at=now())
    message.refresh_from_db()
    _enqueue_send(message)
    return DONE, message


def media_url(message):
    """The signed, expiring public link Twilio fetches an outgoing file from (the site host, no sign-in; 1 hour)."""
    token = signing.TimestampSigner(salt="whatsapp-media").sign(str(message.pk))
    return f"{settings.SITE_URL}{reverse('whatsapp_media', args=[token], urlconf='config.urls')}"


def message_for_media_token(token, max_age=3600):
    try:
        pk = signing.TimestampSigner(salt="whatsapp-media").unsign(token, max_age=max_age)
    except signing.BadSignature:
        return None
    return Message.objects.filter(pk=pk, direction=Message.OUT).exclude(media_key="").first()


def status_callback_url():
    return f"{settings.SITE_URL}{reverse('whatsapp_status', urlconf='config.urls')}"


def deliver(message):
    """The worker's side of a send: one Twilio call, and the outcome written on the message. Never sends twice."""
    if not Message.objects.filter(pk=message.pk, status=Message.QUEUED, claimed_at__isnull=True).update(claimed_at=now()):
        return "skipped"
    message.refresh_from_db()
    if not configured():
        return _fail(message, "not_configured", "WhatsApp is not set up.")
    try:
        sent = twilio_api.send_message(
            message.contact.phone, body=message.body if message.kind != Message.TEMPLATE else "",
            content_sid=message.template.content_sid if message.kind == Message.TEMPLATE and message.template_id else "",
            content_variables=json.dumps(message.template_variables) if message.kind == Message.TEMPLATE else "",
            media_url=media_url(message) if message.media_key else "", status_callback=status_callback_url())
    except twilio_api.TwilioError as error:
        logger.warning("WhatsApp send failed (message %s, code %s, http %s)", message.pk, error.code or "-", error.status)
        return _fail(message, error.code or (f"http_{error.status}" if error.status else "network"), str(error), error.status)
    status = TWILIO_STATUS.get(str(sent.get("status") or "queued"), "queued")
    update = {"twilio_sid": sent.get("sid") or None, "updated_at": now()}
    # a delivery tick may have arrived before this save: never move a message backwards
    current = Message.objects.filter(pk=message.pk).values_list("status", flat=True).first()
    if current == Message.QUEUED and status != Message.QUEUED:
        update["status"] = status
    if status == Message.SENT:
        update["sent_at"] = now()
    Message.objects.filter(pk=message.pk).update(**update)
    return "sent"


def _fail(message, code, text, http_status=None):
    Message.objects.filter(pk=message.pk).update(status=Message.FAILED, error_code=str(code)[:20], error_message=text[:300], updated_at=now())
    return "failed"


# ---------- inbound and delivery ticks (called by the webhooks) ----------

def kind_of(content_type):
    content_type = (content_type or "").lower()
    if content_type.startswith("image/"):
        return Message.IMAGE
    if content_type == "application/pdf":
        return Message.DOCUMENT
    if content_type.startswith("audio/"):
        return Message.AUDIO
    if content_type.startswith("video/"):
        return Message.VIDEO
    return Message.FILE


def _preview(message):
    names = {Message.IMAGE: "Photo", Message.AUDIO: "Voice note", Message.VIDEO: "Video"}
    if message.kind == Message.DOCUMENT:
        return f"PDF: {message.media_filename}"[:200] if message.media_filename else "PDF"
    if message.kind == Message.FILE:
        return (message.media_filename or "File")[:200]
    text = formatting.plain(message.body)[:200]
    return text or names.get(message.kind, "")


def is_word(body, words):
    return re.sub(r"[\s.!]+", "", (body or "").upper()) in words if (body or "").strip() else False


def record_inbound(params):
    """Store one message from him (idempotent on Twilio's MessageSid). Returns (message, created). STOP marks him opted out and START
    clears it; any other message leaves an opt-out as it is (he stays opted out until he sends a clear restart word)."""
    sid = params.get("MessageSid", "")
    existing = Message.objects.filter(twilio_sid=sid).first()
    if existing is not None:
        return existing, False
    phone = to_e164(params.get("From", ""))
    contact = get_or_create_contact(phone, params.get("ProfileName", ""))
    body = (params.get("Body") or "").replace("\x00", "")
    fields = {}
    if int(params.get("NumMedia") or 0) > 0 and params.get("MediaUrl0"):
        media_type = (params.get("MediaContentType0") or "").lower()
        fields = {"kind": kind_of(media_type), "media_type": media_type[:100], "media_source_url": params["MediaUrl0"][:500]}
    elif params.get("Latitude") and params.get("Longitude"):
        place = ", ".join(x for x in (params.get("Label"), params.get("Address")) if x)
        body = body or f"Location: {place + ' ' if place else ''}({params['Latitude']}, {params['Longitude']})"
        fields = {"kind": Message.OTHER}
    try:
        with transaction.atomic():
            message = Message.objects.create(contact=contact, direction=Message.IN, body=body, status=Message.RECEIVED, twilio_sid=sid, **fields)
    except IntegrityError:  # Twilio sent it twice at once
        return Message.objects.get(twilio_sid=sid), False
    update = {"last_inbound_at": message.created_at, "last_message_at": message.created_at, "last_preview": _preview(message), "last_kind": message.kind, "last_direction": Message.IN}
    if is_word(body, STOP_WORDS):
        update["opted_out_at"] = contact.opted_out_at or message.created_at
    elif is_word(body, START_WORDS):
        update["opted_out_at"] = None
    Contact.objects.filter(pk=contact.pk).update(**update)
    return message, True


def store_media(message):
    """The worker copies his file from Twilio into the default storage. Over the limit or unreachable: the message says so instead."""
    if not message.media_source_url:
        return False
    limit = settings.WHATSAPP_MAX_FILE_BYTES
    try:
        got = twilio_api.fetch_media(message.media_source_url, limit)
    except twilio_api.TwilioError:
        logger.warning("Could not fetch the file of WhatsApp message %s", message.pk)
        got = False
    if not got:
        note = "The file could not be loaded." if got is False else "The file was too big to keep."
        Message.objects.filter(pk=message.pk).update(kind=Message.OTHER, media_source_url="", body=(message.body + "\n" if message.body else "") + note)
        return False
    data, content_type = got
    kind = kind_of(content_type or message.media_type)
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "application/pdf": ".pdf", "audio/ogg": ".ogg", "audio/mpeg": ".mp3", "video/mp4": ".mp4"}.get(content_type or message.media_type, "")
    key = default_storage.save(f"whatsapp/{message.contact_id}/{uuid.uuid4().hex}{ext}", ContentFile(data))
    width, height = imagesize.size_of(data) if kind == Message.IMAGE else (None, None)
    Message.objects.filter(pk=message.pk).update(kind=kind, media_key=key, media_type=content_type or message.media_type, media_size=len(data), media_width=width, media_height=height,
                                                 media_filename=f"{kind}-{message.pk}{ext}", media_source_url="")
    Contact.objects.filter(pk=message.contact_id, last_message_at=message.created_at).update(last_kind=kind, last_preview=_preview(Message.objects.get(pk=message.pk)))
    return True


def apply_status(params):
    """A delivery tick from Twilio. Idempotent; never moves a message backwards; failures keep Twilio's code. False when the sid is not ours."""
    message = Message.objects.filter(twilio_sid=params.get("MessageSid", ""), direction=Message.OUT).first()
    status = TWILIO_STATUS.get(str(params.get("MessageStatus", "")).lower())
    if message is None or status is None:
        return False
    update = {}
    if status in Message.BAD:
        if message.status not in (Message.DELIVERED, Message.READ, *Message.BAD):
            update = {"status": status, "error_code": str(params.get("ErrorCode", ""))[:20], "error_message": str(params.get("ErrorMessage", ""))[:300]}
    elif RANK[status] > RANK.get(message.status, -1):
        update = {"status": status, **({"sent_at": now()} if status == Message.SENT and not message.sent_at else {})}
    if update:
        Message.objects.filter(pk=message.pk).update(updated_at=now(), **update)
    return True


# ---------- templates ----------

def _content_body(content):
    for kind in (content.get("types") or {}).values():
        if isinstance(kind, dict) and (kind.get("body") or kind.get("title")):
            return kind.get("body") or kind.get("title")
    return ""


def sync_templates():
    """Read every Content Template and its WhatsApp approval from Twilio; keep the `spa99_` ones. Returns counts. Labels you set stay."""
    seen, created, updated = set(), 0, 0
    for content in twilio_api.list_contents():
        name = str(content.get("friendly_name") or "")
        if not name.lower().startswith(TEMPLATE_PREFIX):
            continue
        approval = ((content.get("approval_requests") or {}).get("whatsapp")) or {}
        body = _content_body(content)
        keys = sorted((content.get("variables") or {}).keys(), key=lambda k: (not str(k).isdigit(), int(k) if str(k).isdigit() else 0, str(k))) or sorted(set(re.findall(r"\{\{\s*(\w+)\s*\}\}", body)))
        row = Template.objects.filter(content_sid=content["sid"]).first()
        labels = {**DEFAULT_LABELS.get(name.lower(), {}), **((row.variable_labels if row else {}) or {})}
        values = {"name": name, "language": str(content.get("language") or "")[:12], "category": str(approval.get("category") or "").lower()[:30],
                  "approval_status": str(approval.get("status") or "unsubmitted").lower()[:20], "body": body, "variables": [str(k) for k in keys],
                  "variable_labels": {k: v for k, v in labels.items() if k in {str(x) for x in keys}}, "synced_at": now()}
        if row is None:
            Template.objects.create(content_sid=content["sid"], **values)
            created += 1
        else:
            for field, value in values.items():
                setattr(row, field, value)
            row.save()
            updated += 1
        seen.add(content["sid"])
    gone = Template.objects.exclude(content_sid__in=seen).exclude(approval_status="removed").update(approval_status="removed")
    return {"created": created, "updated": updated, "removed": gone}


def usable_templates():
    return [t for t in Template.objects.filter(name__istartswith=TEMPLATE_PREFIX, approval_status=Template.APPROVED).order_by("name") if t.sendable]


def check_twilio():
    """System > WhatsApp "Check": does Twilio accept our key, and is the Spa 99 sender online? {ok, steps[{label, ok, detail}]}. Never raises."""
    steps = []
    if not configured():
        return {"ok": False, "steps": [{"label": "Settings", "ok": False, "detail": "Missing: " + ", ".join(twilio_api.missing())}]}
    try:
        account = twilio_api.account()
        steps.append({"label": "Twilio account", "ok": account.get("status") == "active", "detail": f"Status: {account.get('status', 'unknown')}"})
    except twilio_api.TwilioError as error:
        return {"ok": False, "steps": [{"label": "Twilio account", "ok": False, "detail": str(error)}]}
    try:
        found = twilio_api.sender_status()
        online = found["found"] and found["status"].upper() == "ONLINE"
        steps.append({"label": "WhatsApp sender", "ok": online, "detail": (f"{found['name'] or 'Spa 99'}: {found['status'].title() or 'unknown'}" + (f", quality {found['quality'].title()}" if found["quality"] else "")) if found["found"] else "That number was not found among the account's WhatsApp senders."})
    except twilio_api.TwilioError as error:
        steps.append({"label": "WhatsApp sender", "ok": False, "detail": str(error)})
    return {"ok": all(s["ok"] for s in steps), "steps": steps}


# ---------- what the pages need ----------

def message_dict(message):
    reason, can_retry = errors.reason(message.error_code) if message.status in Message.BAD else ("", False)
    template = message.template
    media = None
    if message.media_key:
        media = {"url": _office("office_whatsapp_media", message.pk), "type": message.media_type, "filename": message.media_filename, "size": message.media_size,
                 "width": message.media_width, "height": message.media_height}
    return {"id": message.pk, "direction": message.direction, "kind": message.kind, "body": message.body, "body_html": str(formatting.render(message.body)),
            "status": message.status, "error": {"reason": reason, "can_retry": can_retry} if reason else None,
            "author": message.author_label, "author_id": str(message.author_id) if message.author_id else "", "author_first_name": _first(message.author_label),
            "template": {"id": str(template.pk), "name": template.name, "label": template.label} if template else None,
            "media": media, "created_at": message.created_at.isoformat(), "sent_at": message.sent_at.isoformat() if message.sent_at else "",
            "retry_url": _office("office_whatsapp_retry", message.contact_id, message.pk) if reason and can_retry else ""}


def _first(label):
    """First name from an audit label 'Name (email)'."""
    return (label or "").split(" (")[0].split("@")[0].split(" ")[0]


def contact_dict(contact, user=None, can_send=False):
    state = window_state(contact)
    ends = window_ends_at(contact)
    labels = []
    if contact.application_id:
        labels.append("Gold")
    if contact.user_id:
        labels.append("Registered")
    elif contact.lead_email:
        labels.append("Lead")
    page = ""
    if contact.application_id:
        page = _office("office_gold_application", contact.application_id)
    elif contact.user_id:
        page = _office("office_person", contact.user_id) if hasattr(contact.user, "interest") else ""
    elif contact.lead_email:
        from journey.models import JourneySession

        session = JourneySession.objects.filter(lead_email__iexact=contact.lead_email, is_bot=False).order_by("-created_at").values_list("pk", flat=True).first()
        page = _office("office_lead", session) if session else ""
    return {"id": str(contact.pk), "name": contact.display_name, "has_name": bool(contact.name or contact.profile_name), "phone": contact.phone, "profile_name": contact.profile_name,
            "labels": labels, "page_url": page, "opted_out": contact.opted_out, "window": {"state": state, "open": state == "open", "ends_at": ends.isoformat() if ends else ""},
            "can_send": can_send, "url": _office("office_whatsapp_thread", contact.pk), "last_message_at": contact.last_message_at.isoformat() if contact.last_message_at else "",
            "limits": {"body": settings.WHATSAPP_MAX_BODY, "image_bytes": settings.WHATSAPP_MAX_IMAGE_BYTES, "file_bytes": settings.WHATSAPP_MAX_FILE_BYTES}}


def inbox_rows(contacts, user):
    contacts = list(contacts)
    unread = unread_counts(user, [c.pk for c in contacts])
    return [{"id": str(c.pk), "name": c.display_name, "phone": c.phone, "preview": c.last_preview, "preview_kind": c.last_kind, "direction": c.last_direction,
             "last_message_at": c.last_message_at.isoformat() if c.last_message_at else "", "unread": unread.get(c.pk, 0), "opted_out": c.opted_out,
             "window_open": window_open(c), "url": _office("office_whatsapp_thread", c.pk)} for c in contacts]


def template_dicts(contact=None):
    """Approved templates for the picker: {id, name, label, body_html, variables[{key, label, prefill}]}. Variable "First name" is pre-filled."""
    first = (contact.name or contact.profile_name or "").split(" ")[0] if contact is not None else ""
    return [{"id": str(t.pk), "name": t.name, "label": t.label, "category": t.category, "body": t.body, "body_html": str(template_html(t)),
             "variables": [{"key": k, "label": label_for(t, k), "prefill": first if label_for(t, k).lower() == "first name" else ""} for k in t.variables]}
            for t in usable_templates()]


def page_context(mobile, user_obj, can_send, start_url, edit_url, first_name=""):
    """The `whatsapp` dict on the lead, person and Gold pages."""
    base = {"configured": configured(), "has_mobile": bool(mobile), "mobile": mobile or "", "first_name": first_name, "contact_url": start_url, "start_url": start_url,
            "edit_url": edit_url, "can_send": bool(can_send and mobile and configured()), "can_edit": bool(can_send), "has_chat": False, "window_open": False,
            "window_closes_at": "", "opted_out": False, "unread": 0}
    contact = Contact.objects.filter(phone=mobile).first() if mobile else None
    if contact is None:
        return base
    ends = window_ends_at(contact)
    return {**base, "has_chat": bool(contact.last_message_at), "window_open": window_open(contact), "window_closes_at": ends.isoformat() if ends and window_open(contact) else "",
            "opted_out": contact.opted_out, "unread": unread_counts(user_obj, [contact.pk]).get(contact.pk, 0), "thread_url": _office("office_whatsapp_thread", contact.pk)}


# ---------- timeline, export, erase ----------

def contacts_for_person(user=None, addresses=(), phones=()):
    query = Q(pk__in=[])
    if phones:
        query |= Q(phone__in=[p for p in phones if p])
    if user is not None:
        query |= Q(user=user)
    if addresses:
        query |= Q(lead_email__in=[a.lower() for a in addresses])
    return Contact.objects.filter(query)


def person_phones(user=None, addresses=()):
    """Every mobile held for a person: the account's, the one given at the email step, the one on a Gold application."""
    from gold.models import GoldApplication
    from journey.models import JourneySession

    addresses = {a.lower() for a in addresses if a}
    sessions = JourneySession.objects.exclude(lead_mobile="")
    applications = GoldApplication.objects.exclude(mobile="")
    by_user = Q(user=user) if user is not None else Q(pk__in=[])
    phones = set(sessions.filter(by_user | Q(lead_email__in=addresses) | _ci("lead_email", addresses)).values_list("lead_mobile", flat=True))
    phones |= set(applications.filter(by_user | _ci("email", addresses)).values_list("mobile", flat=True))
    if user is not None and user.mobile:
        phones.add(user.mobile)
    return phones


def _ci(field, values):
    query = Q(pk__in=[])
    for value in values:
        query |= Q(**{f"{field}__iexact": value})
    return query


def timeline_entries(contacts):
    """[(at, kind, label, detail, href)]: not one line per message. The first WhatsApp sent, one line a day ("WhatsApp: 3 from him, 2 from
    us", with his last message), STOP and START replies, and each send that finally failed."""
    out = []
    for contact in contacts:
        href = _office("office_whatsapp_thread", contact.pk)
        rows = list(Message.objects.filter(contact=contact).order_by("id").values_list("direction", "created_at", "body", "status", "error_code", "author_label", "kind", "template__name"))
        first_out = next((r for r in rows if r[0] == Message.OUT), None)
        if first_out is not None:
            what = f"Template {first_out[7]}" if first_out[7] else ""
            out.append((first_out[1], "whatsapp", f"First WhatsApp sent by {first_out[5] and _first(first_out[5]) or 'the team'}", what, href))
        days = {}
        for direction, at, body, status, code, author, kind, template_name in rows:
            if direction == Message.IN and is_word(body, STOP_WORDS):
                out.append((at, "whatsapp_stop", "He replied STOP", "", href))
            elif direction == Message.IN and is_word(body, START_WORDS):
                out.append((at, "whatsapp", "He replied START", "", href))
            if direction == Message.OUT and status in Message.BAD:
                out.append((at, "whatsapp_failed", "WhatsApp not sent", errors.reason(code)[0], href))
            day = timezone.localtime(at).date()
            bucket = days.setdefault(day, {"in": 0, "out": 0, "last_in": "", "at": at})
            bucket[direction] += 1
            bucket["at"] = at
            if direction == Message.IN:
                bucket["last_in"] = formatting.plain(body) or kind.title()
        for bucket in days.values():
            parts = [f"{bucket['in']} from him" if bucket["in"] else "", f"{bucket['out']} from us" if bucket["out"] else ""]
            out.append((bucket["at"], "whatsapp", "WhatsApp: " + ", ".join(p for p in parts if p), bucket["last_in"], href))
    return out


def export_for(contacts):
    """Everything held: each chat with its messages (text, kind, status, times, file name, template, error code)."""
    out = []
    for contact in contacts:
        out.append({"phone": contact.phone, "profile_name": contact.profile_name, "name": contact.name, "opted_out_at": contact.opted_out_at.isoformat() if contact.opted_out_at else None,
                    "messages": [{"direction": m.direction, "kind": m.kind, "text": m.body, "status": m.status, "at": m.created_at.isoformat(), "sent_at": m.sent_at.isoformat() if m.sent_at else None,
                                  "file": m.media_filename or None, "template": m.template.name if m.template_id else None, "error_code": m.error_code or None, "sent_by": m.author_label or None}
                                 for m in contact.messages.select_related("template").order_by("id")]})
    return out


def erase_contacts(contacts):
    """UK GDPR: the chats, their messages, their files in storage and the queue records that name those messages. Returns counts."""
    from common.tasks import erase_task_records

    contacts = list(contacts)
    ids = [c.pk for c in contacts]
    messages = list(Message.objects.filter(contact_id__in=ids).values_list("pk", "media_key"))
    for _, key in messages:
        if key:
            try:
                default_storage.delete(key)
            except Exception:  # noqa: BLE001 - a missing file must not stop the erasure
                logger.warning("Could not delete a WhatsApp file from storage")
    queue = erase_task_records([pk for pk, _ in messages], ["whatsapp.tasks."]) if messages else 0
    Contact.objects.filter(pk__in=ids).delete()  # messages and read markers go with them
    return {"whatsapp_contacts": len(ids), "whatsapp_messages": len(messages), "queue_records": queue}


def erase_person(user=None, addresses=()):
    return erase_contacts(contacts_for_person(user, addresses, person_phones(user, addresses)))
