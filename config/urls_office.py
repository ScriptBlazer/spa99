"""Spa 99 Office (office.spa99.uk): the business back office for staff (Owner, Manager, Viewer).
Chosen by common.middleware.HostRoutingMiddleware. Locked by default (LoginRequiredMiddleware); each office view
then checks the role."""
from django.contrib import admin
from django.conf import settings
from django.contrib.auth.decorators import login_not_required
from django.http import HttpResponse
from django.urls import include, path

from common.views import health

urlpatterns = [
    path("health/", health),  # public: monitoring
    path("robots.txt", login_not_required(lambda request: HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain"))),
    path("", include("users.urls")),  # staff sign-in and sign-out
    path("insights/", include("insights.urls")),  # the older statistics JSON, staff roles only
    path("", include("office.urls")),
    # Hidden Django admin on this host too (content, plans, hours, notifications stay there for now).
    path(settings.ADMIN_PATH, admin.site.urls),
]
