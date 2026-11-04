"""Review round 2: the plain text copy and the cleaner stay fast on hostile mail, and the rate limiter really expires (database cache). Mocked: nothing real is called."""
import time
from datetime import timedelta, timezone as dt_timezone
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from common import richtext
from common.ratelimit import hit

DB_CACHE = {"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "rl_test_cache"}}


class HostileMailTests(SimpleTestCase):
    """Each of these took 30 seconds or more before (a quadratic scan). The bound is generous (10 s for a second's work at worst) so a slow machine does not flake."""

    def timed(self, html):
        start = time.monotonic()
        clean = richtext.clean_incoming(html)
        text = richtext.html_to_text(html)
        return time.monotonic() - start, clean, text

    def test_deep_blockquotes_are_not_cleaned_and_the_text_is_short(self):
        for depth in (2000, 83000):
            took, clean, text = self.timed("<blockquote>" * depth + "hello")
            self.assertLess(took, 10)
            self.assertEqual(clean, "")  # too deep to clean: the caller keeps the text
            self.assertEqual(text, "> " * richtext.QUOTE_MARKS + "hello")

    def test_stray_end_tags_do_not_hide_the_depth(self):
        self.assertTrue(richtext.too_complex("<blockquote></b>" * 5000))
        self.assertFalse(richtext.too_complex("<table><tr><td><div><p>x</p></div></td></tr></table>" * 50))

    def test_many_breaks_and_empty_blocks_are_linear(self):
        for html in ("<br>" * 80000, "<p></p>" * 100000, "<ul><li>" * 5000 + "x", "\n" * 300000):
            took, _, _ = self.timed(html)
            self.assertLess(took, 10)

    def test_text_work_scales_linearly(self):
        def run(n):
            start = time.monotonic()
            richtext.html_to_text("<br>" * n)
            return time.monotonic() - start

        run(1000)
        small, big = min(run(20000) for _ in range(3)), min(run(80000) for _ in range(3))  # 4 times the input: a quadratic scan would take 16 times as long
        self.assertLess(big, max(small, 0.005) * 10)

    def test_a_line_of_only_a_greater_than_sign_is_kept_and_a_quote_gap_too(self):
        self.assertEqual(richtext.html_to_text("<p>&gt;</p>"), ">")
        self.assertEqual(richtext.html_to_text("<p>a</p><p>&gt;</p><p>b</p>"), "a\n\n>\n\nb")
        self.assertEqual(richtext.html_to_text("<blockquote><p>one</p><p></p><p>two</p></blockquote><p>after</p>"), "> one\n>\n> two\n\nafter")
        self.assertEqual(richtext.html_to_text("<ol><li>a</li><li>b</li></ol>"), "1. a\n2. b")


@override_settings(CACHES=DB_CACHE)
class RateLimitDatabaseCacheTests(TestCase):
    """Django's database cache resets an entry's expiry to its default (300 s) on `incr`; the limiter must not depend on that."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with override_settings(CACHES=DB_CACHE):
            call_command("createcachetable", "rl_test_cache", verbosity=0)

    def setUp(self):
        cache.clear()

    def test_the_limit_holds_then_resets_when_the_minute_ends(self):
        moment = [1_000_020.0]
        with mock.patch("common.ratelimit.time", mock.Mock(time=lambda: moment[0])):
            self.assertEqual([hit("t", "ip", 3, 60) for _ in range(5)], [True, True, True, False, False])
            moment[0] += 30
            self.assertFalse(hit("t", "ip", 3, 60))  # refused hits do not extend the window
            moment[0] += 31  # the next minute
            self.assertEqual([hit("t", "ip", 3, 60) for _ in range(4)], [True, True, True, False])

    def test_sliding_mode_keeps_a_non_stop_caller_blocked_across_a_window_edge(self):
        from django.utils import timezone

        moment, start, real = [1_000_050.0], 1_000_050.0, timezone.now()  # 10 s before a minute edge; the DB cache has its own clocks (time.time and tz_now): move them too
        real_ts = time.time()
        with mock.patch("common.ratelimit.time", mock.Mock(time=lambda: moment[0])), mock.patch(
                "django.core.cache.backends.db.tz_now", lambda: real + timedelta(seconds=moment[0] - start)), mock.patch(
                "django.core.cache.backends.base.time.time", lambda: real_ts + moment[0] - start):
            self.assertEqual([hit("login", "ip", 3, 60, sliding=True) for _ in range(5)], [True] * 3 + [False] * 2)
            for _ in range(10):  # keeps trying for 100 s, across the edge: every try, including the "right password", is refused
                moment[0] += 10
                self.assertFalse(hit("login", "ip", 3, 60, sliding=True))
            moment[0] += 61  # stops for a whole window
            self.assertTrue(hit("login", "ip", 3, 60, sliding=True))

    def test_sliding_mode_gives_no_burst_at_a_window_edge(self):
        moment = [1_000_055.0]
        with mock.patch("common.ratelimit.time", mock.Mock(time=lambda: moment[0])):
            self.assertEqual([hit("forgot", "ip", 5, 3600, sliding=True) for _ in range(5)], [True] * 5)
            moment[0] += 3600 - 55 + 1  # the hour edge has passed, but the last hit is only seconds old
            self.assertFalse(hit("forgot", "ip", 5, 3600, sliding=True))

    def test_the_stored_entry_expires_with_its_window_not_after_five_minutes(self):
        from django.db import connection
        from django.utils import timezone

        with mock.patch("common.ratelimit.time", mock.Mock(time=lambda: 1_000_030.0)):
            hit("t", "ip", 3, 60)
            hit("t", "ip", 3, 60)  # the second hit is the one that used to reset the expiry to 300 s
        with connection.cursor() as cursor:
            cursor.execute("select expires from rl_test_cache where cache_key like %s", ["%rl:t:%"])
            (expires,) = cursor.fetchone()
        expires = expires if timezone.is_aware(expires) else timezone.make_aware(expires, dt_timezone.utc)
        self.assertLess((expires - timezone.now()).total_seconds(), 120)  # the window's end (a minute at most) plus a second, never 300

    def test_a_window_longer_than_five_minutes_is_not_cut_short(self):
        moment = [3_600_000.0]
        with mock.patch("common.ratelimit.time", mock.Mock(time=lambda: moment[0])):
            self.assertEqual([hit("long", "ip", 2, 3600) for _ in range(3)], [True, True, False])
            moment[0] += 1800
            from django.utils import timezone

            with mock.patch("django.core.cache.backends.db.tz_now", return_value=timezone.now() + timedelta(seconds=1800)):  # past the old 300 s, inside the hour
                self.assertFalse(hit("long", "ip", 2, 3600))
