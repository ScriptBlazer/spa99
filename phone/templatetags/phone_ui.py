"""Template helpers for the Calls pages."""
from django import template

register = template.Library()


@register.filter
def clock(seconds):
    """83 -> 1:23 (minutes and seconds, as a voicemail player shows it)."""
    try:
        total = max(int(seconds), 0)
    except (TypeError, ValueError):
        return ""
    return f"{total // 60}:{total % 60:02d}"
