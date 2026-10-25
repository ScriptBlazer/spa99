"""System: developers-only business rules. The audit log lives here: SystemChange (what changed) and SystemEvent
(security events). Both are append-only and hash-chained (system/audit.py): each row carries `seq` (one running number
across both tables), `prev_hash` and `hash`."""
from django.conf import settings
from django.db import models, transaction
from datetime import timedelta

from django.utils import timezone

from common.models import UUIDModel


class AppendOnlyError(Exception):
    """An audit row can only be added: never edited, never deleted."""


class AuditQuerySet(models.QuerySet):
    """Refuses every bulk way of editing or removing audit rows. Only the prune command (system.audit.prune) may delete,
    through the two underscore methods below, and only a prefix of the chain."""

    def update(self, **kwargs):
        raise AppendOnlyError("Audit rows cannot be edited.")

    def bulk_update(self, *args, **kwargs):
        raise AppendOnlyError("Audit rows cannot be edited.")

    def bulk_create(self, *args, **kwargs):
        raise AppendOnlyError("Audit rows are added one at a time so each joins the hash chain.")

    def delete(self):
        raise AppendOnlyError("Audit rows cannot be deleted.")

    def _prune_delete(self):
        return self._raw_delete(self.db)

    def _prune_update(self, **kwargs):
        return super().update(**kwargs)


class AuditHead(models.Model):
    """One row (pk 1): the newest hash in the chain and the anchor. It is the lock that serialises writers (select_for_update
    on Postgres; SQLite serialises writes anyway). `anchor_*` is the last row removed by the prune command (0 and empty
    when nothing was ever pruned): verification starts after it."""

    last_seq = models.BigIntegerField(default=0)
    last_hash = models.CharField(max_length=64, blank=True)
    anchor_seq = models.BigIntegerField(default=0)
    anchor_hash = models.CharField(max_length=64, blank=True)
    # the last stored verification result (written by verify_audit_log, the hourly job and "Check now"; pages only read it)
    verified_at = models.DateTimeField(null=True, blank=True)
    verify_ok = models.BooleanField(null=True, blank=True)
    verify_entries = models.PositiveBigIntegerField(default=0)
    verify_broken_id = models.CharField(max_length=64, blank=True)
    verify_broken_seq = models.BigIntegerField(null=True, blank=True)
    verify_message = models.CharField(max_length=300, blank=True)

    @classmethod
    def lock(cls):
        try:
            return cls.objects.select_for_update().get(pk=1)
        except cls.DoesNotExist:
            cls.objects.get_or_create(pk=1)
            return cls.objects.select_for_update().get(pk=1)


class JobStatus(models.Model):
    """Our own last-run record per background job (name: rollup, snapshot, audit_verify), written by the jobs themselves
    (common.jobs.tracked) whoever starts them: the worker, a command or a Run now button. Mutable on purpose."""

    name = models.CharField(max_length=40, unique=True)
    last_started_at = models.DateTimeField(null=True, blank=True)
    last_finished_at = models.DateTimeField(null=True, blank=True)
    last_ok = models.BooleanField(null=True, blank=True)
    last_message = models.CharField(max_length=300, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self):
        return self.name

    @property
    def running(self):
        """Started and not finished (a run that died leaves this on; it is ignored after 10 minutes)."""
        if not self.last_started_at or (self.last_finished_at and self.last_finished_at >= self.last_started_at):
            return False
        return timezone.now() - self.last_started_at < timedelta(minutes=10)


class AuditRow(UUIDModel):
    """Base of the audit tables: sealed into the hash chain when added, refuses to be changed or deleted."""

    seq = models.BigIntegerField(null=True, blank=True, unique=True, editable=False, help_text="Position in the chain (one count across changes and events). Empty only for rows older than the chain.")
    prev_hash = models.CharField(max_length=64, blank=True, editable=False)
    hash = models.CharField(max_length=64, blank=True, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)

    objects = AuditQuerySet.as_manager()

    class Meta:
        abstract = True

    def hash_payload(self):
        raise NotImplementedError

    def save(self, *args, **kwargs):
        from . import audit

        if not self._state.adding:
            raise AppendOnlyError("Audit rows cannot be edited.")
        with transaction.atomic(using=kwargs.get("using")):
            audit.seal(self)
            kwargs["force_insert"] = True
            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyError("Audit rows cannot be deleted.")


class SystemChange(AuditRow):
    """One changed field of one row: when, who, from where, section, model, field, old value, new value, and a plain
    sentence made when it was written. Append-only (undo adds a new row). Rows for models with django-simple-history are
    written from the history record (so edits made anywhere are listed); settings without history (team roles) are
    written directly. Values are JSON so an undo can restore the typed value."""

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
    sentence = models.TextField(blank=True, help_text="The change in plain words, written when it was made.")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    user_label = models.CharField(max_length=254, blank=True, help_text="The person's email when it was made (kept if the account goes).")
    ip_address = models.CharField(max_length=45, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    path = models.CharField(max_length=200, blank=True)
    history_id = models.PositiveBigIntegerField(null=True, blank=True, help_text="The simple-history row this came from (not a foreign key: one table per model).")
    batch_id = models.UUIDField(null=True, blank=True, db_index=True, help_text="Changes saved in one request share this (shown as 'Saved together', undone with 'Undo all').")
    undo_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="undone_by")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["-created_at"]), models.Index(fields=["section", "-created_at"])]

    def __str__(self):
        return self.sentence or f"{self.model_label} {self.object_repr} {self.field}".strip()

    @property
    def undoable(self):
        return self.kind == self.UPDATED and bool(self.field) and self.history_id is not None

    def hash_payload(self):
        # user and undo_of are links that the database may null (an account is deleted; the prune command); the text kept
        # beside them is what is sealed.
        return {"t": "change", "created_at": self.created_at, "section": self.section, "model_label": self.model_label,
                "object_pk": self.object_pk, "object_repr": self.object_repr, "field": self.field, "old": self.old_value,
                "new": self.new_value, "kind": self.kind, "sentence": self.sentence, "user_label": self.user_label,
                "ip": self.ip_address, "ua": self.user_agent, "path": self.path, "history_id": self.history_id,
                "batch_id": self.batch_id}


class SystemEvent(AuditRow):
    """A security event on the System host: sign-in, failures, unlock, lock, sign-out, access refused, roles, undo, export."""

    SIGN_IN, SIGN_IN_FAILED = "sign_in", "sign_in_failed"
    UNLOCK, UNLOCK_FAILED, UNLOCK_RATE_LIMITED = "unlock", "unlock_failed", "unlock_rate_limited"
    LOCK_MANUAL, LOCK_IDLE = "lock_manual", "lock_idle"
    SIGN_OUT, SESSION_EXPIRED, ACCESS_DENIED = "sign_out", "session_expired", "access_denied"
    ROLE_CHANGED, USER_DEACTIVATED, USER_REACTIVATED = "role_changed", "user_deactivated", "user_reactivated"
    UNDO, UNDO_ALL, EXPORT, AUDIT_PRUNED, AUDIT_CHECK, JOB_RUN = "undo", "undo_all", "export", "audit_pruned", "audit_check", "job_run"
    SUPPRESSION_REMOVED = "suppress_removed"
    PASSWORD_CHANGED = "password_changed"
    KIND_CHOICES = [
        (SIGN_IN, "Signed in"), (SIGN_IN_FAILED, "Sign-in failed"), (UNLOCK, "Unlocked"), (UNLOCK_FAILED, "Unlock failed"),
        (UNLOCK_RATE_LIMITED, "Unlock blocked (too many tries)"), (LOCK_MANUAL, "Locked"), (LOCK_IDLE, "Locked (idle)"),
        (SIGN_OUT, "Signed out"), (SESSION_EXPIRED, "Sign-in expired"), (ACCESS_DENIED, "Access refused"),
        (ROLE_CHANGED, "Roles changed"), (USER_DEACTIVATED, "Account deactivated"), (USER_REACTIVATED, "Account reactivated"),
        (UNDO, "Undo"), (UNDO_ALL, "Undo all"), (EXPORT, "Export"), (AUDIT_PRUNED, "Old log removed"), (AUDIT_CHECK, "Chain checked"), (JOB_RUN, "Job run now"),
        (SUPPRESSION_REMOVED, "Email suppression removed"), (PASSWORD_CHANGED, "Password changed"),
    ]
    OK, FAILED, BLOCKED = "ok", "failed", "blocked"
    OUTCOME_CHOICES = [(OK, "OK"), (FAILED, "Failed"), (BLOCKED, "Blocked")]

    kind = models.CharField(max_length=20, choices=KIND_CHOICES, db_index=True)
    outcome = models.CharField(max_length=10, choices=OUTCOME_CHOICES, default=OK)
    section = models.CharField(max_length=20, blank=True, db_index=True, help_text="security, team, or the section an undo touched.")
    sentence = models.TextField(blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    user_label = models.CharField(max_length=254, blank=True, help_text="The person's email (for a failed sign-in: the email that was typed).")
    ip_address = models.CharField(max_length=45, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    path = models.CharField(max_length=200, blank=True)
    batch_id = models.UUIDField(null=True, blank=True, help_text="The request id: shared with the changes saved by the same request.")
    detail = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["-created_at"]), models.Index(fields=["kind", "ip_address", "-created_at"])]

    def __str__(self):
        return self.sentence or self.get_kind_display()

    def hash_payload(self):
        return {"t": "event", "created_at": self.created_at, "kind": self.kind, "outcome": self.outcome, "section": self.section,
                "sentence": self.sentence, "user_label": self.user_label, "ip": self.ip_address, "ua": self.user_agent,
                "path": self.path, "batch_id": self.batch_id, "detail": self.detail}
