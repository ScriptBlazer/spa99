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
        if settings.DEBUG:
            self.no_cache_dev_static()
        self.log_startup()

    @staticmethod
    def no_cache_dev_static():
        """Dev only: runserver serves CSS/JS unhashed (app.css @imports plain file names), so browsers kept old
        copies and pages looked broken after a change. Tell the browser to always revalidate. Live uses hashed
        manifest files and never runs this."""
        from django.contrib.staticfiles.handlers import StaticFilesHandlerMixin

        if getattr(StaticFilesHandlerMixin, "_spa99_no_cache", False):
            return
        original = StaticFilesHandlerMixin.serve

        def serve(self, request):
            response = original(self, request)
            response["Cache-Control"] = "no-cache"
            return response

        StaticFilesHandlerMixin.serve = serve
        StaticFilesHandlerMixin._spa99_no_cache = True

    @staticmethod
    def log_startup():
        report = getattr(settings, "STARTUP_REPORT", None)
        if not report:
            return
        # runserver starts twice (reloader parent, then child); log once.
        if sys.argv[1:2] == ["runserver"] and os.environ.get("RUN_MAIN") != "true":
            return
        logger.info(
            "Spa 99 startup: settings=%s env=[%s] private=%s database=%s hosts=[%s] media=%s sentry=%s chat=%s",
            report["settings"],
            ", ".join(report["env_sources"]) or "none",
            report["private_dir"],
            report["database"],
            report.get("hosts", ""),
            report["media"],
            report.get("sentry", "off"),
            report.get("chat", "off"),
        )
        if report.get("media_is_local") and report["settings"].endswith("prod"):
            logger.warning(
                "PRODUCTION MEDIA IS ON LOCAL DISK, NOT S3: uploaded files will be lost when the container is "
                "replaced. Set AWS_STORAGE_BUCKET_NAME."
            )
        if report.get("unlock_code_invalid"):
            logger.warning("SYSTEM_UNLOCK_CODE is not 6 to 12 digits: System unlock uses the password only")
        elif not report.get("unlock_code_set", True):
            logger.warning("SYSTEM_UNLOCK_CODE not set: System unlock uses the password only")
        for key in report["missing_keys"]:
            logger.warning("%s is missing from the environment / .env (see .env.example)", key)
