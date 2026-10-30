"""Long text that must never be cut off silently: one line with an ellipsis, or a few lines then an ellipsis. The full text is
always in the title (hover) so nothing is lost. Styles: .u-truncate and .u-clamp-2 / .u-clamp-3 in components.css.

    {% load text_tags %}
    {% truncated person.email %}            one line, ellipsis
    {% truncated chat.preview lines=2 %}    up to two lines, then ellipsis
"""
from django import template
from django.utils.html import format_html

register = template.Library()

CLAMP_CLASSES = {1: "u-truncate", 2: "u-clamp-2", 3: "u-clamp-3"}


@register.simple_tag
def truncated(value, lines=1, empty=""):
    text = "" if value is None else str(value)
    if not text:
        return empty
    css = CLAMP_CLASSES.get(int(lines), "u-truncate")
    return format_html('<span class="{}" title="{}">{}</span>', css, text, text)
