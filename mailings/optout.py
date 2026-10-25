"""Turning marketing off for an address (the public Unsubscribe page and one-click header)."""
from django.db import IntegrityError, transaction

from gold.models import GoldApplication
from users import member
from users.models import User

from .models import EmailOptOut


def unsubscribe(email):
    """Stop marketing email to `email`. Idempotent. A person with an account: `marketing_consent` goes off through
    `member.set_marketing_consent` (the history row records it, My Spa 99 shows it off). Gold applications by that address lose
    their news tick. An address with no account goes on `EmailOptOut` (a separate list: it is not a bounce or a complaint, so
    it does not belong in EmailSuppression, and it must not stop service messages).
    Returns {"account": bool, "changed": bool}."""
    email = (email or "").strip().lower()
    changed = False
    user = User.objects.filter(email__iexact=email).first()
    if user is not None:
        changed = member.set_marketing_consent(user, False) or changed
    for application in GoldApplication.objects.filter(email__iexact=email, marketing_consent=True):
        application.marketing_consent = False
        application.save(update_fields=["marketing_consent", "updated_at"])
        changed = True
    if user is None:
        try:
            with transaction.atomic():
                _, created = EmailOptOut.objects.get_or_create(email=email)
        except IntegrityError:  # two clicks at once
            created = False
        changed = created or changed
    return {"account": user is not None, "changed": changed}


def clear(email):
    """The person chose news again (account switch or ticked the box when registering): forget the no-account opt-out."""
    EmailOptOut.objects.filter(email=(email or "").strip().lower()).delete()
