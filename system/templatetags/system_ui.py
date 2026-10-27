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
    "annual_fee": ("annual fee", "annual fees", "The Gold Card fee on the compare table changes at once."),
    "vat_rate": ("VAT rate", "VAT rates", "Every price shown includes the new rate at once."),
    "register_interest_open": ("stage switch", "stage switches", "The public site changes at once."),
    "memberships_public": ("stage switch", "stage switches", "The Memberships page and its links appear or disappear for the public at once."),
    "journey_email_gate": ("switch", "switches", "Visitors see the suggested membership with or without giving an email, from now on."),
    "subscribe_open": ("stage switch", "stage switches", "The public site changes at once."),
    "booking_open": ("stage switch", "stage switches", "Booking opens or closes to the public at once."),
    "opening_date": ("opening date", "opening dates", "The date shown to the public changes at once."),
    "capacity": ("capacity", "capacities", "Booking availability changes at once."),
    "gold_approver_emails": ("recipient list", "recipient lists", "Gold applications go to the new list at once."),
    "gold_approver_cc": ("recipient list", "recipient lists", "Copies go to the new list at once."),
    "contact_email": ("contact address", "contact addresses", "The site shows and replies from the new address at once."),
    "lock_idle_minutes": ("lock setting", "lock settings", "System locks after the new idle time at once."),
    "max_sign_in_hours": ("lock setting", "lock settings", "Every System sign-in ends after the new limit."),
    "gold_invite_days": ("link validity", "link validities", "Gold invites made from now on work for the new number of days."),
    "gold_approval_days": ("link validity", "link validities", "Approval email links, including ones already sent, work for the new number of days."),
    "register_invite_days": ("link validity", "link validities", "Register invites made from now on work for the new number of days."),
    "office_session_days": ("sign-in length", "sign-in lengths", "Office sign-ins from now on last the new number of days."),
    "email_confirm_hours": ("link validity", "link validities", "Confirmation links, including ones already sent, work for the new number of hours."),
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
    from system import services

    return services.lock_idle_seconds()


@register.simple_tag(takes_context=True)
def system_remaining(context):
    """Seconds left before System locks, as the server sees it now (0 when there is no request)."""
    from system import services

    request = context.get("request")
    return services.remaining_seconds(request.session) if request is not None else 0


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
    if getattr(field.field.widget, "input_type", "") == "checkbox":
        attrs["role"] = "switch"
        return format_html('<label class="sys-toggle">{}</label>', field.as_widget(attrs=attrs))
    return field.as_widget(attrs=attrs)


@register.simple_tag
def token(field, pk):
    """The row's version token (hidden), tied to the row's own `<form id="f-<pk>">` like `cell`. Empty when the form has none."""
    return field.as_widget(attrs={"form": f"f-{pk}"}) if field is not None and field != "" else ""


@register.simple_tag
def switch(field, text=True):
    """The one switch: a real checkbox (role=switch) with a 36x20 track, and On/Off beside it (system.js keeps it current)."""
    from django.utils.html import format_html

    widget = field.as_widget(attrs={"role": "switch"})
    if not text:
        return format_html('<label class="sys-toggle">{}</label>', widget)
    return format_html('<label class="sys-toggle">{} <span data-system-state>{}</span></label>', widget, "On" if field.value() else "Off")


@register.filter
def error_text(form):
    """'Price ex VAT: Enter a price. Order: ...' for a form's errors, shown under its table row."""
    parts = []
    for name, errors in form.errors.items():
        label = form.fields[name].label if name in form.fields else ""
        parts.append(f"{label}: {' '.join(errors)}" if label else " ".join(errors))
    return " ".join(parts)


@register.filter
def error_spans(form, prefix=""):
    """The same sentence as error_text, but each error is a `data-problem` span the problems dialog can read (field, label,
    message), so a failed row save lists its problems the way every other form does. `prefix` (the row name) leads the label."""
    from django.utils.html import format_html, format_html_join

    rows = []
    for name, errors in form.errors.items():
        known = name in form.fields
        label = str(form.fields[name].label or "") if known else ""
        rows.append((form.add_prefix(name) if known else "", " · ".join(part for part in (str(prefix), label) if part), " ".join(errors),
                     f"{label}: " if label else ""))
    return format_html_join(" ", '<span data-problem data-problem-field="{}" data-problem-label="{}" data-problem-message="{}">{}{}</span>',
                            ((field, label, message, lead, message) for field, label, message, lead in rows))


# ---------- audit log helpers ----------

@register.filter
def person(label):
    """'moishe@x.com' -> 'Moishe' (the short name; the full email is in the title and the drawer)."""
    name = (label or "").split("@")[0].replace(".", " ").replace("_", " ").strip()
    return name.title() if name else "A script"


_OS = (("iPhone", "iOS"), ("iPad", "iPadOS"), ("Android", "Android"), ("CrOS", "ChromeOS"), ("Windows", "Windows"), ("Mac OS X", "macOS"),
       ("Macintosh", "macOS"), ("Linux", "Linux"))
_BROWSERS = (("Edg", "Edge"), ("OPR", "Opera"), ("Firefox", "Firefox"), ("FxiOS", "Firefox"), ("CriOS", "Chrome"), ("Chrome", "Chrome"), ("Version", "Safari"))


@register.filter
def browser(ua):
    """A user agent as 'Safari 18 on macOS' (the full text stays in the drawer). Unknown agents show their first words."""
    ua = ua or ""
    if not ua:
        return ""
    system = next((name for key, name in _OS if key in ua), "")
    name = version = ""
    for key, label in _BROWSERS:
        found = re.search(rf"\b{key}/(\d+)", ua)
        if found:
            name, version = label, found.group(1)
            break
    if not name:
        found = re.match(r"([A-Za-z][\w.\- ]*?)/(\d+)", ua)
        if found:
            name, version = found.group(1), found.group(2)
    if not name:
        return ua[:40]
    text = f"{name} {version}".strip()
    return f"{text} on {system}" if system else text


@register.filter
def short_hash(value):
    """a3f91c…e209bc: the first and last six characters."""
    value = value or ""
    return f"{value[:6]}…{value[-6:]}" if len(value) > 14 else value



@register.filter
def group_label(key):
    """The name of a group-send audience ("opted_in" -> "Opted in to news"), for the Group sends list."""
    from mailings.segments import GROUPS

    group = GROUPS.get(key)
    return group.label if group else (key or "")


@register.filter
def minus(value, other):
    """value - other for counts in templates (invited = everyone in an import minus the skipped)."""
    try:
        return int(value) - int(other)
    except (TypeError, ValueError):
        return value
