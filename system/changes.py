"""The change log. A receiver on django-simple-history's `post_create_historical_record` turns each history row of a
tracked model into SystemChange rows (one per changed field, old and new). Undo is `services.undo_change`: it saves the
old value as a new change, so history is never deleted."""
import datetime
import decimal
import threading
import uuid

from django.apps import apps
from django.db import models
from simple_history.signals import post_create_historical_record

# model (app_label.model) -> System section. Fields can override (FIELD_SECTIONS) because SiteSettings serves three sections.
MODEL_SECTIONS = {
    "plans.sitesettings": "settings",
    "plans.plan": "plans",
    "plans.openingrule": "hours",
    "plans.closure": "hours",
    "gold.goldchoice": "gold",
    "gold.goldsignalsource": "gold",
    "gold.goldrule": "gold",
    "journey.question": "journey",
    "journey.option": "journey",
    "journey.suggestionrule": "journey",
    "notifications.notificationtemplate": "emails",
}
FIELD_SECTIONS = {
    ("plans.sitesettings", "gold_approver_emails"): "emails",
    ("plans.sitesettings", "gold_approver_cc"): "emails",
    ("plans.sitesettings", "contact_email"): "emails",
    ("plans.sitesettings", "vat_rate"): "plans",
    ("plans.sitesettings", "capacity"): "hours",
    ("plans.sitesettings", "slot_length_minutes"): "hours",
    ("plans.sitesettings", "slot_step_minutes"): "hours",
    ("plans.sitesettings", "booking_notice_minutes"): "hours",
}
SECTION_LABELS = {
    "plans": "Plans and pricing", "hours": "Hours and closures", "gold": "Gold rules", "journey": "Journey",
    "emails": "Emails", "settings": "Settings", "team": "Team",
}
SKIP_FIELDS = {"id", "created_at", "updated_at", "singleton_key"}

_context = threading.local()


def start_batch():
    """One id per System request: every change saved while it runs shares it."""
    _context.batch = uuid.uuid4()
    return _context.batch


def current_batch():
    return getattr(_context, "batch", None)


def end_batch():
    _context.batch = None


def section_for(model_label, field=""):
    return FIELD_SECTIONS.get((model_label, field)) or MODEL_SECTIONS.get(model_label, "settings")


def to_json(value):
    """A value as plain JSON (Decimal and dates as text); `from_json` reverses it through the model field."""
    if isinstance(value, (decimal.Decimal, uuid.UUID)):
        return str(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, (list, dict, str, int, float, bool)) or value is None:
        return value
    return str(value)


def from_json(field, value):
    return value if value is None else field.to_python(value)


def tracked_fields(model):
    return [f for f in model._meta.concrete_fields if f.name not in SKIP_FIELDS and not f.primary_key]


def is_undoable_field(field):
    return not isinstance(field, models.FileField) and not field.auto_created and field.editable


def current_user_label(user):
    return (getattr(user, "email", "") or "") if user is not None else ""


def record(history_instance, instance, history_user, **_):
    """Receiver. Created rows without a person (seed scripts) are not listed; changes without a person are (a shell edit
    matters), shown as 'a script'."""
    from .models import SystemChange

    model_label = instance._meta.label_lower
    if model_label not in MODEL_SECTIONS:
        return
    kind_code = history_instance.history_type
    base = {
        "model_label": model_label, "object_pk": str(instance.pk), "object_repr": str(instance)[:200],
        "user": history_user if history_user and history_user.pk else None, "user_label": current_user_label(history_user),
        "history_id": history_instance.pk, "undo_of_id": getattr(_context, "undo_of", None), "batch_id": current_batch(),
    }
    if kind_code in ("+", "-"):
        if kind_code == "+" and (history_user is None or model_label == "plans.sitesettings"):  # seeds, and the singleton's first load
            return
        kind = SystemChange.CREATED if kind_code == "+" else SystemChange.DELETED
        SystemChange.objects.create(section=section_for(model_label), kind=kind, **base)
        return
    previous = type(history_instance).objects.filter(**{instance._meta.pk.attname: instance.pk}).exclude(pk=history_instance.pk)
    previous = previous.order_by("-history_date", "-history_id").first()
    if previous is None:
        return
    rows = []
    for field in tracked_fields(instance._meta.model):
        old, new = getattr(previous, field.attname), getattr(history_instance, field.attname)
        if old != new:
            rows.append(SystemChange(
                section=section_for(model_label, field.name), kind=SystemChange.UPDATED, field=field.name,
                old_value=to_json(old), new_value=to_json(new), **base))
    SystemChange.objects.bulk_create(rows)


def connect():
    """Connect to every tracked model's history class (dispatch_uid keeps it to once)."""
    for label in MODEL_SECTIONS:
        model = apps.get_model(label)
        post_create_historical_record.connect(
            record, sender=model.history.model, dispatch_uid=f"system-changes-{label}", weak=False)


class undoing:
    """Context manager: changes saved inside are linked to the entry being undone."""

    def __init__(self, change_id):
        self.change_id = change_id

    def __enter__(self):
        _context.undo_of = self.change_id

    def __exit__(self, *exc):
        _context.undo_of = None
