"""Public routes (the public site only)."""
from django.urls import path

from . import views

urlpatterns = [
    path("unsubscribe/<str:token>/", views.unsubscribe, name="unsubscribe"),
    path("email-image/<uuid:image_id>.<str:ext>", views.email_image, name="email_image_file"),
    path("email-image/<uuid:image_id>/", views.email_image, name="email_image"),
    path("invite/<str:token>/", views.invite_link, name="invite_link"),
]
