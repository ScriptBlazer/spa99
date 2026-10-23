"""Template helpers for the System look: the environment, human field names, shown values, and which changes are risky
(they open the confirm dialog). Pure formatting; no queries."""
import re

from django import template
from django.conf import settings

register = template.Library()

# field name -> (singular, plural, consequence). A change to any of these asks for confirmation (docs/design/SYSTEM.md 4.4).
RISKY = {
    "price_ex_vat": ("price", "prices", "Members see the new price at once."),
    "price": ("price", "prices", "Members see the new price at once."),
    "vat_rate": ("VAT rate", "VAT rates", "Every price shown includes the new rate at once."),
    "register_interest_open": ("stage switch", "stage switches", "The public site changes at once."),
    "subscribe_open": ("stage switch", "stage switches", "The public site changes at once."),
    "booking_open": ("stage switch", "stage switches", "Booking opens or closes to the public at once."),
    "opening_date": ("opening date", "opening dates", "The date shown to the public changes at once."),
    "capacity": ("capacity", "capacities", "Booking availability changes at once."),
    "gold_approver_emails": ("recipient list", "recipient lists", "Gold applications go to the new list at once."),
    "gold_approver_cc": ("recipient list", "recipient lists", "Copies go to the new list at once."),
    "contact_email": ("contact address", "contact addresses", "The site shows and replies from the new address at once."),
    "roles": ("role", "roles", "Access changes at once."),
    "is_active": ("account", "accounts", "Access changes at once."),
}
STAGES = ("register_interest_open", "subscribe_open", "booking_open")
WIDE = {"opening_text", "join_wording"}


def _risk(name):
    if name in RISKY:
        return RISKY[name]
    if "threshold" in name:
        return ("Gold threshold", "Gold thresholds", "Gold applications are judged on the new value at once.")
    return None


@register.simple_tag(takes_context=True)
def system_env(context):
    """'dev' or 'live'. A view or context processor may set `system_env`; otherwise DEBUG decides (dev settings have it on)."""
    value = context.get("system_env")
    if value in ("dev", "live"):
        return value
    return "dev" if settings.DEBUG else "live"


@register.filter
def risky_noun(name):
    risk = _risk(name or "")
    return risk[0] if risk else ""


@register.filter
def risky_plural(name):
    risk = _risk(name or "")
    return risk[1] if risk else ""


@register.filter
def risky_line(name):
    risk = _risk(name or "")
    return risk[2] if risk else ""


@register.filter
def is_risky(name):
    return _risk(name or "") is not None


@register.filter
def is_stage(name):
    return name in STAGES


@register.filter
def is_wide(name):
    return name in WIDE


@register.filter
def human(name):
    """price_ex_vat -> Price ex VAT."""
    text = re.sub(r"_+", " ", name or "").strip()
    text = re.sub(r"\bvat\b", "VAT", text, flags=re.I)
    text = re.sub(r"\bgold\b", "Gold", text, flags=re.I)
    return text[:1].upper() + text[1:]


@register.filter
def what(change):
    """'Gold · Price ex VAT': the row, then the field (no model names)."""
    repr_ = (change.object_repr or "").strip()
    field = human(change.field)
    if change.kind == "created":
        return f"{repr_} (created)"
    if change.kind == "deleted":
        return f"{repr_} (deleted)"
    return f"{repr_} · {field}" if repr_ and field else (field or repr_)


@register.filter
def shown(value, field=""):
    """A stored JSON value as short text: money with £ for price fields, lists joined, booleans Yes/No."""
    if value is None or value == "":
        return "empty"
    if isinstance(value, bool):
        if (field or "").endswith("_open"):
            return "On" if value else "Off"
        return "Yes" if value else "No"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) or "none"
    text = str(value)
    if "price" in (field or "") and re.fullmatch(r"-?\d+(\.\d+)?", text):
        return f"£{float(text):,.2f}"
    if field == "vat_rate" and re.fullmatch(r"-?\d+(\.\d+)?", text):
        return f"{float(text):.1f}%"
    return text


@register.filter
def shown_stage(value):
    return "On" if value else "Off"


@register.simple_tag
def system_idle_seconds():
    return getattr(settings, "SYSTEM_UNLOCK_SECONDS", 900)


@register.filter
def split_extra(tags, prefix):
    """The value after `prefix:` in a message's extra tags (a message can carry an undo URL as 'undo:/changes/<id>/undo/')."""
    for tag in (tags or "").split():
        if tag.startswith(prefix + ":"):
            return tag[len(prefix) + 1:]
    return ""


@register.simple_tag
def office_url():
    return getattr(settings, "OFFICE_URL", "")


@register.simple_tag
def cell(field, pk, label=""):
    """A form field as a table-cell control tied to the row's own form (`<form id="f-<pk>">` in the row's first cell), so a
    whole table row saves as one small form. Booleans get the toggle."""
    from django.utils.html import format_html

    attrs = {"form": f"f-{pk}", "aria-label": label or str(field.label)}
    if field.errors:
        attrs.update({"aria-invalid": "true"})
    widget = field.as_widget(attrs=attrs)
    if getattr(field.field.widget, "input_type", "") == "checkbox":
        return format_html('<span class="sys-toggle">{}</span>', widget)
    return widget


@register.filter
def error_text(form):
    """'Price ex VAT: Enter a price. Order: ...' for a form's errors, shown under its table row."""
    parts = []
    for name, errors in form.errors.items():
        label = form.fields[name].label if name in form.fields else ""
        parts.append(f"{label}: {' '.join(errors)}" if label else " ".join(errors))
    return " ".join(parts)
