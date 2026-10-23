"""Forms for the rule sections (plans, hours, Gold rules, journey). All validation is here, on the server, with plain
field errors. `RISKY` lists the fields whose change deserves a confirm step (the page shows old -> new)."""
from django import forms
from django.core.exceptions import ValidationError

from gold.models import GoldRule
from journey.models import Option, Question, SuggestionRule
from plans.models import Closure, OpeningRule, Plan, SiteSettings

RISKY = {
    "settings": ["vat_rate", "opening_date", "register_interest_open", "subscribe_open", "booking_open"],
    "emails": ["gold_approver_emails", "gold_approver_cc", "contact_email"],
    "plans": ["price_ex_vat", "visits_per_month", "hours", "booking_window_days", "upcoming_limit", "cancel_hours", "guests_per_month", "visible"],
    "hours": ["start_time", "end_time", "offset_minutes", "active", "starts_at", "ends_at", "capacity", "slot_length_minutes", "slot_step_minutes"],
    "gold": ["points", "active", "is_property"],
    "journey": ["plan_points", "gold_points", "active", "min_choices", "screen", "plan_slugs", "conditions", "points", "kind"],
}


def _plan_slugs():
    return set(Plan.objects.values_list("slug", flat=True))


# ---------- plans ----------

class PlanForm(forms.ModelForm):
    class Meta:
        model = Plan
        fields = ["name", "price_ex_vat", "visits_per_month", "hours", "booking_window_days", "upcoming_limit", "cancel_hours",
                  "guests_per_month", "perks", "short_description", "highlight", "visible", "order"]

    def clean_perks(self):
        perks = self.cleaned_data.get("perks") or []
        if not isinstance(perks, list):
            raise ValidationError('Perks must be a list, e.g. [{"key": "merch", "label": "Merch", "value": "Buy"}].')
        seen = set()
        for item in perks:
            if not isinstance(item, dict) or not str(item.get("key", "")).strip() or not str(item.get("label", "")).strip() or "value" not in item:
                raise ValidationError("Each perk needs a key, a label and a value.")
            if item["key"] in seen:
                raise ValidationError(f"The perk key {item['key']} is used twice.")
            seen.add(item["key"])
        return perks

    def clean_upcoming_limit(self):
        value = self.cleaned_data["upcoming_limit"]
        if value < 1:
            raise ValidationError("At least 1.")
        return value


class PlanAddForm(PlanForm):
    class Meta(PlanForm.Meta):
        fields = ["slug", "kind"] + PlanForm.Meta.fields


# ---------- hours ----------

class OpeningRuleForm(forms.ModelForm):
    class Meta:
        model = OpeningRule
        fields = ["label", "start_time", "end_time", "offset_minutes", "public_title", "public_note", "active", "order"]

    def clean(self):
        data = super().clean()
        kind = self.instance.kind or data.get("kind")
        if kind in (OpeningRule.PERIOD, OpeningRule.DAILY_CLOSURE):
            for name in ("start_time", "end_time"):
                if data.get(name) is None and name not in self.errors:
                    self.add_error(name, "Enter a time.")
            if data.get("start_time") and data.get("start_time") == data.get("end_time"):
                self.add_error("end_time", "Start and end cannot be the same time.")
        elif kind in (OpeningRule.CLOSE_BEFORE_CANDLES, OpeningRule.OPEN_AFTER_NIGHTFALL):
            minutes = data.get("offset_minutes")
            if minutes is None:
                self.add_error("offset_minutes", "Enter the number of minutes.")
            elif minutes > 720:
                self.add_error("offset_minutes", "At most 720 minutes.")
        return data


class OpeningRuleAddForm(OpeningRuleForm):
    class Meta(OpeningRuleForm.Meta):
        fields = ["key", "kind"] + OpeningRuleForm.Meta.fields


class ClosureForm(forms.ModelForm):
    class Meta:
        model = Closure
        fields = ["name", "starts_at", "ends_at", "public_note", "active"]
        widgets = {"starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
                   "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")}

    def clean(self):
        data = super().clean()
        if data.get("starts_at") and data.get("ends_at") and data["ends_at"] <= data["starts_at"]:
            self.add_error("ends_at", "The end must be after the start.")
        return data


class CapacityForm(forms.ModelForm):
    class Meta:
        model = SiteSettings
        fields = ["capacity", "slot_length_minutes", "slot_step_minutes", "booking_notice_minutes"]

    def clean(self):
        data = super().clean()
        if data.get("capacity") is not None and data["capacity"] < 1:
            self.add_error("capacity", "At least 1.")
        length, step = data.get("slot_length_minutes"), data.get("slot_step_minutes")
        if step is not None and step < 1:
            self.add_error("slot_step_minutes", "At least 1.")
        elif length is not None and step is not None and length < step:
            self.add_error("slot_length_minutes", "A slot cannot be shorter than the step between slots.")
        return data


# ---------- Gold rules ----------

class GoldRuleForm(forms.ModelForm):
    class Meta:
        model = GoldRule
        fields = ["label", "points", "is_property", "active"]

    def clean_points(self):
        points = self.cleaned_data["points"]
        if (self.instance.group or self.cleaned_data.get("group")) == GoldRule.THRESHOLD and points < 1:
            raise ValidationError("A threshold needs at least 1 point.")
        return points

    def clean(self):
        data = super().clean()
        rule = self.instance
        if rule.pk and rule.group == GoldRule.THRESHOLD and data.get("points") and "points" not in self.errors:
            other = GoldRule.objects.filter(group=GoldRule.THRESHOLD, match_value="medium" if rule.match_value == "high" else "high").first()
            if other is not None:
                high, medium = (data["points"], other.points) if rule.match_value == "high" else (other.points, data["points"])
                if rule.match_value in ("high", "medium") and high < medium:
                    self.add_error("points", "The High threshold cannot be lower than the Medium threshold.")
        return data


class GoldRuleAddForm(GoldRuleForm):
    class Meta(GoldRuleForm.Meta):
        fields = ["group", "match_value"] + GoldRuleForm.Meta.fields


# ---------- journey ----------

class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ["text", "help_text", "screen", "order", "min_choices", "active"]

    def clean_screen(self):
        if self.cleaned_data["screen"] < 1:
            raise ValidationError("Screens start at 1.")
        return self.cleaned_data["screen"]

    def clean_min_choices(self):
        value = self.cleaned_data["min_choices"]
        if self.instance.pk and self.instance.type in (Question.SINGLE, Question.MULTI):
            live = self.instance.options.filter(active=True).count()
            if value > live:
                raise ValidationError(f"Only {live} choices are active, so {value} cannot be required.")
        return value


class OptionForm(forms.ModelForm):
    class Meta:
        model = Option
        fields = ["label", "order", "active", "plan_points", "gold_points", "weight", "reason"]

    def clean_plan_points(self):
        points = self.cleaned_data.get("plan_points") or {}
        if not isinstance(points, dict):
            raise ValidationError('Use an object like {"tier-2": 3}.')
        unknown = sorted(set(points) - _plan_slugs())
        if unknown:
            raise ValidationError(f"Not a plan: {', '.join(unknown)}.")
        if any(isinstance(v, bool) or not isinstance(v, int) for v in points.values()):
            raise ValidationError("Points must be whole numbers.")
        return points


class OptionAddForm(OptionForm):
    class Meta(OptionForm.Meta):
        fields = ["value"] + OptionForm.Meta.fields

    def clean_value(self):
        value = self.cleaned_data["value"]
        if self.instance.question_id and Option.objects.filter(question_id=self.instance.question_id, value=value).exists():
            raise ValidationError("This question already has an option with this value.")
        return value


class SuggestionRuleForm(forms.ModelForm):
    class Meta:
        model = SuggestionRule
        fields = ["name", "kind", "conditions", "plan_slugs", "target_daytime_only", "points", "reason", "active", "order"]

    def clean_conditions(self):
        conditions = self.cleaned_data.get("conditions") or []
        keys = set(Question.objects.values_list("key", flat=True))
        if not isinstance(conditions, list):
            raise ValidationError('Use a list like [{"question": "time", "any_of": ["evening"]}].')
        for item in conditions:
            if not isinstance(item, dict) or item.get("question") not in keys or not isinstance(item.get("any_of"), list) or not item["any_of"]:
                raise ValidationError("Each condition needs a real question key and a list of answers (any_of).")
        return conditions

    def clean_plan_slugs(self):
        slugs = self.cleaned_data.get("plan_slugs") or []
        if not isinstance(slugs, list) or not all(isinstance(s, str) for s in slugs):
            raise ValidationError('Use a list of plan slugs, e.g. ["tier-2"].')
        unknown = sorted(set(slugs) - _plan_slugs())
        if unknown:
            raise ValidationError(f"Not a plan: {', '.join(unknown)}.")
        return slugs
