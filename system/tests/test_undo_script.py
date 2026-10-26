"""Undo on a change a script made asks for the System code again; a person's change undoes instantly."""
import uuid

from django.core.cache import cache
from django.test import TestCase, override_settings

from plans.models import SiteSettings
from system.models import SystemChange, SystemEvent
from system.tests.test_extras import SETTINGS_POST
from system.tests.test_system import PASSWORD, make_user, sign_in

CODE = "493021"
CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "undo-script-tests"}}


@override_settings(SYSTEM_UNLOCK_CODE=CODE, CACHES=CACHE)
class UndoScriptChangeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user()
        self.client, _ = sign_in(self.user)
        self.client.post("/unlock/", {"password": PASSWORD, "code": CODE})
        cache.clear()  # the unlock above spent one try of the shared limit

    def script_change(self):
        site = SiteSettings.load()
        site.lock_idle_minutes = 40  # saved with no person, as a shell or seed would
        site.save()
        return SystemChange.objects.get(field="lock_idle_minutes")

    def undo(self, change, **data):
        return self.client.post(f"/changes/{change.pk}/undo/", data)

    def test_a_persons_change_undoes_without_a_code(self):
        self.client.post("/settings/", SETTINGS_POST | {"lock_idle_minutes": "30"})
        change = SystemChange.objects.get(field="lock_idle_minutes")
        self.assertEqual(self.undo(change).status_code, 302)
        self.assertEqual(SiteSettings.load().lock_idle_minutes, 15)

    def test_a_script_change_without_a_code_is_refused_and_nothing_changes(self):
        change = self.script_change()
        self.assertFalse(change.user_id or change.user_label)
        response = self.undo(change)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["needs_code"], True)
        self.assertFalse(response.json()["ok"])
        self.assertEqual(SiteSettings.load().lock_idle_minutes, 40)
        self.assertFalse(SystemChange.objects.filter(undo_of=change).exists())
        self.assertFalse(SystemEvent.objects.filter(kind="undo_code_failed").exists())  # nothing typed, nothing failed

    def test_a_wrong_code_is_refused_logged_as_a_failure_and_rate_limited(self):
        change = self.script_change()
        for _ in range(5):
            response = self.undo(change, code="000000")
            self.assertEqual((response.status_code, response.json()["needs_code"]), (403, True))
        self.assertEqual(SystemEvent.objects.filter(kind="undo_code_failed", outcome="failed").count(), 5)
        blocked = self.undo(change, code=CODE)  # even the right code is refused once the limit is spent
        self.assertEqual(blocked.status_code, 429)
        self.assertTrue(SystemEvent.objects.filter(kind="undo_rate_limited", outcome="blocked").exists())
        self.assertEqual(SiteSettings.load().lock_idle_minutes, 40)
        self.assertNotIn("000000", " ".join(SystemEvent.objects.values_list("sentence", flat=True)))

    def test_the_right_code_undoes_and_records_the_developer_not_a_script(self):
        change = self.script_change()
        self.assertEqual(self.undo(change, code=CODE).status_code, 302)
        self.assertEqual(SiteSettings.load().lock_idle_minutes, 15)
        entry = SystemChange.objects.get(undo_of=change)
        self.assertEqual((entry.user_id, entry.user_label), (self.user.pk, self.user.email))
        self.assertTrue(SystemEvent.objects.filter(kind="undo", user=self.user).exists())

    def test_undo_all_of_a_script_batch_needs_the_code_too(self):
        change = self.script_change()
        batch = uuid.uuid4()
        SystemChange.objects.filter(pk=change.pk)._prune_update(batch_id=batch)
        url = f"/changes/batch/{batch}/undo/"
        self.assertEqual(self.client.post(url).status_code, 403)
        self.assertEqual(SiteSettings.load().lock_idle_minutes, 40)
        self.assertEqual(self.client.post(url, {"code": CODE}).status_code, 302)
        self.assertEqual(SiteSettings.load().lock_idle_minutes, 15)

    def test_only_a_scripts_undo_button_carries_the_lock(self):
        self.script_change()
        page = self.client.get("/changes/").content.decode()
        self.assertIn("data-system-needs-code", page)
        self.assertIn("Needs the System code", page)
        self.client.post("/settings/", SETTINGS_POST | {"lock_idle_minutes": "40", "max_sign_in_hours": "8"})
        self.assertEqual(self.client.get("/changes/").content.decode().count("data-system-needs-code"), 1)
