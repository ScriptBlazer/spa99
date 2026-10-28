"""System > FAQ: the entry form (also used for adding)."""
from django import forms

from chat.models import FaqItem

from .forms import VersionedForm


class FaqForm(VersionedForm):
    class Meta:
        model = FaqItem
        fields = ["question", "answer", "order", "suggested", "visible"]
        widgets = {"answer": forms.Textarea(attrs={"rows": 3}), "order": forms.NumberInput(attrs={"min": 0, "max": 1000})}
