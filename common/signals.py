from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver
from django.utils import timezone

from .audit import record_login_event
from .models import LoginEvent


@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    record_login_event(LoginEvent.LOGIN, request, user=user)
    # Queryset update: skips model history on purpose (the LoginEvent is the record).
    get_user_model()._default_manager.filter(pk=user.pk).update(last_login=timezone.now())


@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    record_login_event(LoginEvent.LOGOUT, request, user=user)


@receiver(user_login_failed)
def on_login_failed(sender, credentials, request=None, **kwargs):
    attempted = credentials.get("email") or credentials.get("username") or ""
    record_login_event(LoginEvent.FAILED, request, attempted_email=str(attempted))
