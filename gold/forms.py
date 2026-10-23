"""Gold application form. Validation reuses common/validators.py (same rules as sign-up and the JS mirror)."""
import copy

from django import forms
from django.core.exceptions import ValidationError

from common.validators import normalise_email, normalise_uk_mobile, password_problems, validate_adult, validate_person_name

from users.forms import SignUpForm

from . import rating
from .models import BML, PROPERTY_LINK, SIZE, WHERE


class GoldApplicationForm(forms.Form):
    first_name = forms.CharField(max_length=200)
    last_name = forms.CharField(max_length=200)
    email = forms.CharField(max_length=254)
    mobile = forms.CharField(max_length=40)
    industry = forms.ChoiceField(choices=[], error_messages={"required": "Choose what you do."})
    industry_other = forms.CharField(max_length=100, required=False)
    property_link = forms.ChoiceField(choices=[], required=False)  # only for industry Property (see clean())
    size_range = forms.ChoiceField(choices=[], required=False)
    location = forms.ChoiceField(choices=[], required=False)
    company = forms.CharField(max_length=150, required=False)
    role = forms.CharField(max_length=150, required=False)
    bml_relationship = forms.ChoiceField(choices=[], required=False)
    referred_by = forms.CharField(max_length=150, required=False)
    note = forms.CharField(max_length=2000, required=False)
    privacy_accepted = forms.BooleanField(error_messages={"required": "Please accept the privacy notice."})
    marketing_opt_in = forms.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The choices are GoldChoice rows (edited in Control), read each time the form is built.
        self.fields["industry"].choices = rating.industry_choices()
        for field, group in (("property_link", PROPERTY_LINK), ("size_range", SIZE), ("location", WHERE), ("bml_relationship", BML)):
            self.fields[field].choices = rating.choices(group)

    def clean_industry_other(self):
        return " ".join(self.cleaned_data["industry_other"].split())

    def clean(self):
        """The property questions belong to Property people only: for anyone else they are dropped, never required."""
        data = super().clean()
        industry = data.get("industry")
        if industry is None:  # already reported as invalid
            return data
        if industry == rating.PROPERTY_INDUSTRY:
            if not data.get("property_link"):
                self.add_error("property_link", "Choose your link to property.")
        else:
            data["property_link"] = ""
            data["size_range"] = ""
        if industry != rating.OTHER_INDUSTRY:
            data["industry_other"] = ""
        return data

    def clean_first_name(self):
        return validate_person_name(self.cleaned_data["first_name"])

    def clean_last_name(self):
        return validate_person_name(self.cleaned_data["last_name"])

    def clean_email(self):
        return normalise_email(self.cleaned_data["email"])

    def clean_mobile(self):
        return normalise_uk_mobile(self.cleaned_data["mobile"])

    def clean_company(self):
        return " ".join(self.cleaned_data["company"].split())

    def clean_role(self):
        return " ".join(self.cleaned_data["role"].split())

    def clean_referred_by(self):
        return " ".join(self.cleaned_data["referred_by"].split())

    def clean_note(self):
        return self.cleaned_data["note"].strip()



class GoldSetupForm(forms.Form):
    """Account setup from an invite: only a password and the acceptances. Name, email and mobile come from the
    application and are shown read-only."""

    password = forms.CharField(
        strip=False,
        widget=forms.PasswordInput(attrs={"data-validate": "required password", "autocomplete": "new-password",
                                          "data-password-related": "email,first_name,last_name"}),
    )
    men_only_accepted = forms.BooleanField(
        label="I understand Spa 99 is a men-only spa",
        error_messages={"required": "Please confirm you understand the men-only policy."},
        widget=forms.CheckboxInput(attrs={"data-validate": "required", "data-required-message": "Please confirm you understand the men-only policy."}),
    )
    privacy_accepted = forms.BooleanField(
        label="I have read the privacy notice", error_messages={"required": "Please accept the privacy notice."},
        widget=forms.CheckboxInput(attrs={"data-validate": "required", "data-required-message": "Please accept the privacy notice."}),
    )
    marketing_opt_in = forms.BooleanField(label="Send me news from Spa 99", required=False)

    # Same field and 18+ rule as registration (users.forms.SignUpForm), so there is one definition of both.
    date_of_birth = copy.deepcopy(SignUpForm.base_fields["date_of_birth"])
    mobile = forms.CharField(
        max_length=40, required=False,
        widget=forms.TextInput(attrs={"data-validate": "required mobile", "autocomplete": "tel", "inputmode": "tel"}),
    )

    def __init__(self, *args, application=None, mobile_editable=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.application = application
        self.mobile_editable = mobile_editable
        if mobile_editable:
            self.fields["mobile"].required = True
            self.initial.setdefault("mobile", application.mobile)
            self.fields["mobile"].widget.attrs.setdefault("data-validate", "required mobile")
        else:
            del self.fields["mobile"]

    def clean_date_of_birth(self):
        return validate_adult(self.cleaned_data["date_of_birth"])

    def clean_mobile(self):
        mobile = normalise_uk_mobile(self.cleaned_data["mobile"])
        from users.models import User

        if User.objects.filter(mobile=mobile).exists():
            raise ValidationError("That mobile number is already registered.")
        return mobile

    def clean_password(self):
        a = self.application
        problems = password_problems(
            self.cleaned_data["password"], email=a.email if a else "", first_name=a.first_name if a else "",
            last_name=a.last_name if a else "",
        )
        if problems:
            raise ValidationError(problems)
        return self.cleaned_data["password"]
