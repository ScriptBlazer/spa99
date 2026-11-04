"""Email chat logic: threads and who they belong to, sending (queued, never twice), his inbound mail (Postmark inbound), bounces, files, what the Office
pages need, the timeline lines, and export / erasure. The views stay thin and call these. Rich text is cleaned by `common.richtext`; mail is sent by
`notifications.services.send_templated` (the suppression guard)."""
import base64
import binascii
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from urllib.parse import urlencode, urlparse

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, F, Max, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone
from django.utils.html import linebreaks

from common import richtext
from common.tasks import enqueue

from .models import Attachment, Message, Thread, ThreadRead

logger = logging.getLogger("spa99.emailchat")

EPOCH = datetime(1970, 1, 1, tzinfo=dt_timezone.utc)
DUPLICATE_WINDOW = timedelta(seconds=10)
STUCK_AFTER = timedelta(minutes=5)
CLAIM_TIMEOUT = timedelta(minutes=10)  # longer than the worker job limit and all its retries (Q_CLUSTER timeout 120 s, retry 180 s, 3 attempts)
MAX_TEXT = 100_000
MAX_INBOUND_TEXT = 200_000
MAX_INBOUND_HTML = 1_000_000
DEFAULT_SUBJECT = "A message from Spa 99"
INLINE_TYPES = {"image/png": b"\x89PNG", "image/jpeg": b"\xff\xd8\xff", "image/gif": b"GIF8", "application/pdf": b"%PDF-"}  # + WebP, checked by hand below
NEVER_SENT = {"exe", "bat", "cmd", "com", "scr", "pif", "js", "jse", "vbs", "vbe", "wsf", "wsh", "jar", "msi", "dll", "lnk", "ps1", "hta", "cpl", "reg", "app", "dmg", "apk"}
EMBED_LIMIT, EMBED_TOTAL = 1_000_000, 5_000_000  # his cid: pictures are put into the frame as data: addresses up to this size each and in all

DONE, EMPTY, TOO_LONG, DUPLICATE, BAD_ADDRESS, BAD_FILE, TOO_BIG, NOT_RETRYABLE, NO_SUBJECT, BAD_TARGET = (
    "done", "empty", "too_long", "duplicate", "bad_address", "bad_file", "too_big", "not_retryable", "no_subject", "bad_target")
WORDS = {EMPTY: "Write a message first.", TOO_LONG: "That message is too long.", DUPLICATE: "That message was just sent.", BAD_ADDRESS: "That email address does not look right.",
         BAD_FILE: "That type of file cannot be sent by email.", TOO_BIG: "Files can be 10 MB each and 9 MB in all.", NOT_RETRYABLE: "That message cannot be sent again.",
         NO_SUBJECT: "Add a subject.", BAD_TARGET: "That person could not be found."}
REASONS = {"suppressed": ("Not sent. This address bounced before or marked an email as spam, so nothing more can be sent to it.", False),
           "bounced": ("Bounced. The address did not accept this email.", False), "complaint": ("Marked as spam by the recipient. Nothing more can be sent to this address.", False),
           "send_failed": ("Not sent. Try again.", True)}


MAYBE_NOT_SENT = "This may not have been sent. Check with him before trying again, in case it did arrive."


def now():
    return timezone.now()


# ---------- settings ----------

def inbound_domain():
    return settings.EMAIL_INBOUND_DOMAIN


def replies_to_mailbox():
    """No inbound domain: Reply-To stays the hello@ address and his replies go to that mailbox, not into the Office."""
    return not inbound_domain()


def inbound_configured():
    return bool(settings.EMAIL_INBOUND_DOMAIN and settings.EMAIL_INBOUND_USER and settings.EMAIL_INBOUND_PASSWORD)


def reply_to_address(thread):
    return f"reply+{thread.token}@{inbound_domain()}" if inbound_domain() else ""


def _office(name, *args):
    return reverse(name, args=args, urlconf="config.urls_office")


# ---------- addresses, subjects, previews ----------

def clean_address(value):
    """Lower-cased address, or '' when it is not one."""
    value = (value or "").strip().lower()
    if not value or len(value) > 254 or any(ch.isspace() for ch in value) or "\x00" in value:
        return ""
    try:
        validate_email(value)
    except ValidationError:
        return ""
    return value


def subject_key(subject):
    return re.sub(r"^(?:\s*(?:re|fw|fwd|aw|sv)\s*:\s*)+", "", subject or "", flags=re.I).strip().lower()


def clean_subject(subject):
    return " ".join((subject or "").replace("\x00", "").split())[:300]


def preview_of(text):
    for line in (text or "").splitlines():
        line = line.strip().lstrip(">").strip()
        if line:
            return line[:200]
    return ""


def _shows_subject(thread, subject):
    last = Message.objects.filter(thread=thread).exclude(subject="").order_by("-id").values_list("subject", flat=True).first()
    return last is None or subject_key(last) != subject_key(subject)


def reply_subject(thread, given=""):
    """What the next email's subject is: the one typed, else "Re: " and the last subject (the thread's first subject while nothing is in it yet)."""
    given = clean_subject(given)
    if given:
        return given
    last = Message.objects.filter(thread=thread).exclude(subject="").order_by("-id").values_list("subject", flat=True).first()
    base = last or thread.subject or DEFAULT_SUBJECT
    if last is None or re.match(r"^\s*re\s*:", base, re.I):
        return base
    return clean_subject(f"Re: {base}")  # clean_subject trims to the column length (300) after "Re: " is added


# ---------- threads and who they are ----------

def resolve_links(thread, save=True):
    """Find who owns this address: an account, a lead (he left it at the journey gate), a Gold application. Only a VERIFIED account is linked (an unverified account may carry
    someone else's address: anyone can register with any address, so it never takes the thread, its owner link or its name). A link found now replaces the stored one; nothing
    found never clears it. The owner link does not survive an address correction by itself: `move_address` moves the threads (and so the erasure still finds them)."""
    from gold.models import GoldApplication
    from journey.models import JourneySession
    from users.models import User

    user = User.objects.filter(email__iexact=thread.email, email_verified_at__isnull=False).first()
    session = JourneySession.objects.filter(lead_email__iexact=thread.email, is_bot=False).order_by("-created_at").first()
    application = GoldApplication.objects.filter(email__iexact=thread.email).order_by("-created_at").first()
    name = ""
    if user is not None:
        name = (user.get_full_name() or "").strip()
    if not name and session is not None:
        named = JourneySession.objects.filter(lead_email__iexact=thread.email, is_bot=False).exclude(lead_first_name="").order_by("-created_at").first()
        name = named.lead_first_name if named else ""
    if not name and application is not None:
        name = application.full_name
    if user is not None:
        thread.user = user
    elif session is not None:
        thread.lead_email = thread.email
    if application is not None:
        thread.application = application
    if name:
        thread.name = name[:100]
    if save:
        thread.save(update_fields=["user", "lead_email", "application", "name"])
    return thread


def move_address(old, new):
    """A lead's address was corrected (outreach.services.correct_lead_email, in its transaction): his threads move to the new address, so the lead page, export and erasure
    find them. Each thread keeps its reply token, so a late reply to the old Reply-To still lands in the same thread. A thread owned by an account is left alone. Returns the number moved."""
    old, new = (old or "").strip().lower(), (new or "").strip().lower()
    if not old or not new or old == new:
        return 0
    moved = Thread.objects.filter(email=old, user__isnull=True).update(email=new)
    Thread.objects.filter(lead_email=old).update(lead_email=new)
    return moved


def relink(*addresses):
    """An address was added or corrected: refresh the links of the threads on it. Best effort."""
    try:
        for thread in Thread.objects.filter(email__in=[a.lower() for a in addresses if a]):
            resolve_links(thread)
    except Exception:  # noqa: BLE001
        logger.exception("Could not refresh the email chat links")


def create_thread(email, subject, actor=None):
    """A new thread for this address (always a new one: a person can have many). Returns (result, thread)."""
    address = clean_address(email)
    if not address:
        return BAD_ADDRESS, None
    subject = clean_subject(subject)
    if not subject:
        return NO_SUBJECT, None
    thread = Thread(email=address, subject=subject, created_by=actor if getattr(actor, "pk", None) else None)
    resolve_links(thread, save=False)
    thread.save()
    return DONE, thread


def threads_for(addresses=(), user=None, application=None):
    query = Q(pk__in=[])
    addresses = [a.lower() for a in addresses if a]
    if addresses:
        query |= Q(email__in=addresses) | Q(lead_email__in=addresses)
    if user is not None:
        query |= Q(user=user)
    if application is not None:
        query |= Q(application=application)
    return Thread.objects.filter(query)


def latest_thread(addresses=(), user=None, application=None):
    """His most recent thread (by its last message, or when it was made), or None. The page button says Open when there is one and Start when not."""
    found = threads_for(addresses, user, application).filter(Exists(Message.objects.filter(thread=OuterRef("pk")))).annotate(
        at=Coalesce("last_message_at", "created_at")).order_by("-at", "-created_at")  # an empty thread (nothing sent or received) is not one to open
    return found.first()


def page_context(target, user_obj, can_edit):
    """The `email_chat` dict on the lead, person and Gold pages: {has_thread, thread_count, latest_thread_url, new_email_url, open_url, state (start|open), label, email,
    can_send, can_edit, unread, replies_to_mailbox, suppressed, reason}. `open_url` opens his latest thread, or the New email screen when there is none."""
    from notifications import suppression

    kind = target.kind
    ref = f"{kind}:{target.pk}"
    new_url = _office("office_email_new") + "?" + urlencode({"person": ref})
    threads = threads_for(target.addresses, target.user, target.application)
    latest = latest_thread(target.addresses, target.user, target.application)
    address = target.main
    count = threads.count()
    unread = unread_counts(user_obj, [t.pk for t in threads]) if count else {}
    suppressed = bool(address and suppression.is_suppressed(address))
    return {"has_thread": latest is not None, "thread_count": count, "latest_thread_url": _office("office_email_thread", latest.pk) if latest else "",
            "new_email_url": new_url, "open_url": reverse(f"office_{kind}_email_chat", args=[target.pk]), "state": "open" if latest else "start", "label": "Open email thread" if latest else "Start email",
            "email": address, "can_send": bool(can_edit and address), "can_edit": bool(can_edit), "unread": sum(unread.values()), "replies_to_mailbox": replies_to_mailbox(),
            "suppressed": suppressed, "reason": "This address bounced or marked an email as spam: nothing can be sent to it." if suppressed else ""}


# ---------- unread (per staff member) ----------

def _read_after(user, thread_ref):
    return Coalesce(Subquery(ThreadRead.objects.filter(thread=OuterRef(thread_ref), user=user).values("read_at")[:1]), Value(EPOCH))


def unread_counts(user, thread_ids):
    rows = (Message.objects.filter(thread_id__in=list(thread_ids), direction=Message.IN, spam=False).annotate(ra=_read_after(user, "thread_id"))
            .filter(created_at__gt=F("ra")).values("thread_id").annotate(n=Count("id")))
    return {r["thread_id"]: r["n"] for r in rows}


def unread_total(user):
    """How many threads have unread messages (the navigation badge counts threads)."""
    return (Thread.objects.annotate(ra=_read_after(user, "pk"))
            .filter(Exists(Message.objects.filter(thread=OuterRef("pk"), direction=Message.IN, spam=False, created_at__gt=OuterRef("ra")))).count())


def first_unread(user, thread):
    after = ThreadRead.objects.filter(thread=thread, user=user).values_list("read_at", flat=True).first() or EPOCH
    rows = list(Message.objects.filter(thread=thread, direction=Message.IN, spam=False, created_at__gt=after).order_by("id").values_list("id", flat=True))
    return len(rows), (rows[0] if rows else None)


def mark_read(thread, user):
    ThreadRead.objects.update_or_create(thread=thread, user=user, defaults={"read_at": now()})


# ---------- files ----------

def safe_filename(name, fallback="file"):
    name = re.sub(r"[^\w .()@+-]", "_", (name or "").replace("\\", "/").rsplit("/", 1)[-1]).strip(" .")[:200]
    return name or fallback


def sniff_inline(data, declared):
    """The checked content type of an image or PDF whose own first bytes match, else ''. The declared type is never trusted alone."""
    declared = (declared or "").split(";")[0].strip().lower()
    if declared == "image/webp" and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    magic = INLINE_TYPES.get(declared)
    return declared if magic and data.startswith(magic) else ""


def _store_file(thread, data):
    return default_storage.save(f"emailchat/{thread.pk}/{uuid.uuid4().hex}", ContentFile(data))


# ---------- sending ----------

def send(thread, actor, subject, html, uploads=()):
    """Queue an email in this thread. `html` is what the editor produced: it is cleaned here (and again by send_templated) and a plain text copy is made. `uploads` are
    files. Returns (result, message). A duplicate within 10 seconds is refused."""
    clean = richtext.clean_outgoing(html)
    text = richtext.html_to_text(clean)
    uploads = list(uploads)
    if not text and not uploads:
        return EMPTY, None
    if len(text) > MAX_TEXT or len(clean) > MAX_TEXT * 3:
        return TOO_LONG, None
    files, total = [], 0
    for upload in uploads[:settings.EMAILCHAT_MAX_ATTACHMENTS]:
        name = safe_filename(getattr(upload, "name", ""))
        if name.rsplit(".", 1)[-1].lower() in NEVER_SENT and "." in name:
            return BAD_FILE, None
        data = upload.read(settings.EMAILCHAT_MAX_ATTACHMENT_BYTES + 1)
        total += len(data)
        if len(data) > settings.EMAILCHAT_MAX_ATTACHMENT_BYTES or total > settings.EMAILCHAT_MAX_SEND_BYTES:
            return TOO_BIG, None
        files.append((name, data, (getattr(upload, "content_type", "") or "application/octet-stream").split(";")[0][:100]))
    subject = reply_subject(thread, subject)
    since = now() - DUPLICATE_WINDOW
    recent = Message.objects.filter(thread=thread, direction=Message.OUT, body_html=clean, created_at__gte=since)
    recent = recent.filter(author=actor) if getattr(actor, "pk", None) else recent.filter(author__isnull=True)
    if recent.exists() and not files:
        return DUPLICATE, None
    from gold import audit

    keys = []
    try:
        for name, data, content_type in files:
            keys.append((_store_file(thread, data), name, content_type, len(data)))
        with transaction.atomic():
            message = Message.objects.create(thread=thread, direction=Message.OUT, subject=subject, shows_subject=_shows_subject(thread, subject), body_text=text, body_html=clean,
                                             status=Message.QUEUED, author=actor if getattr(actor, "pk", None) else None, author_label=audit.label_for(actor))
            for key, name, content_type, size in keys:
                Attachment.objects.create(message=message, key=key, filename=name, content_type=content_type, declared_type=content_type, size=size, checked=True)
            _touch_thread(thread, message)
    except Exception:
        for key, *_ in keys:
            default_storage.delete(key)
        raise
    _enqueue_send(message)
    return DONE, message


def _touch_thread(thread, message):
    update = {"last_message_at": message.created_at, "last_preview": preview_of(message.body_text) or ("Attachment" if message.pk and message.attachments.exists() else ""), "last_direction": message.direction}
    if message.direction == Message.IN:
        update["last_inbound_at"] = message.created_at
    if message.attachments.exists():
        update["has_attachment"] = True
    Thread.objects.filter(pk=thread.pk).update(**update)


def _enqueue_send(message):
    try:
        enqueue("emailchat.tasks.send_message", message.pk)
    except Exception:  # noqa: BLE001 - recorded as queued; "Try again" resends
        logger.exception("Could not queue email chat message %s", message.pk)


def is_stuck(message, at=None):
    """Queued and lost: never taken by a worker for a few minutes, or taken by a worker that then died (claimed more than CLAIM_TIMEOUT ago, still queued). In the second
    case the worker may have died after the mail server took the email and before SENT was written, so a Try again can, rarely, send it twice; the page says "may not have
    been sent"."""
    at = at or now()
    if message.direction != Message.OUT or message.status != Message.QUEUED:
        return False
    if message.claimed_at is None:
        return message.updated_at < at - STUCK_AFTER
    return message.claimed_at < at - CLAIM_TIMEOUT


def is_unsure(message, at=None):
    return bool(message.claimed_at is not None and is_stuck(message, at))


def can_retry(message):
    """Only a send that failed before the mail server took it (never a bounce: that mail was accepted once), or one the queue lost."""
    if message.direction != Message.OUT:
        return False
    if message.status == Message.FAILED:
        return REASONS.get(message.error_code, REASONS["send_failed"])[1]
    return is_stuck(message)


def retry(message):
    """The same bubble again. One conditional update, so a double click sends once. Returns (result, message)."""
    message.refresh_from_db()
    if not can_retry(message):
        return NOT_RETRYABLE, None
    claimed = Message.objects.filter(pk=message.pk, status=message.status, claimed_at=message.claimed_at).update(
        status=Message.QUEUED, error_code="", error_message="", claimed_at=None, updated_at=now())
    if not claimed:
        return NOT_RETRYABLE, None
    message.refresh_from_db()
    _enqueue_send(message)
    return DONE, message


def _headers(message):
    """Message-ID of our own, In-Reply-To and References from the mail before it (so mail apps keep the thread together), and the Postmark tag and metadata that
    bring a bounce back to this message (SMTP gives us no Postmark MessageID at send time)."""
    host = urlparse(settings.SITE_URL).hostname or "spa99.uk"
    own = f"<spa99-{message.pk}-{uuid.uuid4().hex[:12]}@{host}>"
    headers = {"Message-ID": own, "X-PM-Tag": "office-chat", "X-PM-Metadata-chat": str(message.pk)}
    prior = Message.objects.filter(thread_id=message.thread_id, pk__lt=message.pk).exclude(rfc_message_id="").order_by("-id")
    last = prior.filter(direction=Message.IN).first() or prior.first()
    last_id = clean_id(last.rfc_message_id) if last is not None else ""  # cleaned on read too: older rows may hold a newline
    if last_id:
        chain = (clean_references(last.references).split() + [last_id])[-10:]
        headers["In-Reply-To"] = last_id
        headers["References"] = " ".join(chain)
    return headers, own


def deliver(message):
    """The worker's side of a send: one `send_templated` call, and the outcome on the message. Never sends twice. A suppressed address comes back SUPPRESSED from
    send_templated (its guard) and shows as failed with a plain reason."""
    if not Message.objects.filter(pk=message.pk, status=Message.QUEUED, claimed_at__isnull=True).update(claimed_at=now()):
        return "skipped"
    message.refresh_from_db()
    from notifications import emailsettings
    from notifications.models import EmailLog
    from notifications.services import send_templated
    from plans.models import SiteSettings

    thread = message.thread
    try:
        headers, own = _headers(message)
        Message.objects.filter(pk=message.pk).update(rfc_message_id=own)
        from_email, _ = emailsettings.sender_for(emailsettings.options_for("office_message"), SiteSettings.load())
        attachments = []
        for item in message.attachments.all():
            with default_storage.open(item.key, "rb") as handle:
                attachments.append((item.filename, handle.read(), item.declared_type or "application/octet-stream"))
        reply_to = [reply_to_address(thread)] if inbound_domain() else None  # None: send_templated uses the contact (hello@) address
        first_name = (thread.name or "").split(" ")[0]
        log = send_templated("office_message", [thread.email], message.subject, {"first_name": first_name}, subject_email=thread.email, headers=headers,
                             html_body=message.body_html, plain_body=message.body_text, attachments=attachments, from_email=from_email or settings.DEFAULT_FROM_EMAIL, reply_to=reply_to)
    except Exception:  # noqa: BLE001 - the outcome is recorded on the message, never raised
        logger.exception("Email chat message %s could not be prepared", message.pk)
        return _fail(message, "send_failed", "Could not be prepared.")
    if log.status == EmailLog.SENT:
        Message.objects.filter(pk=message.pk, status=Message.QUEUED).update(status=Message.SENT, sent_at=now(), updated_at=now())
        return "sent"
    if log.status == EmailLog.SUPPRESSED:
        return _fail(message, "suppressed", "On the suppression list.")
    return _fail(message, "send_failed", (log.error or "")[:300])


def _fail(message, code, text):
    Message.objects.filter(pk=message.pk).update(status=Message.FAILED, error_code=code[:20], error_message=text[:300], updated_at=now())
    return "failed"


# ---------- bounces and deliveries (Postmark feedback webhook) ----------

IGNORED_BOUNCES = {"Transient", "AutoResponder", "DnsError"}  # not a failure of this email


def _our_message(record):
    metadata = record.get("Metadata")
    try:
        pk = int(metadata.get("chat")) if isinstance(metadata, dict) else None
    except (TypeError, ValueError):
        return None
    message = Message.objects.select_related("thread").filter(pk=pk, direction=Message.OUT).first() if pk else None
    address = record.get("Email") or record.get("Recipient") or ""
    if message is None or not isinstance(address, str) or message.thread.email != address.strip().lower():  # the address must be the one we wrote to
        return None
    return message


def apply_feedback(record):
    """A Postmark Bounce, SpamComplaint or Delivery record: mark the chat message it names (Metadata `chat`). Returns True when a message was updated. Never raises."""
    try:
        kind = record.get("RecordType")
        message = _our_message(record) if kind in ("Bounce", "SpamComplaint", "Delivery") else None
        if message is None:
            return False
        provider = record.get("MessageID") if isinstance(record.get("MessageID"), str) else ""
        update = {"updated_at": now()}
        if provider and not Message.objects.filter(provider_id=provider).exclude(pk=message.pk).exists():
            update["provider_id"] = provider[:100]
        if kind == "Delivery":
            if message.status == Message.SENT:
                update["status"] = Message.DELIVERED
        elif kind == "SpamComplaint" or record.get("Type") in ("SpamComplaint", "Unsubscribe"):
            update.update(status=Message.BOUNCED, error_code="complaint", error_message="Marked as spam by the recipient.")
        elif record.get("Type") in IGNORED_BOUNCES:
            return False
        else:
            detail = record.get("Details") or record.get("Description") or ""
            update.update(status=Message.BOUNCED, error_code="bounced", error_message=(detail if isinstance(detail, str) else "")[:300])
        Message.objects.filter(pk=message.pk).update(**update)
        return True
    except Exception:  # noqa: BLE001 - the existing bounce handling must never be stopped by the chat
        logger.exception("Could not apply Postmark feedback to the email chat")
        return False


# ---------- inbound (Postmark inbound webhook) ----------

def _header(payload, name):
    for item in payload.get("Headers") or []:
        if isinstance(item, dict) and str(item.get("Name", "")).lower() == name.lower():
            return str(item.get("Value", ""))
    return ""


def clean_id(value):
    """A Message-ID or In-Reply-To value on one line with no whitespace (a stored newline would make every later reply fail with BadHeaderError)."""
    return "".join((value or "").split())


def clean_references(value):
    return " ".join((value or "").split())


def _text(value, limit):
    return value.replace("\x00", "")[:limit] if isinstance(value, str) else ""


def thread_for_token(payload):
    token = _text(payload.get("MailboxHash"), 64).strip().lower()
    return Thread.objects.filter(token=token).first() if re.fullmatch(r"[0-9a-f]{24}", token) else None


def record_inbound(payload, thread):
    """Store one email from him in `thread` (idempotent on Postmark's MessageID). Returns (message, created). Files are not touched here: see store_inbound_files."""
    provider_id = _text(payload.get("MessageID"), 100).strip()
    existing = Message.objects.filter(provider_id=provider_id).first()
    if existing is not None:
        return existing, False
    full = payload.get("FromFull") if isinstance(payload.get("FromFull"), dict) else {}
    from_address = clean_address(_text(full.get("Email"), 254)) or clean_address(_text(payload.get("From"), 254))
    from_name = _text(full.get("Name"), 200) or _text(payload.get("FromName"), 200)
    html_in = _text(payload.get("HtmlBody"), MAX_INBOUND_HTML)
    html = richtext.clean_incoming(html_in) if html_in.strip() else ""
    stripped, whole = _text(payload.get("StrippedTextReply"), MAX_INBOUND_TEXT).strip(), _text(payload.get("TextBody"), MAX_INBOUND_TEXT).strip()
    text = stripped or whole or richtext.html_to_text(html)  # his new words, else his whole text, else the HTML as text
    subject = clean_subject(_text(payload.get("Subject"), 400))
    spam = _header(payload, "X-Spam-Status").strip().lower().startswith("yes")
    try:
        with transaction.atomic():
            message = Message.objects.create(
                incomplete=True, claimed_at=now(), thread=thread, direction=Message.IN, subject=subject, shows_subject=_shows_subject(thread, subject), body_text=text, body_full=whole if stripped and whole != stripped else "",
                body_html=html, has_remote_images=bool(richtext.remote_image_count(html)), status=Message.RECEIVED, provider_id=provider_id or None,
                rfc_message_id=clean_id(_text(_header(payload, "Message-ID"), 300)), in_reply_to=clean_id(_text(_header(payload, "In-Reply-To"), 300)),
                references=clean_references(_text(_header(payload, "References"), 3000)), from_address=from_address, from_name=from_name, spam=spam)
            if not spam:  # spam never moves the thread, never counts unread, never pushes. In the same transaction as the message: a death cannot leave one the inbox does not show
                _touch_thread(thread, message)
    except IntegrityError:  # Postmark sent it twice at once
        return Message.objects.get(provider_id=provider_id), False
    return message, True


INBOUND_CLAIM = timedelta(minutes=2)


class StoreError(Exception):
    """His files could not be stored."""


def claim_inbound(message):
    """Take an incomplete email to finish (Postmark's retry of the same MessageID). One conditional update: an attempt still working on it (claimed less than two minutes
    ago) keeps it, so two attempts never store its files twice at once."""
    return bool(Message.objects.filter(pk=message.pk, incomplete=True).filter(Q(claimed_at__isnull=True) | Q(claimed_at__lt=now() - INBOUND_CLAIM)).update(claimed_at=now()))


def clear_files(message):
    """Take the stored files of a message out (rows and storage) so a second go at storing them cannot double them."""
    for item in list(message.attachments.all()):
        try:
            default_storage.delete(item.key)
        except Exception:  # noqa: BLE001
            logger.warning("Could not delete an email file from storage")
        item.delete()


def finish_inbound(message, payload, resumed=False):
    """Files stored and the worker task queued: then (and only then) the message is complete. A resume (a retry after a death or a failed queue) starts its files again from
    the payload, so nothing is stored twice. Raises when the files cannot be stored or the task cannot be queued: the webhook answers 500 and Postmark retries."""
    try:
        if resumed:
            clear_files(message)
        store_inbound_files(message, payload.get("Attachments"))
    except Exception as error:
        raise StoreError from error
    enqueue("emailchat.tasks.process_inbound", message.pk)
    Message.objects.filter(pk=message.pk).update(incomplete=False)


def store_inbound_files(message, items):
    """His attachments (Postmark `Attachments`: Name, Content base64, ContentType, ContentLength, ContentID). A file over the size limit, past the count limit or
    that cannot be decoded is dropped and the message gets a note. Each file goes straight to the default storage (web and worker share no disk, so S3 is the
    one safe place to hand bytes over: the task queue only ever holds ids). Returns the number kept."""
    kept, notes, limit = 0, [], settings.EMAILCHAT_MAX_ATTACHMENT_BYTES
    items = [i for i in (items or []) if isinstance(i, dict)]
    for index, item in enumerate(items):
        name = safe_filename(_text(item.get("Name"), 300), fallback="file")
        content = item.get("Content") if isinstance(item.get("Content"), str) else ""
        if index >= settings.EMAILCHAT_MAX_ATTACHMENTS:
            notes.append(f"{name} was not kept (too many files).")
            continue
        if len(content) * 3 // 4 > limit:
            notes.append(f"{name} was too big to keep (over {limit // (1024 * 1024)} MB).")
            continue
        try:
            data = base64.b64decode(content, validate=False)
        except (binascii.Error, ValueError):
            notes.append(f"{name} could not be read.")
            continue
        if len(data) > limit:
            notes.append(f"{name} was too big to keep (over {limit // (1024 * 1024)} MB).")
            continue
        key = _store_file(message.thread, data)  # a storage failure is not caught: the webhook answers 500 and Postmark retries
        declared = _text(item.get("ContentType"), 100).split(";")[0].strip().lower()
        cid = _text(item.get("ContentID"), 300).strip().removeprefix("cid:").strip("<>")
        Attachment.objects.create(message=message, key=key, filename=name, content_type="application/octet-stream", declared_type=declared, size=len(data), content_id=cid)
        kept += 1
    if notes:
        Message.objects.filter(pk=message.pk).update(note=" ".join(notes)[:500])
    if kept:
        Thread.objects.filter(pk=message.thread_id).update(has_attachment=True)
        if not message.thread.last_preview and not message.spam:
            Thread.objects.filter(pk=message.thread_id).update(last_preview="Attachment")
    return kept


def check_files(message):
    """The worker looks at each file's first bytes. Only an image or PDF whose bytes match its declared type is shown inline; everything else downloads."""
    for item in message.attachments.filter(checked=False):
        try:
            with default_storage.open(item.key, "rb") as handle:
                head = handle.read(16)
        except Exception:  # noqa: BLE001
            logger.warning("Could not read email file %s", item.pk)
            head = b""
        checked = sniff_inline(head, item.declared_type)
        Attachment.objects.filter(pk=item.pk).update(checked=True, inline_ok=bool(checked), content_type=checked or "application/octet-stream")


def push_payload(message):
    thread = message.thread
    who = thread.name or message.from_name or thread.email
    first = preview_of(message.body_text) or ("Sent a file" if message.attachments.exists() else "New email")
    return {"title": f"Email from {who}", "body": f"{message.subject}: {first}"[:100] if message.subject else first[:100], "url": _office("office_email_thread", thread.pk), "tag": f"email-{thread.pk}"}


# ---------- his HTML, for the sandboxed frame ----------

IMG = re.compile(r"<img\b[^>]*>", re.I)
SRC = re.compile(r'\ssrc="([^"]*)"', re.I)
FRAME_CSS = ("body{margin:0;padding:8px;font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#222;background:#fff;overflow-wrap:anywhere}"
             "img{max-width:100%;height:auto}table{max-width:100%}a{color:#06c}pre{white-space:pre-wrap}"
             "blockquote,.quoted{margin:8px 0;background:#f6f5f2;border-radius:6px;padding:8px 10px;color:#555}"  # a tint, not a one-sided line (BRAND)
             "@media (max-width:30em){body{font-size:16px}}")  # BRAND's body minimum on a phone


def frame_html(message, images=False):
    """The document for his email's frame: his cleaned HTML, outside pictures removed unless `images`, `cid:` pictures put in from the stored files as data: addresses.
    Returns (document, blocked) where `blocked` counts outside pictures left out. The endpoint adds a strict CSP: no scripts, no forms."""
    cids = {a.content_id: a for a in message.attachments.exclude(content_id="") if a.size <= EMBED_LIMIT}
    state = {"blocked": 0, "embedded": 0}

    def swap(match):
        tag = match.group(0)
        found = SRC.search(tag)
        src = found.group(1) if found else ""
        if src.lower().startswith("cid:"):
            item = cids.get(src[4:].strip("<>"))
            if item is None or state["embedded"] + item.size > EMBED_TOTAL:
                return ""
            kind = sniff_inline_file(item)
            if not kind.startswith("image/"):
                return ""
            with default_storage.open(item.key, "rb") as handle:
                data = handle.read()
            state["embedded"] += item.size
            return tag.replace(found.group(0), f' src="data:{kind};base64,{base64.b64encode(data).decode()}"', 1)
        if src.lower().startswith(("http://", "https://")):
            if images:
                return tag
            state["blocked"] += 1
            return ""
        return ""

    body = IMG.sub(swap, message.body_html)
    doc = f'<!doctype html><html><head><meta charset="utf-8"><meta name="referrer" content="no-referrer"><style>{FRAME_CSS}</style></head><body>{body}</body></html>'
    return doc, state["blocked"]


def sniff_inline_file(item):
    try:
        with default_storage.open(item.key, "rb") as handle:
            return sniff_inline(handle.read(16), item.declared_type)
    except Exception:  # noqa: BLE001
        return ""


def frame_csp(images=False):
    pictures = "data: https: http:" if images else "data:"
    return (f"default-src 'none'; img-src {pictures}; style-src 'unsafe-inline'; font-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'self'; "
            "sandbox allow-same-origin allow-popups allow-popups-to-escape-sandbox")


# ---------- what the pages need ----------

def _first(label):
    return (label or "").split(" (")[0].split("@")[0].split(" ")[0]


def attachment_dict(item):
    return {"id": item.pk, "filename": item.filename, "type": item.content_type, "size": item.size, "url": _office("office_email_file", item.pk), "inline": item.inline_ok,
            "is_image": item.inline_ok and item.content_type.startswith("image/")}


def message_dict(message):
    """{id, direction, subject, shows_subject, body_text, body_full, body_html (ours: cleaned, safe to show; his: always empty), frame_url and frame_images_url (his HTML: a
    sandboxed frame; empty when he sent plain text), has_remote_images, status, error{reason, can_retry} or null, author, author_id, author_first_name, from_address,
    from_name, from_other (it came from an address other than the thread's), spam, note, attachments[{id, filename, type, size, url, inline, is_image}], created_at, sent_at, retry_url}."""
    reason = ""
    if message.status in Message.BAD:
        reason = REASONS.get(message.error_code, REASONS["send_failed"])[0]
    elif is_stuck(message):
        reason = MAYBE_NOT_SENT if is_unsure(message) else REASONS["send_failed"][0]
    can = bool(reason) and can_retry(message)
    mine = message.direction == Message.OUT
    html = message.body_html or (str(linebreaks(message.body_text, autoescape=True)) if mine else "")  # an old copied message has text only: shown as safe paragraphs
    frame = _office("office_email_frame", message.pk) if (not mine and message.body_html) else ""
    return {"id": message.pk, "direction": message.direction, "subject": message.subject, "shows_subject": message.shows_subject, "body_text": message.body_text,
            "body_full": message.body_full, "body_html": html if mine else "", "frame_url": frame, "frame_images_url": frame + "?images=1" if frame else "",
            "has_remote_images": message.has_remote_images, "status": message.status, "error": {"reason": reason, "can_retry": can} if reason else None, "author": message.author_label,
            "author_id": str(message.author_id) if message.author_id else "", "author_first_name": _first(message.author_label), "from_address": message.from_address,
            "from_name": message.from_name, "from_other": bool(not mine and message.from_address != message.thread.email), "spam": message.spam, "note": message.note,
            "attachments": [attachment_dict(a) for a in message.attachments.all()], "created_at": message.created_at.isoformat(), "sent_at": message.sent_at.isoformat() if message.sent_at else "",
            "retry_url": _office("office_email_retry", message.thread_id, message.pk) if can else ""}


def thread_dict(thread, can_send=False):
    """{id, email, name, has_name, subject, labels[Lead|Registered|Gold], page_url, url, last_message_at, replies_to_mailbox, suppressed, reason, can_send, limits{...}}."""
    from notifications import suppression

    labels = []
    if thread.application_id:
        labels.append("Gold")
    if thread.user_id:
        labels.append("Registered")
    elif thread.lead_email:
        labels.append("Lead")
    page = ""
    if thread.application_id:
        page = _office("office_gold_application", thread.application_id)
    elif thread.user_id:
        page = _office("office_person", thread.user_id) if hasattr(thread.user, "interest") else ""
    elif thread.lead_email:
        from journey.models import JourneySession

        session = JourneySession.objects.filter(lead_email__iexact=thread.lead_email, is_bot=False).order_by("-created_at").values_list("pk", flat=True).first()
        page = _office("office_lead", session) if session else ""
    suppressed = suppression.is_suppressed(thread.email)
    return {"id": str(thread.pk), "email": thread.email, "name": thread.name or thread.email, "has_name": bool(thread.name), "subject": thread.subject, "labels": labels, "page_url": page,
            "url": _office("office_email_thread", thread.pk), "last_message_at": thread.last_message_at.isoformat() if thread.last_message_at else "",
            "replies_to_mailbox": replies_to_mailbox(), "suppressed": suppressed, "reason": "This address bounced or marked an email as spam: nothing can be sent to it." if suppressed else "",
            "can_send": bool(can_send and not suppressed),
            "limits": {"file_bytes": settings.EMAILCHAT_MAX_ATTACHMENT_BYTES, "send_bytes": settings.EMAILCHAT_MAX_SEND_BYTES, "files": settings.EMAILCHAT_MAX_ATTACHMENTS}}


def inbox_rows(threads, user):
    """One dict per thread: {id, subject, name, email, preview, direction, status (the tick of the latest message when ours), last_message_at, unread, has_attachment, no_reply, gold, url}."""
    threads = list(threads)
    ids = [t.pk for t in threads]
    unread = unread_counts(user, ids)
    newest = [r["m"] for r in Message.objects.filter(thread_id__in=ids).values("thread_id").annotate(m=Max("id"))]
    status = dict(Message.objects.filter(pk__in=newest).values_list("thread_id", "status"))
    return [{"id": str(t.pk), "subject": t.subject, "name": t.name or t.email, "has_name": bool(t.name), "email": t.email, "preview": t.last_preview, "direction": t.last_direction,
             "status": status.get(t.pk, ""), "last_message_at": t.last_message_at.isoformat() if t.last_message_at else "", "unread": unread.get(t.pk, 0), "has_attachment": t.has_attachment,
             "no_reply": t.last_direction == Message.OUT, "gold": bool(t.application_id), "url": _office("office_email_thread", t.pk)} for t in threads]


def search_people(q, limit=10):
    """Known people for the New email screen: leads (an address left at the journey gate), registered people and Gold applicants, matched on name or address. Two letters
    at least, ten results at most, and only name and address: never a list to export. [{name, email, kind, kinds, person, suppressed}]."""
    from gold.models import GoldApplication
    from journey.models import JourneySession
    from notifications import suppression
    from users.models import User

    q = (q or "").strip()
    if len(q) < 2:
        return []
    found = {}

    def add(email, name, kind, ref):
        email = (email or "").strip().lower()
        if not email:
            return
        row = found.setdefault(email, {"name": name or "", "email": email, "kinds": [], "person": ref})
        if kind not in row["kinds"]:
            row["kinds"].append(kind)
        if name and not row["name"]:
            row["name"] = name

    for u in User.objects.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q), interest__isnull=False).order_by("-created_at")[:limit]:
        add(u.email, u.get_full_name(), "registered", f"person:{u.pk}")
    for a in GoldApplication.objects.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)).order_by("-created_at")[:limit]:
        add(a.email, a.full_name, "gold", f"gold:{a.pk}")
    for s in JourneySession.objects.filter(Q(lead_email__icontains=q) | Q(lead_first_name__icontains=q), is_bot=False).exclude(lead_email="").order_by("-created_at")[:limit * 3]:
        add(s.lead_email, s.lead_first_name, "lead", f"lead:{s.pk}")
    rows = list(found.values())[:limit]
    blocked = suppression.suppressed_set([r["email"] for r in rows])
    return [{**r, "kind": r["kinds"][0], "suppressed": r["email"] in blocked} for r in rows]


# ---------- timeline, export, erase ----------

def timeline_entries(threads):
    """[(at, kind, label, detail, href)]: not one line per email. The first email we sent, one line a thread a day ("Email: 2 from him, 1 from us", with the subject), and each
    email that bounced or was not sent."""
    out = []
    for thread in threads:
        href = _office("office_email_thread", thread.pk)
        rows = list(Message.objects.filter(thread=thread).order_by("id").values_list("direction", "created_at", "subject", "status", "error_code", "author_label", "spam"))
        first_out = next((r for r in rows if r[0] == Message.OUT), None)
        if first_out is not None:
            out.append((first_out[1], "email_chat", f"First email sent by {_first(first_out[5]) or 'the team'}", first_out[2], href))
        days = {}
        for direction, at, subject, status, code, author, spam in rows:
            if direction == Message.OUT and status in Message.BAD:
                out.append((at, "email_failed", "Email bounced" if status == Message.BOUNCED else "Email not sent", REASONS.get(code, REASONS["send_failed"])[0], href))
            if spam:
                continue
            bucket = days.setdefault(timezone.localtime(at).date(), {"in": 0, "out": 0, "subject": subject, "at": at})
            bucket[direction] += 1
            bucket["at"], bucket["subject"] = at, subject or bucket["subject"]
        for bucket in days.values():
            parts = [f"{bucket['in']} from him" if bucket["in"] else "", f"{bucket['out']} from us" if bucket["out"] else ""]
            out.append((bucket["at"], "email_chat", "Email: " + ", ".join(p for p in parts if p), bucket["subject"], href))
    return out


def threads_for_person(user=None, addresses=()):
    """Every thread held for a person: by his addresses and by the owner link (staff-run export and erasure)."""
    return threads_for(addresses, user)


def threads_for_member(user):
    """Member self-service: only the thread(s) on his account email, and only once that address is verified (an unverified account may carry someone else's address)."""
    if user is None or not user.email_verified_at:
        return Thread.objects.none()
    return Thread.objects.filter(email=user.email.strip().lower())


def export_for(threads):
    """Everything held: each thread with its emails (subject, text, the whole text with his quoted mail, status, times, from address and name, sent by) and a listing of the files (names, sizes, types; the file bytes are not in the export)."""
    out = []
    for thread in threads:
        out.append({"email": thread.email, "subject": thread.subject, "name": thread.name,
                    "messages": [{"direction": m.direction, "subject": m.subject, "text": m.body_text, "full_text": m.body_full, "html": m.body_html, "status": m.status, "at": m.created_at.isoformat(),
                                  "sent_at": m.sent_at.isoformat() if m.sent_at else None, "from": m.from_address or None, "from_name": m.from_name or None, "spam": m.spam, "sent_by": m.author_label or None,
                                  "note": m.note or None, "files": [{"name": a.filename, "type": a.declared_type or a.content_type, "size": a.size} for a in m.attachments.all()]}
                                 for m in thread.messages.prefetch_related("attachments").order_by("id")]})
    return out


def erase_threads(threads):
    """UK GDPR: the threads, their messages, their files in storage and the queue records that name those messages. Returns counts."""
    from common.tasks import erase_task_records

    threads = list(threads)
    ids = [t.pk for t in threads]
    keys = list(Attachment.objects.filter(message__thread_id__in=ids).values_list("key", flat=True))
    message_ids = list(Message.objects.filter(thread_id__in=ids).values_list("pk", flat=True))
    for key in keys:
        try:
            default_storage.delete(key)
        except Exception:  # noqa: BLE001 - a missing file must not stop the erasure
            logger.warning("Could not delete an email file from storage")
    queue = erase_task_records(message_ids, ["emailchat.tasks."]) if message_ids else 0
    Thread.objects.filter(pk__in=ids).delete()  # messages, files rows and read markers go with them
    return {"email_threads": len(ids), "email_messages": len(message_ids), "email_files": len(keys), "queue_records": queue}


def erase_person(user=None, addresses=()):
    return erase_threads(threads_for_person(user, addresses))


def erase_attachments(items):
    """Attachment rows and their files in storage (admin delete). A missing file does not stop the delete."""
    for item in items:
        try:
            default_storage.delete(item.key)
        except Exception:  # noqa: BLE001
            logger.warning("Could not delete an email file from storage")
        item.delete()


def erase_message(message):
    """Take one message out whole (files and row), used when its files could not be stored so that a retry starts clean."""
    for key in Attachment.objects.filter(message=message).values_list("key", flat=True):
        try:
            default_storage.delete(key)
        except Exception:  # noqa: BLE001
            pass
    thread = message.thread
    message.delete()
    last = Message.objects.filter(thread=thread, spam=False).order_by("-id").first()
    Thread.objects.filter(pk=thread.pk).update(last_message_at=last.created_at if last else None, last_preview=preview_of(last.body_text) if last else "",
                                               last_direction=last.direction if last else "")
