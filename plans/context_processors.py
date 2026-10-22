"""Makes `site_settings` available in every template (stage switches, wording, contact email).
Lazy on purpose: the database is only asked when a template actually uses it, so error pages never depend on it."""
from django.utils.functional import SimpleLazyObject

from .models import SiteSettings


def site(request):
    return {"site_settings": SimpleLazyObject(SiteSettings.load)}
