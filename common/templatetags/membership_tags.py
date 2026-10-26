"""The memberships switch for templates. Until `SiteSettings.memberships_public` is on, public pages point at the journey
instead of the Memberships page (signed-in team members still see the real link, so they can check the page)."""
from django import template
from django.urls import reverse

from pages.access import memberships_visible

register = template.Library()


@register.simple_tag(takes_context=True)
def memberships_shown(context):
    """True when the Memberships link may be shown to this visitor."""
    return memberships_visible(context.get("request"))


@register.simple_tag(takes_context=True)
def memberships_url(context):
    """The Memberships page, or the journey while the page is hidden."""
    return reverse("memberships") if memberships_visible(context.get("request")) else reverse("journey")
