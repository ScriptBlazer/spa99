from django.contrib.admin import AdminSite
from django.contrib.admin.apps import AdminConfig

from . import levels


class SuperuserAdminSite(AdminSite):
    """Only an active, staff superuser gets in; Office, Admin and Developer levels do not (docs/features/user-rules.md U2)."""

    def has_permission(self, request):
        return request.user.is_staff and levels.level_of(request.user) == levels.SUPERUSER


class SpaAdminConfig(AdminConfig):
    """The Django admin app, using the superuser-only site (named in INSTALLED_APPS)."""
    default_site = "common.admin_site.SuperuserAdminSite"
