"""Gold application form. Validation reuses common/validators.py (same rules as sign-up and the JS mirror)."""
from django import forms

from common.validators import normalise_email, normalise_uk_mobile, validate_person_name

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

