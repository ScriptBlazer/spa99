"""System > Launch: the plan skips what is already on, one press flips the settings and opens payments once, the typed word is checked by
the server, access is like the other risky System actions, and the change log gets its rows. Mocked: the local mail outbox, no real sending."""
from unittest import mock

from django.core import mail
from django.test import Client

from plans import payments
from plans.models import PaymentWindow, SiteSettings
from plans.tests.test_payments import PaymentCase
from system import launch, services
from system.models import SystemChange, SystemEvent
from system.tests.test_system import PASSWORD, SYSTEM, make_user, sign_in, unlocked_client


class LaunchCase(PaymentCase):
    def setUp(self):
        super().setUp()
        SiteSettings.objects.update(memberships_public=False, journey_email_gate=True, join_wording=SiteSettings.INTEREST, launched_at=None, launched_by=None)
        self.dev = make_user("launcher@example.com")
        self.client = unlocked_client(self.dev)

    def press(self, word="LAUNCH", client=None):
        return (client or self.client).post("/launch/", {"confirm": word})


class PlanTests(LaunchCase):
    def test_the_plan_lists_four_steps_and_skips_what_is_already_on(self):
        steps = {s["key"]: s for s in launch.plan(SiteSettings.load())}
        self.assertEqual(list(steps), ["memberships_public", "journey_email_gate", "join_wording", "payments"])
        self.assertFalse(any(s["already_done"] for s in steps.values()))
        self.assertEqual((steps["join_wording"]["now"], steps["join_wording"]["after"]), ("Register", "Join"))
        SiteSettings.objects.update(memberships_public=True, join_wording=SiteSettings.JOIN)
        steps = {s["key"]: s for s in launch.plan(SiteSettings.load())}
        self.assertTrue(steps["memberships_public"]["already_done"] and steps["join_wording"]["already_done"])
        self.assertFalse(steps["journey_email_gate"]["already_done"])
        payments.open_now(self.dev)
        self.assertTrue({s["key"]: s for s in launch.plan(SiteSettings.load())}["payments"]["already_done"])

    def test_checks_count_the_members_and_warn_about_card_payments_and_an_existing_window(self):
        self.member(), self.member(), self.member(verified=False)
        by_key = {c["key"]: c for c in launch.checks(SiteSettings.load())}
        self.assertTrue(by_key["plans"]["ok"] and by_key["emails"]["ok"])
        self.assertFalse(by_key["online"]["ok"])
        self.assertIn("2 members will be emailed", by_key["members"]["text"])
        payments.open_now(self.dev)
        self.assertIn("window", {c["key"] for c in launch.checks(SiteSettings.load())})


class LaunchTests(LaunchCase):
    def test_one_press_flips_the_settings_opens_payments_once_and_logs_it(self):
        a, b = self.member(), self.member()
        self.press()
        self.press()  # a second click or tab
        site = SiteSettings.load()
        self.assertTrue(site.memberships_public)
        self.assertFalse(site.journey_email_gate)
        self.assertEqual(site.join_wording, SiteSettings.JOIN)
        self.assertIsNotNone(site.launched_at)
        self.assertEqual(site.launched_by, self.dev)
        self.assertEqual(PaymentWindow.objects.count(), 1)
        self.assertEqual(PaymentWindow.objects.get().status, PaymentWindow.OPEN)
        self.assertEqual(len(self.mails("set up")), 2)  # each member once
        self.assertEqual(SystemEvent.objects.filter(kind=SystemEvent.LAUNCHED).count(), 1)
        fields = set(SystemChange.objects.filter(model_label="plans.sitesettings").values_list("field", flat=True))
        self.assertTrue({"memberships_public", "journey_email_gate", "join_wording", "launched_at"} <= fields)

    def test_a_step_already_on_is_not_changed_again_and_a_window_already_open_is_kept(self):
        site = SiteSettings.load()
        site.memberships_public = True
        services.save_logged(site, self.dev, fields=["memberships_public"])
        window, _ = payments.open_now(self.dev)
        old = set(SystemChange.objects.values_list("pk", flat=True))
        before = len(mail.outbox)
        result = launch.launch(self.dev)
        self.assertEqual(result["changed"], ["Email gate", "Wording"])
        self.assertFalse(result["payments_opened"])
        self.assertEqual(PaymentWindow.objects.get().pk, window.pk)
        self.assertEqual(len(mail.outbox), before)
        fields = set(SystemChange.objects.exclude(pk__in=old).filter(model_label="plans.sitesettings").values_list("field", flat=True))
        self.assertNotIn("memberships_public", fields)
        self.assertIn("journey_email_gate", fields)

    def test_launch_when_already_launched_does_nothing_and_says_so(self):
        launch.launch(self.dev)
        again = launch.launch(self.dev)
        self.assertFalse(again["launched"])
        self.assertIn("already launched", again["message"])
        self.assertEqual(SystemEvent.objects.filter(kind=SystemEvent.LAUNCHED).count(), 1)

    def test_payments_failing_leaves_the_settings_saved_and_says_so(self):
        with mock.patch("plans.payments.open_now", side_effect=RuntimeError("boom")):
            result = launch.launch(self.dev)
        self.assertTrue(result["launched"] and result["payments_failed"])
        self.assertTrue(SiteSettings.load().launched_at)
        self.assertEqual(PaymentWindow.objects.count(), 0)


class LaunchViewTests(LaunchCase):
    def test_the_wrong_word_changes_nothing(self):
        for word in ("", "launch", "LAUNCH ", "yes"):
            self.assertEqual(self.press(word).status_code, 302)
        site = SiteSettings.load()
        self.assertIsNone(site.launched_at)
        self.assertFalse(site.memberships_public)
        self.assertEqual(PaymentWindow.objects.count(), 0)

    def test_the_page_before_and_after(self):
        html = self.client.get("/launch/").content.decode()
        self.assertIn("data-launch-button", html)
        self.assertIn('data-confirm-guard="LAUNCH"', html)
        self.assertIn("Not yet", self.client.get("/").content.decode())
        self.press()
        html = self.client.get("/launch/").content.decode()
        self.assertIn("data-launched", html)
        self.assertNotIn("data-launch-button", html)
        self.assertIn("Launched ", self.client.get("/").content.decode())

    def test_only_unlocked_developers_get_in(self):
        self.assertEqual(Client(HTTP_HOST=SYSTEM).get("/launch/").status_code, 404)  # System answers 404 to anyone without access
        office = make_user("office@example.com", system=False)
        client = Client(HTTP_HOST=SYSTEM)
        client.force_login(office)
        self.assertEqual(client.get("/launch/").status_code, 404)
        self.assertEqual(client.post("/launch/", {"confirm": "LAUNCH"}).status_code, 404)
        locked, _ = sign_in(make_user("locked@example.com"))  # signed in but not unlocked: sent to the unlock page
        response = locked.post("/launch/", {"confirm": "LAUNCH"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/unlock/"))
        self.assertIsNone(SiteSettings.load().launched_at)

    def test_csrf_is_enforced(self):
        self.client.handler.enforce_csrf_checks = True
        self.assertEqual(self.press().status_code, 403)
        self.assertIsNone(SiteSettings.load().launched_at)
