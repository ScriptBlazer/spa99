from django.db import models

from common.models import BaseModel


class EmailLog(BaseModel):
    """One row per email we tried to send. Append-only record (like LoginEvent it is itself the log, so it has
    no HistoricalRecords). Bodies are not stored: sign-in links must not sit in the database."""

    SENT = "sent"
    FAILED = "failed"
    STATUS_CHOICES = [(SENT, "Sent"), (FAILED, "Failed")]

    to = models.TextField(help_text="Comma separated")
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
