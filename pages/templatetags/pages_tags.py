from django import template

from pages import services

register = template.Library()


@register.simple_tag
def hours_summary():
    return services.hours_summary()


@register.filter
def split_main(label):
    return services.split_label(label)[0]


@register.filter
def split_sub(label):
    return services.split_label(label)[1]


@register.simple_tag
def interest_cards():
    """The memberships a person can register interest in, as plan cards (name, price, character)."""
    from users.services import interest_plans

    return [services.plan_card(plan) for plan in interest_plans()]


@register.simple_tag(takes_context=True)
def account_greeting(context):
    return services.greeting(context["request"].user)


@register.simple_tag
def signin_shell():
    """{% signin_shell as shell %}: heading, lead, caption, picture and address line for the sign-in shell (SIGN-IN.md)."""
    return services.signin_shell()


@register.simple_tag
def tour_modules():
    """{% tour_modules as mods %}: slug -> hashed static URL of each 3D room module that exists (common/js/tour/rooms/<slug>.js).
    Rooms without a module are simply absent, so the tour opens their photo page instead (docs/features/virtual-tour.md)."""
    from django.contrib.staticfiles import finders
    from django.templatetags.static import static

    mods = {}
    for slug in services.tour_slugs():
        rel = f"common/js/tour/rooms/{slug}.js"
        if finders.find(rel):
            mods[slug] = static(rel)
    return mods
