"""Public host: Twilio's webhooks."""
from django.urls import path

from . import views

urlpatterns = [
    path("voice/", views.voice, name="phone_voice"),
    path("after-record/", views.after_record, name="phone_after_record"),
    path("recording/", views.recording, name="phone_recording"),
]
