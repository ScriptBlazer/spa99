"""Plans, site settings, opening hours and facilities. Everything here is data edited in Spa 99 Control.
Nothing in this file is a rule: values come from rows (see docs/SPA99_RULES.md "Rules will change")."""
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from simple_history.models import HistoricalRecords

from common.models import BaseModel


class Plan(BaseModel):
    """One purchasable or applied-for plan: Tier 1/2/3, Gold Card or the single visit. Plans are rows, not code."""

    MONTHLY = "monthly"
    FREE_BY_APPLICATION = "free_by_application"
    ONE_OFF = "one_off"
    KIND_CHOICES = [
        (MONTHLY, "Monthly membership"),
        (FREE_BY_APPLICATION, "Free, by application"),
        (ONE_OFF, "One-off purchase"),
    ]
    DAYTIME_ONLY = "daytime"
    ANY_TIME = "any"
    HOURS_CHOICES = [(DAYTIME_ONLY, "Daytime only"), (ANY_TIME, "Any time")]

    slug = models.SlugField(unique=True, help_text="Stable key used by the journey and rules, e.g. tier-2. Do not rename.")
    name = models.CharField(max_length=60)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=MONTHLY)
    price_ex_vat = models.DecimalField(
        "price ex VAT", max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("0"))],
        help_text="Per month for memberships, per visit for the single visit. VAT is added from Site settings.",
    )
    visits_per_month = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Empty means unlimited.")
    hours = models.CharField(max_length=10, choices=HOURS_CHOICES, default=ANY_TIME)
    booking_window_days = models.PositiveSmallIntegerField(default=1, help_text="Spa days ahead: 3 means today + 3.")
    upcoming_limit = models.PositiveSmallIntegerField(default=1, help_text="Upcoming bookings at once.")
    cancel_hours = models.PositiveSmallIntegerField(default=10, help_text="Cancel up to this many hours before the slot.")
    guests_per_month = models.PositiveSmallIntegerField(default=0)
    no_show_result = models.CharField(max_length=160, blank=True, help_text="Plain words, shown to staff.")
    perks = models.JSONField(
        default=list, blank=True,
        help_text='List of {"key": "merch", "label": "Merch", "value": "Buy"}. Flexible: add any perk.',
    )
    short_description = models.CharField(max_length=200, blank=True)
    highlight = models.BooleanField(default=False, help_text="Shown as the recommended plan (Tier 2).")
    order = models.PositiveSmallIntegerField(default=0)
    visible = models.BooleanField("visible on site", default=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["order", "price_ex_vat"]

    def __str__(self):
        return self.name

    @property
    def is_daytime_only(self):
        return self.hours == self.DAYTIME_ONLY

    @property
    def is_unlimited(self):
        return self.visits_per_month is None

    def perk(self, key):
        """The value of one perk, or None."""
        for item in self.perks or []:
            if item.get("key") == key:
                return item.get("value")
        return None


class SiteSettings(BaseModel):
    """One row for the whole site (singleton). Use SiteSettings.load()."""

    INTEREST = "register_interest"
    JOIN = "join"
    WORDING_CHOICES = [(INTEREST, "Register interest"), (JOIN, "Join")]

    singleton_key = models.CharField(max_length=10, default="site", unique=True, editable=False)
    vat_rate = models.DecimalField("VAT rate (%)", max_digits=5, decimal_places=2, default=Decimal("20.00"))
    capacity = models.PositiveSmallIntegerField(default=25, help_text="Places in the spa at once (BK-03).")
    slot_length_minutes = models.PositiveSmallIntegerField(default=120)
    slot_step_minutes = models.PositiveSmallIntegerField(default=30)
    booking_notice_minutes = models.PositiveSmallIntegerField(default=10)
    opening_date = models.DateField(null=True, blank=True, help_text="Leave empty until fixed.")

    register_interest_open = models.BooleanField(default=True, help_text="Stage A: accounts and Gold applications.")
    subscribe_open = models.BooleanField(default=False, help_text="Stage B: checkout (Phase 2).")
    booking_open = models.BooleanField(default=False, help_text="Stage C: bookings (Phase 3).")
    join_wording = models.CharField(
        "wording", max_length=20, choices=WORDING_CHOICES, default=INTEREST,
        help_text='"Register interest" now; "Join" when payments open.',
    )

    contact_email = models.EmailField(default="hello@spa99.uk")
    gold_alert_to = models.CharField(
        max_length=300, default="barry@bmlgroup.co.uk", help_text="Comma separated addresses."
    )
    gold_alert_cc = models.CharField(
        max_length=300, blank=True, default="moishe.berkowitz@bmlgroup.co.uk", help_text="Comma separated addresses."
    )
    privacy_version = models.CharField(
        max_length=20, default="draft-1", help_text="Recorded on each person who accepts the privacy notice."
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "site settings"
        verbose_name_plural = "site settings"

    def __str__(self):
        return "Site settings"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(singleton_key="site")
        return obj

    @staticmethod
    def _split(value):
        return [part.strip() for part in (value or "").split(",") if part.strip()]

    @property
    def gold_alert_to_list(self):
        return self._split(self.gold_alert_to)

    @property
    def gold_alert_cc_list(self):
        return self._split(self.gold_alert_cc)

    @property
    def wording(self):
        return self.get_join_wording_display()


class OpeningRule(BaseModel):
    """Data for the opening hours (SPA99_RULES section 03). Used by the site now, by bookings later.
    Times are Europe/London wall-clock times. Shabbos/Yom Tov times come from candle-lighting data in
    Phase 3 (Hebcal sync); here only the offsets are stored."""

    PERIOD = "period"
    DAILY_CLOSURE = "daily_closure"
    CLOSE_BEFORE_CANDLES = "close_before_candles"
    OPEN_AFTER_NIGHTFALL = "open_after_end"
    KIND_CHOICES = [
        (PERIOD, "Open period (daytime, evening)"),
        (DAILY_CLOSURE, "Closed every day"),
        (CLOSE_BEFORE_CANDLES, "Close before candle lighting (Friday, Yom Tov)"),
        (OPEN_AFTER_NIGHTFALL, "Open after Shabbos / Yom Tov ends"),
    ]

    key = models.SlugField(unique=True)
    label = models.CharField(max_length=80)
    kind = models.CharField(max_length=24, choices=KIND_CHOICES)
    start_time = models.TimeField(null=True, blank=True, help_text="Periods and daily closure. May run past midnight.")
    end_time = models.TimeField(null=True, blank=True)
    offset_minutes = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Shabbos / Yom Tov rules only.")
    active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    history = HistoricalRecords()

    class Meta:
        ordering = ["order", "key"]

    def __str__(self):
        return self.label


class Closure(BaseModel):
    """A one-off closure (maintenance, private hire, a Yom Tov that needs listing by hand)."""

    name = models.CharField(max_length=120)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    public_note = models.CharField(max_length=200, blank=True)
    active = models.BooleanField(default=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["starts_at"]

    def __str__(self):
        return self.name


def facility_image_path(instance, filename):
    return f"facilities/{instance.slug}/{filename}"


class Facility(BaseModel):
    name = models.CharField(max_length=80)
    slug = models.SlugField(unique=True)
    short_line = models.CharField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    image = models.FileField(upload_to=facility_image_path, blank=True)  # default storage: S3 on live
    order = models.PositiveSmallIntegerField(default=0)
    visible = models.BooleanField(default=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["order", "name"]
        verbose_name_plural = "facilities"

    def __str__(self):
        return self.name
