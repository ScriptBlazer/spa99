from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.db.models.functions import Lower
from simple_history.models import HistoricalRecords

from common.ids import format_public_code, generate_public_code
from common.models import BaseModel
from common.validators import normalise_email, normalise_uk_mobile

from .managers import UserManager


class User(BaseModel, AbstractBaseUser, PermissionsMixin):
    """A person. Person data only: memberships, bookings, bands, lockers etc. live in their own apps
    and point at this model (see SPA99_RULES "Keep these apart in the data model"). No status field:
    interest is an InterestRegistration record and membership comes from the memberships app."""

    email = models.EmailField("email address", unique=True)
    public_id = models.CharField(
        "account ID", max_length=8, unique=True, editable=False,
        help_text="Short shareable ID for guest invites (ACC-05).",
    )
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    mobile = models.CharField(max_length=16, unique=True, null=True, blank=True, help_text="E.164, e.g. +447123456789")
    date_of_birth = models.DateField(null=True, blank=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)

    marketing_consent = models.BooleanField(default=False)
    marketing_consent_at = models.DateTimeField(null=True, blank=True)
    privacy_accepted_version = models.CharField(max_length=20, blank=True)
    privacy_accepted_at = models.DateTimeField(null=True, blank=True)
    men_only_accepted_at = models.DateTimeField(null=True, blank=True, help_text="Accepted the men-only policy (ACC-09).")

    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    objects = UserManager()
    history = HistoricalRecords(excluded_fields=["password"])  # never keep password hashes in history

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        ordering = ["email"]
        constraints = [models.UniqueConstraint(Lower("email"), name="users_user_email_ci_unique")]

    def __str__(self):
        return self.email

    def clean(self):
        super().clean()
        self.email = normalise_email(self.email)
        if self.mobile:
            self.mobile = normalise_uk_mobile(self.mobile)

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        # Always stored as E.164 so uniqueness holds across formats; blank must be NULL (unique), not "".
        self.mobile = normalise_uk_mobile(self.mobile) if self.mobile else None
        if not self.public_id:
            self.public_id = self._new_public_id()
        super().save(*args, **kwargs)

    @classmethod
    def _new_public_id(cls):
        while True:
            candidate = generate_public_code()
            if not cls.objects.filter(public_id=candidate).exists():
                return candidate

    @property
    def public_id_display(self):
        return format_public_code(self.public_id)

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        return self.first_name


class InterestRegistration(BaseModel):
    """A person's registered interest in a plan (Phase 1). Separate from the User (person data only) and from
    the memberships Phase 2 will add. One per person: changing interest updates it and history keeps the old plan."""

    JOURNEY = "journey"
    DIRECT = "direct"
    SOURCE_CHOICES = [(JOURNEY, "After the guided journey"), (DIRECT, "Directly")]

    user = models.OneToOneField("users.User", on_delete=models.CASCADE, related_name="interest")
    plan = models.ForeignKey("plans.Plan", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default=DIRECT)
    journey_session = models.ForeignKey(
        "journey.JourneySession", null=True, blank=True, on_delete=models.SET_NULL, related_name="registrations"
    )
    # The sale price this person keeps (docs/features/sales.md). A snapshot: name, percent and months are copied, so editing or
    # deleting the sale never changes it. `sale` is only a link back (SET_NULL). Set by plans.sales.snapshot_fields, never backfilled.
    sale = models.ForeignKey("plans.Sale", null=True, blank=True, on_delete=models.SET_NULL, related_name="interests")
    sale_name = models.CharField(max_length=80, blank=True)
    sale_percent_off = models.PositiveSmallIntegerField(null=True, blank=True)
    sale_months = models.PositiveSmallIntegerField(null=True, blank=True)
    sale_locked_at = models.DateTimeField(null=True, blank=True, help_text="When the sale price was locked in.")

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["-created_at"])]

    def __str__(self):
        return f"{self.user_id} interested in {self.plan_id}"
