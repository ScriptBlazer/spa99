from insights.metrics import K

from . import selectors


def _person(user, roles):
    """The signed-in person for the header and the navigation: name, initials and role."""
    from .permissions import READERS

    name = user.get_full_name() or user.email
    letters = [part[0] for part in (user.first_name, user.last_name) if part] or [user.email[:1]]
    role = next((r for r in READERS if r in roles), "Owner" if user.is_superuser else "Staff")
    return {"name": name, "first_name": user.first_name or name, "initials": "".join(letters[:2]).upper(), "role": role}


def office(request):
    """Office pages only: the Gold 'waiting' badge for the navigation (a stored counter), what the person may do,
    and who they are."""
    if getattr(request, "urlconf", "") != "config.urls_office" or not request.user.is_authenticated:
        return {}
    from .permissions import abilities, role_names

    roles = role_names(request.user)
    return {"office_waiting": selectors.waiting_count(selectors.counters(K.GOLD_BY_STATUS)), "office_can": abilities(request.user, roles),
            "office_person": _person(request.user, roles)}
