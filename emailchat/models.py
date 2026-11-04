"""Email chat in the Office (docs/features/office-email-chat.md): threads, messages, files.
A thread is one subject with one person's address, like a mail thread: a person can have many. Each has its own random reply token (the
`reply+<token>@<EMAIL_INBOUND_DOMAIN>` Reply-To), so his reply lands in the right thread. Personal data (addresses, text, files) is erased with the person:
see emailchat.services.erase_threads. Deviation (one line): no django-simple-history, messages are themselves the log and copies would double what must be erased."""
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from common.models import UUIDModel


def _user(**kwargs):
    return models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", **kwargs)


def new_token():
    return secrets.token_hex(12)  # 24 lower-case hex characters: safe in an address, no way to guess another thread


class Thread(UUIDModel):
    email = models.CharField(max_length=254, db_index=True, help_text="Lower case. His address; many threads can share it.")
    token = models.CharField(max_length=32, unique=True, default=new_token, help_text="Random: the part after reply+ in the Reply-To address.")
    subject = models.CharField(max_length=300, blank=True, help_text="The first subject; each message keeps its own.")
    name = models.CharField(max_length=100, blank=True, help_text="Resolved name: the account, lead or application name.")
    user = _user()
    lead_email = models.CharField(max_length=254, blank=True, db_index=True, help_text="Lower case. The lead this address belongs to (no account).")
    application = models.ForeignKey("gold.GoldApplication", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_by = _user()
    created_at = models.DateTimeField(default=timezone.now)
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_inbound_at = models.DateTimeField(null=True, blank=True)
    last_preview = models.CharField(max_length=200, blank=True)
    last_direction = models.CharField(max_length=3, blank=True)
    has_attachment = models.BooleanField(default=False, help_text="Any message has a file.")
    direct_to = models.CharField(max_length=254, blank=True, default="", db_default="", help_text="Started by an email sent directly to this staff address (lower case): the first one it was sent to. Blank: started in the Office.")
    direct_name = models.CharField(max_length=100, blank=True, default="", db_default="", help_text="The staff member's first name, for 'Sent to Barry'.")

    class Meta:
        ordering = ["-last_message_at", "-created_at"]
        indexes = [models.Index(fields=["email", "-last_message_at"])]

    def __str__(self):
        return f"Email thread {self.subject[:40] or self.pk}"


class ThreadRead(models.Model):
    """When a staff member last read a thread. Unread = his messages after it (spam excluded), per user."""

    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="reads")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="emailchat_reads")
    read_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["thread", "user"], name="emailchat_one_read_per_user")]


class Message(models.Model):
    """One email in a thread. Integer id on purpose: it only grows, so the poll `?after=<id>` is one cheap range read."""

    IN, OUT = "in", "out"
    DIRECTIONS = [(IN, "From him"), (OUT, "From us")]
    QUEUED, SENT, DELIVERED, BOUNCED, FAILED, RECEIVED = "queued", "sent", "delivered", "bounced", "failed", "received"
    STATUSES = [(QUEUED, "Queued"), (SENT, "Sent"), (DELIVERED, "Delivered"), (BOUNCED, "Bounced"), (FAILED, "Failed"), (RECEIVED, "Received")]
    BAD = (FAILED, BOUNCED)

    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="messages")
    direction = models.CharField(max_length=3, choices=DIRECTIONS)
    subject = models.CharField(max_length=300, blank=True)
    shows_subject = models.BooleanField(default=False, help_text="First in the thread, or the subject changed: the thread shows it.")
    body_text = models.TextField(blank=True, help_text="Plain text. His: only his new text (Postmark StrippedTextReply), else the whole text.")
    body_full = models.TextField(blank=True, help_text="His whole plain text with the earlier quoted mail, when that differs from body_text.")
    body_html = models.TextField(blank=True, help_text="Cleaned to an allow-list (common.richtext) before it is stored. Ours: shown in the page. His: only ever served in a sandboxed frame.")
    has_remote_images = models.BooleanField(default=False)
    author = _user()
    author_label = models.CharField(max_length=254, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=QUEUED)
    provider_id = models.CharField(max_length=100, unique=True, null=True, blank=True, help_text="Postmark MessageID: his inbound mail (idempotent), or ours once a bounce or delivery names it.")
    rfc_message_id = models.CharField(max_length=300, blank=True, help_text="The Message-ID header, for In-Reply-To and References.")
    in_reply_to = models.CharField(max_length=300, blank=True)
    references = models.TextField(blank=True)
    from_address = models.CharField(max_length=254, blank=True, help_text="Lower case. His: who it came from (it can differ from the thread address, e.g. forwarded mail).")
    from_name = models.CharField(max_length=200, blank=True)
    to_address = models.CharField(max_length=254, blank=True, default="", db_default="", help_text="Ours: the address it was sent to (the thread's address can be corrected later). Blank on older rows: the thread's address.")
    spam = models.BooleanField(default=False, help_text="Postmark's X-Spam-Status said Yes: stored, marked, never pushed or counted unread.")
    note = models.CharField(max_length=500, blank=True, help_text="Something staff should know about this email, e.g. a file that was too big to keep.")
    error_code = models.CharField(max_length=20, blank=True)
    error_message = models.CharField(max_length=300, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True, help_text="The worker that took this send (a send is never made twice).")
    incomplete = models.BooleanField(default=False, db_default=False, help_text="His email is stored but its files or its worker task are not done yet: Postmark's retry of the same MessageID finishes it.")
    notified_at = models.DateTimeField(null=True, blank=True, help_text="The team push for this email was taken by a worker (it is never pushed twice).")
    signature_html = models.TextField(blank=True, default="", db_default="", help_text="Ours: the signature this email went with, cleaned (common.richtext.clean_signature), as it was when the email was queued. Not part of body_html.")
    signature_text = models.TextField(blank=True, default="", db_default="", help_text="Ours: the plain text sign-off this email went with (the plain text copy's last lines).")
    group_copied_at = models.DateTimeField(null=True, blank=True, help_text="His reply was copied to the group address (taken by a worker once; Postmark's retries never copy it twice).")
    direct_to = models.CharField(max_length=300, blank=True, default="", db_default="", help_text="His email was sent directly to these staff (first names, comma separated) and reached us by their forward. Blank: not direct mail.")
    direct_key = models.CharField(max_length=64, null=True, blank=True, unique=True, help_text="Direct mail only: a hash of the original Message-ID, so one email forwarded from two mailboxes is one message.")
    legacy_person_message = models.UUIDField(null=True, blank=True, unique=True, help_text="The old outreach.PersonMessage this was copied from (backfill_email_threads).")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(default=timezone.now, db_index=True, help_text="Changed when the status changes: the poll reads it.")
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["thread", "id"]), models.Index(fields=["thread", "direction", "created_at"], name="emailchat_unread_idx")]  # unread counts and the inbox filter

    def __str__(self):
        return f"{self.direction} email {self.pk}"


class Attachment(models.Model):
    """A file on an email, in the default storage (S3 on live). Only images and PDFs whose own first bytes match are `inline_ok`; everything else downloads."""

    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="attachments")
    key = models.CharField(max_length=500, help_text="Where the file is in the default storage.")
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, help_text="What it is served as: the checked type for an inline file, else application/octet-stream.")
    declared_type = models.CharField(max_length=100, blank=True)
    size = models.PositiveIntegerField(default=0)
    content_id = models.CharField(max_length=300, blank=True, help_text="The Content-ID an inline picture in his HTML points at (cid:).")
    inline_ok = models.BooleanField(default=False)
    inline_ref = models.BooleanField(default=False, db_default=False, help_text="Part of his email's layout (a picture his HTML points at, or a signature picture), not a file he sent: stored and erased, never listed as a file.")
    checked = models.BooleanField(default=False, help_text="The worker has looked at its first bytes.")

    class Meta:
        ordering = ["id"]


class StaffSender(models.Model):
    """What a staff member's Office emails go out with (System > Team > Email): a sending address when his own login address is not on the sending domain, and his signature.
    One row per person, made on first save. Erased with the account (CASCADE); the signature is cleaned HTML (common.richtext.clean_signature)."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="email_sender")
    sending_address = models.CharField(max_length=254, blank=True, default="", help_text="Lower case, on the sending domain. Used only when his own login address is not.")
    signature_html = models.TextField(blank=True, default="", help_text="Cleaned HTML: tables, text, links and pictures only. Pictures may be /static/common/img/email/... (made absolute from SITE_URL when sent).")
    inbox_token = models.CharField(max_length=32, null=True, blank=True, unique=True, help_text="Random: the part after inbox+ in the address his mailbox forwards to (inbox+<token>@<EMAIL_INBOUND_DOMAIN>). Made when his Email settings are saved.")
    updated_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Email sender for {self.user_id}"
