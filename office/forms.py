"""Office forms: the manual membership set-up (Admin and up)."""
from django import forms

from common.validators import validate_sensible_year
from plans.models import Plan


class ManualSetupForm(forms.Form):
    plan = forms.ModelChoiceField(queryset=Plan.objects.none(), empty_label=None)
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    agreed_price = forms.DecimalField(required=False, min_value=0, max_digits=8, decimal_places=2, label="Agreed price ex VAT, a month")
    agreed_months = forms.IntegerField(required=False, min_value=1, max_value=120, label="Months at this price")
    billing_note = forms.CharField(required=False, max_length=1000, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plan"].queryset = Plan.objects.exclude(kind=Plan.ONE_OFF).order_by("order")  # memberships, Gold included

    def clean_start_date(self):
        return validate_sensible_year(self.cleaned_data.get("start_date"))


class CappedText(forms.CharField):
    """Text with a hard limit that is refused, never cut, and says how many characters were typed ("keep it to 300 characters
    (you typed 412)"). No `maxlength` on the input: the page shows its own counter."""

    def __init__(self, noun, limit, **kwargs):
        super().__init__(strip=True, **kwargs)
        self.noun, self.limit = noun, limit

    def validate(self, value):
        super().validate(value)
        if value and len(value) > self.limit:
            raise forms.ValidationError(f"{self.noun}: keep it to {self.limit} characters (you typed {len(value)}).", code="max_length")


class StickyNoteForm(forms.Form):
    note = CappedText("Note", 1000, error_messages={"required": "Write the note."})


class MessageForm(forms.Form):
    message = CappedText("Message", 5000, min_length=5, error_messages={"required": "Write the message.", "min_length": "Message: write at least 5 characters."})


class ContactForm(forms.Form):
    """Add or fix a lead's first name and mobile (a missing or empty field is left as it is)."""
    first_name = forms.CharField(required=False, strip=True, max_length=100)
    mobile_country = forms.CharField(required=False, strip=True, max_length=2)  # ISO code, default GB
    mobile = forms.CharField(required=False, strip=True, max_length=40)


class OutreachAddForm(forms.Form):
    reason = CappedText("Reason", 300, required=False)


class ArchiveForm(forms.Form):
    reason = CappedText("Reason", 300, required=False)
