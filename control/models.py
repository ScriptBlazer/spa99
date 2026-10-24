"""Control media Library (docs/features/control.md): uploaded audio, video and images, and playlists made from them.
Files live in the default storage (S3 on live, .private/media locally) under control/media/<uuid>.<ext>."""
import uuid

from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords


def asset_path(instance, filename):
    """Never trust the uploaded name: the file is stored by the asset's uuid. The extension comes from the sniffed type."""
    return f"control/media/{instance.pk}.{instance.ext}"


def poster_path(instance, filename):
    return f"control/media/{instance.pk}-poster.jpg"


class MediaAsset(models.Model):
    AUDIO, VIDEO, IMAGE = "audio", "video", "image"
    KINDS = [(AUDIO, "Audio"), (VIDEO, "Video"), (IMAGE, "Image")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=120)
    kind = models.CharField(max_length=5, choices=KINDS)
    file = models.FileField(upload_to=asset_path, max_length=200)
    ext = models.CharField(max_length=5, help_text="From the sniffed type, never from the uploaded name.")
    mime = models.CharField(max_length=60)
    size_bytes = models.PositiveBigIntegerField()
    duration_seconds = models.FloatField(null=True, blank=True, help_text="Reported by the browser after upload.")
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    tags = models.JSONField(default=list, blank=True, help_text="A short list of lowercase words, e.g. music, screens.")
    artist = models.CharField(max_length=120, blank=True, help_text="Audio only, optional.")
    peaks = models.JSONField(null=True, blank=True, help_text="Audio: about 200 waveform heights from 0 to 1, made by the browser.")
    poster = models.FileField(upload_to=poster_path, max_length=200, blank=True, help_text="Video: a still frame (jpg) made by the browser.")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords(excluded_fields=["peaks"])

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class Playlist(models.Model):
    MUSIC, SCREENS = "music", "screens"
    KINDS = [(MUSIC, "Music"), (SCREENS, "Screens")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=7, choices=KINDS)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class PlaylistItem(models.Model):
    playlist = models.ForeignKey(Playlist, on_delete=models.CASCADE, related_name="items")
    asset = models.ForeignKey(MediaAsset, on_delete=models.CASCADE, related_name="playlist_items")
    position = models.PositiveIntegerField()
    seconds = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Pictures in a screens playlist: seconds on screen (4 to 60). Empty means 8.")

    class Meta:
        ordering = ["position"]
        constraints = [models.UniqueConstraint(fields=["playlist", "position"], name="control_item_position_unique")]
