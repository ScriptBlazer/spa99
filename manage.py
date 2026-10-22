#!/usr/bin/env python
"""Django's command-line utility. `manage.py test` defaults to the test settings.

DJANGO_SETTINGS_MODULE is read with the project's load order (environment, private .env, project .env).
"""
import os
import sys
from pathlib import Path


def main():
    base_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(base_dir))
    from common.envloader import pick_settings_module

    if "DJANGO_SETTINGS_MODULE" not in os.environ:
        if sys.argv[1:2] == ["test"]:
            os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.test"
        else:
            os.environ["DJANGO_SETTINGS_MODULE"] = pick_settings_module(base_dir, "config.settings.dev")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
