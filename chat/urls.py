from django.urls import path

from . import views

app_name = "chat"

urlpatterns = [
    path("state/", views.state, name="state"),
    path("message/", views.message, name="message"),
    path("email/", views.email, name="email"),
]
