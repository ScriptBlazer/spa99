"""Office host only (config.urls_office). Email chat."""
from django.urls import path

from . import views as v

urlpatterns = [
    path("email/", v.inbox, name="office_email"),
    path("email/unread/", v.unread, name="office_email_unread"),
    path("email/new/", v.new, name="office_email_new"),
    path("email/people/", v.people, name="office_email_people"),
    path("email/file/<int:pk>/", v.file, name="office_email_file"),
    path("email/message/<int:pk>/frame/", v.frame, name="office_email_frame"),
    path("email/<uuid:pk>/", v.thread, name="office_email_thread"),
    path("email/<uuid:pk>/messages/", v.messages_before, name="office_email_messages"),
    path("email/<uuid:pk>/poll/", v.poll, name="office_email_poll"),
    path("email/<uuid:pk>/send/", v.send, name="office_email_send"),
    path("email/<uuid:pk>/read/", v.read, name="office_email_read"),
    path("email/<uuid:pk>/link/", v.link, name="office_email_link"),
    path("email/<uuid:pk>/delete/", v.delete, name="office_email_delete"),
    path("email/<uuid:pk>/retry/<int:message>/", v.retry, name="office_email_retry"),
    path("people/<uuid:pk>/email-chat/", v.start_person, name="office_person_email_chat"),
    path("leads/<uuid:pk>/email-chat/", v.start_lead, name="office_lead_email_chat"),
    path("gold/<uuid:pk>/email-chat/", v.start_gold, name="office_gold_email_chat"),
]
