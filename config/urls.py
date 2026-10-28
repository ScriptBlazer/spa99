"""Public site (spa99.uk): the website pages, the data endpoints (journey, Gold) and the account routes."""
from django.urls import include, path

from common.views import check_mobile, health
from plans.views import preview_start
from notifications.views import postmark_webhook, ses_notifications

urlpatterns = [
    path("health/", health, name="health"),  # public: monitoring
    path("validate/mobile/", check_mobile, name="check_mobile"),  # public: live mobile check, rate limited
    path("ses/notifications/", ses_notifications, name="ses_notifications"),  # public: Amazon SNS, signature checked
    path("postmark/webhook/", postmark_webhook, name="postmark_webhook"),  # public: Postmark, Basic auth checked
    path("sale-preview/", preview_start, name="sale_preview_start"),  # public: POST from the "Start preview" button (signed link, CSRF)
    path("journey/", include("journey.urls")),
    path("gold/", include("gold.urls")),
    path("chat/", include("chat.urls")),  # the Ask us chat (public host only)
    path("", include("mailings.urls")),  # public: unsubscribe and personal invite links
    path("", include("users.urls")),  # login, logout
    path("", include("users.urls_public")),  # register interest, verify, reset, account
    path("", include("pages.urls")),  # the website pages, the journey and Gold application screens
]
