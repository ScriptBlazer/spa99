"""Reference data, not a backfill: make sure the two new team Groups exist after a deploy (Viewer level, Membership approver role).

Live runs `migrate` on start and nobody runs setup_roles by hand, so System > Team could not hand out the new level without these rows.
It only get_or_creates the two Groups. It touches no user, no permission and no existing Group, and going back does nothing (a Group may by then
have members, so it is never deleted here). `setup_roles` still creates the same groups on a fresh machine and is safe to repeat.
"""
from django.db import migrations

NEW_GROUPS = ("Viewer", "Membership approver")


def make_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for name in NEW_GROUPS:
        Group.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0008_user_users_user_email_upper"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]
    operations = [migrations.RunPython(make_groups, migrations.RunPython.noop)]
