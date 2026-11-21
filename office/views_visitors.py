"""Analytics > Visitors: the page and the link maker's address endpoint (docs/features/analytics-design.md). The figures come from the
stored snapshot (`selectors.visitors`), the one live reading from `insights.live`; the wording lives in `visitors_page`."""
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from insights import campaigns, live
from system import defaults

from . import selectors, visitors_page
from .permissions import developer
from .views import _remembered_range


@developer
@require_GET
@never_cache
def analytics_visitors(request):
    name = _remembered_range(request, "office_range_analytics", selectors.ANALYTICS_RANGES, defaults.get(request).analytics_range)
    context = visitors_page.build(selectors.visitors(name, request), live.live_now())
    return render(request, "office/analytics_visitors.html", {**context, "section": "analytics"})


@developer
@require_GET
@never_cache
def analytics_link(request):
    """The link maker's address, built by `campaigns.build_link` (the one place the cleaning rules live). ?placement=&name=&page=
    Returns {name: the cleaned name, url: the full address, or '' until a placement, a name and a page are all chosen}."""
    placement, page = request.GET.get("placement", ""), request.GET.get("page", "")
    saved = campaigns.clean_utm(request.GET.get("name", ""), campaigns.LIMITS["campaign"])
    path = visitors_page.link_page_path(page)
    url = campaigns.build_link(path, placement, saved, base=settings.SITE_URL) if saved and path and placement in campaigns.PLACEMENTS else ""
    return JsonResponse({"name": saved, "url": url})
