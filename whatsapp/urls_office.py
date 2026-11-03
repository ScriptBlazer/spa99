"""Office host only (config.urls_office). Chats, push controls, the manifest and the service worker."""
from django.urls import path

from . import pwa, views as v

urlpatterns = [
    path("manifest.webmanifest", pwa.manifest, name="office_manifest"),
    path("sw.js", pwa.service_worker, name="office_sw"),
    path("whatsapp/", v.inbox, name="office_whatsapp"),
    path("whatsapp/unread/", v.unread, name="office_whatsapp_unread"),
    path("whatsapp/templates/", v.templates, name="office_whatsapp_templates"),
    path("whatsapp/media/<int:pk>/", v.media, name="office_whatsapp_media"),
    path("whatsapp/push/config/", v.push_config, name="office_push_config"),
    path("whatsapp/push/subscribe/", v.push_subscribe, name="office_push_subscribe"),
    path("whatsapp/push/unsubscribe/", v.push_unsubscribe, name="office_push_unsubscribe"),
    path("whatsapp/push/mute/", v.push_mute, name="office_push_mute"),
    path("whatsapp/push/test/", v.push_test, name="office_push_test"),
    path("whatsapp/<uuid:pk>/", v.thread, name="office_whatsapp_thread"),
    path("whatsapp/<uuid:pk>/messages/", v.messages_before, name="office_whatsapp_messages"),
    path("whatsapp/<uuid:pk>/poll/", v.poll, name="office_whatsapp_poll"),
    path("whatsapp/<uuid:pk>/send/", v.send, name="office_whatsapp_send"),
    path("whatsapp/<uuid:pk>/send-media/", v.send_media, name="office_whatsapp_send_media"),
    path("whatsapp/<uuid:pk>/send-template/", v.send_template, name="office_whatsapp_send_template"),
    path("whatsapp/<uuid:pk>/read/", v.read, name="office_whatsapp_read"),
    path("whatsapp/<uuid:pk>/retry/<int:message>/", v.retry, name="office_whatsapp_retry"),
    # the Message button on the lead, person and Gold pages, and adding or fixing a mobile
    path("people/<uuid:pk>/whatsapp/", v.start_person, name="office_person_whatsapp"),
    path("leads/<uuid:pk>/whatsapp/", v.start_lead, name="office_lead_whatsapp"),
    path("gold/<uuid:pk>/whatsapp/", v.start_gold, name="office_gold_whatsapp"),
    path("leads/<uuid:pk>/contact/", v.lead_contact, name="office_lead_contact"),
    path("people/<uuid:pk>/mobile/", v.person_mobile, name="office_person_mobile"),
]
