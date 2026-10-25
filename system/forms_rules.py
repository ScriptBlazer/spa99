"""Forms for the rule sections (plans, hours, Gold rules, journey). All validation is here, on the server, with plain
field errors. `RISKY` lists the fields whose change deserves a confirm step (the page shows old -> new)."""
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from common import jsonshape as shape
from gold.models import GoldRule
from journey.models import Option, Question, SuggestionRule
from plans.models import Closure, OpeningRule, Plan, SiteSettings

from .forms import DIGITS_MESSAGE, VersionedForm

POINTS_LIMIT = 1000  # plan points and Gold points: -1000 to 1000

RISKY = {
    "settings": ["vat_rate", "opening_date", "register_interest_open", "subscribe_open", "booking_open", "lock_idle_minutes", "max_sign_in_hours"],
    "emails": ["gold_approver_cc", "contact_email"],
    "plans": ["price_ex_vat", "visits_per_month", "hours", "booking_window_days", "upcoming_limit", "cancel_hours", "guests_per_month", "visible"],
    "hours": ["start_time", "end_time", "offset_minutes", "active", "starts_at", "ends_at", "capacity", "slot_length_minutes", "slot_step_minutes"],
    "gold": ["points", "active", "is_property"],
    "journey": ["plan_points", "gold_points", "active", "min_choices", "screen", "plan_slugs", "conditions", "points", "kind"],
}


def _plan_slugs():
    return set(Plan.objects.values_list("slug", flat=True))


class PlanPointsWidget(forms.Widget):
    """One small whole-number input per plan (named `<field>.<slug>`), assembled into the points object on submit. A single
    JSON text under the plain field name is still accepted. An empty box means no points for that plan."""

    def _slugs(self):
        return list(Plan.objects.order_by("order", "slug").values_list("slug", flat=True))

    def value_from_datadict(self, data, files, name):
        if name in data:  # the old single JSON text
            return data.get(name)
        points = {}
        for slug in self._slugs():
            raw = (data.get(f"{name}.{slug}") or "").strip()
            if raw != "":
                points[slug] = shape.parse_whole(raw)  # ASCII digits only; anything else stays text so validation can refuse it
        return points

    def value_omitted_from_data(self, data, files, name):
        return name not in data and not any(key.startswith(f"{name}.") for key in data)

    def render(self, name, value, attrs=None, renderer=None):
        from django.utils.html import format_html, format_html_join

        value = value if isinstance(value, dict) else {}
        extra = {k: v for k, v in (attrs or {}).items() if k not in ("id", "aria-label")}
        extra_html = format_html_join("", ' {}="{}"', extra.items())
        label = (attrs or {}).get("aria-label", "Plan points")
        boxes = format_html_join("", '<label class="sys-pp"><span class="mono">{}</span><input type="number" step="1" name="{}.{}" value="{}" aria-label="{} {}"{}></label>',
                                 ((slug, name, slug, value.get(slug, ""), label, slug, extra_html) for slug in self._slugs()))
        return format_html('<span class="sys-points">{}</span>', boxes)


class PlanPointsField(forms.JSONField):
    widget = PlanPointsWidget

    def bound_data(self, data, initial):
        return data if isinstance(data, dict) else super().bound_data(data, initial)

    def has_changed(self, initial, data):
        try:
            now = data if isinstance(data, dict) else (self.to_python(data) or {})
        except ValidationError:
            return True
        return (initial or {}) != now


# ---------- plans ----------

class PlanForm(VersionedForm):
    class Meta:
        model = Plan
        fields = ["name", "price_ex_vat", "visits_per_month", "hours", "booking_window_days", "upcoming_limit", "cancel_hours",
                  "guests_per_month", "perks", "short_description", "highlight", "visible", "order"]
        # money: a plain text box (no 1p arrows), shown as 299.00; the DecimalField still validates on the server
        widgets = {"price_ex_vat": forms.TextInput(attrs={"inputmode": "decimal", "autocomplete": "off", "data-money": ""})}

    def clean_perks(self):
        perks = shape.no_nul(self.cleaned_data.get("perks") or [])
        shape.need_list(perks, 'Perks must be a list, e.g. [{"key": "merch", "label": "Merch", "value": "Buy"}].')
        seen = set()
        for item in perks:  # type-check first: a list or object as a key would break the set
            if not isinstance(item, dict) or "value" not in item:
                raise ValidationError("Each perk needs a key, a label and a value.")
            shape.need_text(item.get("key"), "Each perk needs a key (text), a label and a value.")
            shape.need_text(item.get("label"), "Each perk needs a key, a label (text) and a value.")
            if any(name in item and not shape.is_text(item[name]) for name in ("phrase", "pill")):
                raise ValidationError('A perk\'s "phrase" and "pill" must be text.')
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

class OpeningRuleForm(VersionedForm):
    class Meta:
        model = OpeningRule
        fields = ["label", "start_time", "end_time", "offset_minutes", "public_title", "public_note", "active", "order"]


class OpeningRuleAddForm(OpeningRuleForm):
    class Meta(OpeningRuleForm.Meta):
        fields = ["key", "kind"] + OpeningRuleForm.Meta.fields


class ClosureForm(VersionedForm):
    class Meta:
        model = Closure
        fields = ["name", "starts_at", "ends_at", "public_note", "active"]
        widgets = {"starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
                   "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")}

    def clean_ends_at(self):
        """A closure being added cannot already be over (the end-after-start rule is the model's)."""
        value = self.cleaned_data.get("ends_at")
        if value and self.instance._state.adding and value < timezone.now():
            raise ValidationError("A closure that has already ended cannot be added.")
        return value


class CapacityForm(VersionedForm):
    class Meta:
        model = SiteSettings
        fields = ["capacity", "slot_length_minutes", "slot_step_minutes", "booking_notice_minutes"]


# ---------- Gold rules ----------

class GoldRuleForm(VersionedForm):
    class Meta:
        model = GoldRule
        fields = ["label", "points", "is_property", "active"]


class GoldRuleAddForm(GoldRuleForm):
    class Meta(GoldRuleForm.Meta):
        fields = ["group", "match_value"] + GoldRuleForm.Meta.fields


# ---------- journey ----------

class QuestionForm(VersionedForm):
    class Meta:
        model = Question
        fields = ["text", "help_text", "screen", "order", "min_choices", "active"]

    def clean_min_choices(self):
        value = self.cleaned_data["min_choices"]
        if self.instance.pk and self.instance.type in (Question.SINGLE, Question.MULTI):
            live = self.instance.options.filter(active=True).count()
            if value > live:
                raise ValidationError(f"Only {live} choices are active, so {value} cannot be required.")
        return value


class OptionForm(VersionedForm):
    plan_points = PlanPointsField(required=False, label="Plan points", help_text="Whole points for each plan this answer points towards. Empty means none.")

    class Meta:
        model = Option
        fields = ["label", "order", "active", "plan_points", "gold_points", "weight", "reason"]

    def clean_plan_points(self):
        points = shape.no_nul(self.cleaned_data.get("plan_points") or {})
        shape.need_dict(points, 'Use an object like {"tier-2": 3}.')
        unknown = sorted(set(points) - _plan_slugs())  # JSON object keys are always text
        if unknown:
            raise ValidationError(f"Not a plan: {', '.join(unknown)}.")
        if any(shape.has_non_ascii_digit(v) for v in points.values()):
            raise ValidationError(DIGITS_MESSAGE)
        if any(not shape.is_whole(v) for v in points.values()):
            raise ValidationError("Points must be whole numbers.")
        if any(not -POINTS_LIMIT <= v <= POINTS_LIMIT for v in points.values()):
            raise ValidationError(f"Points must be between -{POINTS_LIMIT} and {POINTS_LIMIT}.")
        return points

    def clean(self):
        data = super().clean()
        option = self.instance
        if not option._state.adding and option.active and data.get("active") is False and "active" not in self.errors:
            question = Question.objects.get(pk=option.question_id)  # fresh: the cached one may be older
            if question.type in (Question.SINGLE, Question.MULTI):
                others = question.options.filter(active=True).exclude(pk=option.pk).count()
                if others < question.min_choices:
                    self.add_error("active", f"This question needs {question.min_choices} active choice{'s' if question.min_choices != 1 else ''}, "
                                             "so this one has to stay active. Lower the question's minimum first.")
        return data


class OptionAddForm(OptionForm):
    class Meta(OptionForm.Meta):
        fields = ["value"] + OptionForm.Meta.fields

    def clean_value(self):
        value = self.cleaned_data["value"]
        if self.instance.question_id and Option.objects.filter(question_id=self.instance.question_id, value=value).exists():
            raise ValidationError("This question already has an option with this value.")
        return value


class SuggestionRuleForm(VersionedForm):
    class Meta:
        model = SuggestionRule
        fields = ["name", "kind", "conditions", "plan_slugs", "target_daytime_only", "points", "reason", "active", "order"]

    def clean_conditions(self):
        conditions = shape.no_nul(self.cleaned_data.get("conditions") or [])
        keys = set(Question.objects.values_list("key", flat=True))
        shape.need_list(conditions, 'Use a list like [{"question": "time", "any_of": ["evening"]}].')
        message = "Each condition needs a real question key and a list of answers (any_of)."
        for item in conditions:  # type-check before the lookup: a list as the question would break `in keys`
            if not isinstance(item, dict) or not shape.is_text(item.get("question")) or item["question"] not in keys:
                raise ValidationError(message)
            shape.need_text_list(item.get("any_of"), message, empty=False)
        return conditions

    def clean_plan_slugs(self):
        slugs = shape.need_text_list(shape.no_nul(self.cleaned_data.get("plan_slugs") or []), 'Use a list of plan slugs, e.g. ["tier-2"].')
        unknown = sorted(set(slugs) - _plan_slugs())
        if unknown:
            raise ValidationError(f"Not a plan: {', '.join(unknown)}.")
        return slugs
