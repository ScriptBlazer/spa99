"""Review round 2: the rate limiter's rows really expire with their window (RateHit table). Mocked: nothing real is called."""
from unittest import mock

from django.test import TestCase

from common.models import RateHit
from common.ratelimit import hit


class RateLimitExpiryTests(TestCase):
    """The stored row must expire with its window (the old database cache reset it to 300 s on every increment); the limiter must not depend on a default."""

    def test_the_limit_holds_then_resets_when_the_minute_ends(self):
        moment = [1_000_020.0]
        with mock.patch("common.ratelimit.time", mock.Mock(time=lambda: moment[0])):
            self.assertEqual([hit("t", "ip", 3, 60) for _ in range(5)], [True, True, True, False, False])
            moment[0] += 30
            self.assertFalse(hit("t", "ip", 3, 60))  # refused hits do not extend the window
            moment[0] += 31  # the next minute
            self.assertEqual([hit("t", "ip", 3, 60) for _ in range(4)], [True, True, True, False])

    def test_the_stored_row_expires_with_its_window_not_after_five_minutes(self):
        moment = [1_000_030.0]  # 10 s into a minute that started at 1_000_020
        with mock.patch("common.ratelimit.time", mock.Mock(time=lambda: moment[0])):
            hit("t", "ip", 3, 60)
            moment[0] += 5
            hit("t", "ip", 3, 60)  # later hits in the same window must not move the expiry
        row = RateHit.objects.get(key__startswith="rl:t:")
        self.assertEqual(row.expires_at.timestamp(), 1_000_081.0)  # the window's end (1_000_080) plus a second
        self.assertEqual(row.count, 2)

    def test_a_window_longer_than_five_minutes_is_not_cut_short(self):
        moment = [3_600_000.0]
        with mock.patch("common.ratelimit.time", mock.Mock(time=lambda: moment[0])):
            self.assertEqual([hit("long", "ip", 2, 3600) for _ in range(3)], [True, True, False])
            moment[0] += 1800
            self.assertFalse(hit("long", "ip", 2, 3600))
