"""Background tasks (django-q2; inline in tests). Ids only in the queue: no typed text sits in the task table."""
import logging

from notifications import sender as sender_mod
from notifications.models import EmailLog
from notifications.services import send_templated, subject_for

from .models import PersonMessage

logger = logging.getLogger("spa99.email")


def send_office_message(message_id):
    """The email for an Office Email button: the typed text in the branded layout (editable template `office_message`), From the logged-in person (notifications.sender), Reply-To the
    same address (the contact address when it falls back to hello@), his signature or a plain "Kind regards" under it. Sets the row's status. Returns a status string."""
    from users.models import User

    message = PersonMessage.objects.filter(pk=message_id).first()
    if message is None or message.status != PersonMessage.QUEUED:  # gone, or already done: a retry never sends twice
        return None
    user = User.objects.filter(email__iexact=message.email).first()
    first_name = (user.first_name if user is not None else "") or ""
    sender = sender_mod.sender_for(message.author)
    html, text = sender_mod.sign_off(message.author)
    subject = subject_for("office_message", first_name=first_name)
    log = send_templated("office_message", [message.email], subject, {"first_name": first_name, "message": message.text}, subject_email=message.email,
                         from_email=sender_mod.format_address(sender.address, sender.name), reply_to=[sender.address] if sender.source != "site" else None,
                         signature_html=html, signature_text=text)
    message.subject = subject
    message.status = PersonMessage.SENT if log.status == EmailLog.SENT else PersonMessage.FAILED
    message.save(update_fields=["subject", "status"])
    return log.status
