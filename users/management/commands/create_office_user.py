"""Deprecated name for `create_team_member`. Old --role values map: owner and manager -> admin, viewer -> office,
approver -> office + Approver. Prefer: manage.py create_team_member --email ... --level office|admin|developer [--approver]"""
from django.core.management.base import CommandError

from .create_team_member import Command as TeamCommand

OLD_ROLES = {"owner": ("admin", False), "manager": ("admin", False), "viewer": ("office", False), "approver": ("office", True)}


class Command(TeamCommand):
    help = "DEPRECATED: use create_team_member. Same thing, with the old --role option still accepted."

    def add_arguments(self, parser):
        super().add_arguments(parser)
        for action in parser._actions:
            if action.dest == "level":
                action.required = False
        parser.add_argument("--role", choices=sorted(OLD_ROLES), help="Old role names (mapped to a level).")

    def handle(self, *args, **options):
        self.stderr.write("create_office_user is deprecated: use create_team_member --email ... --level office|admin|developer [--approver].")
        if options.get("role"):
            options["level"], approver = OLD_ROLES[options["role"]]
            options["approver"] = options["approver"] or approver
        if not options.get("level"):
            raise CommandError("Give --level (or the old --role).")
        return super().handle(*args, **options)
