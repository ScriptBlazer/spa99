from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from common import levels
from plans.models import SiteSettings


def make_team_member(email, level=levels.OFFICE, approver=False, final=False, is_active=True):
    """A team account at `level`, optionally holding the Approver and Final approver groups (the groups are made if missing)."""
    user = get_user_model().objects.filter(email__iexact=email).first() or get_user_model().objects.create_user(email, "x-Pass-123456")
    user.is_staff, user.is_active, user.is_superuser = True, is_active, level == levels.SUPERUSER
    user.save()
    names = ([levels.GROUP_FOR[level]] if level in levels.GROUP_FOR else []) + ([levels.APPROVER_GROUP] if approver else []) + ([levels.FINAL_APPROVER_GROUP] if final else [])
    user.groups.set([Group.objects.get_or_create(name=name)[0] for name in names])
    return user


def set_recipients(approvers="approver@example.test", cc="cc@example.test", contact="hello@example.test", final=""):
    """Approvers are team members now: each address in `approvers` / `final` (comma separated) becomes an Office / Admin account
    holding the role. CC and contact stay plain settings."""
    for address in [a.strip() for a in approvers.split(",") if a.strip()]:
        make_team_member(address, levels.OFFICE, approver=True)
    for address in [a.strip() for a in final.split(",") if a.strip()]:
        make_team_member(address, levels.ADMIN, final=True)
    site = SiteSettings.load()
    site.gold_approver_cc, site.contact_email = cc, contact
    site.save()
