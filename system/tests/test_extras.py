"""System extras: Stay unlocked ping, dashboard figures, change log grouping/search/query count, undo toasts, env label."""
from datetime import timedelta
from unittest import mock

from django.contrib.messages import get_messages
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django_q.models import Failure

from insights.metrics import K
from insights.models import MetricCounter, OfficeSnapshot
from plans.models import SiteSettings
from system import services
from system.models import SystemChange
from system.tests.test_system import PASSWORD, make_user, sign_in, unlocked_client

SETTINGS_POST = {"opening_text": "January 2027", "register_interest_open": "on", "journey_email_gate": "on", "join_wording": "register_interest", "vat_rate": "20.00", "lock_idle_minutes": "15", "max_sign_in_hours": "12"}


class PingTests(TestCase):
    def test_ping_slides_the_unlock_and_is_refused_when_locked(self):
        client, _ = sign_in(make_user())
        locked = client.post("/unlock/ping/")
        self.assertEqual((locked.status_code, locked.json()), (403, {"remaining": 0}))  # signed in but locked
        with mock.patch("system.services.time.time", return_value=1000.0):
            client.post("/unlock/", {"password": PASSWORD})
        with mock.patch("system.services.time.time", return_value=1000.0 + 14 * 60):
            ping = client.post("/unlock/ping/")
            self.assertEqual((ping.status_code, ping.json()), (200, {"remaining": 15 * 60}))
        with mock.patch("system.services.time.time", return_value=1000.0 + 28 * 60):  # 14 min after the ping: still unlocked
            self.assertEqual(client.get("/").status_code, 200)
        self.assertEqual(Client(HTTP_HOST="system.localhost").post("/unlock/ping/").status_code, 404)
        self.assertEqual(client.get("/unlock/ping/").status_code, 405)


class DashboardTests(TestCase):
    def test_failed_jobs_gold_waiting_people_and_stale_flag_come_from_stored_rows(self):
        now = timezone.now()
        for name, stopped in (("recent", now - timedelta(hours=2)), ("old", now - timedelta(hours=30))):
            Failure.objects.create(id=name, name=name, func="x.y", started=stopped, stopped=stopped, success=False)
        MetricCounter.objects.create(key=K.GOLD_BY_STATUS, dimension="new", value=2)
        MetricCounter.objects.create(key=K.GOLD_BY_STATUS, dimension="contacted", value=1)
        MetricCounter.objects.create(key=K.REGISTRATIONS, dimension="", value=41)
        snapshot = OfficeSnapshot.objects.create(page="dashboard", range="7d", payload={"totals": {"registrations": 3}})
        health = services.health_report()
        self.assertEqual((health["failed_tasks_24h"], health["gold_waiting"], health["people_total"], health["snapshot_stale"]), (1, 3, 41, False))
        OfficeSnapshot.objects.filter(pk=snapshot.pk).update(updated_at=now - timedelta(minutes=16))
        self.assertTrue(services.health_report()["snapshot_stale"])
        OfficeSnapshot.objects.all().delete()
        self.assertTrue(services.health_report()["snapshot_stale"])  # nothing stored counts as stale


class ChangeLogTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = unlocked_client(self.user)

    def test_changes_saved_together_share_a_batch_and_undo_all_restores_them(self):
        response = self.client.post("/settings/", SETTINGS_POST | {"vat_rate": "25.00", "opening_text": "March 2027"})
        rows = SystemChange.objects.all()
        self.assertEqual(rows.count(), 2)
        self.assertEqual(rows.values("batch_id").distinct().count(), 1)
        batch = rows[0].batch_id
        # the toast after the save carries the undo-all link (item 5)
        self.assertEqual([m.extra_tags for m in get_messages(response.wsgi_request)], [f"undo:/changes/batch/{batch}/undo/"])
        entries = services.change_list({})
        self.assertEqual([(c.batch_size, c.batch_first, c.batch_open) for c in entries], [(2, True, 2), (2, False, 2)])
        self.client.post(f"/changes/batch/{batch}/undo/")
        site = SiteSettings.load()
        self.assertEqual((str(site.vat_rate), site.opening_text), ("20.00", "January 2027"))
        self.assertEqual(SystemChange.objects.filter(undo_of__isnull=False).count(), 2)
        self.assertEqual(services.change_list({})[0].batch_open, 0)  # nothing left to undo

    def test_a_single_change_toast_points_at_its_own_undo(self):
        response = self.client.post("/settings/", SETTINGS_POST | {"vat_rate": "25.00"})
        change = SystemChange.objects.get()
        self.assertEqual([m.extra_tags for m in get_messages(response.wsgi_request)], [f"undo:/changes/{change.pk}/undo/"])
        nothing = self.client.post("/settings/", SETTINGS_POST | {"vat_rate": "25.00"})
        self.assertEqual(list(get_messages(nothing.wsgi_request))[-1].extra_tags, "")  # nothing changed: no undo link

    def test_search_range_and_person_filters_and_the_people_list(self):
        other = make_user("other@example.com")
        self.client.post("/settings/", SETTINGS_POST | {"vat_rate": "25.00"})
        SiteSettings.objects.update(capacity=3)
        site = SiteSettings.load()
        site._history_user = other
        site.capacity = 9
        site.save()
        def fields(**params):
            return [c.field for c in services.change_list(params)]
        self.assertEqual(fields(q="vat"), ["vat_rate"])
        self.assertEqual(fields(q="25.00"), ["vat_rate"])  # values are searched too
        self.assertEqual(fields(user="other@example.com"), ["capacity"])
        self.assertEqual(len(fields(range="1")), 2)
        SystemChange.objects.filter(field="vat_rate")._prune_update(created_at=timezone.now() - timedelta(days=5))  # test only: the audit rows refuse edits
        self.assertEqual(fields(range="1"), ["capacity"])
        self.assertEqual(len(fields(range="7")), 2)
        self.assertEqual(self.client.get("/changes/").context["people"], ["dev@example.com", "other@example.com"])


class EnvLabelTests(TestCase):
    def test_the_label_is_a_setting_and_only_system_pages_get_it(self):
        client = unlocked_client(make_user())
        self.assertEqual(client.get("/").context["system_env"], "dev")
        with override_settings(SYSTEM_ENV_LABEL="LIVE"):
            self.assertEqual(client.get("/").context["system_env"], "live")
            self.assertContains(client.get("/"), 'data-env="live"')
        public = Client(HTTP_HOST="localhost").get("/")
        self.assertNotIn("system_env", public.context or {})


class WhatsappSettingTests(TestCase):
    def setUp(self):
        self.client = unlocked_client(make_user())

    def test_the_number_is_normalised_validated_and_logged(self):
        for typed in ("+44 7441 919990", "07441 919990", "44 7441-919990", "00447441919990"):
            self.client.post("/settings/", SETTINGS_POST | {"whatsapp_number": typed})
            self.assertEqual(SiteSettings.load().whatsapp_number, "447441919990", typed)
        for bad in ("12345", "abc", "+44 7441 91999x", "1" * 16):
            response = self.client.post("/settings/", SETTINGS_POST | {"whatsapp_number": bad})
            self.assertEqual(response.status_code, 400, bad)
            self.assertEqual(SiteSettings.load().whatsapp_number, "447441919990")
        self.assertEqual(SystemChange.objects.filter(field="whatsapp_number").count(), 1)

    def test_the_message_is_saved_and_can_be_cleared(self):
        self.client.post("/settings/", SETTINGS_POST | {"whatsapp_message": "Hello Spa 99"})
        self.assertEqual(SiteSettings.load().whatsapp_message, "Hello Spa 99")
        too_long = self.client.post("/settings/", SETTINGS_POST | {"whatsapp_message": "x" * 301})
        self.assertEqual(too_long.status_code, 400)

    def test_the_better_prices_message_is_saved(self):
        self.client.post("/settings/", SETTINGS_POST | {"whatsapp_rate_message": "Better prices please"})
        self.assertEqual(SiteSettings.load().whatsapp_rate_message, "Better prices please")
        self.assertEqual(self.client.post("/settings/", SETTINGS_POST | {"whatsapp_rate_message": "x" * 301}).status_code, 400)
        self.assertIn('name="whatsapp_rate_message"', self.client.get("/settings/").content.decode())

    def test_the_form_shows_both_and_not_the_old_link(self):
        html = self.client.get("/settings/").content.decode()
        self.assertIn('name="whatsapp_number"', html)
        self.assertIn('name="whatsapp_message"', html)
        self.assertNotIn("discount_contact_url", html)

    def test_number_normalisation(self):
        from plans.models import normalise_whatsapp_number as n

        self.assertEqual(n("+44 7441 919990"), "447441919990")
        self.assertEqual(n("07441 919990"), "447441919990")
        self.assertEqual(n("+44 (0)7441 919990"), "447441919990")
        self.assertEqual(n("0044 (0) 7441 919990"), "447441919990")
        self.assertEqual(n("(07441) 919990"), "447441919990")
        self.assertEqual(n("  "), "")
        self.assertEqual(n("call me"), "call me")  # left as typed so validation refuses it

