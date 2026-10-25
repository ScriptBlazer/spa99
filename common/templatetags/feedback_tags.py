from django import template

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
