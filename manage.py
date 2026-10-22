#!/usr/bin/env python
"""Django's command-line utility. `manage.py test` defaults to the test settings."""
import os
import sys


def main():
    default_settings = "config.settings.test" if sys.argv[1:2] == ["test"] else "config.settings.dev"
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", default_settings)
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
