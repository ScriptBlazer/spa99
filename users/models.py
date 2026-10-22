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
    and point at this model (see SPA99_RULES "Keep these apart in the data model")."""

    INTEREST = "interest"
    MEMBER = "member"
    STATUS_CHOICES = [(INTEREST, "Registered interest"), (MEMBER, "Member")]

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

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=INTEREST, db_index=True)
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
        self.mobile = self.mobile or None  # unique + null: blank must be NULL, not ""
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
