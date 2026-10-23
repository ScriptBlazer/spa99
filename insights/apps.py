from django.apps import AppConfig


class InsightsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "insights"

    def ready(self):
        from . import signals  # noqa: F401 - connects the Gold figure handlers
