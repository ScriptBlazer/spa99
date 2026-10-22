"""Sign in / sign out. Included on both hosts: the public site and Spa 99 Control."""
from django.contrib.auth import views as auth_views
from django.urls import path

from .views import LoginView

urlpatterns = [
    # LoginView is public by design (Django marks it login_not_required). Rate limited per IP.
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),  # POST only
]
