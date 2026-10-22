"""Gold Card applications and the editable rules that rate them. See docs/features/gold-application.md.
Phase 1: no account is created and there is no approval flow on the site; Barry decides outside the system."""
from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords

from common.ids import generate_public_code
from common.models import BaseModel

# Answer values shared by the application form, the journey (same option values) and the rules.
PROPERTY_LINKS = [
    ("owner_investor", "Owner / investor"),
    ("developer", "Developer"),
    ("manager", "Manager (block, estate, portfolio)"),
    ("firm", "Work at a property or management firm"),
    ("agent", "Agent / broker"),
    ("property_lawyer", "Property lawyer"),
    ("none", "None of these"),
]
SIZE_RANGES = [("1_9", "1 to 9"), ("10_49", "10 to 49"), ("50_199", "50 to 199"), ("200_plus", "200 or more")]
WHERE_CHOICES = [
    ("north_london", "North London"),
    ("rest_of_london", "Rest of London"),
    ("rest_of_uk", "Rest of the UK"),
    ("abroad", "Abroad"),
]
BML_CHOICES = [("yes", "Yes"), ("not_yet", "Not yet"), ("no", "No")]


def new_reference():
    return "GC-" + generate_public_code(6)


class GoldRule(BaseModel):
    """One weight or threshold of the potential rating. Rows, so Control can change them."""

    PROPERTY_LINK = "property_link"
    SIZE = "size"
    WHERE = "where"
    BML = "bml"
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

    property_link = models.CharField(max_length=20, choices=PROPERTY_LINKS)
    size_range = models.CharField(max_length=10, choices=SIZE_RANGES, blank=True)
    location = models.CharField("where", max_length=20, choices=WHERE_CHOICES, blank=True)
    company = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=150, blank=True)
    bml_relationship = models.CharField(max_length=10, choices=BML_CHOICES, blank=True)
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
