from django.urls import path

from . import views

app_name = "gold"

urlpatterns = [
    path("options/", views.options, name="options"),
    path("apply/", views.apply, name="apply"),
    path("invite/<str:token>/", views.invite_setup, name="invite_setup"),
]
