from django.utils.functional import SimpleLazyObject


def unread(request):
    """Office pages only: `email_unread` (threads with unread email, read only when a template asks) and `email_replies_to_mailbox`."""
    if getattr(request, "urlconf", "") != "config.urls_office" or not request.user.is_authenticated:
        return {}
    from . import services

    return {"email_unread": SimpleLazyObject(lambda: services.unread_total(request.user)), "email_replies_to_mailbox": services.replies_to_mailbox()}
