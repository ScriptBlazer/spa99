"""Background tasks (django-q2; inline in tests). Ids only in the queue: no typed text sits in the task table."""
import logging

from notifications.services import send_templated, subject_for

from .models import PersonMessage

logger = logging.getLogger("spa99.email")


def send_office_message(message_id):
    """The email for an Office Message: the typed text inside the branded layout (editable template `office_message`).
    Returns a status string."""
    from users.models import User

    message = PersonMessage.objects.filter(pk=message_id).first()
    if message is None:
        return None
    user = User.objects.filter(email__iexact=message.email).first()
    first_name = (user.first_name if user is not None else "") or ""
    log = send_templated("office_message", [message.email], subject_for("office_message", first_name=first_name),
                         {"first_name": first_name, "message": message.text}, subject_email=message.email)
    return log.status
