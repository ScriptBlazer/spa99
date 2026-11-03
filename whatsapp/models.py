"""WhatsApp in the Office (docs/features/whatsapp.md): contacts, messages, Twilio templates, push subscriptions.
Personal data (numbers, message text, media) is erased with the person: see whatsapp.services.erase_phones.

Deviation (one line): no django-simple-history on these models. Messages are themselves the log, and history copies would
double every message and every number we must erase."""
from django.conf import settings
from django.db import models
from django.utils import timezone

from common.models import UUIDModel

TEMPLATE_PREFIX = "spa99_"  # BML shares the Twilio account: only these templates are ever listed or sent


def _user(on_delete=models.SET_NULL, **kwargs):
    return models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=on_delete, related_name="+", **kwargs)


class Template(UUIDModel):
    """A Twilio Content Template, synced from Twilio (System > WhatsApp). Only `spa99_` names are listed or sendable."""

    APPROVED = "approved"

    content_sid = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=120, help_text="Twilio friendly name, e.g. spa99_lead_follow_up.")
    language = models.CharField(max_length=12, blank=True)
    category = models.CharField(max_length=30, blank=True, help_text="WhatsApp category: marketing, utility, authentication.")
    approval_status = models.CharField(max_length=20, blank=True, help_text="WhatsApp approval: approved, pending, rejected, unsubmitted ... 'removed' when it left Twilio.")
    body = models.TextField(blank=True, help_text="With {{1}} style variables.")
    variables = models.JSONField(default=list, blank=True, help_text='Variable keys in order, e.g. ["1"].')
    variable_labels = models.JSONField(default=dict, blank=True, help_text='What each variable is, for the form: {"1": "First name"}. Kept across syncs.')
    synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def label(self):
        """'spa99_lead_follow_up' -> 'Lead follow up'."""
        bare = self.name[len(TEMPLATE_PREFIX):] if self.name.lower().startswith(TEMPLATE_PREFIX) else self.name
        return bare.replace("_", " ").strip().capitalize()

    @property
    def is_spa99(self):
        return self.name.lower().startswith(TEMPLATE_PREFIX)

    @property
    def sendable(self):
        return self.is_spa99 and self.approval_status == self.APPROVED


class Contact(UUIDModel):
    """One WhatsApp number (E.164, unique). Links to who he is are found by phone match (`whatsapp.services.resolve_links`)."""

    phone = models.CharField(max_length=20, unique=True, help_text="E.164.")
    profile_name = models.CharField(max_length=100, blank=True, help_text="His WhatsApp profile name (Twilio ProfileName): for reference.")
    name = models.CharField(max_length=100, blank=True, help_text="Resolved name: the account, lead or application name. Wins over the profile name.")
    user = _user()
    lead_email = models.CharField(max_length=254, blank=True, db_index=True, help_text="Lower case. The lead whose mobile this is (no account).")
    application = models.ForeignKey("gold.GoldApplication", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    opted_out_at = models.DateTimeField(null=True, blank=True, help_text="He replied STOP. Nothing is sent until he replies START.")
    last_inbound_at = models.DateTimeField(null=True, blank=True, help_text="His latest message: the 24-hour window runs from it.")
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_preview = models.CharField(max_length=200, blank=True, help_text="First line of the latest message, for the list.")
    last_kind = models.CharField(max_length=12, blank=True)
    last_direction = models.CharField(max_length=3, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-last_message_at", "-created_at"]

    def __str__(self):
        return f"WhatsApp {self.phone}"

    @property
    def display_name(self):
        return self.name or self.profile_name or self.phone

    @property
    def opted_out(self):
        return self.opted_out_at is not None


class ContactRead(models.Model):
    """When a staff member last read a chat. Unread = his inbound messages after it (per user)."""

    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="reads")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="whatsapp_reads")
    read_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["contact", "user"], name="whatsapp_one_read_per_user")]


class Message(models.Model):
    """One WhatsApp message in a chat. Integer id on purpose: it only grows, so the poll `?after=<id>` is one cheap range read."""

    IN, OUT = "in", "out"
    DIRECTIONS = [(IN, "From him"), (OUT, "From us")]
    TEXT, IMAGE, DOCUMENT, AUDIO, VIDEO, FILE, TEMPLATE, OTHER = "text", "image", "document", "audio", "video", "file", "template", "other"
    KINDS = [(TEXT, "Text"), (IMAGE, "Image"), (DOCUMENT, "PDF"), (AUDIO, "Audio"), (VIDEO, "Video"), (FILE, "File"), (TEMPLATE, "Template"), (OTHER, "Other")]
    QUEUED, SENT, DELIVERED, READ, FAILED, UNDELIVERED, RECEIVED = "queued", "sent", "delivered", "read", "failed", "undelivered", "received"
    STATUSES = [(QUEUED, "Queued"), (SENT, "Sent"), (DELIVERED, "Delivered"), (READ, "Read"), (FAILED, "Failed"), (UNDELIVERED, "Undelivered"), (RECEIVED, "Received")]
    BAD = (FAILED, UNDELIVERED)

    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="messages")
    direction = models.CharField(max_length=3, choices=DIRECTIONS)
    kind = models.CharField(max_length=10, choices=KINDS, default=TEXT)
    body = models.TextField(blank=True)
    media_key = models.CharField(max_length=500, blank=True, help_text="Where the file is in the default storage (S3 on live).")
    media_type = models.CharField(max_length=100, blank=True)
    media_filename = models.CharField(max_length=255, blank=True)
    media_size = models.PositiveIntegerField(null=True, blank=True)
    media_width = models.PositiveIntegerField(null=True, blank=True)
    media_height = models.PositiveIntegerField(null=True, blank=True)
    media_source_url = models.CharField(max_length=500, blank=True, help_text="His file at Twilio until the worker has copied it; then empty.")
    twilio_sid = models.CharField(max_length=40, unique=True, null=True, blank=True)
    status = models.CharField(max_length=12, choices=STATUSES, default=QUEUED)
    error_code = models.CharField(max_length=20, blank=True)
    error_message = models.CharField(max_length=300, blank=True)
    author = _user()
    author_label = models.CharField(max_length=254, blank=True)
    template = models.ForeignKey(Template, null=True, blank=True, on_delete=models.SET_NULL, related_name="messages")
    template_variables = models.JSONField(default=dict, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True, help_text="The worker that took this send (a send is never made twice).")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(default=timezone.now, db_index=True, help_text="Changed when the status changes: the poll reads it.")
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["contact", "id"])]

    def __str__(self):
        return f"{self.direction} {self.kind} {self.pk}"


class PushSubscription(models.Model):
    """One staff device that wants notifications (Web Push). Dead ones (404 or 410 from the push service) are deleted."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions")
    endpoint = models.CharField(max_length=700, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    user_agent = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    last_used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"push {self.user_id}"


class WhatsAppPrefs(models.Model):
    """Per staff member: mute all WhatsApp notifications (on every device)."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="whatsapp_prefs")
    muted = models.BooleanField(default=False)
