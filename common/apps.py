import logging
import os
import sys

from django.apps import AppConfig
from django.conf import settings

logger = logging.getLogger("spa99.startup")


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "common"

    def ready(self):
        from django.contrib.auth.models import update_last_login
        from django.contrib.auth.signals import user_logged_in

        from . import signals  # noqa: F401  (connects the login audit receivers)

        # last_login is set by our audit receiver with a queryset update, so logging in does not
        # add a history row to the user every time.
        user_logged_in.disconnect(update_last_login, dispatch_uid="update_last_login")
        self.log_startup()

    @staticmethod
    def log_startup():
        report = getattr(settings, "STARTUP_REPORT", None)
        if not report:
            return
        # runserver starts twice (reloader parent, then child); log once.
        if sys.argv[1:2] == ["runserver"] and os.environ.get("RUN_MAIN") != "true":
            return
        logger.info(
            "Spa 99 startup: settings=%s env=[%s] private=%s database=%s media=%s",
            report["settings"],
            ", ".join(report["env_sources"]) or "none",
            report["private_dir"],
            report["database"],
            report["media"],
        )
        for key in report["missing_keys"]:
            logger.warning("%s is missing from the environment / .env (see .env.example)", key)
