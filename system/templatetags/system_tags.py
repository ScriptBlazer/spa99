from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def inc_vat(price, vat_rate):
    """Display only: a price ex VAT plus the stored VAT rate (percent), to the penny. Nothing is saved from this."""
    try:
        return (Decimal(price) * (Decimal(100) + Decimal(vat_rate)) / Decimal(100)).quantize(Decimal("0.01"), ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return ""
