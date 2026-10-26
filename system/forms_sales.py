"""System > Sales: the sale form. Times are typed in London time (datetime-local boxes). A live sale locks % off, months and the start
(people already hold them); an ended sale is read-only. The version token also covers the plans and an End now."""
import hashlib

from django import forms
from django.utils import timezone

from plans.models import Plan, Sale

from .forms import VersionedForm

WHEN = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"]
LIVE_LOCKED = ("percent_off", "months_at_price", "starts_at")


def _when():
    return forms.DateTimeField(input_formats=WHEN, widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"))


class SaleForm(VersionedForm):
    starts_at = _when()
    ends_at = _when()
    plans = forms.ModelMultipleChoiceField(queryset=Plan.objects.none(), widget=forms.CheckboxSelectMultiple, error_messages={"required": "Choose at least one plan."})

    class Meta:
        model = Sale
        fields = ["name", "percent_off", "starts_at", "ends_at", "months_at_price"]  # plans are saved by plans.sales.save_sale
        widgets = {"percent_off": forms.NumberInput(attrs={"min": 1, "max": Sale.MAX_PERCENT}),
                   "months_at_price": forms.NumberInput(attrs={"min": 1, "max": Sale.MAX_MONTHS})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plans"].queryset = Plan.objects.all()
        self.fields["plans"].label_from_instance = lambda plan: plan.name
        status = "upcoming" if self.instance._state.adding else self.instance.status()
        self.status = status
        if not self.instance._state.adding:
            self.initial["plans"] = list(self.instance.plans.values_list("pk", flat=True))
        locked = LIVE_LOCKED if status == "live" else tuple(self.fields) if status == "ended" else ()
        self.locked_fields = [name for name in locked if name in self.fields]
        for name in self.locked_fields:
            self.fields[name].disabled = True

    def version_fields(self):
        return [*super().version_fields(), "ended_early_at"]

    def fingerprint(self, row):
        base = super().fingerprint(row)
        if row._state.adding:
            return base
        ids = ",".join(sorted(str(pk) for pk in row.plans.values_list("pk", flat=True)))
        return hashlib.sha256(f"{base}|{ids}".encode()).hexdigest()[:24]

    def clean_ends_at(self):
        ends = self.cleaned_data["ends_at"]
        if self.status == "live" and ends <= timezone.now():
            raise forms.ValidationError("Use End now to end a live sale.")
        return ends

    def clean(self):
        data = super().clean()
        if self.status == "ended":
            raise forms.ValidationError("An ended sale cannot be edited.")
        if self.status == "upcoming" and data.get("starts_at") and data["starts_at"] < timezone.now() and self.instance._state.adding:
            self.add_error("starts_at", "The start cannot be in the past.")
        return data
