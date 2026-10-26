"""django-q entry points. They take only an id and return a plain status string (django-q keeps task results, so never an
address or an EmailLog)."""
from . import sending


def send_mailing(mailing_id):
    return sending.run_mailing(mailing_id)


def start_scheduled(mailing_id):
    return sending.start_scheduled(mailing_id)


def send_invites(batch_id):
    return sending.run_invites(batch_id)
