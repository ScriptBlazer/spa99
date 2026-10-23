"""Create (or update) a staff account for the Office and put it in a role. The password is asked for at the prompt:
it is never an argument, never printed. Run `setup_roles` first so the groups exist.

  manage.py create_office_user --email barry@example.com --role approver --first-name Barry
"""
from getpass import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

ROLES = {"owner": "Owner", "manager": "Manager", "viewer": "Viewer", "approver": "Approver"}


class Command(BaseCommand):
    help = "Create an Office staff account (or give an existing one a role). Asks for the password."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--role", required=True, choices=sorted(ROLES))
        parser.add_argument("--first-name", default="")
        parser.add_argument("--last-name", default="")

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        try:
            validate_email(email)
        except ValidationError as error:
            raise CommandError("That is not a valid email address.") from error
        group = Group.objects.filter(name=ROLES[options["role"]]).first()
        if group is None:
            raise CommandError("The roles do not exist yet. Run: manage.py setup_roles")
        User = get_user_model()
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            password = self._ask_password(email)
            user = User.objects.create_user(email, password, is_staff=True, first_name=options["first_name"], last_name=options["last_name"])
            made = "Created"
        else:
            if not user.is_staff:
                user.is_staff = True
                user.save(update_fields=["is_staff"])
            made = "Updated (password unchanged)"
        user.groups.add(group)
        self.stdout.write(f"{made}: {user.email} is now {group.name} in the Office.")

    def _ask_password(self, email):
        first, second = getpass("Password: "), getpass("Password (again): ")
        if first != second:
            raise CommandError("The passwords do not match.")
        try:
            validate_password(first, user=get_user_model()(email=email))
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from error
        return first
