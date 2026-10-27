from django.core import mail
from django.test import TestCase

from notifications import emailbody
from notifications import suppression
from notifications.models import EmailLog, EmailSuppression
from plans.management.commands.seed_phase1 import seed_all
from users import services, tokens
from users.models import User

OLD, NEW = "an-old-passphrase-1", "a brand new passphrase 42"


class PasswordChangedEmailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def setUp(self):
        self.user = User.objects.create_user("pat@example.com", OLD, first_name="Pat")
        mail.outbox.clear()

    def test_signed_in_change_sends_one_email_with_the_reset_link(self):
        self.user.is_superuser = True  # superusers open the member area without a registration
        self.user.save()
        self.client.force_login(self.user)
        response = self.client.post("/account/you/password/", {"old_password": OLD, "new_password1": NEW, "new_password2": NEW})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["pat@example.com"])
        self.assertIn("/forgot-password/", message.body)
        self.assertIn("Hello Pat", message.body)
        self.assertNotIn(NEW, message.body)

    def test_completed_reset_sends_the_email(self):
        uid, token = tokens.make_reset_link_parts(self.user)
        services.reset_password(uid, token, NEW)
        self.assertEqual([m.subject for m in mail.outbox], ["Your Spa 99 password was changed"])

    def test_first_password_from_an_invite_sends_nothing(self):
        team = User.objects.create_user("team@example.com", None, first_name="Tia")
        uid, token = tokens.make_reset_link_parts(team)
        services.reset_password(uid, token, NEW)
        self.assertTrue(User.objects.get(pk=team.pk).check_password(NEW))
        self.assertEqual(len(mail.outbox), 0)

    def test_suppressed_address_is_skipped_by_the_guard(self):
        suppression.add("pat@example.com", EmailSuppression.HARD_BOUNCE, "f1")
        services.password_changed(self.user)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(EmailLog.objects.get(template="password_changed").status, EmailLog.SUPPRESSED)

    def test_wording_is_editable_with_its_placeholders(self):
        spec = emailbody.spec_for("password_changed")
        self.assertEqual(emailbody.validate(spec, body="Hi {first_name}, changed {when}. Reset: {reset_url}"), {})
        self.assertIn("body", emailbody.validate(spec, body="Hi {nope}"))
