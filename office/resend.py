"""Resend an email from a person's page (Admin and up). ONE map, `RULES`: the email's template key -> its name, when it makes sense (`refusal`: "" or the plain reason), and how to send it (`send`).

Bodies are never stored (EmailLog keeps no text, so sign-in links never sit in the database). Every resend is therefore built again by the email's normal sender, to his CURRENT address,
so a link in it is always fresh (a confirm link carries the address, a reset link the password state, a Gold invite is a new invite that retires the old one). A suppressed or bounced address
is refused first with a clear message (outreach.services.email_block); the central send guard checks again.

Not offered, on purpose (one line each):
- password_changed, password_set, email_changed_old, email_changed: security notices about a past event; sending one again would say something happened that did not.
- team_invite and anything to staff (gold_approver*, gold_final, gold_sent_back, payment_staff_alert, voicemail_new): not a customer's email.
- gold_ack, gold_respond, gold_declined, gold_guide, gold_active: each belongs to one Gold event or application, so they are resent from the Gold application page (not built yet).
- office_message: the text staff wrote is not kept with the log; use Message on his page.
- lead_next_morning: once per address by rule; the lead page has Resend follow-up.
- invite and group mailings: they belong to a mailing, not to him."""
from django.db.models import Q
from django.utils import timezone

from common import ratelimit
from gold import invites as gold_invites
from gold.models import GoldApplication
from outreach import services as outreach
from plans import payments
from plans.models import PaymentNotice
from users.models import InterestRegistration
from users import tasks as user_tasks

LIMIT_ACTOR, LIMIT_PERSON, WINDOW = 20, 5, 3600  # per staff member an hour; per customer an hour (a loop or a double click cannot flood one inbox)


class Refused(Exception):
    """Nothing was sent; the message says why (shown as a toast)."""


def _sent(status):
    if status != "sent":
        raise Refused("The email could not be sent." if status in (None, "failed") else "The email was not sent (the address is on the suppression list).")


def _application(user):
    return GoldApplication.objects.filter(email__iexact=user.email).filter(Q(user=user) | Q(user__isnull=True)).order_by("-created_at").first()


# ---- the rules: refusal(user) -> "" or why not; send(user, actor) sends or raises Refused

def _verify_refusal(user):
    return "He is already verified." if user.email_verified_at else ""


def _verify_send(user, actor):
    _sent(user_tasks.send_verification_email(str(user.pk)))


def _reset_refusal(user):
    return "" if user.is_active else "The account is deactivated."


def _reset_send(user, actor):
    _sent(user_tasks.send_password_reset_email(str(user.pk)))


def _welcome_refusal(user):
    return "" if user.email_verified_at else "He has not confirmed his email yet."


def _welcome_send(user, actor):
    _sent(user_tasks.send_welcome_email(str(user.pk)))


def _invite_refusal(user):
    application = _application(user)
    return "" if application is not None and gold_invites.can_resend(application) else "There is no Gold set-up link to send (it is already set up, or not approved)."


def _invite_send(user, actor):
    if gold_invites.resend_invite(_application(user), actor=actor, channel="office") != gold_invites.INVITED:
        raise Refused("There is no Gold set-up link to send.")


def _window_refusal(kind):
    def refusal(user):
        reg = InterestRegistration.objects.select_related("user").filter(user=user).first()
        return "He has no payment window." if reg is None else payments.window_email_open(reg, kind=kind)
    return refusal


def _window_send(kind):
    def send(user, actor):
        _sent(payments.send_window_email(InterestRegistration.objects.select_related("user").get(user=user), kind).status)
    return send


RULES = {
    "verify": ("the confirm email", _verify_refusal, _verify_send),
    "password_reset": ("the password reset email", _reset_refusal, _reset_send),
    "welcome": ("the welcome email", _welcome_refusal, _welcome_send),
    "gold_invite": ("the Gold set-up email", _invite_refusal, _invite_send),
    "payment_window_open": ("the payment window email", _window_refusal(PaymentNotice.INVITE), _window_send(PaymentNotice.INVITE)),
    "payment_window_reminder": ("the payment reminder", _window_refusal(PaymentNotice.REMINDER), _window_send(PaymentNotice.REMINDER)),
}


def offered(template, user):
    """Show a Resend button on this sent email? Only for an email in RULES that still makes sense for him."""
    rule = RULES.get(template)
    return bool(rule and not rule[1](user))


def _throttle(actor, user):
    if not (ratelimit.hit("office-resend", actor.pk, LIMIT_ACTOR, WINDOW, rolling=True) and ratelimit.hit("office-resend-to", user.pk, LIMIT_PERSON, WINDOW, rolling=True)):
        raise Refused("That is a lot of resends. Wait a few minutes.")


def resend(actor, user, template):
    """Send `template` again to his current address and record it in his timeline. Raises Refused (with the reason) when it is not allowed; returns the email's name."""
    rule = RULES.get(template)
    if rule is None:
        raise Refused("That email cannot be resent from here.")
    name, refusal, send = rule
    if reason := refusal(user):
        raise Refused(reason)
    if reason := outreach.email_block(user.email):
        raise Refused(reason)
    _throttle(actor, user)
    send(user, actor)
    outreach.record_resent(user.email, f"Resent {name}", actor)
    return name
