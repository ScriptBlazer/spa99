"""System extras: Stay unlocked ping, dashboard figures, change log grouping/search/query count, undo toasts, env label."""
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.messages import get_messages
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django_q.models import Failure

from insights.metrics import K
from insights.models import MetricCounter, OfficeSnapshot
from office.templatetags.office_tags import pounds
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



class RevenueSettingsTests(TestCase):
    def setUp(self):
        self.client = unlocked_client(make_user())

    def test_the_revenue_page_saves_and_logs_the_assumptions_and_only_the_start_date_asks_for_a_refresh(self):
        post = {"revenue_start_date": "2027-02-01", "revenue_paying_percent": "80", "revenue_dropoff_percent": "5"}
        with mock.patch("office.snapshots.request_refresh") as refresh:
            self.client.post("/revenue/", post)
            self.assertEqual(refresh.call_count, 1)
            self.client.post("/revenue/", post | {"revenue_paying_percent": "70"})
            self.assertEqual(refresh.call_count, 1)  # the percentages apply at page load
        site = SiteSettings.load()
        self.assertEqual((str(site.revenue_start_date), site.revenue_paying_percent, site.revenue_dropoff_percent), ("2027-02-01", 70, 5))
        self.assertEqual(set(SystemChange.objects.values_list("section", flat=True)), {"revenue"})
        self.assertEqual(self.client.post("/revenue/", post | {"revenue_paying_percent": "101"}).status_code, 400)
        self.assertNotContains(self.client.get("/settings/"), "revenue_start_date")
        self.assertContains(self.client.get("/settings/"), "date_format")


class RevenuePageTests(TestCase):
    """System > Revenue: the explained page, its three tiles, the live example's numbers, and the same gate as Settings."""

    def setUp(self):
        self.client = unlocked_client(make_user())

    def store(self, approved_year=100_000_00, months=None, gold=0):
        """A stored Revenue payload by hand: one tier, memberships over 12 months (a month of `months[n]` pence), `gold` pence of Gold fees, and its calendar."""
        months = months or [20_000_00] * 5 + [0] * 7
        due = {"tier-2": {f"2027-{n:02d}-01": {str(n): [pence, 1]} for n, pence in enumerate(months, start=1) if pence}}
        if gold:
            due["gold"] = {"2027-01-01": {"1": [gold, 1]}}
        detail = {"groups": [], "months": months, "calendar": {"start": "2027-01-01", "assumed": True, "first": "2027-01-01", "last": "2027-12-01", "due": due}}
        bucket = {"count": 5, "year_pence": approved_year, "by_plan": [{"slug": "tier-2", "name": "Tier 2", "kind": "tier", "count": 5, "year_pence": sum(months)},
                                                                     {"slug": "gold", "name": "Gold Card", "kind": "gold", "count": 1 if gold else 0, "year_pence": gold}], "detail": detail}
        payload = {"memberships": {"total": 0, "waiting": 0, "approved": 0, "declined": 0}, "gold": {"total": 0, "waiting": 0, "approved": 0, "declined": 0}, "registered_total": 0,
                   "gold_members": 0, "leads_total": 0, "revenue": {"gold_fee_pence": 19900, "approved": bucket, "waiting": {"count": 0, "year_pence": 0, "by_plan": [], "detail": None}}}
        OfficeSnapshot.objects.all().delete()
        OfficeSnapshot.objects.create(page=OfficeSnapshot.COUNTS, range="all", payload=payload, built_at=timezone.now())

    def set_site(self, **values):
        SiteSettings.load()  # the one row exists before it is changed
        SiteSettings.objects.filter(singleton_key="site").update(**values)

    def test_the_page_names_each_setting_and_explains_it(self):
        page = self.client.get("/revenue/")
        self.assertEqual(page.status_code, 200)
        for text in ("Assumed start date", "How many actually pay", "Monthly drop-off", "What it means", "What it never changes", "Public or private",
                     "What the Office Revenue page assumes. Percentages apply as soon as you save. A new date takes a moment to reach the figures.",
                     "The real figure is never changed by anything here.", "What your percentages do", 'data-date-picker data-mode="single" data-format="d/m/Y"'):
            self.assertContains(page, text)
        self.assertNotContains(page, "Changes apply at once")
        self.assertNotContains(page, "—")  # no em dashes in the copy
        self.assertContains(page, "Not ready")  # nothing stored yet: the tiles say so instead of showing £0
        self.assertContains(page, "The figures will be ready after the next hourly update.")

    def test_the_tiles_show_the_saved_figures_and_which_start_date_is_in_use(self):
        self.store(gold=19_900)
        page = self.client.get("/revenue/")
        self.assertEqual(page.context["preview"]["ready"], True)
        self.assertContains(page, '<div class="v" data-revenue-tile="real">£100,000</div>', html=False)
        self.assertContains(page, "A year, excluding VAT. Every approved person paying. Nothing on this page changes it.")
        self.assertContains(page, "The same as the real figure, so the Office does not show it.")  # 100% paying and 0% leaving
        self.assertContains(page, "01/01/2027")
        self.assertContains(page, "Assumed, and private. No opening date is set yet.")
        self.assertNotContains(page, "data-revenue-opening-set")
        self.set_site(revenue_paying_percent=80, revenue_dropoff_percent=10, opening_date="2027-03-10")
        page = self.client.get("/revenue/")
        self.assertContains(page, "Shown beside the real figure in the Office.")
        self.assertContains(page, "10/03/2027")
        self.assertContains(page, "The opening date, set in Settings. Public.")
        self.assertContains(page, 'data-revenue-opening-set>The <a href="/settings/">opening date</a> is set, so this date is not being used.')
        # 5 months of 20,000 pounds at 80% paying and 10% leaving each month, plus Gold's 199 at 80% with no drop-off
        expected = sum(Decimal(2_000_000) * Decimal("0.8") * Decimal("0.9") ** n for n in range(5)) + Decimal(19_900) * Decimal("0.8")
        self.assertEqual(page.context["preview"]["assumed_pence"], expected)
        self.assertContains(page, f'data-revenue-tile="assumed">{pounds(expected)}<')

    def test_the_numbers_for_the_live_example_are_the_stored_ones(self):
        self.store(approved_year=100_000_00 + 19_900, months=[20_000_00] * 5 + [0] * 7, gold=19_900)
        preview = self.client.get("/revenue/").context["preview"]
        self.assertEqual((preview["real_pence"], preview["months"], preview["gold_pence"], preview["plain"]), (10_019_900, [2_000_000] * 5 + [0] * 7, 19_900, True))
        page = self.client.get("/revenue/")
        self.assertContains(page, '<script id="rev-preview" type="application/json">')
        self.assertContains(page, "data-revenue-live")

    def test_the_date_format_setting_changes_how_the_start_date_is_shown(self):
        self.set_site(date_format="mm/dd/yyyy", revenue_start_date="2027-02-01")
        page = self.client.get("/revenue/")
        self.assertContains(page, "02/01/2027")
        self.assertContains(page, 'data-format="m/d/Y"')
        self.assertContains(page, 'value="2027-02-01"')  # the field itself always carries an ISO date

    def test_it_saves_the_settings_and_refuses_what_is_out_of_range_in_plain_words(self):
        post = {"revenue_start_date": "2027-02-01", "revenue_paying_percent": "80", "revenue_dropoff_percent": "5"}
        with mock.patch("office.snapshots.request_refresh"):
            self.assertEqual(self.client.post("/revenue/", post).status_code, 302)
        site = SiteSettings.load()
        self.assertEqual((str(site.revenue_start_date), site.revenue_paying_percent, site.revenue_dropoff_percent), ("2027-02-01", 80, 5))
        for field, bad in (("revenue_paying_percent", "101"), ("revenue_paying_percent", "-1"), ("revenue_paying_percent", ""), ("revenue_dropoff_percent", "abc"), ("revenue_dropoff_percent", "100.01")):
            response = self.client.post("/revenue/", post | {field: bad})
            self.assertEqual(response.status_code, 400, (field, bad))
            self.assertContains(response, "Type a number from 0 to 100.", status_code=400)
        self.assertEqual(SiteSettings.load().revenue_paying_percent, 80)  # nothing was saved by the refused ones
        for edge in ("0", "100", "37.5"):
            with mock.patch("office.snapshots.request_refresh"):
                self.assertEqual(self.client.post("/revenue/", post | {"revenue_dropoff_percent": edge}).status_code, 302, edge)
        empty = self.client.post("/revenue/", post | {"revenue_start_date": ""})
        self.assertEqual(empty.status_code, 400)
        self.assertContains(empty, "Choose a date.", status_code=400)

    def test_a_refused_save_still_shows_the_saved_figures_not_what_was_typed(self):
        self.store()
        self.set_site(revenue_paying_percent=60)
        response = self.client.post("/revenue/", {"revenue_start_date": "2027-02-01", "revenue_paying_percent": "150", "revenue_dropoff_percent": "0"})
        self.assertEqual((response.status_code, response.context["preview"]["plain"]), (400, False))
        self.assertEqual(response.context["preview"]["start"].isoformat(), "2027-01-01")

    def test_it_is_gated_exactly_like_settings(self):
        from system.tests.test_system import SYSTEM

        office_staff, member = make_user("office@example.com", system=False), make_user("member@example.com", system=True, staff=False)
        for user in (None, office_staff, member):
            client = Client(HTTP_HOST=SYSTEM)
            if user:
                client.force_login(user)
            self.assertEqual((client.get("/revenue/").status_code, client.post("/revenue/", {}).status_code), (404, 404), user)
            self.assertEqual(client.get("/revenue/").status_code, client.get("/settings/").status_code)
        locked, _ = sign_in(make_user("dev2@example.com"))
        response = locked.get("/revenue/")
        self.assertEqual((response.status_code, response["Location"]), (302, "/unlock/?next=%2Frevenue%2F"))
        self.assertEqual(locked.get("/settings/").status_code, 302)
        self.assertEqual(self.client.get("/revenue/").status_code, self.client.get("/settings/").status_code)


class SavedDatesDoNotBlockTests(TestCase):
    def test_an_old_saved_start_date_never_blocks_the_percentages_but_a_new_far_off_date_is_refused(self):
        from datetime import date

        from plans.models import SiteSettings
        from system.forms import RevenueForm

        site = SiteSettings.load()
        SiteSettings.objects.filter(pk=site.pk).update(revenue_start_date=date(9999, 1, 1))
        site = SiteSettings.load()
        same = RevenueForm({"revenue_start_date": "9999-01-01", "revenue_paying_percent": "80", "revenue_dropoff_percent": "0"}, instance=site)
        self.assertTrue(same.is_valid(), same.errors)
        new = RevenueForm({"revenue_start_date": "8888-01-01", "revenue_paying_percent": "80", "revenue_dropoff_percent": "0"}, instance=SiteSettings.load())
        self.assertFalse(new.is_valid())
        self.assertIn("revenue_start_date", new.errors)

