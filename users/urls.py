from django.contrib.auth import views as auth_views
from django.urls import path

urlpatterns = [
    # LoginView is public by design (Django marks it login_not_required).
    path("login/", auth_views.LoginView.as_view(template_name="users/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),  # POST only
]
