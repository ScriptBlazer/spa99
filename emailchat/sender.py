"""Who an Office email comes from and what goes under it (docs/features/office-email-chat.md, "Who an Office email comes from").

From: the staff member's own login address when it is on the sending domain (the domain verified in Postmark), else the "sending address" set for him in System > Team > Email (also on that
domain), else the site address (hello@). The display name is "<First name>, Spa 99", or "Spa 99" when he has no first name. Decided when the email is QUEUED and stored on the message, so a retry,
or a later change to his address, never changes what an email already went out with. Automatic and system emails never come through here.

Under the text: his signature (cleaned HTML, System > Team > Email), or a plain sign-off with his name when he has none. Both are snapshots on the message, shown in the thread as sent."""
import re
from collections import namedtuple
from email.utils import formataddr, parseaddr

from django.conf import settings
from django.utils.html import escape
from django.utils.safestring import mark_safe

from common import richtext
from notifications.emailbody import P_STYLE

Sender = namedtuple("Sender", "address name source")  # source: own (his login address), set (his sending address), site (hello@)
BRAND = "Spa 99"
CONTROL = re.compile(r"[\x00-\x1f\x7f<>\"\\@]")


def sending_domain():
    """The domain Office emails may go From a staff member's own address on: EMAIL_SENDING_DOMAIN, else the domain of the site address (DEFAULT_FROM_EMAIL), so nothing is typed twice."""
    return settings.EMAIL_SENDING_DOMAIN or parseaddr(settings.DEFAULT_FROM_EMAIL)[1].rpartition("@")[2].strip().lower()


def clean_address(value):
    return (value or "").strip().lower()


def on_sending_domain(address):
    """True for `name@<sending domain>` exactly (not `x@evil-<domain>`, not `a@b@<domain>`)."""
    address = clean_address(address)
    local, _, domain = address.rpartition("@")
    return bool(local) and "@" not in local and not any(ch.isspace() for ch in address) and bool(sending_domain()) and domain == sending_domain()


def site_address():
    """hello@: the address part of DEFAULT_FROM_EMAIL."""
    return parseaddr(settings.DEFAULT_FROM_EMAIL)[1].strip()


def first_name(user):
    """His first name for the display name: one line, no angle brackets, quotes, @ or control characters, at most 40 characters."""
    name = " ".join(CONTROL.sub(" ", getattr(user, "first_name", "") or "").split())
    return name[:40].strip()


def display_name(user):
    name = first_name(user)
    return f"{name}, {BRAND}" if name else BRAND


def profile_for(user):
    from .models import StaffSender

    return StaffSender.objects.filter(user=user).first() if getattr(user, "pk", None) else None


def sender_for(user):
    """Sender(address, name, source) for an email written by `user` (None or anonymous: the site address). Own address, then the sending address set in System, then hello@."""
    name = display_name(user)
    if getattr(user, "pk", None):
        if on_sending_domain(user.email):
            return Sender(clean_address(user.email), name, "own")
        profile = profile_for(user)
        if profile is not None and on_sending_domain(profile.sending_address):
            return Sender(clean_address(profile.sending_address), name, "set")
    return Sender(clean_address(site_address()), name, "site")


def format_address(address, name):
    """`"Barry, Spa 99" <barry@spa99.uk>`: the display name quoted when it needs it and encoded when it is not ASCII, so a stray comma or an accent cannot break the header."""
    return formataddr((name, address)) if name else address


def full_name(user):
    return " ".join(CONTROL.sub(" ", (user.get_full_name() if getattr(user, "pk", None) else "") or "").split())[:100]


def signature_html_of(user):
    """His signature as stored, cleaned again, our own picture addresses made absolute from SITE_URL. '' when he has none."""
    profile = profile_for(user)
    html = richtext.clean_signature(profile.signature_html) if profile is not None else ""
    return richtext.absolute_images(html, settings.SITE_URL) if html else ""


def sign_off(user):
    """(html, text) that go under his email. With a signature: the signature, and a plain name block for the text copy. Without: a plain 'Kind regards' with his name in both."""
    name = full_name(user) or first_name(user) or BRAND
    html = signature_html_of(user)
    if html:
        return html, "\n".join(x for x in (name, BRAND if name != BRAND else "", settings.SITE_URL) if x)
    return f'<p style="{P_STYLE}">Kind regards,<br>{escape(name)}</p>', f"Kind regards,\n{name}"


def preview_html(user):
    """What the composer shows as "with your signature": safe to put in the page (cleaned HTML, or an escaped sign-off)."""
    return mark_safe(sign_off(user)[0])  # cleaned by clean_signature above, or built from an escaped name


def composer_info(user):
    """For the thread and New email screens: {from (the whole header), label (the same, for people to read), address, source, has_signature, signature_html}."""
    sender = sender_for(user)
    return {"from": format_address(sender.address, sender.name), "label": f"{sender.name} <{sender.address}>", "address": sender.address, "source": sender.source, "has_signature": bool(signature_html_of(user)), "signature_html": preview_html(user)}
