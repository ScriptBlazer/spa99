"""Gold Card applications and the editable rules that rate them. See docs/features/gold-application.md.
Phase 1: no account is created and there is no approval flow on the site; Barry decides outside the system."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from common.ids import generate_public_code
from common.models import BaseModel, UUIDModel

# The answer choices (link to property, size, where, BML) are GoldChoice rows, the points are GoldRule rows and the
# journey questions that feed them are GoldSignalSource rows: all edited in Control.
PROPERTY_LINK = "property_link"
SIZE = "size"
WHERE = "where"
BML = "bml"
CHOICE_GROUPS = [
    (PROPERTY_LINK, "Link to property"),
    (SIZE, "Size of portfolio"),
    (WHERE, "Where"),
    (BML, "Works with BML"),
]


def new_reference():
    return "GC-" + generate_public_code(6)


class GoldChoice(BaseModel):
    """One answer on the Gold application form (and the Gold questions in the journey). Rows, so Control can change
    the wording or retire a choice. The value is stored on applications and used by GoldRule: do not rename it."""

    group = models.CharField(max_length=20, choices=CHOICE_GROUPS)
    value = models.SlugField(max_length=20, help_text="Stable value stored on applications and matched by the rating rules. Do not rename.")
    label = models.CharField(max_length=120)
    order = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True, help_text="Retire by unticking. Never delete: old applications keep their answer.")

    history = HistoricalRecords()

    class Meta:
        ordering = ["group", "order", "value"]
        constraints = [models.UniqueConstraint(fields=["group", "value"], name="gold_choice_unique")]

    def __str__(self):
        return f"{self.group}:{self.value}"


class GoldSignalSource(BaseModel):
    """Which journey answer feeds which Gold signal, so the journey result can rate Gold potential from answers
    already given. First matching row (by order) wins for each signal.

    answer_value empty: pass the chosen option through (its value must be a GoldChoice value).
    answer_value set: only when that option is chosen, and the signal becomes `sets_value`.
    """

    signal = models.CharField(max_length=20, choices=CHOICE_GROUPS)
    question_key = models.SlugField(help_text="Key of the journey question to read, e.g. property_link.")
    answer_value = models.SlugField(blank=True, help_text="Only when this option is chosen. Empty = any option, passed through.")
    sets_value = models.SlugField(max_length=20, blank=True, help_text="The Gold value this gives, e.g. property_lawyer. Empty = the option's own value.")
    order = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["signal", "order", "question_key"]

    def __str__(self):
        return f"{self.signal} from {self.question_key}"


class GoldRule(BaseModel):
    """One weight or threshold of the potential rating. Rows, so Control can change them."""

    PROPERTY_LINK = PROPERTY_LINK
    SIZE = SIZE
    WHERE = WHERE
    BML = BML
    REFERRED = "referred"
    THRESHOLD = "threshold"
    GROUP_CHOICES = [
        (PROPERTY_LINK, "Link to property"),
        (SIZE, "Size of portfolio"),
        (WHERE, "Where"),
        (BML, "Works with BML"),
        (REFERRED, "Referred by someone"),
        (THRESHOLD, "Threshold (points needed for High / Medium)"),
    ]

    group = models.CharField(max_length=20, choices=GROUP_CHOICES)
    match_value = models.CharField(
        max_length=40, help_text="The answer value this applies to. Thresholds: high or medium. Referred: yes."
    )
    label = models.CharField(max_length=120, blank=True, help_text='Plain words used in the reasons, e.g. "Owner or investor".')
    points = models.SmallIntegerField(default=0, validators=[MinValueValidator(-1000), MaxValueValidator(1000)])
    is_property = models.BooleanField(default=False, help_text="Counts as a property person (statistics, nudges).")
    active = models.BooleanField(default=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["group", "-points", "match_value"]
        constraints = [models.UniqueConstraint(fields=["group", "match_value"], name="gold_rule_unique")]

    def __str__(self):
        return f"{self.group}:{self.match_value} = {self.points}"

    def clean(self):
        """Threshold rules (forms, undo and the code view all go through full_clean): at least 1 point, and High is not
        below Medium."""
        if self.group != self.THRESHOLD:
            return
        if self.points is not None and self.points < 1:
            raise ValidationError({"points": "A threshold needs at least 1 point."})
        if self.match_value in ("high", "medium") and self.points is not None:
            other = type(self).objects.filter(group=self.THRESHOLD, match_value="medium" if self.match_value == "high" else "high").exclude(pk=self.pk).first()
            if other is not None:
                high, medium = (self.points, other.points) if self.match_value == "high" else (other.points, self.points)
                if high < medium:
                    raise ValidationError({"points": "The High threshold cannot be lower than the Medium threshold."})


class GoldApplication(BaseModel):
    NEW = "new"
    CONTACTED = "contacted"
    APPROVED = "approved"
    DECLINED = "declined"
    AWAITING_FINAL = "awaiting_final"  # a Low potential approval waiting for a final approver (docs/features/gold-final-approval.md)
    STATUS_CHOICES = [(NEW, "New"), (CONTACTED, "Contacted"), (APPROVED, "Approved"), (DECLINED, "Declined"),
                      (AWAITING_FINAL, "Awaiting final approval")]
    WAITING = (NEW, CONTACTED)  # in the approvers' queue
    NOTE_MAX = 1000

    reference = models.CharField(max_length=12, unique=True, default=new_reference, editable=False)

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(db_index=True)
    mobile = models.CharField(max_length=16, blank=True, help_text="E.164")

    industry = models.CharField(max_length=20, blank=True, help_text="First of the industries chosen (older applications: the only one). Use `industry_values` to read them all.")
    industries = models.JSONField(default=list, blank=True, help_text="Everything he does: journey `industry` option values (multi-select). Empty on older applications: they have `industry` only.")
    industry_other = models.CharField(max_length=100, blank=True, help_text="Typed when the industry is Other.")
    property_link = models.CharField(max_length=20, blank=True, help_text="Only asked when the industry is Property.")
    size_range = models.CharField(max_length=10, blank=True)
    location = models.CharField("where", max_length=20, blank=True)
    company = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=150, blank=True)
    bml_relationship = models.CharField(max_length=10, blank=True)
    referred_by = models.CharField(max_length=150, blank=True)
    note = models.TextField(blank=True)

    spa_interest = models.JSONField(default=dict, blank=True, help_text="What the journey collected, as readable text, at the time of applying.")
    journey_session = models.ForeignKey(
        "journey.JourneySession", null=True, blank=True, on_delete=models.SET_NULL, related_name="gold_applications"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="gold_applications",
        help_text="Linked automatically if the same email registers (no account is created by applying).",
    )

    potential_level = models.CharField(max_length=6, blank=True)
    potential_score = models.SmallIntegerField(null=True, blank=True)
    potential_reasons = models.JSONField(default=list, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=NEW, db_index=True)
    internal_notes = models.TextField(blank=True)
    repeat_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="repeats")

    email_sent_at = models.DateTimeField(null=True, blank=True, help_text="Empty = the email to Barry has not gone out.")
    email_error = models.CharField(max_length=300, blank=True)

    marketing_consent = models.BooleanField(default=False)
    privacy_accepted_version = models.CharField(max_length=20, blank=True)
    privacy_accepted_at = models.DateTimeField(null=True, blank=True)

    approved_at = models.DateTimeField(
        null=True, blank=True, help_text="When Gold was approved. Gold's month starts here (LC-27). Set by 'Approve and invite'.")
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False)

    # Final approval (Low potential only). Every step is also a history row (who, when, the note).
    final_requested_at = models.DateTimeField(null=True, blank=True, help_text="When an approver sent it for final approval.")
    final_requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False)
    final_previous_status = models.CharField(max_length=20, blank=True, editable=False, help_text="The status before it went to final approval; a send-back restores it.")
    sent_back_at = models.DateTimeField(
        null=True, blank=True, help_text="When a final approver sent it back. Once set, the next approval goes through at once.")
    sent_back_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False)
    sent_back_note = models.CharField(max_length=NOTE_MAX, blank=True, help_text="The final approver's optional note.")

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} {self.first_name} {self.last_name}"

    @property
    def final_review_done(self):
        """True once a final approver has looked at it and sent it back: the next approval is not reviewed again."""
        return self.sent_back_at is not None

    @property
    def industry_values(self):
        """Every industry chosen, in order. Older applications (before multi-select) only have `industry`."""
        return list(self.industries or ([self.industry] if self.industry else []))

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_repeat(self):
        return self.repeat_of_id is not None


class GoldInvite(BaseModel):
    """One invite to set up an account after approval (docs/features/gold-application.md). The link carries a signed
    copy of this row's id; the row decides whether it still works (not expired, not used, not replaced by a resend).
    No history table: the row holds no personal data and is itself the record. Erased with the application."""

    application = models.ForeignKey(GoldApplication, on_delete=models.CASCADE, related_name="invites")
    expires_at = models.DateTimeField()
    sent_at = models.DateTimeField(null=True, blank=True, help_text="Empty = the email has not gone out.")
    used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True, help_text="Set when a newer invite replaces this one.")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"invite for {self.application_id}"

    @property
    def is_usable(self):
        from django.utils import timezone

        return self.used_at is None and self.revoked_at is None and self.expires_at > timezone.now()


class ApproverDelivery(BaseModel):
    """Where one person's approval emails go (System > Approval). They apply to both roles a person holds (Approver and
    Final approver). No row = their account email. Lives in `gold` because the Gold emails read it; the roles themselves
    are the Approver and Final approver groups (common.levels). Erased with the account."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="approver_delivery")
    use_account_email = models.BooleanField(default=True, help_text="Send to the account email. Untick to use the other address.")
    other_email = models.EmailField(blank=True, help_text="Used only when the account email box is unticked.")

    # No history table: the address is personal data and the change is already in the System audit log.

    def __str__(self):
        return f"approval emails for {self.user_id}"

    def clean(self):
        if not self.use_account_email and not self.other_email:
            raise ValidationError({"other_email": "Enter the other address, or send to the account email."})

    @property
    def address(self):
        return self.user.email if self.use_account_email or not self.other_email else self.other_email


class AppendOnlyError(Exception):
    """An audit row was asked to change or go."""


class EventQuerySet(models.QuerySet):
    """Bulk edits and deletes are refused too. (An application being erased still removes its events: Django's cascade
    does not go through these methods.)"""

    def update(self, **kwargs):
        raise AppendOnlyError("The Gold audit trail cannot be edited.")

    def delete(self):
        raise AppendOnlyError("The Gold audit trail cannot be deleted.")

    def bulk_update(self, *args, **kwargs):
        raise AppendOnlyError("The Gold audit trail cannot be edited.")


class ApplicationEvent(UUIDModel):
    """One step in the life of a Gold application: who did what, when, through which door, the status change and the text
    (reason, message or note). Append-only (docs/features/gold-actions.md). Written only by gold.audit.record, inside the
    same transaction as the change. Erased with the application (UK GDPR): the text can hold personal details."""

    SUBMITTED, APPROVED, SENT_FOR_FINAL, FINAL_CONFIRMED, SENT_BACK = "submitted", "approved", "sent_for_final", "final_confirmed", "sent_back"
    DECLINED, RESPONDED, NOTE_ADDED = "declined", "responded", "note_added"
    INVITE_SENT, INVITE_RESENT, EMAIL_SENT, EMAIL_FAILED, STATUS_CHANGED_ADMIN = "invite_sent", "invite_resent", "email_sent", "email_failed", "status_changed_admin"
    ACTION_CHOICES = [
        (SUBMITTED, "Applied"), (APPROVED, "Approved"), (SENT_FOR_FINAL, "Sent for final approval"),
        (FINAL_CONFIRMED, "Final approval confirmed"), (SENT_BACK, "Sent back for review"), (DECLINED, "Declined"),
        (RESPONDED, "Responded to the applicant"), (NOTE_ADDED, "Note added"), (INVITE_SENT, "Invite emailed"),
        (INVITE_RESENT, "New invite requested"), (EMAIL_SENT, "Email sent"), (EMAIL_FAILED, "Email failed"),
        (STATUS_CHANGED_ADMIN, "Status changed in the admin"),
    ]
    OFFICE, EMAIL_LINK, ADMIN, SYSTEM, SHELL = "office", "email_link", "admin", "system", "shell"
    CHANNEL_CHOICES = [(OFFICE, "Office"), (EMAIL_LINK, "Email link"), (ADMIN, "Django admin"), (SYSTEM, "System"), (SHELL, "Command line")]

    application = models.ForeignKey(GoldApplication, on_delete=models.CASCADE, related_name="events")
    at = models.DateTimeField(default=timezone.now, db_index=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                              help_text="Empty = the system or the applicant.")
    actor_label = models.CharField(max_length=254, blank=True, help_text="Name and email when it happened (kept if the account goes).")
    action = models.CharField(max_length=24, choices=ACTION_CHOICES, db_index=True)
    channel = models.CharField(max_length=12, choices=CHANNEL_CHOICES, default=SYSTEM)
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20, blank=True)
    message = models.TextField(blank=True, help_text="The reason, message or note.")
    meta = models.JSONField(default=dict, blank=True, help_text="Recipient, template, error, result.")

    objects = EventQuerySet.as_manager()

    class Meta:
        ordering = ["-at", "-id"]
        indexes = [models.Index(fields=["application", "-at"])]

    def __str__(self):
        return f"{self.action} on {self.application_id} at {self.at:%Y-%m-%d %H:%M}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AppendOnlyError("The Gold audit trail cannot be edited.")
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyError("The Gold audit trail cannot be deleted.")
