"""manage.py setup_live: dry run writes and sends nothing, a real run makes both accounts and invites them, a second run changes
nothing, an edited value is left alone. Email is the locmem outbox (nothing real is sent)."""
from io import StringIO

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from unittest import mock

from common import levels
from plans.models import SiteSettings
from system.management.commands import setup_live
from system.models import SiteDefaults

User = get_user_model()


OUT = StringIO()


def run(*args):
    OUT.seek(0), OUT.truncate()
    call_command("setup_live", *args, stdout=OUT)
    return OUT.getvalue()


class SetupLiveTests(TestCase):
    def real_run(self, *args):
        with self.captureOnCommitCallbacks(execute=True):
            return run(*args)

    def test_a_real_run_refuses_when_email_only_prints(self):
        from django.core.management.base import CommandError
        with self.settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend"):
            with self.assertRaisesMessage(CommandError, "Email is not set up"):
                run()
            self.assertFalse(User.objects.filter(email="moishe@spa99.uk").exists())
            self.assertIn("Dry run", run("--dry-run"))  # the preview still works
            with self.captureOnCommitCallbacks(execute=True):
                run("--no-email-check")
        self.assertTrue(User.objects.filter(email="moishe@spa99.uk").exists())

    def test_a_dry_run_writes_nothing_and_sends_nothing(self):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            text = run("--dry-run")
        self.assertEqual(callbacks, [])
        self.assertEqual(mail.outbox, [])
        self.assertFalse(User.objects.filter(email__endswith="@spa99.uk").exists())
        self.assertEqual(SiteSettings.load().contact_email, "")
        self.assertEqual(SiteSettings.load().discount_contact_url, "")
        self.assertFalse(SiteDefaults.load().staff_alert_seeded)
        self.assertIn("would create as", text)
        self.assertNotIn("set created", text)
        self.assertIn("Dry run", text)

    def test_a_real_run_creates_both_accounts_with_the_right_groups_and_invites_them(self):
        text = self.real_run()
        moishe, barry = User.objects.get(email="moishe@spa99.uk"), User.objects.get(email="barry@spa99.uk")
        self.assertEqual((levels.held_level(moishe), levels.held_roles(moishe)), (levels.DEVELOPER, (False, True)))
        self.assertEqual((levels.held_level(barry), levels.held_roles(barry)), (levels.ADMIN, (True, False)))
        self.assertEqual((moishe.first_name, moishe.last_name, barry.last_name), ("Moishe", "Berkowitz", "Lobenstein"))
        self.assertFalse(moishe.has_usable_password() or barry.has_usable_password())
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ["barry@spa99.uk", "moishe@spa99.uk"])
        site = SiteSettings.load()
        self.assertEqual((site.contact_email, site.gold_approver_cc, site.discount_contact_url),
                         ("hello@spa99.uk", "moishe@spa99.uk", "https://wa.me/447530117902"))
        self.assertFalse(site.final_approval_on)
        self.assertEqual(SiteDefaults.load().staff_alert_emails, "moishe@spa99.uk")
        self.assertNotIn("/reset/", text)  # no link is ever printed
        self.assertIn("created as Developer + Final approver", text)
        self.assertIn("invite moishe@spa99.uk: invite sent", OUT.getvalue())

    def test_a_second_run_changes_nothing(self):
        self.real_run()
        mail.outbox.clear()
        before = (User.objects.count(), SiteSettings.load().updated_at, sorted(moishe_groups()))
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            text = run()
        self.assertEqual((callbacks, mail.outbox), ([], []))
        self.assertEqual((User.objects.count(), SiteSettings.load().updated_at, sorted(moishe_groups())), before)
        self.assertIn(": 0 set,", text)

    def test_an_edited_value_is_left_alone(self):
        SiteSettings.load()
        SiteSettings.objects.update(contact_email="info@elsewhere.test")
        text = self.real_run()
        self.assertEqual(SiteSettings.load().contact_email, "info@elsewhere.test")
        self.assertIn("contact_email: already set (left alone)", text)
        self.assertEqual(SiteSettings.load().discount_contact_url, "https://wa.me/447530117902")  # the others are still filled

    def test_an_existing_account_only_gains_and_never_loses(self):
        from plans.tests.helpers import make_team_member

        make_team_member("barry@spa99.uk", levels.DEVELOPER, approver=False, final=True)  # higher level and another role
        User.objects.filter(email="barry@spa99.uk").update(first_name="Keep")
        self.real_run()
        barry = User.objects.get(email="barry@spa99.uk")
        self.assertEqual((levels.held_level(barry), levels.held_roles(barry), barry.first_name), (levels.DEVELOPER, (True, True), "Keep"))
        self.assertEqual([m.to[0] for m in mail.outbox], ["moishe@spa99.uk"])  # only the new account is invited

    def test_a_bad_value_is_reported_and_the_rest_carry_on(self):
        with mock.patch.dict(setup_live.SITE_SETTINGS, {"discount_contact_url": "http://not-https.test"}):
            text = self.real_run()
        self.assertIn("discount_contact_url: PROBLEM", text)
        self.assertEqual(SiteSettings.load().contact_email, "hello@spa99.uk")
        self.assertEqual(SiteSettings.load().discount_contact_url, "")


def moishe_groups():
    return list(User.objects.get(email="moishe@spa99.uk").groups.values_list("name", flat=True))


class SetupLiveExtrasTests(TestCase):
    def test_a_failed_invite_is_reported_and_counted(self):
        OUT.seek(0), OUT.truncate()
        with mock.patch("users.tasks.send_team_invite_email", return_value="failed"), self.captureOnCommitCallbacks(execute=True):
            call_command("setup_live", stdout=OUT)
        self.assertIn("invite FAILED: resend in System > Team", OUT.getvalue())

    def test_old_default_subjects_are_updated_but_a_custom_one_is_not(self):
        from notifications.models import NotificationTemplate

        call_command("setup_live", stdout=StringIO())
        NotificationTemplate.objects.filter(key="gold_final").update(subject="Final approval: {name} (Low potential)")
        NotificationTemplate.objects.filter(key="gold_sent_back").update(subject="My own subject")
        with self.captureOnCommitCallbacks(execute=True):
            call_command("setup_live", stdout=StringIO())
        subjects = dict(NotificationTemplate.objects.filter(key__in=["gold_final", "gold_sent_back"]).values_list("key", "subject"))
        self.assertEqual(subjects["gold_final"], "Final approval: {name} ({potential} potential)")
        self.assertEqual(subjects["gold_sent_back"], "My own subject")
