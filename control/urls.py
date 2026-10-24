from django.urls import path

from . import views

urlpatterns = [
    path("", views.rooms, name="control_rooms"),
    path("schedule/", views.schedule, name="control_schedule"),
    path("screens/", views.screens, name="control_screens"),
    path("password/", views.ControlPasswordView.as_view(), name="control_password"),
]
