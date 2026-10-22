from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from common.ids import UNAMBIGUOUS_ALPHABET, normalise_public_code
from common.models import LoginEvent
from users.models import User
from users.services import delete_user_data, export_user_data


class UserModelTests(TestCase):
    def test_create_user_normalises_email_and_sets_defaults(self):
        user = User.objects.create_user("  Person@Example.COM ", "a-long-password-1")
        self.assertEqual(user.email, "person@example.com")
        self.assertEqual((user.is_staff, user.is_superuser, user.is_active), (False, False, True))
        self.assertTrue(user.check_password("a-long-password-1"))
        self.assertEqual(authenticate(username="PERSON@example.com", password="a-long-password-1"), user)

    def test_email_is_unique_ignoring_case_even_if_saved_around_the_manager(self):
        User.objects.create_user("same@example.com", "a-long-password-1")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user("SAME@example.com", "a-long-password-1")
        # Straight to the database with different case: the functional unique constraint catches it.
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.bulk_create([User(email="Same@Example.com", password="x")])

    def test_superuser_flags_and_guard(self):
        admin = User.objects.create_superuser("root@example.com", "a-long-password-1")
        self.assertTrue(admin.is_staff and admin.is_superuser)
        with self.assertRaises(ValueError):
            User.objects.create_superuser("bad@example.com", "x", is_staff=False)

    def test_public_id_is_short_unambiguous_and_unique(self):
        users = [User.objects.create_user(f"u{i}@example.com") for i in range(30)]
        ids = {u.public_id for u in users}
        self.assertEqual(len(ids), 30)
        for public_id in ids:
            self.assertEqual(len(public_id), 8)
            self.assertTrue(set(public_id) <= set(UNAMBIGUOUS_ALPHABET))
        first = users[0]
        self.assertEqual(normalise_public_code(first.public_id_display.lower()), first.public_id)
        first.save()
        self.assertEqual(User.objects.get(pk=first.pk).public_id, first.public_id)  # never regenerated

    def test_mobile_is_unique_when_set_but_blank_is_allowed_many_times(self):
        User.objects.create_user("a@example.com", mobile=None)
        User.objects.create_user("b@example.com", mobile="")
        User.objects.create_user("c@example.com", mobile="+447912345678")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user("d@example.com", mobile="+447912345678")

    def test_save_stores_mobile_as_e164_so_uniqueness_holds_across_formats(self):
        user = User.objects.create_user("g@example.com", mobile="07912 345678")
        self.assertEqual(User.objects.get(pk=user.pk).mobile, "+447912345678")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user("h2@example.com", mobile="+44 7912 345678")
        with self.assertRaises(ValidationError):
            User.objects.create_user("i@example.com", mobile="not a number")

    def test_user_has_no_status_field(self):
        self.assertNotIn("status", [f.name for f in User._meta.get_fields()])

    def test_clean_normalises_mobile_and_rejects_bad_ones(self):
        user = User(email="e@example.com", mobile="07912 345679")
        user.clean()
        self.assertEqual(user.mobile, "+447912345679")
        with self.assertRaises(ValidationError):
            User(email="f@example.com", mobile="020 7946 0958").clean()

    def test_history_records_changes_but_never_the_password_hash(self):
        user = User.objects.create_user("h@example.com", "a-long-password-1")
        user.first_name = "Hugo"
        user.save()
        self.assertEqual(user.history.count(), 2)
        self.assertEqual(user.history.first().first_name, "Hugo")
        self.assertFalse(hasattr(user.history.first(), "password"))


class PersonDataTests(TestCase):
    def test_export_and_delete_cover_login_events_and_history(self):
        user = User.objects.create_user("gone@example.com", "a-long-password-1", first_name="Gus")
        LoginEvent.objects.create(event=LoginEvent.LOGIN, user=user, attempted_email=user.email, ip_address="203.0.113.1")
        LoginEvent.objects.create(event=LoginEvent.FAILED, attempted_email="GONE@example.com")
        LoginEvent.objects.create(event=LoginEvent.FAILED, attempted_email="someone-else@example.com")
        user.first_name = "Gustav"
        user.save()
        data = export_user_data(user)
        self.assertEqual(data["profile"]["first_name"], "Gustav")
        self.assertEqual(len(data["login_events"]), 2)  # by user and by attempted email; not someone else's
        self.assertEqual([h["first_name"] for h in data["history"]], ["Gus", "Gustav"])
        self.assertNotIn("password", data["history"][0])

        result = delete_user_data(user)
        self.assertFalse(User.objects.filter(email="gone@example.com").exists())
        self.assertEqual(LoginEvent.objects.count(), 1)  # only the unrelated one remains
        self.assertEqual(User.history.filter(email="gone@example.com").count(), 0)
        self.assertEqual(result["login_events"], 2)
