"""Erasing an address from group sends and invites (called when a person's data, or a Gold applicant's, is erased)."""
from django.db.models import Q

from .models import Invite, MailingRecipient, UnsubscribeKey


def erase_address(email, user=None):
    """Remove group-send rows, invites and the unsubscribe key for this address (and rows linked to `user`). Returns the number removed.
    EmailOptOut stays: it holds only the address and honours a request to stop."""
    email = (email or "").strip().lower()
    rows = MailingRecipient.objects.filter(Q(email__iexact=email) | Q(user=user)) if user is not None else MailingRecipient.objects.filter(email__iexact=email)
    return rows.delete()[0] + Invite.objects.filter(email__iexact=email).delete()[0] + UnsubscribeKey.objects.filter(email=email).delete()[0]
