"""Public site (spa99.uk): the website pages, the data endpoints (journey, Gold) and the account routes."""
from django.urls import include, path

from common.views import check_mobile, health
from plans.views import preview_start
from notifications.views import postmark_webhook, ses_notifications
from whatsapp import webhooks as whatsapp_webhooks

urlpatterns = [
    path("health/", health, name="health"),  # public: monitoring
    path("validate/mobile/", check_mobile, name="check_mobile"),  # public: live mobile check, rate limited
    path("ses/notifications/", ses_notifications, name="ses_notifications"),  # public: Amazon SNS, signature checked
    path("postmark/webhook/", postmark_webhook, name="postmark_webhook"),  # public: Postmark, Basic auth checked
    path("twilio/whatsapp/incoming/", whatsapp_webhooks.incoming, name="whatsapp_incoming"),  # public: Twilio, X-Twilio-Signature checked
    path("twilio/whatsapp/status/", whatsapp_webhooks.status, name="whatsapp_status"),  # public: Twilio delivery ticks, signature checked
    path("twilio/whatsapp/media/<str:token>/", whatsapp_webhooks.media, name="whatsapp_media"),  # public: Twilio fetches a file we send; signed, expires in an hour
    path("sale-preview/", preview_start, name="sale_preview_start"),  # public: POST from the "Start preview" button (signed link, CSRF)
    path("journey/", include("journey.urls")),
    path("gold/", include("gold.urls")),
    path("chat/", include("chat.urls")),  # the Ask us chat (public host only)
    path("", include("mailings.urls")),  # public: unsubscribe and personal invite links
    path("", include("users.urls")),  # login, logout
    path("", include("users.urls_public")),  # register interest, verify, reset, account
    path("", include("pages.urls")),  # the website pages, the journey and Gold application screens
]
