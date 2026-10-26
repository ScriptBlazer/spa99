"""Makes `site_settings` available in every template (stage switches, wording, contact email).
Lazy on purpose: the database is only asked when a template actually uses it, so error pages never depend on it."""
from django.conf import settings
from django.utils.functional import SimpleLazyObject

from . import sales
from .models import SiteSettings


def site(request):
    # gc_export: local dev only; lets gold-card-3d.js render the still (docs/design/GOLD-CARD-3D.md 4.3) with ?gc-export=1.
    return {"site_settings": SimpleLazyObject(SiteSettings.load), "gc_export": settings.DEBUG, "site_webgl": settings.SITE_WEBGL}


def sale(request):
    """`sale_bar` for public pages: {id, name, percent, plans_text, plan_slugs, months, starts_at, ends_at (ISO), preview} or None.
    Lazy (one query, only when a template reads it); None on the office, control and system hosts and when no sale is on."""
    return {"sale_bar": SimpleLazyObject(lambda: sales.sale_bar_for_request(request))}
