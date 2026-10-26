"""Plans, site settings, opening hours and facilities. Everything here is data edited in Spa 99 Control.
Nothing in this file is a rule: values come from rows (see docs/SPA99_RULES.md "Rules will change")."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, URLValidator
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from common.models import BaseModel
from common.validators import split_emails, validate_email_list


def plan_image_path(instance, filename):
    return f"plans/{instance.slug}/{filename}"


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
    visits_per_month = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MaxValueValidator(100)], help_text="Empty means unlimited.")
    hours = models.CharField(max_length=10, choices=HOURS_CHOICES, default=ANY_TIME)
    booking_window_days = models.PositiveSmallIntegerField(default=1, validators=[MaxValueValidator(365)], help_text="Spa days ahead: 3 means today + 3.")
    upcoming_limit = models.PositiveSmallIntegerField(default=1, validators=[MaxValueValidator(50)], help_text="Upcoming bookings at once.")
    cancel_hours = models.PositiveSmallIntegerField(default=10, validators=[MaxValueValidator(720)], help_text="Cancel up to this many hours before the slot.")
    guests_per_month = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(50)])
    no_show_result = models.CharField(max_length=160, blank=True, help_text="Plain words, shown to staff.")
    perks = models.JSONField(
        default=list, blank=True,
        help_text='List of {"key": "merch", "label": "Merch", "value": "Buy", "phrase": "Each merch release"}. '
                  'Flexible: add any perk. "phrase" is the short line on the Gold Card page (empty = the label). '
                  '"pill" is the short chip on the memberships page (empty = no chip).',
    )
    short_description = models.CharField(max_length=200, blank=True)
    tagline = models.CharField(
        max_length=80, blank=True, help_text="One calm line under the name. Empty = Daytime / Any time / Unlimited.")
    image = models.FileField(
        upload_to=plan_image_path, blank=True, help_text="Picture on the memberships page. Wins over the render.")  # default storage: S3 on live
    render = models.CharField(
        max_length=40, blank=True,
        help_text="Name of a built render (content image manifest), used when no picture is uploaded.")
    image_alt = models.CharField(max_length=200, blank=True, help_text="Describes the picture. Empty = decorative.")
    highlight = models.BooleanField(default=False, help_text="Shown as the recommended plan (Tier 2).")
    order = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(1000)])
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
    def interest_allowed(self):
        """Can a person register interest in this plan? Visible monthly memberships only (not Gold, which is by
        application, and not the single visit). Templates use this to hide the 'Register' action."""
        return self.visible and self.kind == self.MONTHLY

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
    WORDING_CHOICES = [(INTEREST, "Register"), (JOIN, "Join")]

    singleton_key = models.CharField(max_length=10, default="site", unique=True, editable=False)
    vat_rate = models.DecimalField(
        "VAT rate (%)", max_digits=5, decimal_places=2, default=Decimal("20.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))])
    capacity = models.PositiveSmallIntegerField(default=25, validators=[MinValueValidator(1), MaxValueValidator(500)], help_text="Places in the spa at once (BK-03).")
    slot_length_minutes = models.PositiveSmallIntegerField(default=120, validators=[MinValueValidator(1), MaxValueValidator(1440)])
    slot_step_minutes = models.PositiveSmallIntegerField(default=30, validators=[MinValueValidator(1), MaxValueValidator(1440)])
    booking_notice_minutes = models.PositiveSmallIntegerField(default=10, validators=[MaxValueValidator(1440)])
    opening_date = models.DateField(null=True, blank=True, help_text="Leave empty until fixed.")
    opening_text = models.CharField(
        max_length=60, default="January 2027", blank=True,
        help_text='Shown as the opening time while the opening date is empty, e.g. "January 2027". Used by the {opening} placeholder in site copy.',
    )
    address_street = models.CharField(max_length=120, default="99 Vale Road")
    address_town = models.CharField(max_length=80, default="London")
    address_postcode = models.CharField(max_length=12, default="N4 1PR")

    register_interest_open = models.BooleanField(default=True, help_text="Stage A: accounts and Gold applications.")
    subscribe_open = models.BooleanField(default=False, help_text="Stage B: checkout (Phase 2).")
    booking_open = models.BooleanField(default=False, help_text="Stage C: bookings (Phase 3).")
    notify_booking_open = models.BooleanField(
        default=False, help_text='Turn on only once we really send the "booking is open" email. Changes the line on Book a visit.')
    join_wording = models.CharField(
        "wording", max_length=20, choices=WORDING_CHOICES, default=INTEREST,
        help_text='"Register" now; "Join" when payments open.',
    )

    # Recipients: edited by developers in System > Emails (never in env, never hard-coded). Blank = nothing is sent / the
    # From address is used.
    gold_approver_emails = models.CharField(
        max_length=500, blank=True, validators=[validate_email_list],
        help_text="DEPRECATED, no longer used for sending: approvers are the team members picked in System > Approval. Kept until the old addresses are imported (manage.py import_approvers_from_emails).")
    gold_approver_cc = models.CharField(
        max_length=500, blank=True, validators=[validate_email_list], help_text="Comma separated. Copied on each Gold application email.")
    contact_email = models.CharField(
        max_length=254, blank=True, validators=[validate_email_list],
        help_text="Shown on the site and used as Reply-To. Empty = the address inside DEFAULT_FROM_EMAIL.")

    privacy_version = models.CharField(
        max_length=20, default="2026-10-23",
        help_text="Recorded on each person who accepts the privacy notice. Change it (and the notice's Last updated row) "
                  "whenever the notice changes in a way people should accept again."
    )

    # System security (edited in System > Settings > Security; the settings constants are only the fallback defaults).
    lock_idle_minutes = models.PositiveSmallIntegerField(
        "Lock after idle minutes", default=15, validators=[MinValueValidator(1), MaxValueValidator(240)],
        help_text="System asks for the password again after this many minutes without activity (1 to 240).")
    max_sign_in_hours = models.PositiveSmallIntegerField(
        "Longest sign-in (hours)", default=12, validators=[MinValueValidator(1), MaxValueValidator(72)],
        help_text="A System sign-in ends after this many hours, however active the person is (1 to 72).")

    code_theme_default = models.CharField(
        "Code view theme", max_length=5, choices=[("dark", "Dark"), ("light", "Light")], default="dark",
        help_text="The look of the System code view for people who have not picked their own (the toggle in the code view remembers their choice).")

    discount_contact_url = models.URLField(
        "Discount contact link (WhatsApp)", max_length=300, blank=True, validators=[URLValidator(schemes=["https"])],
        help_text="Barry's personal WhatsApp link (https only), shown as 'Looking for a better rate?' on the sign-up and "
                  "choose-membership screens. Empty = the line is hidden on live (dev shows a 'link to come' marker).")

    history = HistoricalRecords()

    class Meta:
        verbose_name = "site settings"
        verbose_name_plural = "site settings"

    def __str__(self):
        return "Site settings"

    def clean(self):
        """Cross-field rule (forms, undo and the code view all go through full_clean): a slot is at least as long as the step."""
        if self.slot_length_minutes and self.slot_step_minutes and self.slot_length_minutes < self.slot_step_minutes:
            raise ValidationError({"slot_length_minutes": "A slot cannot be shorter than the step between slots."})

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(singleton_key="site")
        return obj

    @property
    def contact_address(self):
        """What the site shows and Reply-To uses: the stored contact email, else the address inside DEFAULT_FROM_EMAIL."""
        from email.utils import parseaddr

        from django.conf import settings

        return (split_emails(self.contact_email) or [parseaddr(settings.DEFAULT_FROM_EMAIL)[1]])[0]

    @property
    def approver_cc_list(self):
        return split_emails(self.gold_approver_cc)

    @property
    def wording(self):
        return self.get_join_wording_display()

    @property
    def address_one_line(self):
        """'99 Vale Road, London N4 1PR'."""
        town_line = " ".join(part for part in (self.address_town, self.address_postcode) if part)
        return ", ".join(part for part in (self.address_street, town_line) if part)

    @property
    def opening_label(self):
        """'January 2027': the opening date as month and year if it is set, otherwise the opening text."""
        if self.opening_date:
            return f"{self.opening_date:%B %Y}"
        return self.opening_text


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
    offset_minutes = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MaxValueValidator(720)], help_text="Shabbos / Yom Tov rules only.")
    public_title = models.CharField(
        max_length=80, blank=True, help_text="Heading for the public hours list (closure rules). Empty = the label."
    )
    public_note = models.CharField(
        max_length=200, blank=True,
        help_text='Plain words shown on the site for a Shabbos / Yom Tov rule, e.g. "Closed from Friday afternoon until Saturday night". Empty = not listed.',
    )
    active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(1000)])

    history = HistoricalRecords()

    class Meta:
        ordering = ["order", "key"]

    def __str__(self):
        return self.label

    def clean(self):
        """What each kind of rule needs (forms, undo and the code view all go through full_clean)."""
        errors = {}
        if self.kind in (self.PERIOD, self.DAILY_CLOSURE):
            for name in ("start_time", "end_time"):
                if getattr(self, name) is None:
                    errors[name] = "Enter a time."
            if self.start_time is not None and self.start_time == self.end_time:
                errors["end_time"] = "Start and end cannot be the same time."
        elif self.kind in (self.CLOSE_BEFORE_CANDLES, self.OPEN_AFTER_NIGHTFALL) and self.offset_minutes is None:
            errors["offset_minutes"] = "Enter the number of minutes."
        if errors:
            raise ValidationError(errors)


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

    def clean(self):
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "The end must be after the start."})


def facility_image_path(instance, filename):
    return f"facilities/{instance.slug}/{filename}"


class Facility(BaseModel):
    name = models.CharField(max_length=80)
    slug = models.SlugField(unique=True)
    short_line = models.CharField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    image = models.FileField(upload_to=facility_image_path, blank=True)  # default storage: S3 on live
    image_alt = models.CharField(max_length=200, blank=True, help_text="Describes the picture for people who cannot see it. Empty = the name.")
    FEATURE = "feature"
    TILE = "tile"
    COMPANION = "companion"
    DISPLAY_CHOICES = [
        (FEATURE, "Feature (large picture, own section)"),
        (TILE, "Tile (small portrait, in a row)"),
        (COMPANION, "Companion (small, beside the feature before it)"),
    ]
    FACTS_MAX = 4
    FACT_MAX_LENGTH = 32

    display = models.CharField(
        max_length=10, choices=DISPLAY_CHOICES, default=TILE,
        help_text="How the room is shown on The spa page. The page adjusts if a room is hidden or moved.")
    image_name = models.CharField(
        max_length=40, blank=True,
        help_text="Name of a built render (content image manifest). Used when no picture is uploaded; empty = the brand tile.")
    image_focus = models.CharField(
        max_length=20, blank=True, default="50% 50%", help_text='Which part of the picture stays in view when cropped, e.g. "40% 60%".')
    detail_image = models.FileField(
        upload_to=facility_image_path, blank=True, help_text="Optional small second picture for a feature room. Wins over the render name.")
    detail_image_name = models.CharField(max_length=40, blank=True, help_text="Built render for the small picture, when none is uploaded.")
    detail_alt = models.CharField(max_length=200, blank=True, help_text="Describes the small picture. Empty = decorative.")
    facts = models.JSONField(
        default=list, blank=True,
        help_text='Short facts shown as small pills, e.g. ["Loungers", "Low light"]. Up to 4 of 32 characters. Leave empty to show none.')
    order = models.PositiveSmallIntegerField(default=0)
    visible = models.BooleanField(default=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["order", "name"]
        verbose_name_plural = "facilities"

    def _saved_with(self, field, value):
        """True when this row is already saved with this value (the gym's picture is named before it is built)."""
        return bool(self.pk) and Facility.objects.filter(pk=self.pk, **{field: value}).exists()

    def clean(self):
        from content import images  # local: keeps this module free of the content app at import time

        errors = {}
        facts = self.facts if self.facts is not None else []
        if not isinstance(facts, list) or not all(isinstance(f, str) for f in facts):
            errors["facts"] = "Facts must be a list of short texts."
        elif len(facts) > self.FACTS_MAX:
            errors["facts"] = f"At most {self.FACTS_MAX} facts."
        elif any(not f.strip() or len(f) > self.FACT_MAX_LENGTH for f in facts):
            errors["facts"] = f"Each fact must be 1 to {self.FACT_MAX_LENGTH} characters."
        for field in ("image_name", "detail_image_name"):
            name = getattr(self, field)
            if name and not images.has_image(name) and not self._saved_with(field, name):  # an unchanged name never blocks a save
                errors[field] = "No built render with this name."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.name


class Sale(BaseModel):
    """A limited-time sale (System > Sales): a percentage off some plans, for the people who register while it is live.
    Only one sale is live at a time. The window is starts_at to `window_end` (ended_early_at when End now was used, else ends_at).
    A person's kept price is a snapshot on their InterestRegistration (users app), so editing or deleting a sale never changes it.
    Lives in the plans app because it is pricing data for Plan rows."""

    MAX_PERCENT = 90
    MAX_MONTHS = 36

    name = models.CharField(max_length=80, help_text='Shown on the site bar, e.g. "Christmas sale".')
    percent_off = models.PositiveSmallIntegerField(
        "% off", validators=[MinValueValidator(1), MaxValueValidator(MAX_PERCENT)], help_text="1 to 90. Locked once the sale is live.")
    plans = models.ManyToManyField(Plan, related_name="sales")
    starts_at = models.DateTimeField(db_index=True, help_text="London time.")
    ends_at = models.DateTimeField(db_index=True, help_text="London time.")
    months_at_price = models.PositiveSmallIntegerField(
        "months at the sale price", validators=[MinValueValidator(1), MaxValueValidator(MAX_MONTHS)],
        help_text="How long a person who registers during the sale keeps the sale price once billing starts. Locked once live.")
    ended_early_at = models.DateTimeField(null=True, blank=True, help_text="Set by End now.")
    created_by = models.ForeignKey("users.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    history = HistoricalRecords()

    class Meta:
        ordering = ["-starts_at"]
        indexes = [models.Index(fields=["starts_at", "ends_at"])]

    def __str__(self):
        return self.name

    # ---- the window ----

    @property
    def window_end(self):
        return self.ended_early_at or self.ends_at

    def status(self, now=None):
        """"upcoming", "live" or "ended" (ended early, or its end time has passed)."""
        now = now or timezone.now()
        if self.ended_early_at is not None and (self.ended_early_at <= now or self.ended_early_at <= self.starts_at):
            return "ended"  # ended early (an upcoming sale ended early never runs)
        if now >= self.ends_at:
            return "ended"
        return "upcoming" if now < self.starts_at else "live"

    @classmethod
    def overlapping(cls, starts_at, ends_at, exclude_pk=None):
        """Other sales whose live window shares time with [starts_at, ends_at). A sale ended early frees the rest of its time; one
        that was ended before it started has no window at all."""
        queryset = cls.objects.filter(starts_at__lt=ends_at).filter(
            models.Q(ended_early_at__isnull=True, ends_at__gt=starts_at) | models.Q(ended_early_at__gt=starts_at)
        ).exclude(ended_early_at__lte=models.F("starts_at"))
        return queryset.exclude(pk=exclude_pk) if exclude_pk else queryset

    # ---- rules ----

    def clean(self):
        super().clean()
        errors = {}
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            errors["ends_at"] = "The sale must end after it starts."
        if self.ended_early_at and self.ends_at and self.ended_early_at > self.ends_at:
            errors["ended_early_at"] = "A sale cannot be ended after its end time."
        if not errors and self.starts_at and self.ends_at:
            other = self.overlapping(self.starts_at, self.window_end, self.pk if not self._state.adding else None).first()
            if other is not None and self.window_end > self.starts_at:
                errors["starts_at"] = f"This overlaps {other.name}. Only one sale can be live at a time."
        if not self._state.adding:
            stored = type(self).objects.filter(pk=self.pk).first()
            if stored is not None:
                self._clean_against_stored(stored, errors)
                if not self.plans.exists():
                    errors["plans"] = "Choose at least one plan."
        if errors:
            raise ValidationError(errors)

    def _clean_against_stored(self, stored, errors):
        """A live sale's % off, months and start are locked (people already hold them). An ended-early sale can only be put back
        while its original end is still in the future."""
        if stored.status() == "live":
            for name in ("percent_off", "months_at_price", "starts_at"):
                now_value, was = getattr(self, name), getattr(stored, name)
                if name == "starts_at":  # forms drop microseconds
                    now_value, was = now_value.replace(microsecond=0), was.replace(microsecond=0)
                if now_value != was:
                    errors[name] = "This cannot change once the sale is live: people already hold it."
            if self.ends_at <= timezone.now() and self.ended_early_at is None:
                errors["ends_at"] = "Use End now to end a live sale."
        if stored.ended_early_at and self.ended_early_at is None and self.ends_at <= timezone.now():
            errors["ended_early_at"] = "The original end time has passed, so this sale cannot be put back."
