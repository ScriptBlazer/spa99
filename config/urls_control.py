"""Spa 99 Control (control.spa99.uk): the building control room. A DEMO for now (docs/features/control.md): pretend
values, nothing reaches hardware. The business back office is the Office (config.urls_office). Chosen by
common.middleware.HostRoutingMiddleware. Admin level and up; everyone else gets a plain 404."""
from django.contrib import admin
from django.conf import settings
from django.urls import include, path

from common.views import health

urlpatterns = [
    path("health/", health),  # public: monitoring
    path("", include("users.urls")),  # staff sign-in
    path("", include("control.urls")),  # Rooms, Schedule, Screens, change password
    # Hidden Django admin: superuser fallback only. Path is set by ADMIN_PATH.
    path(settings.ADMIN_PATH, admin.site.urls),
]
