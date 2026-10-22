"""Public site (spa99.uk): the website pages, the data endpoints (journey, Gold) and the account routes."""
from django.urls import include, path

from common.views import health

urlpatterns = [
    path("health/", health, name="health"),  # public: monitoring
    path("journey/", include("journey.urls")),
    path("gold/", include("gold.urls")),
    path("", include("users.urls")),  # login, logout
    path("", include("users.urls_public")),  # register interest, verify, reset, account
    path("", include("pages.urls")),  # the website pages, the journey and Gold application screens
]
