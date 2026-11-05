from django.utils.functional import SimpleLazyObject


def push(request):
    """Office pages only: what the notifications control needs (`whatsapp_push`: configured, vapid_public_key, muted, devices, urls) and the number of
    chats with unread messages (`whatsapp_unread`, read only when a template asks for it)."""
    if getattr(request, "urlconf", "") != "config.urls_office" or not request.user.is_authenticated:
        return {}
    from . import services, views

    return {"whatsapp_push": SimpleLazyObject(lambda: views.push_state(request.user)), "whatsapp_unread": SimpleLazyObject(lambda: services.unread_total(request.user)),
            "whatsapp_configured": services.configured()}
