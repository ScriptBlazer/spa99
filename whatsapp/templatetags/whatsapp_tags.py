from django import template

from .. import formatting

register = template.Library()


@register.filter
def wa_format(value):
    """WhatsApp formatting as safe HTML (escaped first). {{ message.body|wa_format }}"""
    return formatting.render(value)
