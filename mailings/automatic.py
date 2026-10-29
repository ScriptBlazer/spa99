"""Automatic emails that can also be sent to a group ("Send to a group" on the email's page in System > Emails > Automatic).

Only an email that makes sense to send to a chosen group is listed here, with the kind of group send it becomes. Transactional emails
(confirm email, password reset, Gold approval, payment notices ...) are never listed: they go to one person when something happens.
The group send uses the email's own subject and wording (edited on its page); the Invitation keeps each person's personal register link
and its tracking (mailings.models.Invite, one row per person, batch_id = the mailing's id)."""
from .models import Mailing

SENDABLE = {"invite": Mailing.INVITATION}


def can_send_to_group(key):
    return key in SENDABLE
