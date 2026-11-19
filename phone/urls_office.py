"""Office host, mounted at /calls/."""
from django.urls import path

from . import views_office as views

urlpatterns = [
    path("", views.call_list, name="office_calls"),
    path("<uuid:pk>/", views.call_detail, name="office_call"),
    path("<uuid:pk>/audio/", views.call_audio, name="office_call_audio"),
    path("<uuid:pk>/heard/", views.call_heard, name="office_call_heard"),
]
