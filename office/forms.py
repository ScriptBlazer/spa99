"""Office forms: the manual membership set-up (Admin and up)."""
from django import forms

from plans.models import Plan


class ManualSetupForm(forms.Form):
    plan = forms.ModelChoiceField(queryset=Plan.objects.none(), empty_label=None)
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    agreed_price = forms.DecimalField(required=False, min_value=0, max_digits=8, decimal_places=2, label="Agreed price ex VAT, a month")
    billing_note = forms.CharField(required=False, max_length=1000, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plan"].queryset = Plan.objects.exclude(kind=Plan.ONE_OFF).order_by("order")  # memberships, Gold included
