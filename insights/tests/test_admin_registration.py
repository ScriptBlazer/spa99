from django.apps import apps
from django.contrib import admin
from django.test import Client, TestCase

from plans.management.commands.seed_phase1 import seed_all
from users.models import User

OUR_APPS = ["common", "users", "plans", "content", "journey", "gold", "notifications"]


class AdminRegistrationTests(TestCase):
    def test_every_model_is_in_the_hidden_admin_and_its_list_page_loads(self):
        seed_all()
        missing = [
            m._meta.label for app in OUR_APPS for m in apps.get_app_config(app).get_models()
            if not m._meta.label_lower.split(".")[1].startswith("historical") and m not in admin.site._registry
        ]
        self.assertEqual(missing, [])

        root = User.objects.create_superuser("root@example.com", "x")
        client = Client(HTTP_HOST="control.localhost")
        client.force_login(root)
        from django.conf import settings

        for model in admin.site._registry:
            if model._meta.app_label in OUR_APPS:
                url = f"/{settings.ADMIN_PATH}{model._meta.app_label}/{model._meta.model_name}/"
                self.assertEqual(client.get(url).status_code, 200, url)
