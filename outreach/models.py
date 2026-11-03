"""Sticky notes, the approach list ("Barry's list") and one-to-one messages. All three hang on a PERSON, found by lower-cased
email (a note on a lead carries over when he registers). See docs/features/office-outreach.md.
Erased with the person (UK GDPR): see outreach.services.erase_email."""
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from common.models import UUIDModel

NOTE_MAX = 1000
REASON_MAX = 300
MESSAGE_MAX = 5000


def _person(on_delete=models.SET_NULL):
    return models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=on_delete, related_name="+")


class StickyNote(UUIDModel):
    """A short note about a person. Soft delete: a deleted note leaves the board but its text stays for the history line
    "Note deleted by X". `source_event` is the Gold NOTE_ADDED event it was copied from (backfill), so a re-run copies nothing."""

    email = models.CharField(max_length=254, db_index=True, help_text="Lower case. The person's main address when the note was written.")
    text = models.TextField(help_text="The form and the service keep new notes to 1000 characters; copied Gold notes may be longer (up to 2000).")
    author = _person()
    author_label = models.CharField(max_length=254, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = _person()
    deleted_by_label = models.CharField(max_length=254, blank=True)
    edited_at = models.DateTimeField(null=True, blank=True, help_text="The last time the text was changed (R9). Author and date stay as they were.")
    edited_by = _person()
    edited_by_label = models.CharField(max_length=254, blank=True)
    source_event = models.UUIDField(null=True, blank=True, unique=True, help_text="Gold history event this note was copied from.")

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"note on {self.email}"

    @property
    def is_deleted(self):
        return self.deleted_at is not None


class NoteEvent(UUIDModel):
    """A sticky note was deleted, restored or edited: the lines "Note deleted by X" / "Note restored by X" / "Note edited by X" of the
    timeline. A deleted note keeps its text, so the line can show it and Restore can bring it back; an edit line keeps the PREVIOUS text
    in `text`. Goes with the note (and with the person's erasure)."""

    DELETED, RESTORED, EDITED = "deleted", "restored", "edited"
    KIND_CHOICES = [(DELETED, "Deleted"), (RESTORED, "Restored"), (EDITED, "Edited")]

    note = models.ForeignKey(StickyNote, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    at = models.DateTimeField(default=timezone.now, db_index=True)
    by = _person()
    by_label = models.CharField(max_length=254, blank=True)
    text = models.TextField(blank=True, help_text="Edited lines only: the text the note had before the edit.")

    class Meta:
        ordering = ["-at", "-id"]

    def __str__(self):
        return f"note {self.kind}"


class OutreachEntry(UUIDModel):
    """One person on the approach list: by account, by lead address or by Gold application (exactly one). One OPEN entry per
    target (partial unique constraints, fine on SQLite and Postgres); a done entry stays until removed (removing deletes the row)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="outreach_entries")
    lead_email = models.CharField(max_length=254, blank=True, db_index=True, help_text="Lower case.")
    gold_application = models.ForeignKey("gold.GoldApplication", null=True, blank=True, on_delete=models.CASCADE, related_name="outreach_entries")
    reason = models.CharField(max_length=REASON_MAX, blank=True)
    added_by = _person()
    added_by_label = models.CharField(max_length=254, blank=True)
    added_at = models.DateTimeField(default=timezone.now, db_index=True)
    done_at = models.DateTimeField(null=True, blank=True)
    done_by = _person()
    done_by_label = models.CharField(max_length=254, blank=True)

    class Meta:
        ordering = ["-added_at", "-id"]
        constraints = [
            models.CheckConstraint(name="outreach_exactly_one_target", condition=(
                (Q(user__isnull=False) & Q(lead_email="") & Q(gold_application__isnull=True))
                | (Q(user__isnull=True) & ~Q(lead_email="") & Q(gold_application__isnull=True))
                | (Q(user__isnull=True) & Q(lead_email="") & Q(gold_application__isnull=False)))),
            models.UniqueConstraint(fields=["user"], condition=Q(done_at__isnull=True, user__isnull=False), name="outreach_one_open_per_user"),
            models.UniqueConstraint(fields=["lead_email"], condition=Q(done_at__isnull=True) & ~Q(lead_email=""), name="outreach_one_open_per_lead"),
            models.UniqueConstraint(fields=["gold_application"], condition=Q(done_at__isnull=True, gold_application__isnull=False), name="outreach_one_open_per_gold"),
        ]

    def __str__(self):
        return f"outreach {self.pk}"

    @property
    def is_done(self):
        return self.done_at is not None


class PersonMessage(UUIDModel):
    """A one-to-one email an Office user wrote to a lead or a person. The text is kept so the timeline can show it."""

    email = models.CharField(max_length=254, db_index=True, help_text="Lower case. Where it was sent.")
    text = models.TextField()
    author = _person()
    author_label = models.CharField(max_length=254, blank=True)
    sent_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-sent_at", "-id"]

    def __str__(self):
        return f"message to {self.email}"


class PersonEdit(UUIDModel):
    """Staff added or fixed a person's first name or mobile (lead page, person page): one line of the timeline, "Mobile added by X" /
    "Mobile changed by X". Erased with the person (the values are personal data)."""

    FIRST_NAME, MOBILE = "first_name", "mobile"
    WHAT_CHOICES = [(FIRST_NAME, "First name"), (MOBILE, "Mobile")]

    email = models.CharField(max_length=254, db_index=True, help_text="Lower case. The person's main address when it was changed.")
    what = models.CharField(max_length=12, choices=WHAT_CHOICES)
    before = models.CharField(max_length=100, blank=True)
    after = models.CharField(max_length=100, blank=True)
    by = _person()
    by_label = models.CharField(max_length=254, blank=True)
    at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-at", "-id"]

    def __str__(self):
        return f"{self.what} edit on {self.email}"


# ---------- archived leads (round 2, R6) ----------

class ArchivedLead(UUIDModel):
    """A lead the team put away: he leaves Leads, its counts and the next-morning email, but nothing is deleted. One row per
    lower-cased address while he is archived; Move back deletes the row (LeadArchiveEvent keeps the history). Once the address
    has a verified account the row no longer matters (he is a Registered person)."""

    email = models.CharField(max_length=254, unique=True, help_text="Lower case.")
    reason = models.CharField(max_length=REASON_MAX, blank=True)
    archived_by = _person()
    archived_by_label = models.CharField(max_length=254, blank=True)
    archived_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-archived_at", "-id"]

    def __str__(self):
        return f"archived {self.email}"


class LeadArchiveEvent(UUIDModel):
    """One line of a lead's timeline: "Archived by X" or "Moved back by X". Append-only in practice; erased with the address."""

    ARCHIVED, RESTORED = "archived", "restored"
    KIND_CHOICES = [(ARCHIVED, "Archived"), (RESTORED, "Moved back")]

    email = models.CharField(max_length=254, db_index=True, help_text="Lower case.")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    reason = models.CharField(max_length=REASON_MAX, blank=True)
    by = _person()
    by_label = models.CharField(max_length=254, blank=True)
    at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-at", "-id"]

    def __str__(self):
        return f"{self.kind} {self.email}"


# ---------- the next-morning email to new leads (round 2, R7) ----------

class NextMorningEmail(UUIDModel):
    """One row per lead address, ever (unique email): when the next-morning email is due and what became of it. `sent_at` or
    `skipped_at` (with the reason) ends the row; a row is never sent twice and never retried."""

    email = models.CharField(max_length=254, unique=True, help_text="Lower case.")
    lead_at = models.DateTimeField(help_text="When the address was first given at the journey gate.")
    due_at = models.DateTimeField(db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    skipped_at = models.DateTimeField(null=True, blank=True)
    skip_reason = models.CharField(max_length=120, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True, help_text="Set by the worker that picked the row up (the once-only guard on databases without row locks).")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["due_at", "id"]

    def __str__(self):
        return f"next-morning {self.email}"

    @property
    def is_finished(self):
        return self.sent_at is not None or self.skipped_at is not None
