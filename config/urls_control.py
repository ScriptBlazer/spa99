"""Spa 99 Control (control.spa99.uk): the building control room. A DEMO for now (docs/features/control.md): pretend
values, nothing reaches hardware. The business back office is the Office (config.urls_office). Chosen by
common.middleware.HostRoutingMiddleware. Admin level and up; everyone else gets a plain 404."""
from django.contrib import admin
from django.core.files.storage import default_storage
from django.conf import settings
from django.http import Http404
from django.urls import include, path, re_path

from common import levels
from common.permissions import level_required
from django.views.static import serve

from common.views import health

urlpatterns = [
    path("health/", health),  # public: monitoring
    path("", include("users.urls")),  # staff sign-in
    path("", include("control.urls")),  # Rooms, Schedule, Screens, change password
    # Hidden Django admin: superuser fallback only. Path is set by ADMIN_PATH.
    path(settings.ADMIN_PATH, admin.site.urls),
]

# Local development only: serve the Library files (control/media/ only) from the local media folder to Admin level and up
# (live uses signed S3 URLs).
def _dev_media(request, path):
    if not path.startswith("control/media/"):
        raise Http404
    return serve(request, path, document_root=default_storage.location)


if settings.DEBUG and hasattr(default_storage, "location") and not getattr(default_storage, "bucket_name", None):
    urlpatterns += [re_path(r"^media/(?P<path>.*)$", level_required(levels.ADMIN, deny=Http404)(_dev_media))]
