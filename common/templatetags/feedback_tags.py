import logging

from django import template
from django.utils.html import format_html

register = template.Library()

# Django message level tag -> toast kind (docs/design/FEEDBACK.md section 5). Unknown tags read as plain notes.
TOAST_KINDS = {"debug": "info", "info": "info", "success": "success", "warning": "warning", "error": "error"}


@register.filter
def toast_kind(level_tag):
    """{{ message.level_tag|toast_kind }}: success, info, warning or error."""
    tag = (str(level_tag or "").split() or [""])[0]
    return TOAST_KINDS.get(tag, "info")


@register.filter
def undo_url(extra_tags):
    """The undo link a message can carry as an extra tag ('undo:/changes/<id>/undo/'), else ''."""
    for tag in (extra_tags or "").split():
        if tag.startswith("undo:"):
            return tag[len("undo:"):]
    return ""


@register.simple_tag(takes_context=True)
def toast_times(context):
    """data attributes for the toast region: how long a toast stays (System > Defaults), in ms. feedback.js reads them and falls back
    to 4 s / 6 s. Never breaks a page: on any trouble it prints nothing."""
    try:
        from system import defaults

        d = defaults.get(context.get("request"))
        return format_html('data-toast-ms="{}" data-toast-long-ms="{}"', d.toast_seconds * 1000, d.toast_long_seconds * 1000)
    except Exception:  # noqa: BLE001
        logging.getLogger("spa99.common").warning("Toast times not read", exc_info=True)
        return ""
