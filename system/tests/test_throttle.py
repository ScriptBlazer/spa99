"""Wrong-try feedback and the escalating wait on /dev-login/ and /unlock/ (time frozen with mock.patch)."""
from unittest import mock

from django.test import Client, TestCase, override_settings

from system import throttle
from system.models import SystemEvent
from system.tests.test_system import PASSWORD, SYSTEM, make_user, sign_in

CODE = "493021"
NOW = "system.throttle.time.time"
F = throttle.FREE_TRIES  # wrong tries in a row before the first wait
LEFT = range(F - 1, 0, -1)  # the tries-left numbers shown before the lock


@override_settings(SYSTEM_UNLOCK_CODE=CODE)
class ThrottleTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def unlock_client(self):
        client, _ = sign_in(self.user)
        return client

    def bad_unlock(self, client, now):
        with mock.patch(NOW, return_value=now):
            return client.post("/unlock/", {"code": "000000"})

    def test_tries_left_count_down_then_the_fifth_wrong_try_locks_for_a_minute(self):
        client = self.unlock_client()
        for left in LEFT:
            response = self.bad_unlock(client, 1000.0)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, f"Wrong code. {left} more tr")
        response = self.bad_unlock(client, 1000.0)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.context["locked_seconds"], 60)
        self.assertContains(response, "Try again in", status_code=429)
        self.assertContains(response, "1:00", status_code=429)
        self.assertContains(response, "disabled", status_code=429)

    def test_a_try_during_the_wait_is_not_checked_and_not_counted(self):
        client = self.unlock_client()
        for _ in range(F):
            self.bad_unlock(client, 1000.0)
        with mock.patch(NOW, return_value=1030.0), mock.patch("system.views.services.code_matches") as check:
            response = client.post("/unlock/", {"code": CODE})
        self.assertEqual((response.status_code, response.context["locked_seconds"]), (429, 30))
        check.assert_not_called()
        self.assertTrue(client.get("/changes/").status_code == 302)  # even the right code did not unlock
        self.assertEqual(SystemEvent.objects.filter(kind="unlock_rate_limited").count(), 1)  # one row per lockout

    def test_after_the_wait_each_wrong_try_adds_a_minute(self):
        client = self.unlock_client()
        for _ in range(F):
            self.bad_unlock(client, 1000.0)
        for now, wait in ((1061.0, 120), (1061.0 + 121, 180), (1061.0 + 121 + 181, 240)):
            response = self.bad_unlock(client, now)
            self.assertEqual((response.status_code, response.context["locked_seconds"]), (429, wait))
        self.assertEqual(SystemEvent.objects.filter(kind="unlock_rate_limited").count(), 4)

    def test_the_wait_is_capped_at_an_hour(self):
        buckets = [throttle.Bucket("t", "x")]
        for n in range(80):
            throttle.reserve(buckets, now=1000.0 + n * 4000)  # each try after the previous wait
        self.assertEqual(throttle.wait_seconds(buckets, now=1000.0 + 79 * 4000), 3600)

    def test_success_resets_and_so_does_a_quiet_day(self):
        client = self.unlock_client()
        for _ in range(F - 1):
            self.bad_unlock(client, 1000.0)
        with mock.patch(NOW, return_value=1001.0):
            self.assertEqual(client.post("/unlock/", {"code": CODE}).status_code, 302)
        self.assertContains(self.bad_unlock(client, 1002.0), f"{F - 1} more tries")
        for _ in range(F - 1):
            self.bad_unlock(client, 2000.0)
        self.assertContains(self.bad_unlock(client, 2000.0 + 24 * 3600 + 1), f"{F - 1} more tries")  # a day with no attempts forgets

    def test_sign_in_counts_down_locks_and_never_checks_the_password_while_waiting(self):
        client = Client(HTTP_HOST=SYSTEM)
        data = {"username": self.user.email, "password": "wrong"}
        for left in LEFT:
            with mock.patch(NOW, return_value=1000.0):
                response = client.post("/dev-login/", data)
            self.assertContains(response, f"Email or password not recognised. {left} more tr")
        with mock.patch(NOW, return_value=1000.0):
            self.assertEqual(client.post("/dev-login/", data).status_code, 429)
        with mock.patch(NOW, return_value=1010.0):
            response = client.post("/dev-login/", {"username": self.user.email, "password": PASSWORD})  # the right one waits too
        self.assertEqual((response.status_code, response.context["locked_seconds"]), (429, 60 - 10))
        self.assertEqual(client.get("/", HTTP_HOST=SYSTEM).status_code, 404)
        with mock.patch(NOW, return_value=1061.0):
            self.assertEqual(client.post("/dev-login/", {"username": self.user.email, "password": PASSWORD}).status_code, 302)

    def test_the_sign_in_message_is_the_same_for_an_unknown_email(self):
        real = Client(HTTP_HOST=SYSTEM).post("/dev-login/", {"username": self.user.email, "password": "wrong"})
        unknown = Client(HTTP_HOST=SYSTEM).post("/dev-login/", {"username": "nobody@example.com", "password": "wrong"})
        self.assertEqual(real.context["error_text"], unknown.context["error_text"])

    def test_spraying_many_emails_from_one_ip_locks_that_ip(self):
        client = Client(HTTP_HOST=SYSTEM, REMOTE_ADDR="203.0.113.7")
        with mock.patch(NOW, return_value=1000.0):
            codes = [client.post("/dev-login/", {"username": f"x{n}@example.com", "password": "x"}).status_code for n in range(2 * F)]
            self.assertEqual(codes, [200] * (2 * F - 1) + [429])
            self.assertEqual(client.post("/dev-login/", {"username": "fresh@example.com", "password": "x"}).status_code, 429)
        other = Client(HTTP_HOST=SYSTEM, REMOTE_ADDR="203.0.113.8")
        with mock.patch(NOW, return_value=1000.0):
            self.assertEqual(other.post("/dev-login/", {"username": "fresh@example.com", "password": "x"}).status_code, 200)

    def test_parallel_tries_cannot_all_be_verified(self):
        buckets = [throttle.Bucket("race", "x")]
        results = [throttle.reserve(buckets, now=1000.0) for _ in range(12)]
        self.assertEqual(sum(r.allowed for r in results), F)  # at most the tries left
        self.assertEqual(sum(r.started for r in results), 1)

    def test_only_one_request_can_take_a_new_wait_even_when_all_passed_the_first_check(self):
        buckets = [throttle.Bucket("race2", "x")]
        for _ in range(F - 1):
            throttle.reserve(buckets, now=1000.0)
        with mock.patch("system.throttle.wait_seconds", side_effect=[0, 0, 0, 60, 60, 60]):  # every request saw "free" at the door
            results = [throttle.reserve(buckets, now=1000.0) for _ in range(3)]
        self.assertEqual([r.allowed for r in results], [True, False, False])

    def test_one_more_try_is_singular(self):
        self.assertEqual((throttle.tries_text(1), throttle.tries_text(2)), ("1 more try", "2 more tries"))

    def test_ipv6_counts_by_its_64_and_emails_are_normalised(self):
        self.assertEqual(throttle.network_of("2001:db8:1:2:aaaa::1"), throttle.network_of("2001:db8:1:2:bbbb::9"))
        self.assertNotEqual(throttle.network_of("2001:db8:1:2::1"), throttle.network_of("2001:db8:1:3::1"))
        self.assertEqual(throttle.network_of("203.0.113.9"), "203.0.113.9")
        self.assertEqual(throttle.email_key("  Ｄev@Example.COM "), throttle.email_key("dev@example.com"))

    def test_one_email_from_many_addresses_is_capped_at_fifty(self):
        with mock.patch(NOW, return_value=1000.0):
            codes = [Client(HTTP_HOST=SYSTEM, REMOTE_ADDR=f"10.1.{n // 200}.{n % 200 + 1}").post("/dev-login/", {"username": "t@example.com", "password": "x"}).status_code for n in range(51)]
        self.assertEqual(codes[:49], [200] * 49)  # (the per-IP cap never trips: each address is new)
        self.assertEqual(codes[50], 429)

    def test_a_good_sign_in_does_not_clear_the_per_ip_count(self):
        client = Client(HTTP_HOST=SYSTEM, REMOTE_ADDR="203.0.113.50")
        with mock.patch(NOW, return_value=1000.0):
            for n in range(F - 1):
                client.post("/dev-login/", {"username": f"y{n}@example.com", "password": "x"})
            client.post("/dev-login/", {"username": self.user.email, "password": PASSWORD})
            codes = [Client(HTTP_HOST=SYSTEM, REMOTE_ADDR="203.0.113.50").post("/dev-login/", {"username": f"z{n}@example.com", "password": "x"}).status_code for n in range(F + 1)]
        self.assertEqual((codes[F - 1], codes[F]), (200, 429))  # F-1 + F+1 wrong tries reach the address limit of 2F: the good one neither reset nor used any

    def test_when_the_wait_ends_the_right_code_works_on_the_first_try(self):
        client = self.unlock_client()
        for _ in range(F):
            self.bad_unlock(client, 1000.0)
        with mock.patch(NOW, return_value=1059.9):
            self.assertEqual(client.post("/unlock/", {"code": CODE}).status_code, 429)  # still waiting
        with mock.patch(NOW, return_value=1060.01):
            response = client.post("/unlock/", {"code": CODE})
            self.assertEqual(response.status_code, 302)  # not counted as a 6th wrong try, no longer waiting
            self.assertEqual(client.get("/changes/").status_code, 200)
        self.assertContains(self.bad_unlock(client, 1100.0), f"{F - 1} more tries")  # and success cleared the count

    def test_the_sign_in_right_password_works_the_moment_the_wait_ends(self):
        client = Client(HTTP_HOST=SYSTEM)
        for _ in range(F):
            with mock.patch(NOW, return_value=1000.0):
                client.post("/dev-login/", {"username": self.user.email, "password": "wrong"})
        with mock.patch(NOW, return_value=1060.01):
            self.assertEqual(client.post("/dev-login/", {"username": self.user.email, "password": PASSWORD}).status_code, 302)
