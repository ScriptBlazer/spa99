"""Analytics > Visitors: the page and the link maker's address endpoint (docs/features/analytics-design.md). The figures come from the
stored snapshot (`selectors.visitors`), the one live reading from `insights.live`; the wording lives in `visitors_page`."""
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from insights import campaigns, live
from system import defaults

from . import analytics_visitors as av, selectors, visitors_page
from .permissions import developer
from .views import _remembered_range


def _remembered_who(request):
    """?who=real|all wins and is remembered in the session like the range; otherwise the remembered one; real by default (A12)."""
    asked = request.GET.get("who")
    if asked in av.WHO:
        if request.session.get("office_who_visitors") != asked:
            request.session["office_who_visitors"] = asked
        return asked
    if asked is not None:
        return "real"  # a bad value is real (and is not remembered)
    return av.clean_who(request.session.get("office_who_visitors"))


@developer
@require_GET
@never_cache
def analytics_visitors(request):
    name = _remembered_range(request, "office_range_analytics", selectors.ANALYTICS_RANGES, defaults.get(request).analytics_range)
    who = _remembered_who(request)
    context = visitors_page.build(selectors.visitors(name, request, who), live.live_now(who=who))
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
