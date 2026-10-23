"""System: developers-only business rules. The change list lives here."""
from django.conf import settings
from django.db import models

from common.models import BaseModel


class SystemChange(BaseModel):
    """One changed field of one row: when, who, section, model, field, old value, new value. Append-only (the admin
    cannot edit or delete it; undo adds a new row). Rows for models with django-simple-history are written from the
    history record (so edits made anywhere are listed); settings without history (team roles) are written directly.
    Values are JSON so an undo can restore the typed value."""

    CREATED, UPDATED, DELETED, DIRECT = "created", "updated", "deleted", "direct"
    KIND_CHOICES = [(CREATED, "Created"), (UPDATED, "Changed"), (DELETED, "Deleted"), (DIRECT, "Changed (no history)")]

    section = models.CharField(max_length=20, db_index=True)
    model_label = models.CharField(max_length=60, help_text="app_label.model, lower case")
    object_pk = models.CharField(max_length=64, blank=True)
    object_repr = models.CharField(max_length=200, blank=True)
    field = models.CharField(max_length=60, blank=True, help_text="Empty for a created or deleted row.")
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=UPDATED)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    user_label = models.CharField(max_length=254, blank=True, help_text="The person's email when it was made (kept if the account goes).")
    history_id = models.PositiveBigIntegerField(null=True, blank=True, help_text="The simple-history row this came from (not a foreign key: one table per model).")
    batch_id = models.UUIDField(null=True, blank=True, db_index=True, help_text="Changes saved in one request share this (shown as 'Saved together', undone with 'Undo all').")
    undo_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="undone_by")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["-created_at"]), models.Index(fields=["section", "-created_at"])]

    def __str__(self):
        return f"{self.model_label} {self.object_repr} {self.field}".strip()

    @property
    def undoable(self):
        return self.kind == self.UPDATED and bool(self.field) and self.history_id is not None
