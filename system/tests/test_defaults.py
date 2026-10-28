"""System > Defaults: code values, the pages and rules that read them, validation, access, log and reset. Mocked: no real APIs."""
import time
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, RequestFactory, TestCase
from django.utils import timezone

from gold import approval, invites
from gold.models import GoldApplication, GoldInvite
from gold.tests.test_gold import application_data
from gold import services as gold_services
from office import leads as lead_lists
from office import lists
from office.tests.test_office import OFFICE, get, staff
from plans.management.commands.seed_phase1 import seed_all
from system import defaults, forms_defaults, services
from system.models import SiteDefaults, SystemChange
from system.tests.test_system import PASSWORD, make_user, unlocked_client

User = get_user_model()


def values(**over):
    """The whole form as the page posts it (today's values), with some changed."""
    form = forms_defaults.DefaultsForm(instance=SiteDefaults.load())
    return {**{name: form.initial[name] for name in forms_defaults.FIELDS}, "row_token": form.initial["row_token"], **over}


class CodeValueTests(TestCase):
    def test_no_row_means_todays_values_and_the_row_is_made_on_first_read(self):
        self.assertFalse(SiteDefaults.objects.exists())
        d = defaults.get()
        self.assertEqual((d.leads_range, d.leads_show, d.leads_sort, d.leads_page_size, d.list_page_size), ("30d", "all", "last_seen", 25, 50))
        self.assertEqual((d.dashboard_range, d.analytics_range, d.result_reasons, d.toast_seconds, d.toast_long_seconds), ("7d", "30d", 3, 4, 6))
        self.assertEqual((d.gold_invite_days, d.gold_approval_days, d.register_invite_days, d.office_session_days, d.email_confirm_hours),
                         (14, 14, 30, 30, 24))
        self.assertEqual(SiteDefaults.objects.count(), 1)

    def test_every_field_on_the_page_has_a_hint_and_a_group(self):
        self.assertEqual(sorted(forms_defaults.FIELDS), sorted(f.name for f in SiteDefaults._meta.fields if f.editable and f.name not in ("id", "created_at", "updated_at")))
        self.assertEqual(forms_defaults.hint("leads_range"), "Default: 30 days")
        self.assertEqual(forms_defaults.hint("email_confirm_hours"), "Default: 24 hours")

    def test_the_request_copy_is_loaded_once(self):
        SiteDefaults.load()
        request = RequestFactory().get("/")
        with self.assertNumQueries(1):
            defaults.get(request)
        with self.assertNumQueries(0):
            defaults.get(request)


class UnreadableTests(TestCase):
    def test_an_unreadable_table_gives_the_code_defaults_not_an_error(self):
        from django.db import DatabaseError

        with mock.patch.object(SiteDefaults.objects, "get_or_create", side_effect=DatabaseError("no such table")):
            d = defaults.get()
            self.assertEqual((d.leads_range, d.toast_seconds, d.office_session_days), ("30d", 4, 30))
            self.assertIsNone(SiteDefaults().pk and None)  # an unsaved copy
            self.assertEqual(Client().get("/").status_code, 200)  # a public page still renders


class TextFollowsDefaults(TestCase):
    def test_privacy_and_register_wording_fill_from_the_defaults(self):
        from content import legal_render, services as content_services

        SiteDefaults.objects.update_or_create(singleton_key="site", defaults={"gold_invite_days": 7, "email_confirm_hours": 1})
        self.assertIn("expires after 7 days", legal_render.render("It expires after {gold_invite_days}."))
        self.assertEqual(content_services.fill("It works for {confirm_for}.", ""), "It works for 1 hour.")


class OfficeUsesTheDefaults(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles")

    def test_changing_the_leads_range_changes_the_default_view_and_what_counts_as_unfiltered(self):
        request = RequestFactory().get("/leads/")
        filters = lead_lists.filters_from(request)
        self.assertEqual((filters["range"], lead_lists.is_filtered(filters, request)), ("30d", False))
        SiteDefaults.objects.update_or_create(singleton_key="site", defaults={"leads_range": "90d", "leads_sort": "visits"})
        request = RequestFactory().get("/leads/")
        filters = lead_lists.filters_from(request)
        self.assertEqual((filters["range"], filters["sort"], lead_lists.is_filtered(filters, request)), ("90d", "visits", False))
        explicit = lead_lists.filters_from(RequestFactory().get("/leads/?range=30d"))
        self.assertTrue(lead_lists.is_filtered(explicit, request))  # 30 days is now a narrowing choice

    def test_a_page_size_applies(self):
        for i in range(7):
            User.objects.create_user(f"u{i}@example.com", "x")
        SiteDefaults.objects.update_or_create(singleton_key="site", defaults={"list_page_size": 5})
        rows, has_next = lists.cut(User.objects.order_by("email"), 1)
        self.assertEqual((len(rows), has_next), (5, True))

    def test_the_dashboard_opens_on_the_default_range(self):
        seed_all()
        SiteDefaults.objects.update_or_create(singleton_key="site", defaults={"dashboard_range": "30d"})
        response = get(staff("Admin", "a@example.com"), "/")
        self.assertEqual(response.context["data"]["range"], "30d")


class LinkAndSignInTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles")
        seed_all()

    def test_office_sign_in_length_is_read_at_sign_in(self):
        SiteDefaults.objects.update_or_create(singleton_key="site", defaults={"office_session_days": 3})
        user = staff("Admin", "a@example.com")
        user.set_password(PASSWORD)
        user.save()
        client = Client(HTTP_HOST=OFFICE)
        self.assertEqual(client.post("/login/", {"username": user.email, "password": PASSWORD}).status_code, 302)
        self.assertAlmostEqual(client.session.get_expiry_age(), 3 * 86400, delta=60)

    def test_gold_invite_days_apply_to_new_links_and_never_cut_off_links_already_sent(self):
        application = gold_services.submit_application(application_data())[0]
        invites.approve_and_invite(application, staff("Admin", "a@example.com"))
        old = application.invites.get()
        token = invites.make_token(old)
        SiteDefaults.objects.update_or_create(singleton_key="site", defaults={"gold_invite_days": 3})
        self.assertEqual(invites.read_invite(token)[0], invites.OK)  # the row's own date still rules
        old.refresh_from_db()
        self.assertAlmostEqual(old.expires_at - old.created_at, timedelta(days=14), delta=timedelta(seconds=10))
        invites.resend_invite(application)
        new = GoldInvite.objects.exclude(pk=old.pk).get()
        self.assertAlmostEqual(new.expires_at - new.created_at, timedelta(days=3), delta=timedelta(seconds=10))

    def test_approval_link_days_apply_to_links_already_sent(self):
        application = gold_services.submit_application(application_data())[0]
        token = approval.make_approve_token(application)
        later = time.time() + 5 * 86400
        with mock.patch("django.core.signing.time.time", return_value=later):
            self.assertTrue(approval.approve_token_is_valid(token, application))  # 14 days
            SiteDefaults.objects.update_or_create(singleton_key="site", defaults={"gold_approval_days": 3})
            self.assertFalse(approval.approve_token_is_valid(token, application))

    def test_email_confirmation_hours_are_read_when_checked(self):
        from users import tokens

        user = User.objects.create_user("v@example.com", "x")
        token = tokens.make_verify_token(user)
        SiteDefaults.objects.update_or_create(singleton_key="site", defaults={"email_confirm_hours": 2})
        with mock.patch("django.core.signing.time.time", return_value=time.time() + 3 * 3600):
            self.assertEqual(tokens.read_verify_token(token)[0], tokens.EXPIRED)


class NotificationTests(TestCase):
    def test_toast_times_are_in_every_staff_base_template_and_the_public_site(self):
        call_command("setup_roles")
        seed_all()
        SiteDefaults.objects.update_or_create(singleton_key="site", defaults={"toast_seconds": 9, "toast_long_seconds": 12})
        marker = 'data-toast-ms="9000" data-toast-long-ms="12000"'
        self.assertContains(get(staff("Admin", "a@example.com"), "/"), marker)
        system_client = unlocked_client(make_user())
        self.assertContains(system_client.get("/defaults/"), marker)
        self.assertContains(Client().get("/"), marker)


class PageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles")

    def setUp(self):
        self.dev = make_user()
        self.client = unlocked_client(self.dev)

    def test_only_developers_get_in(self):
        for user in (None, staff("Admin", "a@example.com")):
            client = Client(HTTP_HOST="system.localhost")
            if user:
                client.force_login(user)
            self.assertEqual(client.get("/defaults/").status_code, 404)
            self.assertEqual(client.post("/defaults/", values()).status_code, 404)
            self.assertEqual(client.post("/defaults/reset/", {"field": "leads_range"}).status_code, 404)
        self.assertContains(self.client.get("/defaults/"), "Reset to default")

    def test_save_is_logged_and_undoable_and_reset_restores_the_code_value(self):
        self.assertEqual(self.client.post("/defaults/", values(leads_page_size="40", leads_range="90d")).status_code, 302)
        d = SiteDefaults.load()
        self.assertEqual((d.leads_page_size, d.leads_range), (40, "90d"))
        change = SystemChange.objects.get(section="defaults", field="leads_page_size")
        self.assertEqual((change.old_value, change.new_value), (25, 40))
        services.undo_change(change, self.dev)
        self.assertEqual(SiteDefaults.load().leads_page_size, 25)
        self.client.post("/defaults/reset/", {"field": "leads_range"})
        self.assertEqual(SiteDefaults.load().leads_range, "30d")
        self.assertTrue(SystemChange.objects.filter(section="defaults", field="leads_range", new_value="30d").exists())
        self.client.post("/defaults/reset/", {"field": "not_a_field"})  # refused, nothing breaks

    def test_out_of_range_and_unknown_choices_are_refused_and_nothing_is_saved(self):
        for bad in ({"office_session_days": "31"}, {"leads_page_size": "0"}, {"leads_page_size": "5000"}, {"toast_seconds": "1"}, {"gold_invite_days": "400"},
                    {"leads_range": "forever"}, {"dashboard_range": "90d"}, {"gold_nudge_low": "popup"}, {"leads_page_size": "abc"}):
            response = self.client.post("/defaults/", values(**bad))
            self.assertEqual(response.status_code, 400, bad)
        self.assertEqual(SiteDefaults.load().leads_page_size, 25)
        self.assertFalse(SystemChange.objects.filter(section="defaults").exists())


class EmailWordingFollowsDefaults(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles")

    def test_verify_email_says_the_configured_hours_and_follows_a_change(self):
        from django.core import mail

        from notifications.services import send_templated
        from users.tasks import send_verification_email

        user = User.objects.create_user("v@example.com", "x", first_name="Vic")
        send_verification_email(user.pk)
        self.assertIn("The link works for 24 hours.", mail.outbox[-1].body)
        SiteDefaults.objects.update_or_create(singleton_key="site", defaults={"email_confirm_hours": 48})
        send_verification_email(user.pk)
        self.assertIn("The link works for 48 hours.", mail.outbox[-1].body)
        self.assertNotIn("{valid_for}", mail.outbox[-1].body)

    def test_link_emails_use_days_in_plain_words_and_the_row_length(self):
        from notifications import emailbody

        SiteDefaults.objects.update_or_create(singleton_key="site", defaults={"gold_invite_days": 1, "register_invite_days": 21})
        self.assertEqual(emailbody.values_for(emailbody.SPECS["gold_invite"], {})["valid_for"], "1 day")
        self.assertEqual(emailbody.values_for(emailbody.SPECS["gold_invite"], {"valid_days": 14})["valid_for"], "14 days")  # a sent link keeps its own length
        self.assertEqual(emailbody.values_for(emailbody.SPECS["invite"], {})["valid_for"], "21 days")

    def test_preview_shows_it_and_the_placeholder_is_accepted(self):
        from notifications import emailbody

        SiteDefaults.objects.update_or_create(singleton_key="site", defaults={"email_confirm_hours": 6})
        client = unlocked_client(make_user())
        body = "Hello {first_name}. It works for {valid_for}.\n\n{button}"
        self.assertEqual(emailbody.validate(emailbody.SPECS["verify"], body=body), {})
        data = client.post("/emails/automatic/verify/preview/", {"subject": "Hi", "body": body}).json()
        self.assertTrue(data["ok"])
        self.assertIn("It works for 6 hours.", data["text"])
        self.assertContains(client.get("/emails/automatic/verify/"), "valid_for")
