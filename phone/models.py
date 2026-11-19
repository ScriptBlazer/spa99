"""One row per call to the Spa 99 number (docs/features/voicemail.md): the Calls tab in the Office.

A row is created when Twilio asks what to do with the call (/phone/voice/): kind "missed" (shown as "No message") until the recording callback arrives, then "voicemail".
The audio is copied to our private media storage (S3 on live) under voicemails/YYYY/MM/ (phone.naming). Twilio keeps its own copy; we never delete it."""
from django.conf import settings
from django.db import models

from common.models import BaseModel

MAX_ATTEMPTS = 8  # per voicemail, for the download and the email together; then it stops and last_error says why


def audio_upload_to(instance, filename):
    """The caller gives the finished key (phone.naming.free_key); Django keeps it as is."""
    return filename


class Call(BaseModel):
    VOICEMAIL, MISSED = "voicemail", "missed"
    KIND_CHOICES = [(VOICEMAIL, "Voicemail"), (MISSED, "No message")]
    LIVE, IMPORT = "live", "import"
    SOURCE_CHOICES = [(LIVE, "Live"), (IMPORT, "Imported from Twilio")]
    COMPLETED, ABSENT = "completed", "absent"  # Twilio's RecordingStatus; absent = nothing was recorded (silence)

    call_sid = models.CharField(max_length=40, unique=True)
    from_number = models.CharField(max_length=32, blank=True, help_text="As Twilio gave it (E.164), or masked on an imported call.")
    to_number = models.CharField(max_length=32, blank=True)
    received_at = models.DateTimeField(help_text="When the call started.")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=MISSED)
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default=LIVE)
    recording_sid = models.CharField(max_length=40, unique=True, null=True, blank=True)
    recording_status = models.CharField(max_length=12, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    audio = models.FileField(upload_to=audio_upload_to, max_length=200, blank=True)  # default storage: private S3 on live

    # Processing (download, then email). Every run counts an attempt; at MAX_ATTEMPTS it stops.
    audio_saved_at = models.DateTimeField(null=True, blank=True)
    emailed_at = models.DateTimeField(null=True, blank=True)
    email_skipped = models.BooleanField(default=False, help_text="No email was sent on purpose (nobody on the list, or every address is suppressed).")
    last_error = models.CharField(max_length=300, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    claimed_until = models.DateTimeField(null=True, blank=True, help_text="A worker is on it until then (stops two workers doing the same one).")

    heard_at = models.DateTimeField(null=True, blank=True)
    heard_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-received_at", "-pk"]
        indexes = [
            models.Index(fields=["-received_at"], name="phone_call_received_idx"),
            models.Index(fields=["kind", "heard_at"], name="phone_call_unheard_idx"),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} from {self.from_number or 'unknown'} at {self.received_at:%Y-%m-%d %H:%M}"

    @property
    def has_sound(self):
        return self.kind == self.VOICEMAIL and self.recording_status != self.ABSENT

    @property
    def audio_pending(self):
        return bool(self.recording_sid) and self.recording_status == self.COMPLETED and not self.audio

    @property
    def email_pending(self):
        return self.source == self.LIVE and self.kind == self.VOICEMAIL and not self.emailed_at and not self.email_skipped
