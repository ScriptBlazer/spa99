from django.db import models
from simple_history.models import HistoricalRecords

from common.models import BaseModel


class NotificationTemplate(BaseModel):
    """The wording of an email that staff can change: today the subject line. The body layout stays in
    notifications/templates/notifications/emails/. Placeholders in {braces} are filled in when sending."""

    key = models.SlugField(unique=True, help_text="Stable name the code asks for, e.g. verify. Do not rename.")
    subject = models.CharField(max_length=300, help_text="May contain {name}, {potential}.")
    note = models.CharField(max_length=200, blank=True, help_text="When this email is sent.")

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
    STATUS_CHOICES = [(SENT, "Sent"), (FAILED, "Failed")]

    to = models.TextField(help_text="Comma separated")
    subject_email = models.EmailField(
        blank=True, db_index=True,
        help_text="Who the message is about (e.g. a Gold applicant when the email went to Barry). Erased with that person.",
    )
    cc = models.TextField(blank=True)
    subject = models.CharField(max_length=300)
    template = models.CharField(max_length=60)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    error = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["-created_at"])]

    def __str__(self):
        return f"{self.template} to {self.to} ({self.status})"
