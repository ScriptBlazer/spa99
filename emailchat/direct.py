"""Emails sent directly to staff (docs/features/office-email-chat.md, "Emails sent directly to staff").

A staff mailbox keeps its copy in Outlook and also forwards to `inbox+<token>@<EMAIL_INBOUND_DOMAIN>`; Postmark posts that to the same inbound webhook. `route` decides what a mail
like that is: nothing (answer 200, store nothing, log without personal data), or a `Route` the webhook stores through `services.record_inbound`. The rules, in order:
  1. the token must be a staff member's (`StaffSender.inbox_token`); a guess stores nothing;
  2. his address must be directly in the ORIGINAL To or Cc, and neither hello@, the staff group address nor the group-copy address may be (else the team would see it three times);
  3. internal mail (from staff, the sending domain or EMAIL_INTERNAL_DOMAIN) and robot mail (auto-replies, bounces, lists, calendar replies) stays in Outlook;
  4. the same email forwarded from two mailboxes is one message (one thread, both staff named); a reply to a message we sent, by In-Reply-To or References, joins that thread, anything
     else starts a new one with that sender and subject (never joined by subject);
  5. From is unproven (nothing here checks SPF or DKIM itself): the thread gets no owner link from it (common.ownership), and a mail whose headers say the sender check failed is stored
     flagged, never pushed.
No group copy is sent for direct mail (tasks.process_inbound)."""
import hashlib
import logging
import re
import secrets
from collections import namedtuple
from email.utils import getaddresses, parseaddr

from django.conf import settings
from django.contrib.auth import get_user_model

from common import levels

from . import sender as sender_mod
from . import services
from .models import Message, StaffSender, Thread

logger = logging.getLogger("spa99.emailchat")

Route = namedtuple("Route", "thread email subject names staff key spam note new")  # thread: existing one or None (made with the message); names: "Barry"; staff: his address; key: hash of the original Message-ID
TOKEN = re.compile(r"[0-9a-f]{24}")
ROBOT_PRECEDENCE = {"bulk", "list", "junk", "auto_reply", "auto-reply"}
ROBOT_SENDERS = {"mailer-daemon", "postmaster"}
FAILED_CHECKS = services.FAILED_CHECKS
MAX_IDS = 20


def new_token():
    return secrets.token_hex(12)  # 24 lower-case hex characters, like a thread's token, but in a different table and behind inbox+


def ensure_token(profile):
    """Give this staff row its inbox token if it has none (saved by the Team email editor). Returns the token."""
    if not profile.inbox_token:
        for _ in range(5):
            token = new_token()
            if not StaffSender.objects.filter(inbox_token=token).exists():
                StaffSender.objects.filter(pk=profile.pk, inbox_token__isnull=True).update(inbox_token=token)
                profile.refresh_from_db(fields=["inbox_token"])
                break
    return profile.inbox_token


def inbox_address(profile):
    """What his Microsoft mailbox forwards to, or '' (no inbound domain or no token yet)."""
    domain = services.inbound_domain()
    return f"inbox+{profile.inbox_token}@{domain}" if domain and profile is not None and profile.inbox_token else ""


# ---------- reading the payload ----------

def _headers(payload, name):
    return [str(i.get("Value", "")) for i in payload.get("Headers") or [] if isinstance(i, dict) and str(i.get("Name", "")).lower() == name.lower()]


def _first(payload, name):
    found = _headers(payload, name)
    return found[0].strip() if found else ""


def is_direct(payload):
    """True for mail that came in at `inbox+...`: by the address Postmark received it for. Without that field (old payloads), by a token that is not a thread's and is a staff member's."""
    original = payload.get("OriginalRecipient")
    if isinstance(original, str) and original.strip():
        return parseaddr(original)[1].lower().partition("@")[0].startswith("inbox+")
    token = _token(payload)
    return bool(token) and not Thread.objects.filter(token=token).exists() and StaffSender.objects.filter(inbox_token=token).exists()


def _token(payload):
    value = payload.get("MailboxHash")
    value = value.replace("\x00", "")[:64].strip().lower() if isinstance(value, str) else ""
    return value if TOKEN.fullmatch(value) else ""


def staff_for_token(payload):
    token = _token(payload)
    return StaffSender.objects.select_related("user").filter(inbox_token=token, user__is_active=True).first() if token else None


def staff_addresses(profile):
    """The addresses that are this staff member's: his login address and his sending address."""
    return {a for a in (services.clean_address(profile.user.email), services.clean_address(profile.sending_address)) if a}


def original_recipients(payload):
    """Every address in the ORIGINAL To and Cc, lower case. A forward may rewrite `To` to the forward address, so both Postmark's parsed lists (ToFull, CcFull) and the original header
    lines (Headers) are read and joined; the inbox+ address itself (and the reply domain) is not an original recipient. An empty result means the original To cannot be told."""
    found = set()
    for key in ("ToFull", "CcFull"):
        for item in payload.get(key) or []:
            if isinstance(item, dict) and isinstance(item.get("Email"), str):
                found.add(services.clean_address(item["Email"]))
    for name in ("To", "Cc"):
        for value in _headers(payload, name):
            found.update(services.clean_address(addr) for _, addr in getaddresses([value[:5000]]))
    domain = services.inbound_domain()
    return {a for a in found if a and not (domain and a.rpartition("@")[2] in (domain, f"mail.{domain}"))}


def kept_out_addresses():
    """hello@, the staff group address and the group-copy address (System > Defaults): a mail addressed to any of them already reaches the team another way."""
    from system import defaults

    return {a for a in (services.clean_address(sender_mod.site_address()), services.clean_address(settings.EMAIL_STAFF_GROUP_ADDRESS), services.clean_address(defaults.get().office_copy_email)) if a}


# ---------- internal and robot mail ----------

def is_internal(address):
    """From a staff member, the sending domain, the reply domain or EMAIL_INTERNAL_DOMAIN (the BML domain, a setting; blank = none): that stays in Outlook."""
    domain = address.rpartition("@")[2]
    for own in (sender_mod.sending_domain(), settings.EMAIL_INTERNAL_DOMAIN, services.inbound_domain()):
        if own and (domain == own or domain.endswith("." + own)):
            return True
    if StaffSender.objects.filter(sending_address__iexact=address).exists():
        return True
    return any(levels.level_of(u) != levels.NONE for u in get_user_model().objects.filter(email__iexact=address, is_active=True))


def is_automatic(payload, address):
    auto = _first(payload, "Auto-Submitted").lower()
    return bool((auto and auto != "no") or _first(payload, "Precedence").lower() in ROBOT_PRECEDENCE or _first(payload, "List-Id") or _first(payload, "X-Auto-Response-Suppress")
                or address.partition("@")[0] in ROBOT_SENDERS or _first(payload, "Return-Path") == "<>")


def failed_checks(payload):
    """True when the headers say the sender check failed. The receiving mail system's own verdict (Authentication-Results, which Microsoft adds to the original) wins: dmarc=fail, or
    spf=fail or dkim=fail without dmarc=pass. Only when there is none, Postmark's Received-SPF is used, and only a plain 'fail' (a forward always looks like a different sender to SPF)."""
    results = " ".join(_headers(payload, "Authentication-Results")).lower()
    if results:
        return "dmarc=fail" in results or (("spf=fail" in results or "dkim=fail" in results) and "dmarc=pass" not in results)
    return _first(payload, "Received-SPF").lower().startswith("fail")


# ---------- threads ----------

def key_for(payload):
    """A hash of the original Message-ID header: the same email forwarded from two mailboxes has two Postmark MessageIDs and one of these. None without a Message-ID."""
    own = services.clean_id(_first(payload, "Message-ID")).lower()
    return hashlib.sha256(own.encode()).hexdigest() if own else None


def reference_ids(payload):
    """The <ids> in In-Reply-To and References, at most 20, one line each (the stored ones are cleaned the same way)."""
    text = f"{_first(payload, 'In-Reply-To')[:2000]} {_first(payload, 'References')[:5000]}"
    return list(dict.fromkeys(re.findall(r"<[^<>\s]{1,298}>", text)))[:MAX_IDS]


def thread_by_headers(payload, address):
    """The thread of a message we sent that this mail answers (In-Reply-To or References), else the thread of an earlier direct mail from the same sender it answers. Never by subject."""
    ids = reference_ids(payload)
    if not ids:
        return None
    ours = Message.objects.filter(direction=Message.OUT, rfc_message_id__in=ids).order_by("-id").select_related("thread").first()
    if ours is not None:
        return ours.thread
    earlier = Message.objects.filter(direction=Message.IN, rfc_message_id__in=ids, thread__email=address).exclude(direct_to="").order_by("-id").select_related("thread").first()
    return earlier.thread if earlier is not None else None


def first_name_of(user):
    return sender_mod.first_name(user) or (user.email or "Staff").partition("@")[0].title()


def add_names(message, name):
    """The same email arrived from a second staff mailbox: name that member too in the small To line."""
    have = [n.strip() for n in message.direct_to.split(",") if n.strip()]
    if name not in have:
        Message.objects.filter(pk=message.pk).update(direct_to=", ".join(have + [name])[:300])


def route(payload):
    """What to do with direct mail: a Route to store, or None (nothing to store; the reason is logged with no address or text in it)."""
    profile = staff_for_token(payload)
    if profile is None:
        logger.info("Direct email for an unknown inbox token: not stored")
        return None
    name = first_name_of(profile.user)
    existing = Message.objects.filter(provider_id=services._text(payload.get("MessageID"), 100).strip()).select_related("thread").first()
    if existing is not None:
        return Route(existing.thread, "", "", name, "", None, False, "", False)  # Postmark's retry of one we have: record_inbound answers it
    recipients = original_recipients(payload)
    if not recipients:
        logger.warning("Direct email: the original To could not be determined: not stored")
        return None
    if not (staff_addresses(profile) & recipients) or (kept_out_addresses() & recipients):
        logger.info("Direct email not addressed directly to this staff member, or also to hello@ or the group: not stored")
        return None
    full = payload.get("FromFull") if isinstance(payload.get("FromFull"), dict) else {}
    address = services.clean_address(services._text(full.get("Email"), 254)) or services.clean_address(services._text(payload.get("From"), 254))
    if not address:
        logger.info("Direct email without a usable From address: not stored")
        return None
    if is_internal(address):
        logger.info("Direct email from an internal address: left in Outlook")
        return None
    if is_automatic(payload, address):
        logger.info("Direct email is automatic (auto-reply, bounce, list or calendar): not stored")
        return None
    key = key_for(payload)
    dup = Message.objects.filter(direct_key=key).first() if key else None
    if dup is not None:
        add_names(dup, name)
        logger.info("Direct email already stored from another mailbox: staff name added")
        return None
    spam = failed_checks(payload)
    thread = thread_by_headers(payload, address)
    own = sorted(staff_addresses(profile) & recipients)[0]
    return Route(thread, address, services.clean_subject(services._text(payload.get("Subject"), 400)) or "(No subject)", name, own, key, spam, FAILED_CHECKS if spam else "", thread is None)


def discard_empty(thread):
    """A direct thread whose only message was taken back out (its files could not be stored) goes too, so a retry does not leave an empty one behind."""
    if thread.direct_to and not Message.objects.filter(thread=thread).exists():
        thread.delete()
