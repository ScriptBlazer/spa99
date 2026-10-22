from django import template

from content import services

register = template.Library()


@register.simple_tag
def page_content(page_key):
    """{% page_content "home" as home %} then {{ home.hero.heading }}."""
    return services.page_content(page_key)
