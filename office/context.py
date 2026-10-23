from insights.metrics import K

from . import selectors


def office(request):
    """Office pages only: the Gold 'waiting' badge for the navigation (a stored counter) and what the person may do."""
    if getattr(request, "urlconf", "") != "config.urls_office" or not request.user.is_authenticated:
        return {}
    from .permissions import abilities

    return {"office_waiting": selectors.waiting_count(selectors.counters(K.GOLD_BY_STATUS)), "office_can": abilities(request.user)}
