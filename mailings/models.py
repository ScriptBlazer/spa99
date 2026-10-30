"""Group sends (Mailing and its recipient rows), invites, and addresses that unsubscribed without having an account.

Mailing and Invite hold people's addresses, so they are erased with the person (users.services.delete_user_data). They have
no django-simple-history: the rows are the record, and history would copy the addresses. Every start, schedule and cancel is
written to the System audit log (SystemEvent) with counts instead."""
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import functions as _f
from django.utils import timezone

from simple_history.models import HistoricalRecords

from common.models import BaseModel



class Mailing(BaseModel):
    NEWS, SERVICE, INVITATION = "news", "service", "invitation"
    KIND_CHOICES = [(NEWS, "News (marketing: only people who opted in, with unsubscribe)"), (SERVICE, "Service message (no unsubscribe, says why they get it)"),
                    (INVITATION, "Invitation (to an uploaded list: with unsubscribe and a personal register link)")]
    MARKETING = (NEWS, INVITATION)  # these carry the unsubscribe link and headers
    DRAFT, SCHEDULED, SENDING, PAUSED, SENT, CANCELLED, FAILED = "draft", "scheduled", "sending", "paused", "sent", "cancelled", "failed"
    STATUS_CHOICES = [(DRAFT, "Draft"), (SCHEDULED, "Scheduled"), (SENDING, "Sending"), (PAUSED, "Paused"), (SENT, "Sent"), (CANCELLED, "Cancelled"), (FAILED, "Failed")]
    EDITABLE = (DRAFT,)

    name = models.CharField(max_length=120, help_text="Only shown in System.")
    subject = models.CharField(max_length=200)
    body = models.TextField(blank=True, help_text="Older mailings: paragraphs separated by a blank line; {first_name} is filled in for each person. Used only when there are no blocks.")
    blocks = models.JSONField(default=list, blank=True, help_text="The email as parts (mailings.blocks): a list of {type, ...}. When set, it is used instead of the body.")
    kind = models.CharField(max_length=12, choices=KIND_CHOICES, default=NEWS)
    automatic_key = models.SlugField(max_length=40, blank=True, help_text="Set when this sends an automatic email's wording (mailings.automatic), e.g. 'invite'. The wording then comes from that email.")
    group = models.CharField(max_length=40, help_text="A key of mailings.segments.GROUPS.")
    params = models.JSONField(default=dict, blank=True, help_text="The group's options (plan, dates, status).")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=DRAFT, db_index=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    confirmed_count = models.PositiveIntegerField(null=True, blank=True, help_text="The number of people the person confirmed when scheduling. If more would get it when the time comes, it goes back to draft.")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=300, blank=True, help_text="Why it failed or could not start.")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    # Counts, set when sending starts (total) and after every batch (the rest). The recipient rows are the truth.
    total_count = models.PositiveIntegerField(default=0)
    sent_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "-created_at"])]

    def __str__(self):
        return self.name

    @property
    def editable(self):
        return self.status in self.EDITABLE

    @property
    def has_personal_links(self):
        """Does a Button part link to a personal (tracked) link? Then each person gets an Invite row and the send follows the invitation rules."""
        from .blocks import has_personal

        return has_personal(self.blocks)

    @property
    def schedule_name(self):
        return f"mailing-{self.pk}"


IMAGE_EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif"}


def image_path(instance, filename):
    """A random name under mailings/images/ (the uploaded name is never kept)."""
    return f"mailings/images/{secrets.token_hex(16)}.{IMAGE_EXTENSIONS[instance.content_type]}"


class MailingImage(BaseModel):
    """A picture uploaded for an email. The bucket is private, so emails link to /email-image/<id>/ (served by the app); the random
    id is the primary key. Never deleted while a mailing that was sent uses it (there is no delete yet)."""

    file = models.FileField(upload_to=image_path, max_length=200)
    content_type = models.CharField(max_length=20, choices=[(k, k) for k in IMAGE_EXTENSIONS])
    size = models.PositiveIntegerField(help_text="Bytes.")
    width = models.PositiveIntegerField(null=True, blank=True, help_text="Pixels, read from the file header; blank when it could not be read.")
    height = models.PositiveIntegerField(null=True, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.file.name} ({self.width}x{self.height})"

    @property
    def path(self):
        """With a file extension (CDNs such as Cloudflare cache by extension). The old /email-image/<id>/ keeps working."""
        return f"/email-image/{self.pk}.{IMAGE_EXTENSIONS[self.content_type]}"

    @property
    def url(self):
        return f"{settings.SITE_URL}{self.path}"


class MailingTemplate(BaseModel):
    """A saved starting point for a new group send (System > Emails > Templates): subject, kind, Who and the parts. No people's data,
    so it has history like other System settings. `key` marks the ones the seed makes (booking_open); a renamed template keeps its key,
    so seeding again never adds a second copy. Pictures used by a template are never deleted."""

    key = models.SlugField(max_length=40, unique=True, null=True, blank=True, help_text="Set for the built-in ones the seed creates.")
    name = models.CharField(max_length=120)
    subject = models.CharField(max_length=200, blank=True)
    kind = models.CharField(max_length=12, choices=Mailing.KIND_CHOICES, default=Mailing.NEWS)
    group = models.CharField(max_length=40, blank=True, help_text="A key of mailings.segments.GROUPS, or blank (Who is chosen later).")
    blocks = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    history = HistoricalRecords()

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(_f.Lower("name"), name="mailings_template_name_ci")]

    def __str__(self):
        return self.name


class MailingRecipient(BaseModel):
    """One person in one mailing, written when sending starts (a snapshot of the group at that moment)."""

    QUEUED, SENDING, SENT, SKIPPED, FAILED, BOUNCED = "queued", "sending", "sent", "skipped", "failed", "bounced"
    STATUS_CHOICES = [(QUEUED, "Queued"), (SENDING, "Sending"), (SENT, "Sent"), (SKIPPED, "Skipped"), (FAILED, "Failed"), (BOUNCED, "Bounced")]

    mailing = models.ForeignKey(Mailing, on_delete=models.CASCADE, related_name="recipients")
    email = models.EmailField()
    first_name = models.CharField(max_length=100, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=QUEUED)
    reason = models.CharField(max_length=200, blank=True, help_text="Why it was skipped or failed.")
    sent_at = models.DateTimeField(null=True, blank=True)
    message_id = models.CharField(max_length=100, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0, help_text="Sends that SES throttled; after 5 the row fails.")
    retry_at = models.DateTimeField(null=True, blank=True, help_text="A throttled send waits until then (backoff).")

    class Meta:
        ordering = ["email"]
        constraints = [models.UniqueConstraint(fields=["mailing", "email"], name="mailings_recipient_once")]  # never twice in one mailing
        indexes = [models.Index(fields=["mailing", "status"]), models.Index(fields=["email"])]

    def __str__(self):
        return f"{self.email} ({self.status})"


def new_token():
    return secrets.token_urlsafe(24)


def _register_invite_days():
    from system import defaults

    return defaults.get().register_invite_days


class Invite(BaseModel):
    """One person invited to register. The personal link /invite/<token>/ only pre-fills the register form and marks the invite
    opened: nothing else is trusted from it."""

    QUEUED, SENDING, SENT, OPENED, REGISTERED, BOUNCED, SKIPPED, FAILED = (
        "queued", "sending", "sent", "opened", "registered", "bounced", "skipped", "failed")
    STATUS_CHOICES = [(QUEUED, "Waiting to send"), (SENDING, "Sending"), (SENT, "Sent"), (OPENED, "Opened"), (REGISTERED, "Registered"), (BOUNCED, "Bounced"),
                      (SKIPPED, "Skipped"), (FAILED, "Failed")]
    PENDING = (QUEUED, SENDING, SENT, OPENED)  # invited and not yet resolved

    name = models.CharField(max_length=100, blank=True)
    email = models.EmailField(db_index=True, help_text="Lower case.")
    token = models.CharField(max_length=40, unique=True, default=new_token, editable=False)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=QUEUED, db_index=True)
    reason = models.CharField(max_length=200, blank=True, help_text="Why it was skipped or failed.")
    batch_id = models.UUIDField(db_index=True, help_text="Invites imported together share this.")
    sent_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True, help_text="First click on the personal link (status Opened).")
    email_opened_at = models.DateTimeField(null=True, blank=True, help_text="First time the email itself was opened (Postmark open pixel). Not the link click.")
    registered_at = models.DateTimeField(null=True, blank=True)
    registered_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    expires_at = models.DateTimeField(help_text="The personal link stops working then (System > Defaults days after it was created).")
    message_id = models.CharField(max_length=100, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    retry_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at", "email"]
        indexes = [models.Index(fields=["batch_id", "status"])]

    def __str__(self):
        return f"{self.email} ({self.status})"

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=_register_invite_days())
        super().save(*args, **kwargs)

    @property
    def expired(self):
        return self.expires_at <= timezone.now()


class InviteImport(BaseModel):
    """The one-time token the review page hands out for an invite import: tied to the person and the hash of the exact list. The first
    confirmation claims it (batch_id is set by one conditional update), so a double click, lag, back-and-resubmit or two tabs make one
    batch; any later confirmation is answered with that batch. Holds no addresses, only the hash."""

    token = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    content_hash = models.CharField(max_length=64)
    batch_id = models.UUIDField(null=True, blank=True, unique=True, help_text="Set when the import was made; the batch (or uploaded list save) this token produced.")
    contact_list = models.ForeignKey("mailings.ContactList", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                     help_text="The uploaded list this token saved people into (a repeat answers with it).")
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"import {self.token[:6]}... ({'used' if self.batch_id else 'open'})"


class ContactList(BaseModel):
    """An uploaded list of people (System > Emails > Groups). Saved from a CSV that passed invites.check(); nothing is sent when it is
    saved. A group send can pick it ("Uploaded list"). Names and categories are not personal data; the members are (ContactListMember)."""

    name = models.CharField(max_length=120)
    category = models.CharField(max_length=60, blank=True, help_text="Optional, free text (e.g. Gym members).")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    history = HistoricalRecords()

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(_f.Lower("name"), name="mailings_list_name_ci")]

    def __str__(self):
        return self.name


class ContactListMember(BaseModel):
    """One address on an uploaded list. Personal data: erased with the person (mailings.erasure), exported with their data. No history
    (it would copy the addresses). Whether he can be emailed is decided when a send is made (segments), never stored here."""

    list = models.ForeignKey(ContactList, on_delete=models.CASCADE, related_name="members")
    email = models.EmailField(help_text="Lower case.")
    name = models.CharField(max_length=100, blank=True)
    added_at = models.DateTimeField(default=timezone.now)
    source_row = models.PositiveIntegerField(default=0, help_text="The row number in the file it came from (the header is row 1).")

    class Meta:
        ordering = ["email"]
        constraints = [models.UniqueConstraint(fields=["list", "email"], name="mailings_member_once")]
        indexes = [models.Index(fields=["email"])]

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)


class EmailOptOut(BaseModel):
    """An address that clicked Unsubscribe and has no account (an invitee, a Gold applicant). People with an account use
    `User.marketing_consent` instead (their choice is logged in history and shows in My Spa 99). Kept like EmailSuppression:
    it holds only the address, and forgetting it would mean emailing someone who asked us to stop. News and invites check it."""

    email = models.EmailField(unique=True, help_text="Lower case.")
    source = models.CharField(max_length=20, default="unsubscribe")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.email


class UnsubscribeKey(BaseModel):
    """The opaque reference in an unsubscribe link: one random key per address, so no address appears in a URL. No expiry (an old
    email must still be able to stop the mail). Erased with the person's data; the opt-out itself is EmailOptOut or the consent flag."""

    email = models.EmailField(unique=True, help_text="Lower case.")
    token = models.CharField(max_length=40, unique=True, default=new_token, editable=False)

    def __str__(self):
        return self.email
