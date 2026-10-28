"""Template flags for the Ask us button and panel. No database query unless the button shows."""
from django.conf import settings
from django.utils.functional import SimpleLazyObject

# The button is not on the journey, the Gold application, the member area or the sign-in and register pages (docs/features/ai-chat.md).
HIDDEN_PREFIXES = ("/journey/", "/gold-card/apply/", "/account/", "/login/", "/logout/", "/register/", "/verify/", "/password/", "/reset/",
                   "/unsubscribe/", "/health/", "/ses/", "/postmark/")


def chat(request):
    """`chat_enabled` (key set, public site), `chat_button` (enabled and this page may show it), and lazy `chat_handoff` /
    `chat_suggested` (read from the database only when a template uses them)."""
    public = getattr(request, "urlconf", "") == "config.urls" or not getattr(request, "urlconf", "")
    enabled = bool(settings.ANTHROPIC_API_KEY) and public
    button = enabled and not request.path.startswith(HIDDEN_PREFIXES)
    if not button:
        return {"chat_enabled": enabled, "chat_button": False}
    from . import services

    return {"chat_enabled": True, "chat_button": True, "chat_handoff": SimpleLazyObject(services.handoff_links),
            "chat_suggested": SimpleLazyObject(services.suggested_questions)}
