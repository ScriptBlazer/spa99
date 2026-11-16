"""Invisible characters on an email address (U+200F, U+202C from phone copy-paste): cleaned on the way in, at send time, and in stored data."""
from io import StringIO

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from common.emails import clean_email, has_hidden
from common.validators import normalise_email
from journey import services as journey_services
from mailings.models import ContactList, ContactListMember, EmailOptOut
from notifications.models import EmailLog
from notifications.services import send_templated

User = get_user_model()
BAD = "‬‏"


class CleanerTests(SimpleTestCase):
    def test_removes_format_characters_and_whitespace_only(self):
        self.assertEqual(clean_email(f"  Name@Gmail.com{BAD} "), "name@gmail.com")
        self.assertEqual(clean_email("​n﻿ame@x.com⁠"), "name@x.com")
        self.assertEqual(clean_email("ｎame@x.com"), "ｎame@x.com")  # no NFKC: real characters stay as typed
        self.assertEqual(clean_email(None), "")
        self.assertTrue(has_hidden(f"a@b.com{BAD}"))
        self.assertFalse(has_hidden("a@b.com"))

    def test_the_shared_validator_used_to_accept_them(self):  # Django's EmailValidator passes hidden characters after the domain
        self.assertEqual(normalise_email(f"A@Gmail.com{BAD}"), "a@gmail.com")


class InputPathTests(TestCase):
    def test_the_journey_gate_stores_the_clean_address(self):
        session = journey_services.create_session("Mozilla/5.0 (iPhone) Mobile Safari")
        self.assertEqual(journey_services.save_lead(session, f"Lead@Gmail.com{BAD}", True), "lead@gmail.com")
        session.refresh_from_db()
        self.assertEqual(session.lead_email, "lead@gmail.com")

    def test_a_model_save_cleans_too(self):
        user = User.objects.create_user(f"Out@Gmail.com{BAD}", "correct horse battery staple")
        self.assertEqual(user.email, "out@gmail.com")
        user.email = f"Out2@Gmail.com{BAD}"
        user.save()
        self.assertEqual(User.objects.get().email, "out2@gmail.com")


class SendTimeTests(TestCase):
    def test_a_stored_bad_address_is_sent_to_the_clean_one(self):
        log = send_templated("verify", [f"a@gmail.com{BAD}"], "Confirm", {"first_name": "A", "url": "u"}, cc=[f"b@gmail.com{BAD}"])
        self.assertEqual(log.status, EmailLog.SENT)
        self.assertEqual((mail.outbox[0].to, mail.outbox[0].cc), (["a@gmail.com"], ["b@gmail.com"]))
        self.assertEqual(EmailLog.objects.get().to, "a@gmail.com")


class CommandTests(TestCase):
    def run_command(self, *args):
        out = StringIO()
        call_command("clean_hidden_email_chars", *args, stdout=out)
        return out.getvalue()

    def setUp(self):
        self.user = User.objects.create_user("member@gmail.com", "correct horse battery staple")
        User.objects.filter(pk=self.user.pk).update(email=f"member@gmail.com{BAD}")  # stored dirty, as on live
        self.optout = EmailOptOut.objects.create(email="x@gmail.com")
        EmailOptOut.objects.filter(pk=self.optout.pk).update(email=f"x@gmail.com{BAD}")

    def test_dry_run_masks_and_writes_nothing_then_apply_fixes_and_second_run_is_empty(self):
        out = self.run_command()
        self.assertIn(f"users_user . {self.user.pk} . email: m***@gmail.com<U+202C><U+200F> -> m***@gmail.com", out)
        self.assertNotIn("member@", out)
        self.assertIn("Dry run", out)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, f"member@gmail.com{BAD}")
        self.run_command("--apply")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "member@gmail.com")
        self.assertEqual(EmailOptOut.objects.get().email, "x@gmail.com")
        self.assertIn("Nothing to change", self.run_command("--apply"))

    def test_a_clash_with_an_existing_row_is_a_conflict_and_is_skipped(self):
        EmailOptOut.objects.create(email="x@gmail.com")  # the clean twin already exists
        out = self.run_command("--apply")
        self.assertIn("CONFLICT (skipped)", out)
        self.assertEqual(EmailOptOut.objects.filter(email=f"x@gmail.com{BAD}").count(), 1)  # untouched
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "member@gmail.com")  # the rest still done

    def test_a_clash_inside_a_two_field_unique_constraint_is_a_conflict(self):  # ContactListMember(list, email)
        lst = ContactList.objects.create(name="L")
        other = ContactList.objects.create(name="M")
        clean = ContactListMember.objects.create(list=lst, email="y@gmail.com")
        dirty = ContactListMember.objects.create(list=lst, email="tmp@gmail.com")
        ContactListMember.objects.filter(pk=dirty.pk).update(email=f"y@gmail.com{BAD}")
        elsewhere = ContactListMember.objects.create(list=other, email="tmp2@gmail.com")  # same address in ANOTHER list is fine
        ContactListMember.objects.filter(pk=elsewhere.pk).update(email=f"y@gmail.com{BAD}")
        dry = self.run_command()
        self.assertIn(f"CONFLICT (skipped) mailings_contactlistmember . {dirty.pk} . email", dry)
        self.assertIn(f"WOULD CHANGE mailings_contactlistmember . {elsewhere.pk} . email", dry)
        self.run_command("--apply")  # no IntegrityError
        self.assertEqual(ContactListMember.objects.get(pk=clean.pk).email, "y@gmail.com")
        self.assertEqual(ContactListMember.objects.get(pk=dirty.pk).email, f"y@gmail.com{BAD}")
        self.assertEqual(ContactListMember.objects.get(pk=elsewhere.pk).email, "y@gmail.com")

    def test_history_and_email_log_rows_are_cleaned_keeping_case(self):  # so erasure and the lead timeline still find them
        hist = self.user.history.model.objects.filter(id=self.user.pk)
        hist.update(email=f"member@gmail.com{BAD}")
        log = EmailLog.objects.create(to=f"Member@gmail.com{BAD}", subject_email=f"member@gmail.com{BAD}", subject="s", template="t",
                                      status=EmailLog.FAILED)
        dry = self.run_command()
        self.assertIn(f"notifications_emaillog . {log.pk} . to: M***@gmail.com<U+202C><U+200F> -> M***@gmail.com", dry)
        self.assertEqual(EmailLog.objects.get(pk=log.pk).to, f"Member@gmail.com{BAD}")  # dry run wrote nothing
        self.run_command("--apply")
        log.refresh_from_db()
        self.assertEqual((log.to, log.subject_email), ("Member@gmail.com", "member@gmail.com"))  # case kept on the log
        self.assertFalse(any(has_hidden(e) for e in hist.values_list("email", flat=True)))
