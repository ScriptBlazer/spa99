"""System: 404 for everyone else, sign-in then unlock, the 15 minute idle lock, the change log with undo, recipients in the
database, the one-off env import and Team guards. Mocked: no real APIs, no real clock."""
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import Client, TestCase, override_settings

from insights.models import OfficeSnapshot
from plans.models import SiteSettings
from system import services
from system.models import SystemChange

User = get_user_model()
SYSTEM, OFFICE = "system.localhost", "office.localhost"
PASSWORD = "a-long-test-password-1"
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "system-tests"}}


def make_user(email="dev@example.com", system=True, staff=True, superuser=False):
    user = User.objects.create_user(email, PASSWORD, is_staff=staff, is_superuser=superuser)
    if system:
        user.groups.add(Group.objects.get_or_create(name="System")[0])
    return user


def sign_in(user, host=SYSTEM, password=PASSWORD):
    client = Client(HTTP_HOST=host)
    response = client.post("/login/", {"username": user.email, "password": password})
    return client, response


def unlocked_client(user):
    client, _ = sign_in(user)
    client.post("/unlock/", {"password": PASSWORD})
    return client


class AccessTests(TestCase):
    PATHS = ["/", "/changes/", "/emails/", "/settings/", "/team/", "/unlock/"]

    def test_everyone_who_may_not_be_here_gets_a_plain_404(self):
        office_staff = make_user("office@example.com", system=False)
        member = make_user("member@example.com", system=True, staff=False)  # System group but not staff
        for user in (None, office_staff, member):
            client = Client(HTTP_HOST=SYSTEM)
            if user:
                client.force_login(user)
            for path in self.PATHS:
                self.assertEqual(client.get(path).status_code, 404, (user, path))
            self.assertEqual(client.post("/changes/00000000-0000-0000-0000-000000000000/undo/").status_code, 404)
            self.assertEqual(client.post("/team/00000000-0000-0000-0000-000000000000/roles/").status_code, 404)

    def test_sign_in_page_is_open_but_only_developers_get_in(self):
        self.assertEqual(Client(HTTP_HOST=SYSTEM).get("/login/").status_code, 200)
        _, response = sign_in(make_user("office@example.com", system=False))
        self.assertEqual(response.status_code, 200)  # the ordinary "wrong email or password" answer, no redirect
        self.assertContains(response, "data-system-error")

    def test_sign_in_alone_is_not_enough_unlock_is_required(self):
        client, response = sign_in(make_user())
        self.assertEqual(response.status_code, 302)
        locked = client.get("/changes/")
        self.assertEqual((locked.status_code, locked["Location"]), (302, "/unlock/?next=%2Fchanges%2F"))
        self.assertEqual(client.post("/unlock/", {"password": "wrong"}).status_code, 200)
        self.assertEqual(client.get("/changes/").status_code, 302)  # still locked
        self.assertRedirects(client.post("/unlock/", {"password": PASSWORD, "next": "/changes/"}), "/changes/")
        response = client.get("/changes/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")
        client.post("/lock/")  # the Lock button
        self.assertEqual(client.get("/changes/").status_code, 302)

    def test_unlock_expires_after_15_idle_minutes_and_activity_slides_it(self):
        client, _ = sign_in(make_user())
        with mock.patch("system.services.time.time", return_value=1000.0):
            client.post("/unlock/", {"password": PASSWORD})
        for now, expected in ((1000 + 14 * 60, 200), (1000 + 28 * 60, 200), (1000 + 28 * 60 + 15 * 60 + 1, 302)):
            with mock.patch("system.services.time.time", return_value=float(now)):
                self.assertEqual(client.get("/").status_code, expected, now)

    def test_an_office_session_never_unlocks_system(self):
        user = make_user("both@example.com")
        client, _ = sign_in(user, host=OFFICE)  # a real Office sign-in; the same cookie reaches the System host
        self.assertEqual(client.get("/", HTTP_HOST=SYSTEM).status_code, 404)
        self.assertEqual(client.post("/unlock/", {"password": PASSWORD}, HTTP_HOST=SYSTEM).status_code, 404)
        self.assertEqual(client.get("/changes/", HTTP_HOST=SYSTEM).status_code, 404)

    @override_settings(CACHES=LOCMEM)
    def test_unlock_attempts_are_rate_limited(self):
        from django.core.cache import cache

        cache.clear()
        self.addCleanup(cache.clear)
        client, _ = sign_in(make_user())
        codes = [client.post("/unlock/", {"password": "nope"}).status_code for _ in range(7)]
        self.assertEqual(codes[:5], [200] * 5)
        self.assertEqual(codes[5:], [429, 429])
        self.assertEqual(client.post("/unlock/", {"password": PASSWORD}).status_code, 429)  # even the right one waits


class ChangeLogTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = unlocked_client(self.user)

    def test_a_settings_change_logs_who_when_old_and_new_and_undo_restores_it(self):
        site = SiteSettings.load()
        self.assertEqual(site.vat_rate, Decimal("20.00"))
        response = self.client.post("/settings/", {"opening_text": "January 2027", "register_interest_open": "on", "join_wording": "register_interest", "vat_rate": "25.00", "lock_idle_minutes": "15", "max_sign_in_hours": "12"})
        self.assertEqual(response.status_code, 302)
        change = SystemChange.objects.get(field="vat_rate")
        self.assertEqual((change.old_value, change.new_value, change.user, change.section, change.model_label),
                         ("20.00", "25.00", self.user, "plans", "plans.sitesettings"))
        self.assertEqual(SiteSettings.load().vat_rate, Decimal("25.00"))

        self.client.post(f"/changes/{change.pk}/undo/")
        self.assertEqual(SiteSettings.load().vat_rate, Decimal("20.00"))
        undo = SystemChange.objects.get(undo_of=change)
        self.assertEqual((undo.old_value, undo.new_value, undo.user), ("25.00", "20.00", self.user))
        self.assertEqual(SystemChange.objects.filter(field="vat_rate").count(), 2)  # history is kept, nothing deleted
        self.client.post(f"/changes/{change.pk}/undo/")  # the value is no longer what this entry set: refused
        self.assertEqual(SystemChange.objects.filter(field="vat_rate").count(), 2)

    def test_an_edit_made_outside_system_is_listed_and_filterable(self):
        site = SiteSettings.load()
        site.capacity = 30
        site.save()  # a script: no person
        response = self.client.get("/changes/?section=hours&user=")
        entries = list(response.context["entries"])
        self.assertEqual([(e.field, e.user_label) for e in entries], [("capacity", "")])  # no person: shown as "a script"
        self.assertEqual(list(self.client.get("/changes/?section=gold").context["entries"]), [])

    def test_created_and_team_entries_cannot_be_undone(self):
        for entry in (SystemChange(kind="created", field="", history_id=1), SystemChange(kind="direct", field="roles")):
            with self.assertRaises(services.ChangeRefused):
                services.undo_change(entry, self.user)


class RecipientsTests(TestCase):
    def setUp(self):
        self.client = unlocked_client(make_user())

    def test_recipients_are_validated_saved_in_the_database_and_logged(self):
        bad = self.client.post("/emails/", {"gold_approver_emails": "a@example.test, nonsense", "gold_approver_cc": "", "contact_email": ""})
        self.assertEqual(bad.status_code, 400)
        self.assertContains(bad, "nonsense is not a valid email address", status_code=400)
        self.client.post("/emails/", {"gold_approver_emails": "a@example.test, b@example.test", "gold_approver_cc": "c@example.test", "contact_email": "hello@example.test"})
        site = SiteSettings.load()
        self.assertEqual((site.approver_list, site.approver_cc_list, site.contact_address), (["a@example.test", "b@example.test"], ["c@example.test"], "hello@example.test"))
        self.assertEqual(SystemChange.objects.filter(section="emails").count(), 3)

    def test_no_approver_means_nothing_sent_and_no_crash_and_env_settings_are_gone(self):
        from django.conf import settings
        from gold import tasks

        self.assertFalse(any(hasattr(settings, n) for n in ("GOLD_APPROVER_EMAILS", "GOLD_APPROVER_CC", "CONTACT_EMAIL")))
        self.assertEqual(SiteSettings.load().approver_list, [])
        self.assertTrue(callable(tasks.send_gold_emails))  # empty list behaviour is covered in gold.tests (sends nothing, logs once)


class FakeEnv:
    def __init__(self, **values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)


class ImportCommandTests(TestCase):
    def run_command(self, *args, **env):
        out = StringIO()
        with override_settings(ENV=FakeEnv(**env)):
            call_command("import_email_settings_from_env", *args, stdout=out)
        return out.getvalue()

    ENV = {"GOLD_APPROVER_EMAILS": "a@example.test,b@example.test", "GOLD_APPROVER_CC": "c@example.test", "CONTACT_EMAIL": "hi@example.test"}

    def test_dry_run_changes_nothing_then_a_real_run_copies_blank_fields_only(self):
        out = self.run_command("--dry-run", **self.ENV)
        self.assertIn("would copy", out)
        self.assertEqual(SiteSettings.load().gold_approver_emails, "")
        self.run_command(**self.ENV)
        site = SiteSettings.load()
        self.assertEqual((site.gold_approver_emails, site.gold_approver_cc, site.contact_email), ("a@example.test, b@example.test", "c@example.test", "hi@example.test"))
        site.contact_email = "edited@example.test"
        site.save()
        self.assertIn("left alone", self.run_command(**self.ENV))  # never overwrites what System holds
        self.assertEqual(SiteSettings.load().contact_email, "edited@example.test")


class TeamAndDashboardTests(TestCase):
    def test_team_roles_are_logged_and_you_cannot_lock_yourself_out(self):
        for role in ("Owner", "Viewer", "System"):
            Group.objects.get_or_create(name=role)
        me, other = make_user(), make_user("other@example.com", system=False)
        client = unlocked_client(me)
        client.post(f"/team/{other.pk}/roles/", {"roles": ["Viewer"]})
        self.assertEqual(list(other.groups.values_list("name", flat=True)), ["Viewer"])
        entry = SystemChange.objects.get(section="team", field="roles")
        self.assertEqual((entry.old_value, entry.new_value, entry.undoable), ([], ["Viewer"], False))
        client.post(f"/team/{me.pk}/roles/", {"roles": ["Owner"]})  # would drop my own System role
        self.assertTrue(me.groups.filter(name="System").exists())
        client.post(f"/team/{me.pk}/active/", {"active": "0"})
        me.refresh_from_db()
        self.assertTrue(me.is_active)
        client.post(f"/team/{other.pk}/active/", {"active": "0"})
        other.refresh_from_db()
        self.assertFalse(other.is_active)
        self.assertFalse(me.is_superuser)

    def test_dashboard_reads_stored_figures_only(self):
        OfficeSnapshot.objects.create(page="dashboard", range="7d", payload={"totals": {"registrations": 12, "gold_applications": 3}})
        client = unlocked_client(make_user())
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        health = response.context["health"]
        self.assertEqual((health["database_ok"], health["queue_size"], health["counts"]), (True, 0, {"registrations": 12, "gold_applications": 3}))
        self.assertEqual(response.context["stages"][0], ("Register interest", True))
