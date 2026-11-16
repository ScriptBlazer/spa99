from django.apps import AppConfig


class SystemConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "system"

    def ready(self):
        from . import changes, office_signins

        changes.connect()
        office_signins.connect()
