from django import template

from pages import services

register = template.Library()


@register.simple_tag
def hours_summary():
    return services.hours_summary()


@register.filter
def split_main(label):
    return (label or "").partition(" (")[0].strip()


@register.filter
def split_sub(label):
    _, sep, rest = (label or "").partition(" (")
    return rest.rstrip(")").strip() if sep else ""


@register.simple_tag
def interest_cards():
    """The memberships a person can register interest in, as plan cards (name, price, character)."""
    from users.services import interest_plans

    return [services.plan_card(plan) for plan in interest_plans()]


@register.simple_tag(takes_context=True)
def account_greeting(context):
    return services.greeting(context["request"].user)
