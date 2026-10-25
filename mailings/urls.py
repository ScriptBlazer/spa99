"""Public routes (the public site only)."""
from django.urls import path

from . import views

urlpatterns = [
    path("unsubscribe/<str:token>/", views.unsubscribe, name="unsubscribe"),
    path("invite/<str:token>/", views.invite_link, name="invite_link"),
]
