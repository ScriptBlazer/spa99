"""Gold application form. Validation reuses common/validators.py (same rules as sign-up and the JS mirror)."""
from django import forms

from common.validators import normalise_email, normalise_uk_mobile, validate_person_name

from .models import BML_CHOICES, PROPERTY_LINKS, SIZE_RANGES, WHERE_CHOICES


class GoldApplicationForm(forms.Form):
    first_name = forms.CharField(max_length=200)
    last_name = forms.CharField(max_length=200)
    email = forms.CharField(max_length=254)
    mobile = forms.CharField(max_length=40)
    property_link = forms.ChoiceField(choices=PROPERTY_LINKS)
    size_range = forms.ChoiceField(choices=SIZE_RANGES, required=False)
    location = forms.ChoiceField(choices=WHERE_CHOICES, required=False)
    company = forms.CharField(max_length=150, required=False)
    role = forms.CharField(max_length=150, required=False)
    bml_relationship = forms.ChoiceField(choices=BML_CHOICES, required=False)
    referred_by = forms.CharField(max_length=150, required=False)
    note = forms.CharField(max_length=2000, required=False)
    privacy_accepted = forms.BooleanField(error_messages={"required": "Please accept the privacy notice."})
    marketing_opt_in = forms.BooleanField(required=False)

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

