"""Admin forms and the public sign-up forms. Validation comes from common/validators.py, the same rules the
JS file common/static/common/js/validate.js mirrors (the data-validate attributes switch the JS checks on)."""
from django import forms
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm as BaseUserChangeForm
from django.core.exceptions import ValidationError

from common.validators import normalise_email, normalise_uk_mobile, password_problems, validate_adult, validate_person_name

from .models import User


class UserCreationForm(AdminUserCreationForm):
    class Meta:
        model = User
        fields = ("email",)


class UserChangeForm(BaseUserChangeForm):
    class Meta:
        model = User
        fields = "__all__"


def _attrs(rules, **extra):
    return {"data-validate": rules, **extra}


class SignUpForm(forms.Form):
    """Register interest. The plan is a slug (tier-2); the journey session is passed to the service, not the form."""

    first_name = forms.CharField(max_length=200, widget=forms.TextInput(attrs=_attrs("required name", autocomplete="given-name")))
    last_name = forms.CharField(max_length=200, widget=forms.TextInput(attrs=_attrs("required name", autocomplete="family-name")))
    email = forms.CharField(max_length=254, widget=forms.EmailInput(attrs=_attrs("required email", autocomplete="email")))
    mobile = forms.CharField(max_length=40, widget=forms.TextInput(attrs=_attrs("required mobile", autocomplete="tel", inputmode="tel")))
    password = forms.CharField(
        strip=False,
        widget=forms.PasswordInput(attrs=_attrs("required password", **{"autocomplete": "new-password", "data-password-related": "email,first_name,last_name"})),
    )
    date_of_birth = forms.DateField(
        label="Date of birth", input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs=_attrs("required dob", type="date", autocomplete="bday"), format="%Y-%m-%d"),
    )
    men_only_accepted = forms.BooleanField(
        label="I understand Spa 99 is a men-only spa",
        error_messages={"required": "Please confirm you understand the men-only policy."},
    )
    privacy_accepted = forms.BooleanField(
        label="I have read the privacy notice", error_messages={"required": "Please accept the privacy notice."}
    )
    marketing_opt_in = forms.BooleanField(label="Send me news from Spa 99", required=False)
    plan = forms.CharField(required=False, max_length=60, widget=forms.HiddenInput)

    def clean_first_name(self):
        return validate_person_name(self.cleaned_data["first_name"])

    def clean_last_name(self):
        return validate_person_name(self.cleaned_data["last_name"])

    def clean_email(self):
        return normalise_email(self.cleaned_data["email"])

    def clean_mobile(self):
        return normalise_uk_mobile(self.cleaned_data["mobile"])

    def clean_date_of_birth(self):
        return validate_adult(self.cleaned_data["date_of_birth"])

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        if password and "password" not in self.errors:
            problems = password_problems(
                password, email=cleaned.get("email", ""), first_name=cleaned.get("first_name", ""),
                last_name=cleaned.get("last_name", ""),
            )
            if problems:
                self.add_error("password", ValidationError(problems))
        return cleaned


class ForgotPasswordForm(forms.Form):
    email = forms.CharField(max_length=254, widget=forms.EmailInput(attrs=_attrs("required email", autocomplete="email")))


class ResetPasswordForm(forms.Form):
    password = forms.CharField(
        label="New password", strip=False,
        widget=forms.PasswordInput(attrs=_attrs("required password", autocomplete="new-password")),
    )
