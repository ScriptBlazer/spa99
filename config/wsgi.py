import os
from pathlib import Path

from common.envloader import pick_settings_module

if "DJANGO_SETTINGS_MODULE" not in os.environ:  # also read from the private / project .env files
    os.environ["DJANGO_SETTINGS_MODULE"] = pick_settings_module(
        Path(__file__).resolve().parent.parent, "config.settings.prod"
    )

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
