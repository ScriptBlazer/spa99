import uuid

from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    """UUID primary key: safe to expose in URLs and APIs, no guessable numbers."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class BaseModel(UUIDModel, TimeStampedModel):
    """Default base for most models. Add `history = HistoricalRecords()` on each concrete model."""

    class Meta:
        abstract = True


class LoginEvent(BaseModel):
    """Who logged in, out, or failed to, from where. Append-only: admin cannot edit or delete rows."""

    LOGIN = "login"
    LOGOUT = "logout"
    FAILED = "failed"
    EVENT_CHOICES = [(LOGIN, "Login"), (LOGOUT, "Logout"), (FAILED, "Failed login")]

    event = models.CharField(max_length=10, choices=EVENT_CHOICES)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="login_events"
    )
    attempted_email = models.CharField(max_length=254, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["-created_at"]), models.Index(fields=["attempted_email"])]

    def __str__(self):
        return f"{self.event} {self.attempted_email or self.user_id} {self.created_at:%Y-%m-%d %H:%M}"
