from django import template

register = template.Library()


@register.filter
def frac(value, bounds):
    """Where a slider's value sits between its bounds, 0 to 1 (the fill is drawn from this). `bounds` is "min,max"."""
    low, high = (float(x) for x in bounds.split(","))
    try:
        return round(min(1, max(0, (float(value) - low) / (high - low))), 4)
    except (TypeError, ValueError):
        return 0


@register.filter
def pos_style(item):
    """Inline left/width for a band on a lane."""
    return f"left:{item['pct']}%;width:{item['wpct']}%"


@register.filter
def meter(used, maximum):
    """How full the Library is, 0 to 1 (the meter bar is a scaleX of this)."""
    try:
        return round(min(1, max(0, float(used) / float(maximum))), 4)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0
