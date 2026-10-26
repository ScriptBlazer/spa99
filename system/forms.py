from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from common.jsonshape import has_non_ascii_digit
from plans.models import SiteSettings

from . import services

TOKEN = "row_token"  # the hidden field every System form for an existing row carries (the row's version when the page was made)
DIGITS_MESSAGE = "Use the digits 0-9."


class TokenField(forms.CharField):
    """The version token: never counts as a changed field (so it is never saved or listed)."""

    def __init__(self):
        super().__init__(required=False, widget=forms.HiddenInput)

    def has_changed(self, initial, data):
        return False


class VersionedForm(forms.ModelForm):
    """Base of every System form that edits a row.

    1. Version token. A form for an existing row carries `row_token`, the services.row_fingerprint of the row's fields as
       the page rendered them. Validation fails with STALE_MESSAGE when the row has changed since (nothing is saved;
       `form.stale` is set so the view answers 409). A POST without a token (a script, a test) is not checked: every
       page the System renders carries one. Works without a request, so the code view can validate through it too.
    2. Digits. Number and money inputs accept only 0-9 (Django would take Arabic-Indic digits and save them as ASCII)."""

    stale = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field, forms.IntegerField):  # also Decimal and Float
                field.to_python = self._ascii_only(field.to_python)
        if not self.instance._state.adding:
            self.fields[TOKEN] = TokenField()
            self.initial[TOKEN] = self.fingerprint(self.instance)

    @staticmethod
    def _ascii_only(original):
        def to_python(value):
            if has_non_ascii_digit(value):
                raise ValidationError(DIGITS_MESSAGE, code="invalid")
            return original(value)
        return to_python

    def version_fields(self):
        names = {f.name for f in self.instance._meta.concrete_fields}
        return [name for name in self.fields if name in names]

    def fingerprint(self, row):
        """The row's version (a form with extra parts, like a many-to-many, adds them here)."""
        return services.row_fingerprint(row, self.version_fields())

    def ensure_current(self, lock=False):
        """Raise ValidationError(STALE_MESSAGE) unless the row still has the version this form was made from."""
        token = self.cleaned_data.get(TOKEN) if TOKEN in self.fields else ""
        if not token:
            return
        row = services.current_row(self.instance, lock=lock)
        if row is None or self.fingerprint(row) != token:
            self.stale = True
            raise ValidationError(services.STALE_MESSAGE, code="stale")

    def clean(self):
        data = super().clean()
        self.ensure_current()
        return data


class EmailsForm(VersionedForm):
    class Meta:
        model = SiteSettings
        fields = ["gold_approver_cc", "contact_email"]

    def clean(self):
        data = super().clean()
        data["contact_email"] = self._single(data.get("contact_email", ""))
        return data

    @staticmethod
    def _single(value):
        from common.validators import split_emails

        if len(split_emails(value)) > 1:
            raise forms.ValidationError({"contact_email": "Enter one address."})
        return value


class SettingsForm(VersionedForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["register_interest_open"].label = "Registration open"
        self.fields["memberships_public"].label = "Memberships page public"
        self.fields["discount_contact_url"].assume_scheme = "https"
        self.fields["discount_contact_url"].widget.attrs.update({"placeholder": "https://wa.me/..."})
        self.fields["code_theme_default"].required = False  # a post without it (older forms, scripts) keeps the saved theme
        for name, low, high in (("lock_idle_minutes", 1, 240), ("max_sign_in_hours", 1, 72)):
            self.fields[name].widget.attrs.update({"min": low, "max": high})
            self.fields[name].min_value, self.fields[name].max_value = low, high

    def clean_opening_date(self):
        """A new date cannot be in the past; a past date already saved never blocks saving the other fields."""
        value = self.cleaned_data.get("opening_date")
        if value and value != self.instance.opening_date and value < timezone.localdate():
            raise forms.ValidationError("The opening date cannot be in the past.")
        return value

    def clean_code_theme_default(self):
        return self.cleaned_data.get("code_theme_default") or self.instance.code_theme_default

    def clean_vat_rate(self):
        rate = self.cleaned_data["vat_rate"]
        if rate < 0 or rate > 100:
            raise forms.ValidationError("Enter a rate between 0 and 100.")
        return rate

    class Meta:
        model = SiteSettings
        fields = ["opening_date", "opening_text", "register_interest_open", "memberships_public", "subscribe_open", "booking_open",
                  "join_wording", "show_leil_shishi", "vat_rate", "discount_contact_url", "lock_idle_minutes", "max_sign_in_hours", "code_theme_default"]
        widgets = {"opening_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}
