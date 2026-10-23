"""Permission helpers. Views are locked by default (LoginRequiredMiddleware); public views use
@login_not_required with a comment saying why. Roles are Django Groups; never check names or emails.
"""
from functools import wraps

from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.exceptions import PermissionDenied


def user_in_groups(user, *group_names):
    return user.is_authenticated and (
        user.is_superuser or user.groups.filter(name__in=group_names).exists()
    )


def staff_in_groups(user, *group_names):
    """Roles for the staff hosts: a member account that happens to be in a role group is not staff and never passes."""
    return user.is_authenticated and user.is_staff and user_in_groups(user, *group_names)


def group_required(*group_names):
    """Function-view decorator: logged-in users in one of the groups (superusers always pass)."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not user_in_groups(request.user, *group_names):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def staff_required(view):
    """Function-view decorator: staff only. Anonymous users are sent to login by the middleware first."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


class GroupRequiredMixin(UserPassesTestMixin):
    """Class-view mixin. Set `required_groups = ("Manager",)`."""

    required_groups = ()

    def test_func(self):
        return user_in_groups(self.request.user, *self.required_groups)


class StaffRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff
