from django.utils.functional import SimpleLazyObject

from . import member


def member_area(request):
    """`has_member_area` for the website menu: "My Spa 99" only for someone who can open it (lazy: no query unless a page asks)."""
    user = getattr(request, "user", None)
    return {"has_member_area": SimpleLazyObject(lambda: bool(user is not None and member.can_open(user)))}
