"""Gold Card applications and the editable rules that rate them. See docs/features/gold-application.md.
Phase 1: no account is created and there is no approval flow on the site; Barry decides outside the system."""
from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords

from common.ids import generate_public_code
from common.models import BaseModel

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
    points = models.SmallIntegerField(default=0)
    is_property = models.BooleanField(default=False, help_text="Counts as a property person (statistics, nudges).")
    active = models.BooleanField(default=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["group", "-points", "match_value"]
        constraints = [models.UniqueConstraint(fields=["group", "match_value"], name="gold_rule_unique")]

    def __str__(self):
        return f"{self.group}:{self.match_value} = {self.points}"


class GoldApplication(BaseModel):
    NEW = "new"
    CONTACTED = "contacted"
    APPROVED = "approved"
    DECLINED = "declined"
    STATUS_CHOICES = [(NEW, "New"), (CONTACTED, "Contacted"), (APPROVED, "Approved"), (DECLINED, "Declined")]

    reference = models.CharField(max_length=12, unique=True, default=new_reference, editable=False)

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(db_index=True)
    mobile = models.CharField(max_length=16, blank=True, help_text="E.164")

    industry = models.CharField(max_length=20, blank=True, help_text="What he does: a journey `industry` option value.")
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

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=NEW, db_index=True)
    internal_notes = models.TextField(blank=True)
    repeat_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="repeats")

    email_sent_at = models.DateTimeField(null=True, blank=True, help_text="Empty = the email to Barry has not gone out.")
    email_error = models.CharField(max_length=300, blank=True)

    marketing_consent = models.BooleanField(default=False)
    privacy_accepted_version = models.CharField(max_length=20, blank=True)
    privacy_accepted_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} {self.first_name} {self.last_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_repeat(self):
        return self.repeat_of_id is not None
