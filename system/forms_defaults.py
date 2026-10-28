"""System > Defaults: the form, its groups and the plain-English hints. Choice lists come from the constants of the pages that own
them (never copied here). One form edits the one SiteDefaults row; each number carries its min and max from the model."""
from django import forms

from .forms import VersionedForm
from .models import SiteDefaults

# (group title, [(field, unit shown after the control)]) in page order.
GROUPS = [
    ("Office", [("leads_range", ""), ("leads_show", ""), ("leads_sort", ""), ("leads_page_size", "rows"), ("list_page_size", "rows"),
                ("dashboard_range", ""), ("analytics_range", ""), ("dashboard_hot_leads", "shown"), ("dashboard_activity", "shown"),
                ("dashboard_gold_waiting", "shown"), ("dashboard_latest", "shown"), ("analytics_options", "shown"), ("top_pages", "shown"),
                ("timeline_page_size", "events"), ("person_emails_shown", "emails")]),
    ("Website and journey", [("result_reasons", "reasons"), ("gold_nudge_high", ""), ("gold_nudge_medium", ""), ("gold_nudge_low", ""),
                             ("opener_lines", "lines"), ("chat_monthly_cap_gbp", "£ a month")]),
    ("Gold", [("gold_invite_days", "days"), ("gold_approval_days", "days")]),
    ("Emails", [("register_invite_days", "days"), ("recent_mailings", "shown"), ("recent_batches", "shown")]),
    ("Sign-in", [("office_session_days", "days"), ("email_confirm_hours", "hours")]),
    ("System", [("changelog_page_size", "rows"), ("audit_page_size", "rows"), ("dashboard_recent_changes", "shown")]),
    ("Notifications", [("toast_seconds", "seconds"), ("toast_long_seconds", "seconds")]),
]
FIELDS = [name for _title, rows in GROUPS for name, _unit in rows]
UNITS = {name: unit for _title, rows in GROUPS for name, unit in rows}
RISKY = ["gold_invite_days", "gold_approval_days", "register_invite_days", "office_session_days", "email_confirm_hours"]

RANGE_LABELS = {"today": "Today", "7d": "7 days", "30d": "30 days", "90d": "90 days", "all": "All time"}
SHOW_LABELS = {"lead": "Not registered", "registered": "Registered", "all": "All"}
SORT_LABELS = {"last_seen": "Last seen", "first_seen": "First seen", "potential": "Highest potential", "visits": "Most visits"}


def choice_fields():
    """field -> [(value, label)], from the owning pages' constants."""
    from office import leads, selectors

    def pairs(values, labels):
        return [(v, labels.get(v, v)) for v in values]

    return {"leads_range": pairs(leads.RANGES, RANGE_LABELS), "leads_show": pairs(leads.SHOWS, SHOW_LABELS),
            "leads_sort": pairs(leads.SORTS, SORT_LABELS), "dashboard_range": pairs(selectors.DASHBOARD_RANGES, RANGE_LABELS),
            "analytics_range": pairs(selectors.ANALYTICS_RANGES, RANGE_LABELS),
            **{name: SiteDefaults.GOLD_NUDGES for name in ("gold_nudge_high", "gold_nudge_medium", "gold_nudge_low")}}


def hint(name):
    """'Default: 30 days' / 'Default: Last seen' (the value in code, what Reset to default restores)."""
    value = SiteDefaults.code_default(name)
    shown = dict(choice_fields().get(name, [])).get(value, value)
    unit = UNITS.get(name, "")
    return f"Default: {shown} {unit}".strip()


class DefaultsForm(VersionedForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, choices in choice_fields().items():
            self.fields[name] = forms.ChoiceField(label=self.fields[name].label, choices=choices, initial=SiteDefaults.code_default(name))
        for name in FIELDS:
            field = self.fields[name]
            if isinstance(field, forms.IntegerField):
                limits = {v.__class__.__name__: v.limit_value for v in SiteDefaults._meta.get_field(name).validators}
                low, high = limits.get("MinValueValidator"), limits.get("MaxValueValidator")
                field.min_value, field.max_value = low, high
                field.widget.attrs.update({"min": low, "max": high})

    class Meta:
        model = SiteDefaults
        fields = FIELDS
