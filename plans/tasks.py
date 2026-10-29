"""django-q entry points for the payment window. Ids and plain status strings only (django-q keeps task results)."""
from common.jobs import tracked

from . import payments


def send_payment_notices(window_id):
    return payments.send_slice(window_id)


@tracked("payments_tick")
def tick():
    return payments.tick()
