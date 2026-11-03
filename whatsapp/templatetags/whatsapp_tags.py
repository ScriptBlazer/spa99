from django import template

from .. import formatting

register = template.Library()


@register.filter
def wa_format(value):
    """WhatsApp formatting as safe HTML (escaped first). {{ message.body|wa_format }}"""
    return formatting.render(value)


def _local(value):
    from datetime import datetime

    from django.utils import timezone

    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if value is None:
        return None
    return timezone.localtime(value) if timezone.is_aware(value) else value


@register.filter
def wa_when(value):
    """The chat list's time: today "14:32", yesterday "Yesterday", within 7 days "Mon", else "3 Nov"."""
    from django.utils import timezone

    d = _local(value)
    if d is None:
        return ""
    days = (timezone.localdate() - d.date()).days
    if days <= 0:
        return d.strftime("%H:%M")
    if days == 1:
        return "Yesterday"
    if days < 7:
        return d.strftime("%a")
    return f"{d.day} {d.strftime('%b')}"


@register.filter
def wa_initials(name):
    """"Daniel Cohen" -> "DC", "Daniel" -> "D". Empty when the name starts with a digit or a plus (a bare number)."""
    words = [w for w in (name or "").replace("-", " ").split() if w]
    if not words or not words[0][0].isalpha():
        return ""
    return (words[0][0] + (words[-1][0] if len(words) > 1 else "")).upper()
