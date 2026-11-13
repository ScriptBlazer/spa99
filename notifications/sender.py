"""Who an Office email comes from and what goes under it (the Email button on lead, person and Gold pages).

From: the staff member's own login address when it is on the sending domain (the domain verified in Postmark), else the "sending address" set for him in System > Team > Email (also on that
domain), else the site address (hello@). The display name is "<First name>, Spa 99", or "Spa 99" when he has no first name. Reply-To is the same address, so a reply reaches his Outlook
(for the hello@ fallback: the contact address). Automatic and system emails never come through here.

Under the text: his signature (cleaned HTML, System > Team > Email), or a plain "Kind regards" with his name when he has none."""
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


def belongs_to_someone_else(address, user):
    """True when `address` is another person's login address or another staff member's sending address: nobody may send as them (a Developer typing it into Team > Email would otherwise)."""
    from django.contrib.auth import get_user_model

    from .models import StaffSender

    address = clean_address(address)
    if not address:
        return False
    others = get_user_model().objects.filter(email__iexact=address)
    taken = StaffSender.objects.filter(sending_address__iexact=address)
    if getattr(user, "pk", None):
        others, taken = others.exclude(pk=user.pk), taken.exclude(user=user)
    return others.exists() or taken.exists()


def sender_for(user):
    """Sender(address, name, source) for an email written by `user` (None or anonymous: the site address). Own address, then the sending address set in System, then hello@."""
    name = display_name(user)
    if getattr(user, "pk", None):
        if on_sending_domain(user.email):
            return Sender(clean_address(user.email), name, "own")
        profile = profile_for(user)
        if profile is not None and on_sending_domain(profile.sending_address) and not belongs_to_someone_else(profile.sending_address, user):  # a stored address that is somebody else's is never used
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
    """What the settings page shows as the sign-off: safe to put in the page (cleaned HTML, or an escaped sign-off)."""
    return mark_safe(sign_off(user)[0])  # cleaned by clean_signature above, or built from an escaped name


# ---------- the sender chosen for an automatic email or a group send (Office 2) ----------
# A dropdown of staff who can send as themselves, plus hello@ as the default. The choice is stored as the staff member (a user id), never as typed text, so nobody can send as an
# address that is not a team member's. A member who has left, or has no sending-domain address any more, falls back to hello@: an email never fails because a person left.

SITE_LABEL = f"{BRAND} <hello@>"


def staff_candidates():
    """[(user, Sender)] active team members who can send as themselves (own login or sending address on the sending domain), by first name then email. Anyone with a team level
    (a staff flag or a superuser, active)."""
    from django.contrib.auth import get_user_model
    from django.db.models import Q

    users = get_user_model().objects.filter(is_active=True).filter(Q(is_staff=True) | Q(is_superuser=True)).order_by("first_name", "email")
    out = []
    for user in users:
        sender = sender_for(user)
        if sender.source != "site":
            out.append((user, sender))
    return out


def candidate_by_local_part(local_part):
    """The id (text) of the team member who can send as `<local_part>@...`, or "" when nobody matches (the select then stays on hello@)."""
    wanted = (local_part or "").strip().lower()
    for user, sender in staff_candidates():
        if wanted and sender.address.partition("@")[0] == wanted:
            return str(user.pk)
    return ""


def choice_label(user, sender):
    """`Barry Lobenstein <barry@spa99.uk>`: name first, then the address (two people can share a first name)."""
    name = full_name(user) or first_name(user) or sender.address
    return f"{name} <{sender.address}>"


def site_choice():
    """The default option: `Spa 99 <hello@spa99.uk>`."""
    return formataddr((BRAND, site_address())) if site_address() else BRAND


def sender_choices():
    """[(value, label)] for the Sender select: "" (hello@) first, then one option per staff member (value = his user id as text)."""
    return [("", site_choice())] + [(str(user.pk), choice_label(user, sender)) for user, sender in staff_candidates()]


def chosen(user_or_id):
    """(Sender, why) for a stored choice. `why` is '' when the choice is used as picked, 'site' when none was picked, or 'gone' when the person picked can no longer send (left, deactivated or no
    sending-domain address): hello@ is used and the page says so."""
    site = Sender(clean_address(site_address()), BRAND, "site")
    if user_or_id in (None, ""):
        return site, "site"
    from django.contrib.auth import get_user_model

    user = user_or_id if hasattr(user_or_id, "pk") else get_user_model().objects.filter(pk=user_or_id).first()
    if user is None or not user.is_active or not (user.is_staff or user.is_superuser):
        return site, "gone"
    found = sender_for(user)
    return (found, "") if found.source != "site" else (site, "gone")


def from_and_reply(user_or_id):
    """(from_email, reply_to list or None) for a stored choice. hello@ gives (None, None): the caller's default, the site sender with the contact address as Reply-To. A person gives his
    address with his display name, and Reply-To is that same address, so a reply reaches him."""
    found, why = chosen(user_or_id)
    if found.source == "site":
        return None, None
    return format_address(found.address, found.name), [found.address]


def gone_note(user_or_id):
    """The warning the page shows when the person picked can no longer send, else ''."""
    if user_or_id in (None, ""):
        return ""
    found, why = chosen(user_or_id)
    if why != "gone":
        return ""
    from django.contrib.auth import get_user_model

    user = user_or_id if hasattr(user_or_id, "pk") else get_user_model().objects.filter(pk=user_or_id).first()
    who = (full_name(user) or first_name(user) or "The person picked") if user is not None else "The person picked"
    return f"{who} has no @{sending_domain()} address now. This sends from hello@ until you choose."


def sign_name(user_or_id, fallback=""):
    """The first name that signs an automatic email sent as a chosen staff member (the next-morning email's "Best wishes, Barry"). `fallback` when hello@ is used or he can no longer send."""
    found, why = chosen(user_or_id or None)
    if found.source == "site":
        return fallback
    from django.contrib.auth import get_user_model

    user = user_or_id if hasattr(user_or_id, "pk") else get_user_model().objects.filter(pk=user_or_id).first()
    return first_name(user) or fallback
