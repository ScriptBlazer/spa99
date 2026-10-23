"""Create (or update) a team member: an account at a level (office, admin or developer), optionally an Approver.

  manage.py create_team_member --email barry@example.com --level office --approver --invite
  manage.py create_team_member --email dev@example.com --level developer          (asks for a password)

An existing account just gains the level and keeps its password. A new account gets the password asked for at the prompt
(never an argument, never printed), or with --invite no password at all and an email to choose their own.
Run `setup_roles` first so the groups exist. The same thing is done in System > Team.
"""
from getpass import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

from common import levels


class Command(BaseCommand):
    help = "Create a team member (or give an existing account a level). Asks for the password, or sends an invite."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--level", required=True, choices=sorted(levels.GROUP_FOR))
        parser.add_argument("--approver", action="store_true", help="May also approve, decline and resend Gold applications.")
        parser.add_argument("--invite", action="store_true", help="New account: no password; email a link to choose one.")
        parser.add_argument("--first-name", default="")
        parser.add_argument("--last-name", default="")

    def handle(self, *args, **options):
        from system.team import apply_level
        from system.services import ChangeRefused

        email = options["email"].strip().lower()
        try:
            validate_email(email)
        except ValidationError as error:
            raise CommandError("That is not a valid email address.") from error
        User = get_user_model()
        user = User.objects.filter(email__iexact=email).first()
        created = user is None
        if created:
            password = None if options["invite"] else self._ask_password(email)
            user = User.objects.create_user(email, password, first_name=options["first_name"], last_name=options["last_name"])
        try:
            apply_level(user, options["level"], options["approver"], actor=None)
        except ChangeRefused as error:
            raise CommandError(str(error)) from error
        if created and options["invite"]:
            from users.tasks import send_team_invite_email

            send_team_invite_email(str(user.pk))
        made = "Created" if created else "Updated (password unchanged)"
        extra = " An email to choose a password has been sent." if created and options["invite"] else ""
        self.stdout.write(f"{made}: {user.email} is now {levels.LABELS[options['level']]}{' and Approver' if options['approver'] else ''}.{extra}")

    def _ask_password(self, email):
        first, second = getpass("Password: "), getpass("Password (again): ")
        if first != second:
            raise CommandError("The passwords do not match.")
        try:
            validate_password(first, user=get_user_model()(email=email))
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from error
        return first
