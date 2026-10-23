"""Plain sentences for the audit log, made when a change is written and stored with it:
'Changed Tier 1 · Price ex VAT from £299.00 to £319.00'. Money, percent, on/off, times and choices are formatted; lists are
summarised. Pure functions (no queries)."""
import datetime
import decimal
import re

from django.db import models

from .templatetags.system_ui import human

MAX = 80


def _short(text):
    text = str(text)
    return text if len(text) <= MAX else text[: MAX - 1].rstrip() + "…"


def _number(text):
    return re.fullmatch(r"-?\d+(\.\d+)?", text) is not None


def _item_name(item):
    if isinstance(item, dict):
        for key in ("label", "name", "key", "slug", "title"):
            if item.get(key):
                return str(item[key])
        return "item"
    return str(item)


def _list(value):
    if not value:
        return "none"
    if all(not isinstance(v, (dict, list)) for v in value):
        return _short(", ".join(str(v) for v in value))
    names = ", ".join(_item_name(v) for v in value[:3]) + ("…" if len(value) > 3 else "")
    return f"{len(value)} item{'s' if len(value) != 1 else ''} ({names})"


def show(field, value):
    """One stored JSON value as short readable text. `field` is the model field (or None for a name only)."""
    name = getattr(field, "name", field or "") or ""
    if value is None or value == "":
        return "empty"
    if isinstance(value, bool):
        return ("on" if value else "off") if name.endswith("_open") or name in ("is_active", "active", "visible") else ("yes" if value else "no")
    if hasattr(field, "flatchoices") and field.flatchoices:
        label = dict((str(k), v) for k, v in field.flatchoices).get(str(value))
        if label:
            return str(label)
    if isinstance(value, list):
        return _list(value)
    if isinstance(value, dict):
        return _short(", ".join(f"{k}: {show(None, v)}" for k, v in value.items())) or "none"
    text = str(value)
    if _number(text):
        if "price" in name:
            return f"£{decimal.Decimal(text):,.2f}"
        if name.endswith("_rate") or name.endswith("percent") or name.endswith("_pct"):
            return f"{decimal.Decimal(text).normalize():f}%"
        if isinstance(field, models.DecimalField):
            return f"{decimal.Decimal(text).normalize():f}"
    if isinstance(field, models.TimeField):
        try:
            return datetime.time.fromisoformat(text).strftime("%H:%M")
        except ValueError:
            pass
    if isinstance(field, models.DateTimeField):
        try:
            return datetime.datetime.fromisoformat(text).strftime("%-d %b %Y %H:%M")
        except ValueError:
            pass
    elif isinstance(field, models.DateField):
        try:
            return datetime.date.fromisoformat(text).strftime("%-d %b %Y")
        except ValueError:
            pass
    return _short(text)


def _what(obj_repr, field_name):
    obj_repr = (obj_repr or "").strip()
    label = human(field_name) if field_name else ""
    return f"{obj_repr} · {label}" if obj_repr and label else (label or obj_repr or "a row")


def _diff(old, new):
    """For two lists of items: ' (added: X; removed: Y)' by item name, else ''."""
    if not (isinstance(old, list) and isinstance(new, list)):
        return ""
    before, after = [_item_name(v) for v in old], [_item_name(v) for v in new]
    added, removed = [n for n in after if n not in before], [n for n in before if n not in after]
    parts = ([f"added: {', '.join(added[:3])}"] if added else []) + ([f"removed: {', '.join(removed[:3])}"] if removed else [])
    return f" ({'; '.join(parts)})" if parts else ""


def change_sentence(kind, model, object_repr, field_name="", old=None, new=None, undo=False):
    """The sentence for one change entry. `model` is the model class (or None)."""
    verbose = str(model._meta.verbose_name) if model is not None else ""
    if kind == "created":
        return f"Added {verbose + ' · ' if verbose else ''}{object_repr}".strip()
    if kind == "deleted":
        return f"Deleted {verbose + ' · ' if verbose else ''}{object_repr}".strip()
    field = model._meta.get_field(field_name) if model is not None and field_name and field_name in {f.name for f in model._meta.get_fields()} else None
    what = _what(object_repr, field_name)
    if undo:
        return f"Put back {what} to {show(field, new)} (was {show(field, old)})"
    return f"Changed {what} from {show(field, old)} to {show(field, new)}{_diff(old, new)}"


def team_sentence(field_name, person, old, new):
    if field_name == "is_active":
        return f"{'Reactivated' if new else 'Deactivated'} {person}"
    if field_name == "roles":
        return f"Changed roles for {person} from {', '.join(old) or 'none'} to {', '.join(new) or 'none'}"
    return f"Changed {human(field_name)} for {person} from {show(field_name, old)} to {show(field_name, new)}"
