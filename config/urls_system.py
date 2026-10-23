"""Spa 99 System (system.spa99.uk): developers only. Chosen by common.middleware.HostRoutingMiddleware. Everyone who may
not be here gets a plain 404 (system.permissions); the only open pages are health, robots.txt and the sign-in."""
from django.contrib.auth.decorators import login_not_required
from django.http import HttpResponse
from django.urls import include, path

from common.views import health
from system import views

urlpatterns = [
    path("health/", health),  # public: monitoring
    path("robots.txt", login_not_required(lambda request: HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain"))),
    path("login/", views.SystemLoginView.as_view(), name="login"),
    path("logout/", views.sign_out, name="logout"),  # POST only
    path("", include("system.urls")),
]
