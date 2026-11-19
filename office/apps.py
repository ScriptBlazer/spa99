from django.apps import AppConfig


class OfficeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "office"

    def ready(self):
        from . import signals  # noqa: F401
