"""Barry's membership approval (docs/features/office-2.md). One review per registered person, kept apart from the membership itself.

THE RULE: nothing here is ever read by member-facing code, sends anything, or changes a membership, a payment or an email to the member. It is Barry's own list, so he can
decide who he wants for special prices. `office` is only imported by the Office and System; a test checks that the member-facing apps never import it.

No row means waiting: every existing registration, and every new one, starts waiting without a backfill. Erased with the person (the registration cascades), and exported with him."""
from django.conf import settings
from django.db import models
from django.utils import timezone

from common.models import UUIDModel


class MembershipReview(UUIDModel):
    WAITING, APPROVED, DECLINED = "waiting", "approved", "declined"
    STATUS_CHOICES = [(WAITING, "Waiting"), (APPROVED, "Approved"), (DECLINED, "Declined")]

    registration = models.OneToOneField("users.InterestRegistration", on_delete=models.CASCADE, related_name="review")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=WAITING, db_default=WAITING, db_index=True)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    by_label = models.CharField(max_length=254, blank=True, default="", db_default="", help_text="Who decided, kept as text so it survives the account going.")
    at = models.DateTimeField(null=True, blank=True, help_text="When the current decision was made. Empty while waiting.")

    class Meta:
        ordering = ["-at", "-id"]

    def __str__(self):
        return f"review {self.status}"


class MembershipReviewEvent(UUIDModel):
    """One line of the audit trail: who moved a registration from one status to another, and when. Append-only in practice; goes with the person."""

    registration = models.ForeignKey("users.InterestRegistration", on_delete=models.CASCADE, related_name="review_events")
    from_status = models.CharField(max_length=10, choices=MembershipReview.STATUS_CHOICES)
    to_status = models.CharField(max_length=10, choices=MembershipReview.STATUS_CHOICES)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    by_label = models.CharField(max_length=254, blank=True, default="", db_default="")
    at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-at", "-id"]

    def __str__(self):
        return f"{self.from_status} to {self.to_status}"
