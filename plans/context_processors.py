"""Makes `site_settings` available in every template (stage switches, wording, contact email).
Lazy on purpose: the database is only asked when a template actually uses it, so error pages never depend on it."""
from django.conf import settings
from django.utils.functional import SimpleLazyObject

from .models import SiteSettings


def site(request):
    # gc_export: local dev only; lets gold-card-3d.js render the still (docs/design/GOLD-CARD-3D.md 4.3) with ?gc-export=1.
    return {"site_settings": SimpleLazyObject(SiteSettings.load), "gc_export": settings.DEBUG, "site_webgl": settings.SITE_WEBGL}
