"""Public site (spa99.uk). Pages arrive with the website feature."""
from django.urls import path

from common.views import health

urlpatterns = [
    path("health/", health, name="health"),  # public: monitoring
]
