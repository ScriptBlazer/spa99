"""Gold approval and the account invite (docs/features/gold-application.md, "Approval and invite").

Approve: status approved, approved_at (Gold's month starts here, LC-27), approved_by. A person with no account gets an
invite (a signed link to a GoldInvite row: 14 days, single use). A person who already has an account gets Gold added
and a short email. Declined applications never get an invite. Gold on an account is the member's plan
(users.InterestRegistration.plan = the `gold` plan); no payment step."""
import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import signing
from django.db import IntegrityError, transaction
from django.utils import timezone

from common.tasks import enqueue
from plans.models import Plan, SiteSettings
from users.models import InterestRegistration

from .models import GoldApplication, GoldInvite

logger = logging.getLogger("spa99.gold")

INVITE_SALT = "spa99.gold.invite"
INVITE_DAYS = 14
GOLD_SLUG = "gold"
OK, INVALID = "ok", "invalid"  # bad links are all INVALID: the page never says whether a link expired, was used or never existed

# Results of approve / resend, for the admin message.
INVITED, ACTIVATED, SKIPPED = "invited", "activated", "skipped"


class InviteError(Exception):
    """The invite cannot be used. `text` is safe to show."""

    def __init__(self, text="This link can't be used."):
        super().__init__(text)
        self.text = text


# ---------- tokens ----------

def make_token(invite):
    return signing.dumps(str(invite.pk), salt=INVITE_SALT)


def read_invite(token):
    """(OK, invite) for a usable link, else (INVALID, None)."""
    try:
        pk = signing.loads(token, salt=INVITE_SALT, max_age=INVITE_DAYS * 86400 + 3600)
    except signing.BadSignature:
        return INVALID, None
    try:
        invite = GoldInvite.objects.select_related("application").filter(pk=pk).first()
    except (ValueError, TypeError):
        return INVALID, None
    return (OK, invite) if invite is not None and invite.is_usable else (INVALID, None)


# ---------- gold on the account ----------

def activate_gold(user):
    """Make Gold the member's plan. Returns False if the gold plan row is missing (nothing changed)."""
    plan = Plan.objects.filter(slug=GOLD_SLUG).first()
    if plan is None:
        logger.error("Gold plan row is missing: cannot activate Gold")
        return False
    interest, _ = InterestRegistration.objects.get_or_create(user=user, defaults={"plan": plan})
    if interest.plan_id != plan.pk:
        interest.plan = plan
        interest.save()
    return True


def gold_since(user):
    """When this person's Gold started (the approval date), or None."""
    application = (
        GoldApplication.objects.filter(user=user, status=GoldApplication.APPROVED, approved_at__isnull=False)
        .order_by("-approved_at").first()
    )
    return application.approved_at if application else None


# ---------- approve and resend ----------

def _queue(function, *args):
    try:
        enqueue(function, *args)
    except Exception:  # noqa: BLE001 - the approval is saved; Barry can resend
        logger.exception("Could not queue %s", function)


def _new_invite(application):
    now = timezone.now()
    application.invites.filter(used_at__isnull=True, revoked_at__isnull=True).update(revoked_at=now)
    invite = GoldInvite.objects.create(application=application, expires_at=now + timedelta(days=INVITE_DAYS))
    _queue("gold.tasks.send_gold_invite_email", str(invite.pk))
    return invite


def approve_and_invite(application, approved_by):
    """Approve one application. Returns INVITED, ACTIVATED (existing account) or SKIPPED (declined / already approved)."""
    if application.status in (GoldApplication.DECLINED, GoldApplication.APPROVED):
        return SKIPPED
    existing = get_user_model().objects.filter(email__iexact=application.email).first()
    with transaction.atomic():
        application.status = GoldApplication.APPROVED
        application.approved_at = timezone.now()
        application.approved_by = approved_by
        if existing is not None:
            application.user = existing
            activate_gold(existing)
        application.save()
        if existing is None:
            _new_invite(application)
    if existing is not None:
        _queue("gold.tasks.send_gold_active_email", str(application.pk))
        return ACTIVATED
    return INVITED


def resend_invite(application):
    """A new link; the old one stops working. Only for approved applicants with no account yet. Returns INVITED or SKIPPED."""
    if application.status != GoldApplication.APPROVED or application.user_id is not None:
        return SKIPPED
    if get_user_model().objects.filter(email__iexact=application.email).exists():
        return SKIPPED
    with transaction.atomic():
        _new_invite(application)
    return INVITED


# ---------- the setup page ----------

def accept_invite(token, cleaned):
    """Create the account from a valid invite. `cleaned` is GoldSetupForm.cleaned_data. Returns the user.
    Raises InviteError when the link is no longer usable or the email already has an account."""
    status, invite = read_invite(token)
    if status != OK:
        raise InviteError
    application = invite.application
    User = get_user_model()
    now = timezone.now()
    mobile = application.mobile or None
    if mobile and User.objects.filter(mobile=mobile).exists():
        mobile = None  # held by another account: never say so, he can add it later by writing to us
    try:
        with transaction.atomic():
            invite = GoldInvite.objects.select_for_update().get(pk=invite.pk)
            if not invite.is_usable:
                raise InviteError
            if User.objects.filter(email__iexact=application.email).exists():
                raise InviteError("There is already an account for this email. Please sign in.")
            user = User.objects.create_user(
                application.email, cleaned["password"], first_name=application.first_name, last_name=application.last_name,
                mobile=mobile, email_verified_at=now, men_only_accepted_at=now,
                privacy_accepted_version=SiteSettings.load().privacy_version, privacy_accepted_at=now,
                marketing_consent=bool(cleaned.get("marketing_opt_in")),
                marketing_consent_at=now if cleaned.get("marketing_opt_in") else None,
            )
            invite.used_at = now
            invite.save(update_fields=["used_at", "updated_at"])
            application.user = user
            application.save(update_fields=["user", "updated_at"])
            GoldApplication.objects.filter(email__iexact=user.email, user__isnull=True).update(user=user)
            session = application.journey_session
            if session is not None and session.user_id is None:
                session.user = user
                session.save(update_fields=["user", "updated_at"])
            activate_gold(user)
    except IntegrityError:
        raise InviteError("That could not be saved. Please try again.") from None
    return user
