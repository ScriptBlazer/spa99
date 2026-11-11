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


class ActivityDay(models.Model):
    """Stored daily totals behind Office > Activity (docs/features/office-activity.md): how many staff actions of one type one person did on one London day. Written by the hourly
    roll-up and the debounced refresh (office.activity_store), rebuilt in full by `rebuild_activity`; the page only reads it. Counts only: no names of people, no text. Derived data, so it
    is not part of a person's export and nothing here needs erasing."""

    day = models.DateField(help_text="The London calendar day.")
    group = models.CharField(max_length=12, help_text="The type: approvals, leads, notes, emails, gold or memberships.")
    staff_key = models.CharField(max_length=254, help_text="One person, however his label was stored: the email inside the label (lower case), else the label.")
    staff_label = models.CharField(max_length=254, blank=True, default="", db_default="", help_text="The fullest label stored for him that day.")
    count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["day", "group", "staff_key"], name="office_activityday_unique")]
        indexes = [models.Index(fields=["day"], name="office_activityday_day")]

    def __str__(self):
        return f"{self.day} {self.group} {self.staff_key}: {self.count}"


class ActivityDirtyDay(models.Model):
    """A London day whose Activity totals must be recounted, because a row of that day was deleted or saved after the fact (a person removed from the approach list or erased, a Gold
    application deleted, a backdated row). Written when the change commits (office.signals), read and cleared by the Office refresh (office.activity_store). One row per day however many
    rows changed. Holds only a date."""

    day = models.DateField(unique=True)
    marked_at = models.DateTimeField(default=timezone.now, help_text="When it was last marked; a recount only clears marks made before it started.")

    def __str__(self):
        return f"recount {self.day}"
