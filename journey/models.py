"""The guided journey: anonymous sessions, questions as data, answers saved as they happen,
and the rules that turn answers into a suggested plan. See docs/features/journey.md."""
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from common.models import BaseModel


def new_session_key():
    return secrets.token_urlsafe(32)


class JourneySession(BaseModel):
    """One visitor's run through the journey, tied to a first-party cookie (no personal data until sign-up)."""

    key = models.CharField(max_length=64, unique=True, default=new_session_key, editable=False,
                           help_text="Value of the first-party cookie. A secret: never shown in Control.")
    person_key = models.CharField(max_length=64, blank=True, db_index=True, editable=False,
                                  help_text="Who this is, anonymously: the first session's key, carried over when the browser restarts. "
                                            "Office counting rules C1.")
    last_seen_at = models.DateTimeField(default=timezone.now)  # updated with queryset.update (no history row)
    visit_count = models.PositiveIntegerField(default=1, help_text="Returns after 30 minutes away count as a new visit.")
    device_type = models.CharField(max_length=10, blank=True)
    is_bot = models.BooleanField(default=False, help_text="Excluded from statistics.")
    referrer = models.CharField(max_length=500, blank=True)
    utm_source = models.CharField(max_length=100, blank=True)
    utm_medium = models.CharField(max_length=100, blank=True)
    utm_campaign = models.CharField(max_length=100, blank=True)
    utm_term = models.CharField(max_length=100, blank=True)
    utm_content = models.CharField(max_length=100, blank=True)

    current_step = models.PositiveSmallIntegerField(default=1, help_text="Screen number; one past the last screen is the result.")
    furthest_step = models.PositiveSmallIntegerField(default=1)
    completed = models.BooleanField(default=False, help_text="Reached the result.")
    completed_at = models.DateTimeField(null=True, blank=True)

    # A Gold application points back at the session (GoldApplication.journey_session); see session.gold_applications.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="journey_sessions"
    )
    suggested_plan = models.ForeignKey("plans.Plan", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    suggestion_detail = models.JSONField(default=dict, blank=True, help_text="Points per plan and the reasons shown.")
    gold_potential = models.CharField(max_length=6, blank=True)
    gold_score = models.SmallIntegerField(null=True, blank=True)

    history = HistoricalRecords(excluded_fields=["last_seen_at"])

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["-created_at"]), models.Index(fields=["is_bot", "created_at"])]

    def __str__(self):
        return f"Journey {str(self.id)[:8]} step {self.current_step}"


class Question(BaseModel):
    SINGLE = "single"
    MULTI = "multi"
    SCALE = "scale"
    TEXT = "text"
    TYPE_CHOICES = [
        (SINGLE, "Single choice (tiles)"),
        (MULTI, "Multiple choice (tiles)"),
        (SCALE, "Scale (segmented control or slider, ordered options)"),
        (TEXT, "Short text"),
    ]

    key = models.SlugField(unique=True, help_text="Stable name the engines use, e.g. time, frequency. Do not rename.")
    text = models.CharField(max_length=200)
    help_text = models.CharField(max_length=300, blank=True)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default=SINGLE)
    screen = models.PositiveSmallIntegerField(help_text="Screen number, from 1.")
    order = models.PositiveSmallIntegerField(default=0)
    min_choices = models.PositiveSmallIntegerField(
        default=0, help_text="At least this many choices are required (0 = optional, and it can be skipped). "
                             "The journey cannot move on or finish until it is met.",
    )
    active = models.BooleanField(default=True, help_text="Retire by unticking. Never delete: old answers stay readable.")
    condition = models.JSONField(
        default=dict, blank=True,
        help_text='Show only if another answer matches, e.g. {"question": "industry", "any_of": ["property"]}. '
                  "A list of these means all must match.",
    )
    version = models.PositiveSmallIntegerField(default=1)

    history = HistoricalRecords()

    class Meta:
        ordering = ["screen", "order", "key"]

    def __str__(self):
        return f"{self.key}: {self.text}"


class Option(BaseModel):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    label = models.CharField(max_length=120)
    value = models.SlugField(help_text="Stable value stored and used by rules. Do not rename.")
    order = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True)
    plan_points = models.JSONField(default=dict, blank=True, help_text='Points per plan slug, e.g. {"tier-2": 3, "tier-3": 1}.')
    gold_points = models.SmallIntegerField(default=0, help_text="Extra Gold potential points on top of the Gold rules.")
    weight = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Numeric meaning for statistics: visits a week for a frequency option.",
    )
    reason = models.CharField(max_length=120, blank=True, help_text='Shown when this answer supports the suggestion, e.g. "Evenings suit you".')

    history = HistoricalRecords()

    class Meta:
        ordering = ["question__screen", "question__order", "order", "value"]
        constraints = [models.UniqueConstraint(fields=["question", "value"], name="journey_option_unique_value")]

    def __str__(self):
        return f"{self.question.key}={self.value}"


class Answer(BaseModel):
    """The current answer to one question in one session. Changing it updates this row; history keeps the old ones."""

    session = models.ForeignKey(JourneySession, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="answers")
    options = models.ManyToManyField(Option, blank=True, related_name="answers")
    text_value = models.CharField(max_length=500, blank=True)
    skipped = models.BooleanField(default=False)
    answered_at = models.DateTimeField(default=timezone.now)

    history = HistoricalRecords(m2m_fields=[options])

    class Meta:
        ordering = ["answered_at"]
        constraints = [models.UniqueConstraint(fields=["session", "question"], name="journey_one_answer_per_question")]

    def __str__(self):
        return f"{self.session_id} {self.question.key}"

    def values(self):
        return [o.value for o in self.options.all()]


class SuggestionRule(BaseModel):
    """Constraints and the tie-break that sit on top of option points. Editable in Control."""

    EXCLUDE = "exclude"
    ADD_POINTS = "add_points"
    TIE_BREAK = "tie_break"
    KIND_CHOICES = [
        (EXCLUDE, "Exclude plans when the conditions match"),
        (ADD_POINTS, "Add points to plans when the conditions match"),
        (TIE_BREAK, "Tie-break: preferred plan order"),
    ]

    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=12, choices=KIND_CHOICES)
    conditions = models.JSONField(
        default=list, blank=True,
        help_text='All must match: [{"question": "time", "any_of": ["evening", "late_night"]}]. Empty = always.',
    )
    plan_slugs = models.JSONField(default=list, blank=True, help_text="Plans affected. For a tie-break: most preferred first.")
    target_daytime_only = models.BooleanField(default=False, help_text="Also affects every plan that is daytime only.")
    points = models.SmallIntegerField(default=0, help_text="For add-points rules.")
    reason = models.CharField(max_length=120, blank=True)
    active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    history = HistoricalRecords()

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name
