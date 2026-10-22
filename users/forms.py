"""Admin forms. (Sign-up forms come with the register-interest feature.)"""
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm as BaseUserChangeForm

from .models import User


class UserCreationForm(AdminUserCreationForm):
    class Meta:
        model = User
        fields = ("email",)


class UserChangeForm(BaseUserChangeForm):
    class Meta:
        model = User
        fields = "__all__"
