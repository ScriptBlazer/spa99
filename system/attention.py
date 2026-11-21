"""The "Needs attention" box on the System dashboard: settings that are wrong or empty, each with the page that fixes it.

A few queries, plus two or three per staff member who is not on the sending domain (the team is a short list). One sending domain everywhere: notifications.sender.sending_domain().
Not checked against the sending domain on purpose: contact_email, gold_approver_cc, voicemail_email_to and the staff alert addresses (inbound or internal; they may be anywhere)."""
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.urls import reverse

from gold import approval as gold_approval
from mailings.models import Mailing
from notifications import sender as sender_mod
from notifications.models import NotificationTemplate, StaffSender
from plans import payments
from plans.models import SiteSettings

from . import defaults
from .middleware import SYSTEM_URLCONF

OPEN_MAILING = (Mailing.DRAFT, Mailing.SCHEDULED, Mailing.SENDING, Mailing.PAUSED)


def _name(user):
    return sender_mod.full_name(user) or user.email


def _item(text, url_name=None, *args):
    url = reverse(url_name, args=args, urlconf=SYSTEM_URLCONF) if url_name else ""
    return {"text": text, "fix_url": url}


def _alerts():
    """Same two cases as the Payments page: switched off, else no address."""
    site = defaults.get()
    if not site.staff_alert_emails_on:
        return [_item("Payment alert emails are switched off.", "system_defaults")]
    if not payments.alert_addresses():
        return [_item("No payment alert email address is set.", "system_defaults")]
    return []


def _staff_who_cannot_send():
    """([items], {user ids}): active staff with no address to send from."""
    users = get_user_model().objects.filter(is_active=True).filter(Q(is_staff=True) | Q(is_superuser=True)).order_by("first_name", "email")
    stuck = [u for u in users if sender_mod.sender_for(u).source == "site"]
    return [_item(f"{_name(u)} has no address they can send from.", "system_team_person", u.pk) for u in stuck], {u.pk for u in stuck}


def _gone_senders():
    items = []
    for row in NotificationTemplate.objects.filter(sender_user__isnull=False).select_related("sender_user"):
        if sender_mod.chosen(row.sender_user)[1] == "gone":
            items.append(_item(f"The email \"{row.subject or row.key}\" is set to send as {_name(row.sender_user)}, who can no longer send.", "system_email_edit", row.key))
    for row in Mailing.objects.filter(sender_user__isnull=False, status__in=OPEN_MAILING).select_related("sender_user"):
        if sender_mod.chosen(row.sender_user)[1] == "gone":
            items.append(_item(f"The mailing \"{row.name}\" is set to send as {_name(row.sender_user)}, who can no longer send.", "system_mailing_edit", row.pk))
    return items


def _off_domain_addresses(skip=()):
    """A stored address off the domain. Skips people already listed as unable to send, and people who are not active staff."""
    items = []
    rows = StaffSender.objects.exclude(sending_address="").filter(user__is_active=True).filter(Q(user__is_staff=True) | Q(user__is_superuser=True)).select_related("user")
    for row in rows:
        if row.user_id not in skip and not sender_mod.on_sending_domain(row.sending_address):
            items.append(_item(f"{_name(row.user)}'s sending address {row.sending_address} is not on @{sender_mod.sending_domain()}.", "system_team_person", row.user_id))
    legacy = (SiteSettings.load().auto_email_from_address or "").strip()
    if legacy and not sender_mod.on_sending_domain(legacy):
        # Old field, no System page edits it: no Fix link, the developer changes it.
        items.append(_item(f"The old automatic emails sender address {legacy} is not on @{sender_mod.sending_domain()}. Tell the developer."))
    return items


def _approver():
    return [_item("Gold has no final approver.", "system_approval")] if gold_approval.final_approver_missing() else []


def attention_items():
    """[{text, fix_url}]: empty when everything is fine."""
    stuck_items, stuck_ids = _staff_who_cannot_send()
    return _alerts() + stuck_items + _gone_senders() + _off_domain_addresses(stuck_ids) + _approver()
