"""System: developers-only business rules. The audit log lives here: SystemChange (what changed) and SystemEvent
(security events). Both are append-only and hash-chained (system/audit.py): each row carries `seq` (one running number
across both tables), `prev_hash` and `hash`."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
import logging

from django.db import DatabaseError, models, transaction
from datetime import timedelta

from django.utils import timezone

from simple_history.models import HistoricalRecords

from common.models import TimeStampedModel, UUIDModel


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
    UNDO_CODE_FAILED, UNDO_RATE_LIMITED = "undo_code_failed", "undo_rate_limited"  # the System code asked to undo a script's change
    CODE_EDIT = "code_edit"
    MAILING_SCHEDULED, MAILING_SENT, MAILING_CANCELLED = "mailing_scheduled", "mailing_sent", "mailing_cancelled"
    INVITES_SENT, EMAIL_TEST = "invites_sent", "email_test"
    TEMPLATE_SAVED, TEMPLATE_RENAMED, TEMPLATE_DELETED = "tpl_saved", "tpl_renamed", "tpl_deleted"
    PAYMENTS_OPENED, PAYMENTS_SCHEDULED, PAYMENTS_CLOSED = "payments_opened", "payments_scheduled", "payments_closed"
    PAYMENTS_CANCELLED, SETUP_MANUAL, SETUP_CANCELLED = "payments_cancelled", "setup_manual", "setup_cancelled"
    SALE_RESTORED, SETUP_EDITED = "sale_restored", "setup_edited"
    KIND_CHOICES = [
        (SIGN_IN, "Signed in"), (SIGN_IN_FAILED, "Sign-in failed"), (UNLOCK, "Unlocked"), (UNLOCK_FAILED, "Unlock failed"),
        (UNLOCK_RATE_LIMITED, "Unlock blocked (too many tries)"), (LOCK_MANUAL, "Locked"), (LOCK_IDLE, "Locked (idle)"),
        (SIGN_OUT, "Signed out"), (SESSION_EXPIRED, "Sign-in expired"), (ACCESS_DENIED, "Access refused"),
        (ROLE_CHANGED, "Roles changed"), (USER_DEACTIVATED, "Account deactivated"), (USER_REACTIVATED, "Account reactivated"),
        (UNDO, "Undo"), (UNDO_ALL, "Undo all"), (EXPORT, "Export"), (AUDIT_PRUNED, "Old log removed"), (AUDIT_CHECK, "Chain checked"), (JOB_RUN, "Job run now"),
        (SUPPRESSION_REMOVED, "Email suppression removed"), (PASSWORD_CHANGED, "Password changed"),
        (UNDO_CODE_FAILED, "Undo code wrong"), (UNDO_RATE_LIMITED, "Undo blocked (too many tries)"),
        (CODE_EDIT, "Edited as code"), (MAILING_SCHEDULED, "Mailing scheduled"), (MAILING_SENT, "Mailing sent"),
        (MAILING_CANCELLED, "Mailing cancelled"), (INVITES_SENT, "Invites sent"), (EMAIL_TEST, "Test email sent"),
        (TEMPLATE_SAVED, "Email template saved"), (TEMPLATE_RENAMED, "Email template renamed"), (TEMPLATE_DELETED, "Email template deleted"),
        (PAYMENTS_OPENED, "Payments opened"), (PAYMENTS_SCHEDULED, "Payments scheduled"), (PAYMENTS_CLOSED, "Payments closed"),
        (PAYMENTS_CANCELLED, "Payments schedule cancelled"), (SETUP_MANUAL, "Membership set up manually"), (SETUP_CANCELLED, "Manual membership cancelled"),
        (SALE_RESTORED, "Sale price restored"), (SETUP_EDITED, "Manual membership edited"),
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


# ---------- Defaults (System > Defaults) ----------

_warned = []  # logged once per process


def validate_staff_alert_emails(value):
    """Up to 5 valid addresses, comma separated (blank is allowed: no alert email)."""
    from common.validators import split_emails, validate_email_list

    validate_email_list(value)
    if len(split_emails(value)) > 5:
        raise ValidationError("Enter at most 5 addresses.")


def _number(label, default, low, high, help_text=""):
    return models.PositiveSmallIntegerField(label, default=default, validators=[MinValueValidator(low), MaxValueValidator(high)], help_text=help_text)


class SiteDefaults(UUIDModel, TimeStampedModel):
    """The editable defaults of the site (singleton, `SiteDefaults.load()`; system/defaults.py reads it). A separate model from
    plans.SiteSettings on purpose: Settings stays the small page of switches, and this one is plain numbers and pre-selected
    choices that the Office, journey and emails read. Every default is today's value in code (CODE_DEFAULTS is the hint shown on the
    page and what "Reset to default" restores). The row is created on first read, never by a migration.
    Choices (ranges, show, sort) are checked in clean() against the constants of the pages that own them (imported lazily so this
    model never imports the Office)."""

    GOLD_NUDGES = [("panel", "Panel"), ("line", "One line"), ("none", "Nothing")]

    singleton_key = models.CharField(max_length=10, default="site", unique=True, editable=False)

    # Office
    leads_range = models.CharField("Leads: last seen range", max_length=5, default="30d")
    leads_show = models.CharField("Leads: show", max_length=12, default="all")
    leads_sort = models.CharField("Leads: sort", max_length=12, default="last_seen")
    leads_page_size = _number("Leads: rows per page", 25, 5, 200)
    list_page_size = _number("People and Gold lists: rows per page", 50, 5, 200)
    dashboard_range = models.CharField("Dashboard: default range", max_length=5, default="7d")
    analytics_range = models.CharField("Analytics: default range", max_length=5, default="30d")
    dashboard_hot_leads = _number("Dashboard: hot leads shown", 5, 1, 50)
    dashboard_activity = _number("Dashboard: activity shown", 10, 1, 50)
    dashboard_gold_waiting = _number("Dashboard: Gold waiting shown", 5, 1, 50)
    dashboard_latest = _number("Dashboard: latest registrations shown", 5, 1, 50)
    analytics_options = _number("Analytics: options shown per question", 6, 1, 12, "Takes effect at the next Analytics refresh.")
    top_pages = _number("Top pages shown", 10, 1, 50, "Takes effect at the next Analytics refresh.")
    timeline_page_size = _number("Person page: timeline events per page", 20, 5, 100)
    person_emails_shown = _number("Person page: emails shown", 50, 1, 200)

    # Website and journey
    result_reasons = _number("Result: reasons shown", 3, 1, 6)
    gold_nudge_high = models.CharField("Gold nudge: High potential", max_length=5, choices=GOLD_NUDGES, default="panel")
    gold_nudge_medium = models.CharField("Gold nudge: Medium potential", max_length=5, choices=GOLD_NUDGES, default="line")
    gold_nudge_low = models.CharField("Gold nudge: Low potential", max_length=5, choices=GOLD_NUDGES, default="none")
    opener_lines = _number("Home opener: lines shown", 1, 1, 5)
    chat_monthly_cap_gbp = _number("Ask us chat: monthly spending cap (£)", 25, 1, 1000,
                                   "At the cap the chat shows only the hand-off buttons until the next month. Takes effect at once.")

    # Gold
    gold_invite_days = _number("Gold invite link valid (days)", 14, 1, 90, "A new value applies to links made from now on; links already sent keep the date they were given.")
    gold_approval_days = _number("Approve / final approval email link valid (days)", 14, 1, 90, "These links carry no stored date, so a new value applies to links already sent too.")

    # Emails
    register_invite_days = _number("Register invite link valid (days)", 30, 1, 365, "A new value applies to invites made from now on; invites already sent keep their date.")
    recent_mailings = _number("Recent mailings shown", 5, 1, 50)
    recent_batches = _number("Recent invite batches shown", 5, 1, 50)

    # Sign-in
    office_session_days = _number("Office sign-in lasts (days)", 30, 1, 30, "Applies to sign-ins from now on. At most 30: the privacy notice says team sign-ins last up to 30 days.")
    email_confirm_hours = _number("Email confirmation link valid (hours)", 24, 1, 168, "Applies to links already sent too. The wording of the confirmation email is edited in Emails.")

    # System
    changelog_page_size = _number("Change log rows per page", 50, 10, 200)
    audit_page_size = _number("Audit feed rows per page", 25, 5, 100)
    dashboard_recent_changes = _number("Dashboard recent changes", 10, 1, 50)

    # Payments
    payment_window_days = _number("Payment window (days)", 14, 3, 60, "How long members have to set up their membership once payments open. Applies to windows opened from now on.")
    payment_reminder_days_before = _number("Payment reminder: days before it closes", 3, 1, 30, "One gentle reminder email to members who have not set up yet.")
    payment_staff_alert_days_before = _number("Staff warning: days before it closes", 7, 1, 60, "From then until it closes, staff are warned once a day about launch-price holders who have not set up.")

    staff_alert_emails_on = models.BooleanField("Payment alert emails on", default=True, help_text="Untick to stop the alert emails without clearing the addresses. The notice in the Office and System still shows.")
    staff_alert_seeded = models.BooleanField(default=False, editable=False)
    staff_alert_emails = models.CharField(
        "Payment alert emails", max_length=500, blank=True, default="", validators=[validate_staff_alert_emails],
        help_text="Where the warning about launch-price holders who have not set up is emailed. Up to 5 addresses, separated by commas. Empty: no email is sent (the notice still shows in the Office and System).")

    # Notifications
    toast_seconds = _number("On-screen notification stays (seconds)", 4, 2, 30)
    toast_long_seconds = _number("On-screen notification with a button or warning stays (seconds)", 6, 2, 60, "Errors always stay until closed.")

    history = HistoricalRecords()

    class Meta:
        verbose_name = "site defaults"
        verbose_name_plural = "site defaults"

    def __str__(self):
        return "Site defaults"

    @classmethod
    def load(cls):
        """The one row (made on first read). If the database cannot be read (table missing before migrate, a blip) it logs once and
        returns an unsaved copy with the code defaults, so a public page never answers 500 because of this."""
        try:
            obj, _ = cls.objects.get_or_create(singleton_key="site")
            return obj
        except DatabaseError:
            if not _warned:
                _warned.append(True)
                logging.getLogger("spa99.system").warning("Site defaults not readable; using the code defaults", exc_info=True)
            return cls()

    @classmethod
    def code_default(cls, name):
        return cls._meta.get_field(name).get_default()

    def clean(self):
        from office import leads, selectors

        allowed = {"leads_range": leads.RANGES, "leads_show": leads.SHOWS, "leads_sort": leads.SORTS,
                   "dashboard_range": selectors.DASHBOARD_RANGES, "analytics_range": selectors.ANALYTICS_RANGES}
        errors = {name: "Pick one of the choices." for name, choices in allowed.items() if getattr(self, name) not in choices}
        if errors:
            raise ValidationError(errors)
