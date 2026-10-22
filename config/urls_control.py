"""Spa 99 Control (control.spa99.uk). Chosen by common.middleware.HostRoutingMiddleware."""
from django.contrib import admin
from django.conf import settings
from django.urls import include, path

from common.views import health

from . import views

urlpatterns = [
    path("", views.control_index, name="control_index"),
    path("health/", health),  # public: monitoring
    path("", include("users.urls")),
    path("insights/", include("insights.urls")),  # statistics JSON, staff roles only
    # Hidden Django admin: superuser fallback only. Path is set by ADMIN_PATH.
    path(settings.ADMIN_PATH, admin.site.urls),
]
