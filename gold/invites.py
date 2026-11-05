"""Gold approval and the account invite (docs/features/gold-application.md, "Approval and invite").

Approve: status approved, approved_at (Gold's month starts here, LC-27), approved_by. A person with no account gets an
invite (a signed link to a GoldInvite row: valid for System > Defaults days from when it was made, single use). A person who already has a VERIFIED account gets Gold added
and a short email. An unverified account (anyone can register with any address) counts as no account: the invite goes out, and setting up from it replaces that account. Declined applications never get an invite. Gold on an account is the member's plan
(users.InterestRegistration.plan = the `gold` plan); no payment step."""
import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from common.tasks import enqueue
from insights import metrics
from common.validators import normalise_uk_mobile
from plans import sales as sale_services
from plans.models import PaymentMark, Plan, SiteSettings, Subscription
from users.models import InterestRegistration

from system import defaults

from . import audit
from .models import ApplicationEvent, GoldApplication, GoldInvite

logger = logging.getLogger("spa99.gold")

INVITE_SALT = "spa99.gold.invite"
TOKEN_CAP_DAYS = 91  # outer limit of the signed token (the longest the setting allows, plus a day). The GoldInvite row's own expires_at is what decides.
GOLD_SLUG = "gold"
OK, INVALID = "ok", "invalid"  # bad links are all INVALID: the page never says whether a link expired, was used or never existed

# Results of approve / resend, for the admin message.
INVITED, ACTIVATED, SKIPPED, NEEDS_STAFF = "invited", "activated", "skipped", "needs_staff"  # NEEDS_STAFF: approved, but no invite: see blocking_account


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
        pk = signing.loads(token, salt=INVITE_SALT, max_age=TOKEN_CAP_DAYS * 86400)
    except signing.BadSignature:
        return INVALID, None
    try:
        invite = GoldInvite.objects.select_related("application").filter(pk=pk).first()
    except (ValueError, TypeError):
        return INVALID, None
    return (OK, invite) if invite is not None and invite.is_usable else (INVALID, None)


def account_to_replace(application):
    """The unverified account on this applicant's address (anyone can register with any address): setting up from the invite replaces it. None when there is none, or it is a staff account
    (that is never replaced). A verified account is not this: the person signs in to it."""
    user = get_user_model().objects.filter(email__iexact=application.email, email_verified_at__isnull=True).first()
    return None if user is None or user.is_staff or user.is_superuser else user


def has_payment_record(user):
    """True when this account has a membership set up or any payment recorded on it (a Subscription or a PaymentMark): erasing it would lose a paid membership."""
    return Subscription.objects.filter(registration__user=user).exists() or PaymentMark.objects.filter(registration__user=user).exists()


def blocking_account(application):
    """The unverified account on his address that must NOT be replaced because it holds a membership or a payment, or None. While there is one, no invite goes out (it could not be used):
    staff are told to have him verify that account (Gold is then added to it, `activate_approved`), or to sort it out by hand when it is not his."""
    user = account_to_replace(application)
    return user if user is not None and has_payment_record(user) else None


def mobile_needs_fixing(application):
    """True when the application's mobile cannot go on the account as it is: not a valid UK mobile (same validator as
    registration) or already on another account (the unverified account the invite replaces does not count: it goes). The setup form then lets him enter it."""
    if not application.mobile:
        return False
    try:
        mobile = normalise_uk_mobile(application.mobile)
    except ValidationError:
        return True
    return mobile_taken(mobile, application)


def mobile_taken(mobile, application):
    """Is this (normalised) mobile on another account, not counting the unverified one the invite replaces."""
    held = get_user_model().objects.filter(mobile=mobile)
    replaced = account_to_replace(application)
    return (held.exclude(pk=replaced.pk) if replaced is not None else held).exists()


def verified_account(email):
    """The account that has PROVEN this address, or None. An unverified account proves nothing (anyone can register with any address), so approve never activates Gold on it."""
    return get_user_model().objects.filter(email__iexact=email, email_verified_at__isnull=False).first()


# ---------- gold on the account ----------

def activate_gold(user):
    """Make Gold the member's plan. Returns False if the gold plan row is missing (nothing changed)."""
    plan = Plan.objects.filter(slug=GOLD_SLUG).first()
    if plan is None:
        logger.error("Gold plan row is missing: cannot activate Gold")
        return False
    interest, created = InterestRegistration.objects.get_or_create(user=user, defaults={"plan": plan})
    if created:
        metrics.registered(plan.slug, interest.source, interest.created_at, marketing=user.marketing_consent)
    elif interest.plan_id != plan.pk:
        interest.plan = plan
        for name, value in sale_services.snapshot_fields(plan, held=interest).items():
            setattr(interest, name, value)  # Gold is free: no sale price is kept
        interest.save()  # the plan split follows this save (insights.signals)
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
    invite = GoldInvite.objects.create(application=application, expires_at=now + timedelta(days=defaults.get().gold_invite_days))
    _queue("gold.tasks.send_gold_invite_email", str(invite.pk))
    return invite


class _Rollback(Exception):
    pass


def approve_and_invite(application, approved_by, from_final=False, channel=audit.SYSTEM):
    """Approve one application. Returns INVITED, ACTIVATED (existing account), NEEDS_STAFF (approved, but an unverified account on his address holds a membership, so no invite: staff
    are told what to do) or SKIPPED (declined, already approved, or Gold could not be activated: nothing is changed or sent then). Safe against two people approving at once.
    An application awaiting final approval is only approved by `from_final=True` (a final approver's Confirm), and
    `from_final` only works on an application that is awaiting final approval. The review rule itself is in gold.approval."""
    existing = verified_account(application.email)  # an unverified account may be a stranger's: it gets no Gold (the invite below lets the real applicant take the address)
    held = existing is None and blocking_account(application) is not None  # an unverified account with a membership on it is never replaced: approved, no invite, staff are told
    try:
        with transaction.atomic():
            fresh = GoldApplication.objects.select_for_update().get(pk=application.pk)
            if fresh.status in (GoldApplication.DECLINED, GoldApplication.APPROVED):
                return SKIPPED
            if (fresh.status == GoldApplication.AWAITING_FINAL) != from_final:
                return SKIPPED
            before = fresh.status
            fresh.status = GoldApplication.APPROVED
            fresh.approved_at = timezone.now()
            fresh.approved_by = approved_by
            if existing is not None:
                if not activate_gold(existing):
                    raise _Rollback
                fresh.user = existing
            fresh.save()
            audit.record(fresh, ApplicationEvent.FINAL_CONFIRMED if from_final else ApplicationEvent.APPROVED, actor=approved_by, channel=channel,
                         from_status=before, to_status=GoldApplication.APPROVED, meta={"result": ACTIVATED if existing is not None else NEEDS_STAFF if held else INVITED})
            if existing is None and not held:
                _new_invite(fresh)
    except _Rollback:
        return SKIPPED
    application.refresh_from_db()
    if existing is not None:
        _queue("gold.tasks.send_gold_active_email", str(application.pk))
        return ACTIVATED
    return NEEDS_STAFF if held else INVITED


def decline_application(application, actor=None, reason="", channel=audit.SYSTEM, email_message=None):
    """Decline a waiting application (new or contacted). Declined applicants never get an invite or an account.
    Returns True if declined, False if it was not waiting (nothing changed, nothing recorded). Safe against two people acting
    at once. The reason goes in the trail. `email_message` (text) emails the applicant that message; None = no email."""
    with transaction.atomic():
        fresh = GoldApplication.objects.select_for_update().get(pk=application.pk)
        if fresh.status not in (GoldApplication.NEW, GoldApplication.CONTACTED):
            return False
        before = fresh.status
        fresh.status = GoldApplication.DECLINED
        fresh.save()
        meta = {"email_applicant": True, "email_message": audit.clean_text(email_message)} if email_message else {"email_applicant": False}
        event = audit.record(fresh, ApplicationEvent.DECLINED, actor=actor, channel=channel, from_status=before,
                             to_status=GoldApplication.DECLINED, message=reason, meta=meta)
    application.refresh_from_db()
    if email_message:
        _queue("gold.tasks.send_gold_applicant_email", str(application.pk), str(event.pk))
    return True


def can_resend(application):
    """Approved, nobody has proven the address (no verified account, and a linked account must be unverified), and no unverified account with a membership would be replaced.
    The Office shows the Resend button by this."""
    if application.status != GoldApplication.APPROVED:
        return False
    linked = application.user if application.user_id is not None else None
    if linked is not None and (linked.email_verified_at is not None or linked.is_staff or linked.is_superuser):
        return False
    return verified_account(application.email) is None and blocking_account(application) is None


def resend_invite(application, actor=None, channel=audit.SYSTEM):
    """A new link; the old one stops working. Only for approved applicants with no VERIFIED account yet (an old row linked to an unverified account still gets one: setting up replaces that
    account), and never when that account holds a membership or a payment (`blocking_account`). Returns INVITED or SKIPPED."""
    if not can_resend(application):
        return SKIPPED
    with transaction.atomic():
        application = GoldApplication.objects.select_for_update().get(pk=application.pk)
        if not can_resend(application):
            return SKIPPED
        audit.record(application, ApplicationEvent.INVITE_RESENT, actor=actor, channel=channel)
        _new_invite(application)
    return INVITED


# ---------- the setup page ----------

def activate_approved(user, application_ids):
    """Gold approved while he had no verified account, and now he has one (he verified his registration: users.services.verify_email): the same activation as the normal approval, once
    (`link_user_applications` calls this only for the rows it has just linked, so a second verify finds none). The open invite is revoked (its link then answers as a dead link) and
    the short 'Gold is active' email is queued. Returns True when Gold was activated."""
    ids = list(application_ids)
    if not ids or not activate_gold(user):
        return False
    GoldInvite.objects.filter(application_id__in=ids, used_at__isnull=True, revoked_at__isnull=True).update(revoked_at=timezone.now())
    for pk in ids:
        _queue("gold.tasks.send_gold_active_email", str(pk))
    logger.info("Gold activated on account %s: approved application verified its address", user.pk)
    return True


def accept_invite(token, cleaned):
    """Create the account from a valid invite. `cleaned` is GoldSetupForm.cleaned_data. Returns the user.
    Raises InviteError when the link is no longer usable or the email already has an account."""
    status, invite = read_invite(token)
    if status != OK:
        raise InviteError
    application = invite.application
    User = get_user_model()
    now = timezone.now()
    try:
        mobile = normalise_uk_mobile(cleaned.get("mobile") or application.mobile) if (cleaned.get("mobile") or application.mobile) else None
    except ValidationError:
        raise InviteError("That mobile number could not be used. Please try again.") from None
    try:
        with transaction.atomic():
            invite = GoldInvite.objects.select_for_update().get(pk=invite.pk)
            if not invite.is_usable:
                raise InviteError
            if verified_account(application.email) is not None:
                raise InviteError("There is already an account for this email. Please sign in.")
            squatter = User.objects.filter(email__iexact=application.email).first()  # unverified: someone registered with this address without proving it
            if squatter is not None:
                if squatter.is_staff or squatter.is_superuser:
                    raise InviteError
                if has_payment_record(squatter):  # a membership set up (or a payment) on that account: never erased for an invite
                    raise InviteError("This email already has an account with a membership on it. Please check your email for its verification link, or contact us and we will help.")
                from users.services import delete_user_data

                delete_user_data(squatter)  # the invite went to this address, so its holder is the applicant: the unproven account makes way (only what is proven is erased with it)
            user = User.objects.create_user(
                application.email, cleaned["password"], first_name=application.first_name, last_name=application.last_name,
                mobile=mobile, date_of_birth=cleaned["date_of_birth"], email_verified_at=now, men_only_accepted_at=now,
                privacy_accepted_version=SiteSettings.load().privacy_version, privacy_accepted_at=now,
                marketing_consent=bool(cleaned.get("marketing_opt_in")),
                marketing_consent_at=now if cleaned.get("marketing_opt_in") else None,
            )
            from users.services import _after_registration

            _after_registration(user, bool(cleaned.get("marketing_opt_in")), proven=True)  # invites for this address become registered; the invite proved the address
            invite.used_at = now
            invite.save(update_fields=["used_at", "updated_at"])  # the Gold figures follow this save (insights.signals)
            metrics.email_verified(now)
            application.user = user
            application.save(update_fields=["user", "updated_at"])
            GoldApplication.objects.filter(email__iexact=user.email, user__isnull=True).update(user=user)
            from users.services import link_earlier_data

            link_earlier_data(user)  # the invite proves the address: journeys left with it become his too
            session = application.journey_session
            if session is not None and session.user_id is None:
                session.user = user
                session.save(update_fields=["user", "updated_at"])
            activate_gold(user)
    except (IntegrityError, ValidationError):
        raise InviteError("That could not be saved. Please try again.") from None
    return user
