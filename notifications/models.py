from django.conf import settings
from django.db import models
from django.utils import timezone
from django.db.models import Q
from simple_history.models import HistoricalRecords

from common import emaildefaults
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

    # Email flexibility (docs/features/office-outreach.md E2). "" = this email's built-in default (EmailSpec.default_footer / default_sender).
    footer_mode = models.CharField(
        max_length=12, blank=True, default="", db_default="", choices=emaildefaults.FOOTER_MODES,
        help_text="Which footer: shared, shared without the contact line, or custom (the three lines below). Blank = this email's default.")
    footer_brand_line = models.CharField("Custom footer: brand line", max_length=emaildefaults.FOOTER_LINE_MAX, blank=True,
                                         default=emaildefaults.FOOTER_BRAND, db_default=emaildefaults.FOOTER_BRAND)
    footer_address_line = models.CharField("Custom footer: address line", max_length=emaildefaults.FOOTER_LINE_MAX, blank=True,
                                           default=emaildefaults.FOOTER_ADDRESS, db_default=emaildefaults.FOOTER_ADDRESS)
    footer_contact_line = models.CharField("Custom footer: contact line", max_length=emaildefaults.FOOTER_LINE_MAX, blank=True,
                                           default=emaildefaults.FOOTER_CONTACT, db_default=emaildefaults.FOOTER_CONTACT)
    sender = models.CharField(
        max_length=10, blank=True, default="", db_default="", choices=emaildefaults.SENDERS,
        help_text="Site sender (hello@) or the person sender set in System > Emails. Blank = this email's default.")
    heading = models.CharField(max_length=emaildefaults.HEADING_MAX, blank=True, default="", db_default="",
                               help_text="The big line at the top. Blank = the subject.")
    button_text = models.CharField(max_length=emaildefaults.BUTTON_TEXT_MAX, blank=True, default="", db_default="",
                                   help_text="The text on the button (emails that have one). Blank = the built-in text.")

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


class StaffSender(models.Model):
    """What a staff member's Office emails go out with (System > Team > Email): a sending address when his own login address is not on the sending domain, and his signature.
    One row per person, made on first save. Erased with the account (CASCADE); the signature is cleaned HTML (common.richtext.clean_signature)."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="email_sender")
    sending_address = models.CharField(max_length=254, blank=True, default="", db_default="", help_text="Lower case, on the sending domain. Used only when his own login address is not.")
    signature_html = models.TextField(blank=True, default="", db_default="", help_text="Cleaned HTML: tables, text, links and pictures only. Pictures may be /static/common/img/email/... (made absolute from SITE_URL when sent).")
    updated_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Email sender for {self.user_id}"
