"""WhatsApp logic: contacts and who they are, the 24-hour window, sending (queued), inbound messages, delivery ticks, templates, what the
Office pages need, the timeline lines, and export / erasure. The views stay thin and call these. Twilio itself is `twilio_api`."""
import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from urllib.parse import urlencode

import phonenumbers
from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, F, Max, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from django.utils.safestring import mark_safe

from common import ownership
from common.tasks import enqueue

from . import errors, formatting, imagesize, twilio_api, voice
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
MP4_BRANDS = {b"isom", b"iso2", b"iso4", b"iso5", b"iso6", b"mp41", b"mp42", b"avc1", b"M4V ", b"MSNV", b"dash"}  # MP4 files; QuickTime (qt  ) and audio-only brands are not sent as video


def sniff_send(data):
    """(kind, content type, extension) from the file's own first bytes (never its name or declared type), or None."""
    for content_type, (kind, magic, extension) in SEND_TYPES.items():
        if data.startswith(magic):
            return kind, content_type, extension
    if data[4:8] == b"ftyp" and data[8:12] in MP4_BRANDS:
        return Message.VIDEO, "video/mp4", ".mp4"
    return None
DEFAULT_LABELS = {"spa99_lead_follow_up": {"1": "First name"}}  # what each variable of a template is called in the form (kept across syncs)

DONE, EMPTY, TOO_LONG, WINDOW_CLOSED, OPTED_OUT, DUPLICATE = "done", "empty", "too_long", "window_closed", "opted_out", "duplicate"
BAD_REPLY, NO_VOICE, VOICE_TOO_LONG = "bad_reply", "voice_unavailable", "voice_too_long"
NOT_CONFIGURED, BAD_FILE, TOO_BIG, BAD_TEMPLATE, MISSING_VARIABLES, NOT_RETRYABLE = "not_configured", "bad_file", "too_big", "bad_template", "missing_variables", "not_retryable"
WORDS = {EMPTY: "Write a message first.", TOO_LONG: "That message is too long.", WINDOW_CLOSED: "The 24-hour window has closed. Send a template to reopen it.",
         OPTED_OUT: "He replied STOP, so he gets no more messages.", DUPLICATE: "That message was just sent.", NOT_CONFIGURED: "WhatsApp is not set up yet.",
         BAD_FILE: "Photos, PDFs or MP4 videos only.", TOO_BIG: "Photos up to 5 MB, PDFs and videos up to 16 MB.",
         BAD_REPLY: "That message cannot be replied to.", NO_VOICE: "Voice notes are not available on this server.", VOICE_TOO_LONG: "A voice note can be 5 minutes at most.", BAD_TEMPLATE: "That template cannot be sent.",
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
    """The one automatic step: rule 1c of common.ownership. A chat that ALREADY has a lead address (set by staff) is linked to the account whose verified email is that address, and
    its name comes from what it is already linked to (the account, the lead's first name, the Gold application). Nothing else is linked here, ever: a number typed on a public form
    (journey gate, Register, Gold apply) proves nothing, so it never sets or replaces a link, or a name, on a chat. Staff link a chat by hand (`ownership.link`). An owner already on the
    chat is never replaced. The name staff, the lead or the account gave wins over his WhatsApp profile name."""
    from journey.models import JourneySession
    from users.models import User

    lead = ownership.clean(contact.lead_email)
    if contact.user_id is None and lead:
        account = User.objects.filter(email__iexact=lead, email_verified_at__isnull=False).first()
        if account is not None:
            contact.user = account
    name = ""
    if contact.user_id is not None:
        name = (contact.user.get_full_name() or "").strip()
    if not name and lead:
        named = JourneySession.objects.filter(lead_email__iexact=lead, is_bot=False).exclude(lead_first_name="").order_by("-created_at").first()
        name = named.lead_first_name if named else ""
    if not name and contact.application_id is not None:
        name = contact.application.full_name
    if name:
        contact.name = name[:100]
    if save:
        contact.save(update_fields=["user", "name"])
    return contact


def relink_address(*addresses):
    """An address was proven (an account verified it): chats that staff already gave that lead address join up with the account (rule 1c). Best effort."""
    try:
        for address in {ownership.clean(a) for a in addresses if a}:
            for contact in Contact.objects.filter(lead_email__iexact=address, user__isnull=True):
                resolve_links(contact)
    except Exception:  # noqa: BLE001 - a verification must never fail because a chat could not be relinked
        logger.exception("Could not refresh the WhatsApp links")


def move_address(old, new):
    """Staff corrected a lead's address: the chats that hold the old lead address take the new one (a chat with an owner, or linked to a Gold application on another address, stays).
    Returns the number moved."""
    old, new = ownership.clean(old), ownership.clean(new)
    if not old or not new or old == new:
        return 0
    free = Q(application__isnull=True) | Q(application__email__iexact=new)
    return Contact.objects.filter(user__isnull=True, lead_email__iexact=old).filter(free).update(lead_email=new)


def start_chat(mobile, **links):
    """A staff start action (a POST by an editor): the chat on this number, made when there is none (rule 1b). A NEW chat takes the links of the page it was started from
    (`user`, `lead_email` or `application`, see ownership.link); an existing chat is returned untouched, with no write at all: staff see it first and link it from the thread. Returns (contact, created)."""
    contact, created = Contact.objects.get_or_create(phone=mobile)
    if created:
        ownership.link(contact, **links)
        resolve_links(contact)
    return contact, created


def get_or_create_contact(phone, profile_name=""):
    contact, created = Contact.objects.get_or_create(phone=phone)
    if profile_name and contact.profile_name != profile_name[:100]:
        contact.profile_name = profile_name[:100]
        contact.save()
    return contact


def owner_of_phone(phone, exclude_email="", exclude_user=None):
    """Who already has this number ({name, url}), or None. Used to refuse the same number on two people (two people would share one chat)."""
    from gold.models import GoldApplication
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
    applications = GoldApplication.objects.filter(mobile=phone)  # a Gold applicant's number counts too; a person's own application does not
    if exclude_email:
        applications = applications.exclude(email__iexact=exclude_email)
    if exclude_user is not None:
        applications = applications.exclude(user=exclude_user)
        if exclude_user.email:
            applications = applications.exclude(email__iexact=exclude_user.email)
    gold = applications.order_by("-created_at").first()
    if gold is not None:
        return {"name": gold.full_name or gold.email.lower(), "url": _office("office_gold_application", gold.pk)}
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


QUOTE_CHARS = 100
MEDIA_WORDS = {Message.IMAGE: "Photo", Message.AUDIO: "Voice note", Message.VIDEO: "Video", Message.DOCUMENT: "PDF", Message.FILE: "File", Message.OTHER: "Message"}


def quote_text(message, customer=False):
    """The words a quote shows for a message: its first line (no formatting marks, no quote of its own), or "Photo", "Voice note", "Video", "PDF" for a file with no text.
    A template with no text shows its name to staff; `customer=True` (what goes out to him) says "Message": a template's internal name is never sent."""
    for line in formatting.plain(message.body or "").splitlines():
        line = line.strip().lstrip(">").strip()
        if line:
            return line if len(line) <= QUOTE_CHARS else line[:QUOTE_CHARS - 1].rstrip() + "\u2026"
    if message.kind == Message.TEMPLATE and message.template_id and not customer:  # a template with no text of its own: its name (for staff only)
        return (message.template.label or message.template.name or "Template")[:QUOTE_CHARS]
    return MEDIA_WORDS.get(message.kind, "Message")


def outgoing_text(message):
    """What goes to Twilio as the Body: when staff replied to a bubble, `> first line of the quoted text`, a blank line, then the body as typed (WhatsApp shows the
    `>` as a quote). Used by the send and by a retry, so both send the same."""
    if message.kind in (Message.TEMPLATE, Message.AUDIO) or message.reply_to_id is None:  # a voice note has no text to put a quote in (the Office still links it)
        return message.body
    quote = f"> {quote_text(message.reply_to, customer=True)}"
    return f"{quote}\n\n{message.body}" if message.body else quote


def reply_target(contact, reply_to):
    """The message this reply answers, from a posted id: it must be a message of this same chat. (None, False) when nothing was given, (None, True) when it is not valid."""
    if reply_to in (None, ""):
        return None, False
    try:
        found = Message.objects.filter(pk=int(reply_to), contact=contact).select_related("template").first()  # templates can be replied to: the quote is their text, or their name
    except (TypeError, ValueError):
        return None, True
    return found, found is None


def _too_long(body, reply):
    probe = Message(body=body, kind=Message.TEXT, reply_to=reply)
    return len(outgoing_text(probe)) > settings.WHATSAPP_MAX_BODY


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


def send_text(contact, actor, body, reply_to=None):
    """Free text inside the 24-hour window. `reply_to` is a message id of this chat (staff Reply on a bubble). Returns (result, message)."""
    body = (body or "").replace("\x00", "").strip()
    if not body:
        return EMPTY, None
    reply, invalid = reply_target(contact, reply_to)
    if invalid:
        return BAD_REPLY, None
    if _too_long(body, reply):  # the final text, quote included
        return TOO_LONG, None
    blocked = _blocked(contact, needs_window=True)
    return (blocked, None) if blocked else _queue(contact, actor, Message.TEXT, body, reply_to=reply)


def send_media(contact, actor, upload, caption="", reply_to=None):
    """A photo (JPEG or PNG, 5 MB), a PDF or an MP4 video (16 MB) inside the window, with an optional caption. The file goes to the default storage
    (S3 on live); Twilio fetches it from a signed, expiring link whose content type is the one stored here (Twilio refuses a mismatch). Returns (result, message)."""
    caption = (caption or "").replace("\x00", "").strip()
    reply, invalid = reply_target(contact, reply_to)
    if invalid:
        return BAD_REPLY, None
    if _too_long(caption, reply):
        return TOO_LONG, None
    blocked = _blocked(contact, needs_window=True)
    if blocked:
        return blocked, None
    data = upload.read(settings.WHATSAPP_MAX_FILE_BYTES + 1)
    found = sniff_send(data)  # the file's own first bytes decide, not its name or declared type
    if found is None:
        return BAD_FILE, None
    kind, media_type, ext = found
    if len(data) > (settings.WHATSAPP_MAX_IMAGE_BYTES if kind == Message.IMAGE else settings.WHATSAPP_MAX_FILE_BYTES):
        return TOO_BIG, None
    width, height = imagesize.size_of(data) if kind == Message.IMAGE else (None, None)
    name = re.sub(r"[^\w .()-]", "_", (getattr(upload, "name", "") or f"file{ext}").rsplit("/", 1)[-1])[:200] or f"file{ext}"
    return _store_and_queue(contact, actor, kind, caption, data, media_type, ext, name, width, height, reply)


def _store_and_queue(contact, actor, kind, caption, data, media_type, ext, name, width, height, reply):
    key = default_storage.save(f"whatsapp/{contact.pk}/{uuid.uuid4().hex}{ext}", ContentFile(data))
    result, message = _queue(contact, actor, kind, caption, media_key=key, media_type=media_type, media_filename=name, media_size=len(data), media_width=width, media_height=height, reply_to=reply)
    if result != DONE:
        default_storage.delete(key)
    return result, message


def voice_available():
    return voice.available()


def send_voice(contact, actor, upload, duration=None, reply_to=None):
    """A voice note recorded in the browser (WebM, MP4 or Ogg audio, found by its first bytes), converted by ffmpeg to OGG Opus and sent as audio inside
    the window. `duration` is the browser's own figure, used only to refuse an obviously too long one early: the real length is measured after conversion.
    5 minutes at most. Returns (result, message)."""
    if not voice.available():
        return NO_VOICE, None
    reply, invalid = reply_target(contact, reply_to)
    if invalid:
        return BAD_REPLY, None
    blocked = _blocked(contact, needs_window=True)
    if blocked:
        return blocked, None
    try:
        claimed = float(duration) if duration not in (None, "") else 0.0
    except (TypeError, ValueError):
        claimed = 0.0
    if claimed > settings.WHATSAPP_VOICE_MAX_SECONDS + 1:
        return VOICE_TOO_LONG, None
    data = upload.read(settings.WHATSAPP_VOICE_MAX_UPLOAD_BYTES + 1)
    if len(data) > settings.WHATSAPP_VOICE_MAX_UPLOAD_BYTES:
        return TOO_BIG, None
    try:
        ogg, _seconds = voice.convert(data)
    except voice.VoiceError as error:
        return {"no_ffmpeg": NO_VOICE, "too_long": VOICE_TOO_LONG, "too_big": TOO_BIG}.get(error.code, BAD_FILE), None
    return _store_and_queue(contact, actor, Message.AUDIO, "", ogg, voice.OUTPUT_TYPE, ".ogg", "voice-note.ogg", None, None, reply)


def send_template(contact, actor, template_id, variables):
    """An approved `spa99_` template, any time (not after STOP). `variables` is {key: text}. Returns (result, message); MISSING_VARIABLES
    puts the empty keys in the message's place as a list: (MISSING_VARIABLES, [keys])."""
    blocked = _blocked(contact, needs_window=False)
    if blocked:
        return blocked, None
    try:
        template = Template.objects.filter(pk=template_id).first()
    except (ValidationError, ValueError):  # not a UUID
        template = None
    if template is None or not template.sendable:  # enforced here, whatever a page posted: BML templates never go from Spa 99
        return BAD_TEMPLATE, None
    values = {str(k): _clean_variable(variables.get(str(k))) for k in template.variables}
    empty = [k for k, v in values.items() if not v]
    if empty:
        return MISSING_VARIABLES, empty
    return _queue(contact, actor, Message.TEMPLATE, fill_body(template.body, values), template=template, template_variables=values)


STUCK_AFTER = timedelta(minutes=5)
CLAIM_TIMEOUT = timedelta(minutes=10)  # longer than the worker's job time limit and all its retries (Q_CLUSTER timeout 120 s, retry 180 s, 3 attempts)


def is_stuck(message, at=None):
    """Queued, never taken by a worker and older than a few minutes (the queue lost it), or taken by a worker that then died (claimed more than CLAIM_TIMEOUT ago
    and still queued with no Twilio id): "Try again" is allowed. In that second case the worker may have died after Twilio took the message and before its id was
    saved, so a Try again can, rarely, make a second WhatsApp for him; the wording says "may not have been sent"."""
    at = at or now()
    if message.direction != Message.OUT or message.status != Message.QUEUED or message.twilio_sid is not None:
        return False
    if message.claimed_at is None:
        return message.updated_at < at - STUCK_AFTER
    return message.claimed_at < at - CLAIM_TIMEOUT


def is_unsure(message, at=None):
    """A worker took this and never reported back: it may or may not have been sent."""
    return bool(message.claimed_at is not None and is_stuck(message, at))


def becomes_stuck_between(since, until):
    """Queued messages that crossed into the stuck state in (since, until]: `is_stuck` depends on the clock, so `updated_at` never moves when it happens. Each message matches
    in exactly one poll window, so a poll never rereads old stuck ones and the cost does not grow."""
    waiting = Q(claimed_at__isnull=True, updated_at__gt=since - STUCK_AFTER, updated_at__lte=until - STUCK_AFTER)
    taken = Q(claimed_at__gt=since - CLAIM_TIMEOUT, claimed_at__lte=until - CLAIM_TIMEOUT)
    return Q(direction=Message.OUT, status=Message.QUEUED, twilio_sid__isnull=True) & (waiting | taken)


def poll_updates(queryset, after, since, until):
    """The messages already on the page (id up to `after`) that changed since the cursor, or became stuck since it."""
    return queryset.filter(pk__lte=after).filter(Q(updated_at__gt=since) | becomes_stuck_between(since, until))


def can_retry(message):
    """A message we never handed to Twilio (no sid) that failed for a reason worth retrying, or one the queue lost. A message Twilio has accepted is never
    sent again (that could be a second WhatsApp for him)."""
    if message.direction != Message.OUT or message.twilio_sid:
        return False
    if message.status == Message.FAILED:
        return errors.reason(message.error_code)[1]
    return is_stuck(message)


def retry(message, actor):
    """Send a failed or lost message again (the same bubble). The reset is one conditional update, so a double click sends once. Returns (result, message)."""
    message.refresh_from_db()
    if not can_retry(message):
        return NOT_RETRYABLE, None
    blocked = _blocked(message.contact, needs_window=message.kind != Message.TEMPLATE)
    if blocked:
        return blocked, None
    claimed = Message.objects.filter(pk=message.pk, twilio_sid__isnull=True, status=message.status, claimed_at=message.claimed_at).update(
        status=Message.QUEUED, error_code="", error_message="", claimed_at=None, updated_at=now())
    if not claimed:  # someone else got there first
        return NOT_RETRYABLE, None
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


def status_callback_url(message=None):
    """Where Twilio reports this message. The message id rides in the address (`?m=`; Twilio signs the whole URL), so a tick can find a message whose Twilio id was never saved
    (the worker died after Twilio took it): see apply_status."""
    return f"{settings.SITE_URL}{reverse('whatsapp_status', urlconf='config.urls')}" + (f"?m={message.pk}" if message is not None else "")


def deliver(message):
    """The worker's side of a send: one Twilio call, and the outcome written on the message. Never sends twice."""
    if not Message.objects.filter(pk=message.pk, status=Message.QUEUED, claimed_at__isnull=True).update(claimed_at=now()):
        return "skipped"
    message.refresh_from_db()
    if not configured():
        return _fail(message, "not_configured", "WhatsApp is not set up.")
    if Contact.objects.filter(pk=message.contact_id, opted_out_at__isnull=False).exists():  # he replied STOP after this was queued
        return _fail(message, "opted_out", "He replied STOP.")
    try:
        sent = twilio_api.send_message(
            message.contact.phone, body=outgoing_text(message) if message.kind != Message.TEMPLATE else "",
            content_sid=message.template.content_sid if message.kind == Message.TEMPLATE and message.template_id else "",
            content_variables=json.dumps(message.template_variables) if message.kind == Message.TEMPLATE else "",
            media_url=media_url(message) if message.media_key else "", status_callback=status_callback_url(message))
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
    names = {Message.IMAGE: "Photo", Message.AUDIO: "Voice note", Message.VIDEO: "Video", Message.OTHER: "Message"}
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
    elif not body.strip():  # no text, no file, no location: something we do not know (a reaction?). Twilio documents no format, so: a neutral bubble, and the parameter NAMES (never values) in the log
        logger.info("WhatsApp message with no text, file or location; parameter names: %s", ", ".join(sorted(str(k) for k in params)))
        body, fields = "", {"kind": Message.OTHER}
    quoted = params.get("OriginalRepliedMessageSid", "")
    if quoted:  # he used Reply on one of the messages of this chat (Twilio sends this for messages under 7 days old)
        fields["reply_to"] = Message.objects.filter(twilio_sid=quoted, contact=contact).first()
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
    try:
        key = default_storage.save(f"whatsapp/{message.contact_id}/{uuid.uuid4().hex}{ext}", ContentFile(data))
    except Exception:  # noqa: BLE001 - a storage problem must not lose the message or its notification
        logger.exception("Could not store the file of WhatsApp message %s", message.pk)
        Message.objects.filter(pk=message.pk).update(kind=Message.OTHER, media_source_url="", body=(message.body + "\n" if message.body else "") + "The file could not be saved.")
        return False
    width, height = imagesize.size_of(data) if kind == Message.IMAGE else (None, None)
    Message.objects.filter(pk=message.pk).update(kind=kind, media_key=key, media_type=content_type or message.media_type, media_size=len(data), media_width=width, media_height=height,
                                                 media_filename=f"{kind}-{message.pk}{ext}", media_source_url="")
    Contact.objects.filter(pk=message.contact_id, last_message_at=message.created_at).update(last_kind=kind, last_preview=_preview(Message.objects.get(pk=message.pk)))
    return True


def _by_callback_id(params, message_pk):
    """The message a tick names in its callback address (`?m=`) when the tick's own Twilio id is not on any message: only one with no Twilio id saved, and only when the tick's
    `To` is that chat's number. The id is saved now, so the page stops offering Try again (Twilio did take it)."""
    sid = str(params.get("MessageSid", ""))
    try:
        pk = int(message_pk)
    except (TypeError, ValueError):
        return None
    candidate = Message.objects.select_related("contact").filter(pk=pk, direction=Message.OUT, twilio_sid__isnull=True).first()
    if not sid or candidate is None or to_e164(params.get("To", "")) != candidate.contact.phone:
        return None
    return candidate if Message.objects.filter(pk=pk, twilio_sid__isnull=True).update(twilio_sid=sid) else None


def apply_status(params, message_pk=None):
    """A delivery tick from Twilio. Idempotent; never moves a message backwards; failures keep Twilio's code. False when the message is not ours. A tick whose id is on no
    message is matched through `message_pk` (the `?m=` in the callback address) when that message has no Twilio id: a worker that died after Twilio took the message but before
    the id was saved is put right by the first tick. (Messages sent before the address carried it, or a message Twilio never reports on, cannot be matched.)"""
    message = Message.objects.filter(twilio_sid=params.get("MessageSid", ""), direction=Message.OUT).first() if params.get("MessageSid") else None
    if message is None and message_pk:
        message = _by_callback_id(params, message_pk)
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
        requests_ = content.get("approval_requests") or {}
        approval = requests_.get("whatsapp") or requests_  # nested under "whatsapp", or the status and category right on it
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
    """System > WhatsApp "Check": is the Spa 99 sender online? Read through the WhatsApp Senders API only (a Standard API key cannot read the
    Accounts resource). {ok, steps[{label, ok, detail}]}. Never raises."""
    if not configured():
        return {"ok": False, "steps": [{"label": "Settings", "ok": False, "detail": "Missing: " + ", ".join(twilio_api.missing())}]}
    try:
        found = twilio_api.sender_status()
    except twilio_api.TwilioError as error:
        return {"ok": False, "steps": [{"label": "WhatsApp sender", "ok": False, "detail": str(error)}]}
    online = found["found"] and found["status"].upper() == "ONLINE"
    detail = (f"{found['name'] or 'Spa 99'}: {found['status'].title() or 'unknown'}" + (f", quality {found['quality'].title()}" if found["quality"] else "")) if found["found"] \
        else "That number was not found among the account's WhatsApp senders."
    return {"ok": online, "steps": [{"label": "WhatsApp sender", "ok": online, "detail": detail}]}


# ---------- what the pages need ----------

def message_dict(message):
    reason, _ = errors.reason(message.error_code) if message.status in Message.BAD else ("", False)
    if not reason and is_stuck(message):
        reason = errors.MAYBE_NOT_SENT if is_unsure(message) else errors.TRY_AGAIN
    can_retry_now = bool(reason) and can_retry(message)
    template = message.template
    media = None
    if message.media_key:
        media = {"url": _office("office_whatsapp_media", message.pk), "type": message.media_type, "filename": message.media_filename, "size": message.media_size,
                 "width": message.media_width, "height": message.media_height}
    quoted = message.reply_to
    return {"id": message.pk, "direction": message.direction, "kind": message.kind, "body": message.body,
            "reply_to": {"id": quoted.pk, "direction": quoted.direction, "kind": quoted.kind, "text": quote_text(quoted)} if quoted is not None else None, "body_html": str(formatting.render(message.body)),
            "status": message.status, "error": {"reason": reason, "can_retry": can_retry_now} if reason else None,
            "author": message.author_label, "author_id": str(message.author_id) if message.author_id else "", "author_first_name": _first(message.author_label),
            "template": {"id": str(template.pk), "name": template.name, "label": template.label} if template else None,
            "media": media, "created_at": message.created_at.isoformat(), "sent_at": message.sent_at.isoformat() if message.sent_at else "",
            "retry_url": _office("office_whatsapp_retry", message.contact_id, message.pk) if can_retry_now else ""}


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
            "limits": {"body": settings.WHATSAPP_MAX_BODY, "image_bytes": settings.WHATSAPP_MAX_IMAGE_BYTES, "file_bytes": settings.WHATSAPP_MAX_FILE_BYTES},
            "voice": {"available": voice_available(), "max_seconds": settings.WHATSAPP_VOICE_MAX_SECONDS, "max_bytes": settings.WHATSAPP_VOICE_MAX_UPLOAD_BYTES}}


NO_REPLY_DAYS = 3


def no_reply(contact, at=None):
    """We wrote last, he has never written, and it was more than three days ago (the list's quiet "No reply" badge and chip)."""
    return bool(contact.last_direction == Message.OUT and contact.last_inbound_at is None and contact.last_message_at
                and contact.last_message_at < (at or now()) - timedelta(days=NO_REPLY_DAYS))


def inbox_rows(contacts, user):
    """One dict per chat for the list. `status` is the tick of the latest message when it is ours, `gold` is true for a Gold applicant, `no_reply` for the quiet badge."""
    contacts = list(contacts)
    ids = [c.pk for c in contacts]
    unread = unread_counts(user, ids)
    newest = [r["m"] for r in Message.objects.filter(contact_id__in=ids).values("contact_id").annotate(m=Max("id"))]
    status = dict(Message.objects.filter(pk__in=newest).values_list("contact_id", "status"))
    at = now()
    return [{"id": str(c.pk), "name": c.display_name, "has_name": bool(c.name or c.profile_name), "gold": bool(c.application_id), "phone": c.phone, "preview": c.last_preview,
             "preview_kind": c.last_kind, "direction": c.last_direction, "status": status.get(c.pk, ""), "no_reply": no_reply(c, at),
             "last_message_at": c.last_message_at.isoformat() if c.last_message_at else "", "unread": unread.get(c.pk, 0), "opted_out": c.opted_out,
             "window_open": window_open(c), "url": _office("office_whatsapp_thread", c.pk)} for c in contacts]


def template_dicts(contact=None):
    """Approved templates for the picker: {id, name, label, body_html, variables[{key, label, prefill}]}. Variable "First name" is pre-filled."""
    first = (contact.name or contact.profile_name or "").split(" ")[0] if contact is not None else ""
    return [{"id": str(t.pk), "name": t.name, "label": t.label, "category": t.category, "body": t.body, "body_html": str(template_html(t)),
             "variables": [{"key": k, "label": label_for(t, k), "prefill": first if label_for(t, k).lower() == "first name" else ""} for k in t.variables]}
            for t in usable_templates()]


def open_url(contact, target=None):
    """The link that opens a chat read-only (a plain GET, no write): the thread, remembering which page it was reached from (`from=kind:id`, and `gold=` on a Gold page) so the thread
    can offer the staff link (ownership rule 1a)."""
    query = {}
    if target is not None:
        query["from"] = f"{target.kind}:{target.pk}"
        if target.kind == "gold":
            query["gold"] = str(target.pk)
    return _office("office_whatsapp_thread", contact.pk) + (f"?{urlencode(query)}" if query else "")


def page_context(mobile, user_obj, can_send, start_url, edit_url, first_name="", target=None):
    """The `whatsapp` dict on the lead, person and Gold pages. `state` says what the button shows: `no_mobile` (no number: the email button stands alone, with `reason`
    "Add a number to enable WhatsApp" and, when `can_add_number`, the staff dialog at `edit_url`), `unconfigured` (Twilio is not set up: the button shows greyed with `reason`),
    `view_only` (a reader with no chat yet), `ready` (a number, nothing sent yet) or `chat` (there are messages)."""
    ok = configured()
    base = {"configured": ok, "has_mobile": bool(mobile), "mobile": mobile or "", "first_name": first_name, "contact_url": start_url, "start_url": start_url, "open_url": "",
            "edit_url": edit_url, "can_send": bool(can_send and mobile and ok), "can_edit": bool(can_send), "has_chat": False, "window_open": False,
            "window_closes_at": "", "opted_out": False, "unread": 0, "can_add_number": bool(can_send and edit_url and not mobile), "reason": "", "thread_url": ""}
    contact = Contact.objects.filter(phone=mobile).first() if mobile else None
    if contact is not None and target is not None and not ownership.visible_from_page(contact, target.user, target.addresses, target.application):
        contact = None  # the number is on someone else's chat (a lead's, whoever typed his number): it is not shown as this person's
    if contact is not None:
        ends = window_ends_at(contact)
        base.update({"has_chat": bool(contact.last_message_at), "window_open": window_open(contact), "window_closes_at": ends.isoformat() if ends and window_open(contact) else "",
                     "opted_out": contact.opted_out, "unread": unread_counts(user_obj, [contact.pk]).get(contact.pk, 0), "thread_url": _office("office_whatsapp_thread", contact.pk),
                     "open_url": open_url(contact, target)})
    if not mobile:
        state, reason = "no_mobile", "Add a number to enable WhatsApp"
    elif not ok:
        state, reason = "unconfigured", "WhatsApp is not set up yet."
    elif base["has_chat"]:
        state, reason = "chat", ""
    elif not can_send:
        state, reason = "view_only", ""
    else:
        state, reason = "ready", ""
    return {**base, "state": state, "reason": reason}


# ---------- timeline, export, erase ----------

def contacts_for_person(user=None, addresses=(), application=None):
    """Every chat held for a person, by the rule in common.ownership: the owner link, the lead address (only when his account is verified), a proven Gold application. His mobile
    is never used to find a chat (it was linked by `resolve_links` only where the rule allows). This is the only lookup."""
    return ownership.owned(Contact, user, addresses, application)


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


def erase_person(user=None, addresses=(), application=None):
    return erase_contacts(contacts_for_person(user, addresses, application))


def erase_for_application(application):
    """Gold Delete: the chats staff linked to this application AND to its applicant's address (`ownership.link` gives a Gold-linked chat the applicant's lead address), so an applicant with
    no account leaves none behind. Never a chat held by a verified account: an owner, an account with the applicant's address or the application's own account (his page reaches it). A chat
    linked only through a typed number, or one with no lead address, is not erased here: nothing proves it is his."""
    from users.models import User

    address = ownership.clean(application.email)
    if not address or ownership.is_verified(application.user) or User.objects.filter(email__iexact=address, email_verified_at__isnull=False).exists():
        return erase_contacts([])
    return erase_contacts(Contact.objects.filter(application=application, user__isnull=True, lead_email__iexact=address))


def unclaimed_for_user(user):
    """The chats on his mobile that nobody holds (no owner, no lead address, no application): his page shows them, but person export and delete do not reach them until staff link
    them. [{phone, name, url}], for the confirmation text and the page note; staff open each and delete it from there."""
    if not user.mobile:
        return []
    return [{"phone": c.phone, "name": c.display_name, "url": _office("office_whatsapp_thread", c.pk)}
            for c in Contact.objects.filter(phone=user.mobile) if ownership.is_unlinked(c)]


def delete_chat(contact, actor, request=None):
    """Staff erase one chat: messages, files, queue records (`erase_contacts`). The System audit log gets who, when and the counts, never a message or a name. Returns the counts."""
    from system import audit
    from system.models import SystemEvent

    counts = erase_contacts([contact])
    audit.log_event(SystemEvent.CHAT_DELETED, request, user=actor, detail=counts, sentence=f"{getattr(actor, 'email', '') or 'Staff'} deleted a WhatsApp chat ({counts['whatsapp_messages']} messages)")
    return counts
