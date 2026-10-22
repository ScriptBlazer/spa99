"""Public site (spa99.uk). Page views arrive with the website feature; these are the data endpoints and account routes."""
from django.urls import include, path

from common.views import health

urlpatterns = [
    path("health/", health, name="health"),  # public: monitoring
    path("journey/", include("journey.urls")),
    path("gold/", include("gold.urls")),
    path("", include("users.urls")),  # login, logout
    path("", include("users.urls_public")),  # register interest, verify, reset, account
]
