"""The rolling limiter and its lock, on the RateHit table with a mocked clock (nothing real is called)."""
import time
from contextlib import contextmanager
from unittest import mock

from django.test import Client, TestCase, override_settings

from common.ratelimit import hit
from mailings import tokens
from users.models import User

HOUR = 3600


class Clock:
    """Moves time.time (the limiter's clock) with a real epoch."""

    def __init__(self):
        self.now = time.time()

    def advance(self, seconds):
        self.now += seconds

    @contextmanager
    def patched(self):
        with mock.patch("time.time", lambda: self.now):
            yield self


class RollingLimiterTests(TestCase):
    def setUp(self):
        self.clock = Clock()

    def test_honest_traffic_every_half_hour_is_never_refused(self):
        with self.clock.patched():
            for scope, limit in (("register", 20), ("forgot", 5), ("apply", 10)):
                results = []
                for _ in range(60):  # a full 30 hours of one hit per half hour
                    results.append(hit(scope, "ip", limit, HOUR, rolling=True))
                    self.clock.advance(1800)
                self.assertEqual(results, [True] * 60)

    def test_never_more_than_the_limit_in_any_window_and_no_double_burst_at_an_edge(self):
        with self.clock.patched():
            self.clock.advance(HOUR - 5)  # five seconds before an hour edge
            first = [hit("forgot", "ip", 5, HOUR, rolling=True) for _ in range(7)]
            self.clock.advance(10)  # across the edge
            second = hit("forgot", "ip", 5, HOUR, rolling=True)
            self.clock.advance(HOUR - 10 + 1)  # the first hits are now over an hour old
            third = [hit("forgot", "ip", 5, HOUR, rolling=True) for _ in range(6)]
        self.assertEqual((first, second), ([True] * 5 + [False] * 2, False))
        self.assertEqual(third, [True] * 5 + [False])

    def test_without_the_lock_a_refused_caller_is_let_in_as_soon_as_a_hit_ages_out(self):
        with self.clock.patched():
            [hit("forgot", "ip", 2, 100, rolling=True) for _ in range(2)]
            self.clock.advance(30)
            self.assertFalse(hit("forgot", "ip", 2, 100, rolling=True))  # refused hits are not recorded
            self.clock.advance(71)
            self.assertTrue(hit("forgot", "ip", 2, 100, rolling=True))

    def test_the_lock_keeps_a_non_stop_caller_out_and_the_right_password_refused(self):
        with self.clock.patched():
            self.assertEqual([hit("login", "ip", 10, 300, lock=True) for _ in range(11)], [True] * 10 + [False])  # walk 14: the 11th is throttled
            self.assertFalse(hit("login", "ip", 10, 300, lock=True))  # the right password
            for _ in range(20):  # keeps trying for 20 minutes, across more than one window edge
                self.clock.advance(60)
                self.assertFalse(hit("login", "ip", 10, 300, lock=True))
            self.clock.advance(301)  # silence for a whole window
            self.assertTrue(hit("login", "ip", 10, 300, lock=True))

    def test_the_lock_holds_when_the_first_tries_were_a_window_ago(self):
        with self.clock.patched():
            for _ in range(10):  # ten wrong tries spread over the first 9 s
                hit("login", "ip", 10, 300, lock=True)
                self.clock.advance(1)
            self.clock.advance(280)  # t = 289 s: the 11th is refused, which locks
            self.assertFalse(hit("login", "ip", 10, 300, lock=True))
            self.clock.advance(20)  # t = 309 s: every first try is over a window old, but the lock was set 20 s ago
            self.assertFalse(hit("login", "ip", 10, 300, lock=True))  # the right password, still refused
            self.clock.advance(299)  # the attempt at 309 s moved the lock on: still not a whole window of silence
            self.assertFalse(hit("login", "ip", 10, 300, lock=True))
            self.clock.advance(301)
            self.assertTrue(hit("login", "ip", 10, 300, lock=True))

    def test_the_fixed_mode_is_unchanged(self):
        with self.clock.patched():
            self.assertEqual([hit("t", "ip", 3, 60) for _ in range(4)], [True, True, True, False])


@override_settings(ALLOWED_HOSTS=["testserver"])
class RateLimitedViewsTests(TestCase):
    def setUp(self):
        self.clock = Clock()

    def test_login_walk_eleven_wrong_passwords_then_the_right_one_is_refused_even_past_the_first_window(self):
        User.objects.create_user("walk@example.com", "a-long-test-password-1")
        client = Client()
        with self.clock.patched():
            codes = []
            for _ in range(11):
                codes.append(client.post("/login/", {"username": "walk@example.com", "password": "wrong"}).status_code)
                self.clock.advance(27)  # the 11th lands 270 s in
            self.assertEqual(codes, [200] * 10 + [429])
            self.clock.advance(40)  # 310 s after the first try, 40 s after the refused one
            right = client.post("/login/", {"username": "walk@example.com", "password": "a-long-test-password-1"})
            self.assertEqual(right.status_code, 429)
            self.clock.advance(301)
            self.assertEqual(client.post("/login/", {"username": "walk@example.com", "password": "a-long-test-password-1"}).status_code, 302)

    def test_a_scanner_on_the_unsubscribe_link_never_blocks_the_real_unsubscribe_post(self):
        token = tokens.make_unsubscribe_token("leaver@example.com")
        client = Client()
        with self.clock.patched():
            statuses = []
            for _ in range(80):  # a scanner opening the link every 1.5 s for two minutes
                statuses.append(client.get(f"/unsubscribe/{token}/").status_code)
                self.clock.advance(1.5)
            self.assertIn(429, statuses)  # GETs share a fixed window
            response = client.post(f"/unsubscribe/{token}/")
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "data-unsubscribe-done")

    def test_opening_the_invite_setup_form_does_not_use_up_the_posting_limit(self):
        client = Client()
        with self.clock.patched():
            for _ in range(40):
                self.assertEqual(client.get("/gold/invite/bad-token/").status_code, 410)
            posts = [client.post("/gold/invite/bad-token/", {}).status_code for _ in range(21)]
        self.assertEqual(posts, [410] * 20 + [429])
