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


# ---------- the rest of System > Assistant ----------
from chat.models import AssistantSettings, KnowledgeNote  # noqa: E402
from .models import SiteDefaults  # noqa: E402


class NoteForm(VersionedForm):
    class Meta:
        model = KnowledgeNote
        fields = ["topic", "title", "text", "order", "active"]
        widgets = {"text": forms.Textarea(attrs={"rows": 3}), "order": forms.NumberInput(attrs={"min": 0, "max": 1000})}

    def _no_price(self, name):
        value = self.cleaned_data[name]
        if "£" in value:
            raise forms.ValidationError("Leave prices out. Prices come only from the plans, and only after an email.")
        return value

    def clean_title(self):
        return self._no_price("title")

    def clean_text(self):
        return self._no_price("text")


def _bounds(form):
    """Put each number field's min and max (from the model validators) on the control."""
    for name, field in form.fields.items():
        if isinstance(field, forms.IntegerField):
            limits = {v.__class__.__name__: v.limit_value for v in form.instance._meta.get_field(name).validators}
            low, high = limits.get("MinValueValidator"), limits.get("MaxValueValidator")
            field.min_value, field.max_value = low, high
            field.widget.attrs.update({"min": low, "max": high})


class PersonalityForm(VersionedForm):
    class Meta:
        model = AssistantSettings
        fields = ["name", "welcome_heading", "welcome_line", "tone_notes", "always", "never"]
        widgets = {"tone_notes": forms.Textarea(attrs={"rows": 3}), "always": forms.Textarea(attrs={"rows": 4}), "never": forms.Textarea(attrs={"rows": 4})}


class LimitsForm(VersionedForm):
    class Meta:
        model = AssistantSettings
        fields = ["enabled", "daily_cap_percent", "rate_per_10_minutes", "rate_per_day", "max_messages", "max_chars"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bounds(self)


class CapForm(VersionedForm):
    """The monthly cap stays on the Defaults row (no data moves); this page edits the same field."""

    class Meta:
        model = SiteDefaults
        fields = ["chat_monthly_cap_gbp"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bounds(self)
