from django.db import models
from django.db.models import Q
from simple_history.models import HistoricalRecords

from common.models import BaseModel


class NotificationTemplate(BaseModel):
    """The wording of an email that staff can change: the subject line and the body text. The layout stays in
    notifications/templates/notifications/emails/. Placeholders in {braces} are filled in when sending."""

    key = models.SlugField(unique=True, help_text="Stable name the code asks for, e.g. verify. Do not rename.")
    subject = models.CharField(max_length=300, help_text="May contain {name}, {potential}.")
    note = models.CharField(max_length=200, blank=True, help_text="When this email is sent.")
    body = models.TextField(
        blank=True,
        help_text="The wording: paragraphs separated by a blank line, {placeholders}, {button} for the main link. Blank = the built-in default (notifications/emailbody.py).",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return self.key


class EmailLog(BaseModel):
    """One row per email we tried to send. Append-only record (like LoginEvent it is itself the log, so it has
    no HistoricalRecords). Bodies are not stored: sign-in links must not sit in the database."""

    SENT = "sent"
    FAILED = "failed"
    SUPPRESSED = "suppressed"  # every recipient is on the suppression list: nothing was sent
    STATUS_CHOICES = [(SENT, "Sent"), (FAILED, "Failed"), (SUPPRESSED, "Not sent (suppressed)")]

    to = models.TextField(help_text="Comma separated")
    subject_email = models.EmailField(
        blank=True, db_index=True,
        help_text="Who the message is about (e.g. a Gold applicant when the email went to Barry). Erased with that person.",
    )
    cc = models.TextField(blank=True)
    subject = models.CharField(max_length=300)
    template = models.CharField(max_length=60)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES)
    error = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    message_id = models.CharField(max_length=100, blank=True, help_text="Amazon SES message id, when the backend returned one.")

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["-created_at"])]

    def __str__(self):
        return f"{self.template} to {self.to} ({self.status})"


class EmailSuppression(BaseModel):
    """An address we must not email: SES reported a permanent bounce or a spam complaint (Amazon SNS feedback,
    notifications/sns.py). Kept even if the person deletes their account: it holds only the address, and sending again
    would harm our sender reputation. Soft (transient) bounces are never stored here."""

    HARD_BOUNCE = "hard_bounce"
    COMPLAINT = "complaint"
    REASON_CHOICES = [(HARD_BOUNCE, "Permanent bounce"), (COMPLAINT, "Spam complaint")]

    email = models.EmailField(unique=True, help_text="Lower case.")
    reason = models.CharField(max_length=12, choices=REASON_CHOICES)
    first_seen = models.DateTimeField()
    last_seen = models.DateTimeField()
    count = models.PositiveIntegerField(default=1, help_text="Different feedback messages received for this address.")
    last_feedback_id = models.CharField(max_length=100, blank=True, help_text="SES feedback id of the last message; a repeat of it is ignored.")
    detail = models.CharField(max_length=300, blank=True, help_text="Short subtype / diagnostic from SES.")

    class Meta:
        ordering = ["-last_seen"]

    def __str__(self):
        return f"{self.email} ({self.reason})"


class EmailBounce(BaseModel):
    """One Postmark bounce or spam-complaint record, every one (soft bounces too), so System can show what is happening to our
    mail. A log only: who may be emailed is still decided by EmailSuppression. Deduped by Postmark's record id. Pruned after a year
    (common.tasks.housekeeping)."""

    HARD, SOFT, COMPLAINT, OTHER = "hard", "soft", "complaint", "other"
    KIND_CHOICES = [(HARD, "Hard"), (SOFT, "Soft"), (COMPLAINT, "Complaint"), (OTHER, "Other")]

    email = models.EmailField(db_index=True, help_text="Lower case.")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    postmark_type = models.CharField(max_length=60, blank=True, help_text="Postmark's Type, e.g. HardBounce, SoftBounce, SpamComplaint.")
    detail = models.CharField(max_length=300, blank=True)
    record_id = models.CharField(max_length=100, blank=True, help_text="Postmark's record ID; a repeat of it is ignored.")
    message_id = models.CharField(max_length=100, blank=True)
    received_at = models.DateTimeField(help_text="When Postmark says it happened (else when we received it).")

    class Meta:
        ordering = ["-received_at"]
        indexes = [models.Index(fields=["-received_at"])]
        constraints = [models.UniqueConstraint(fields=["record_id"], condition=~Q(record_id=""), name="notifications_bounce_record_unique")]

    def __str__(self):
        return f"{self.email} ({self.kind})"
