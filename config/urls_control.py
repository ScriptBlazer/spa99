"""Spa 99 Control (control.spa99.uk): the building control room. Parked until the hardware is installed; for now a
placeholder. The business back office is the Office (config.urls_office). Chosen by common.middleware.HostRoutingMiddleware."""
from django.contrib import admin
from django.conf import settings
from django.urls import include, path

from common.views import health

from . import views

urlpatterns = [
    path("", views.control_index, name="control_index"),
    path("health/", health),  # public: monitoring
    path("", include("users.urls")),  # staff sign-in
    # Hidden Django admin: superuser fallback only. Path is set by ADMIN_PATH.
    path(settings.ADMIN_PATH, admin.site.urls),
]
