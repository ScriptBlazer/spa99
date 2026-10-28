"""System > FAQ: the entry form (also used for adding)."""
from django import forms

from chat.models import FaqItem

from .forms import VersionedForm


class FaqForm(VersionedForm):
    class Meta:
        model = FaqItem
        fields = ["question", "answer", "order", "suggested", "visible"]
        widgets = {"answer": forms.Textarea(attrs={"rows": 3}), "order": forms.NumberInput(attrs={"min": 0, "max": 1000})}

    def _no_price(self, name):
        value = self.cleaned_data[name]
        if "£" in value:
            raise forms.ValidationError("Leave prices out. The chat shares prices only after an email, and takes them from the plans.")
        return value

    def clean_question(self):
        return self._no_price("question")

    def clean_answer(self):
        return self._no_price("answer")
