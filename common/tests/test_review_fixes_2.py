"""Review round 2: the rate limiter really expires (database cache). Mocked: nothing real is called."""
from datetime import timedelta, timezone as dt_timezone
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings

from common.ratelimit import hit

DB_CACHE = {"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "rl_test_cache"}}


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
