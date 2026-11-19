"""The RateHit store: no lost hits, the insert race, housekeeping, and that the cache table is no longer touched. Mocked clock; nothing real is called."""
from datetime import timedelta
from unittest import mock

from django.db import IntegrityError, connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from common import ratelimit
from common.models import RateHit
from common.tasks import housekeeping, prune_rate_hits


def ratelimit_key(scope, identifier, window_seconds, moment):
    import hashlib

    digest = hashlib.sha256(str(identifier).encode()).hexdigest()[:32]
    return f"rl:{scope}:{digest}:{int(moment // window_seconds)}"


class StoreTests(TestCase):
    def test_every_hit_is_counted_one_row_per_key(self):
        for _ in range(3):
            hit = ratelimit.hit("t", "ip", 10, 60)
        self.assertTrue(hit)
        self.assertEqual(RateHit.objects.count(), 1)
        self.assertEqual(RateHit.objects.get().count, 3)
        ratelimit.hit("t", "other", 10, 60)
        self.assertEqual(RateHit.objects.count(), 2)

    def test_the_insert_race_retries_once_and_still_counts_both(self):
        """Another request creates the row between our read and our insert: we lose on the unique key, retry, and add to its count."""
        RateHit.objects.create(key=ratelimit_key("race", "ip", 60, 1_000_030.0), expires_at=timezone.now() + timedelta(minutes=5), count=1)
        real_select = RateHit.objects.select_for_update
        calls = []

        def blind_first_read():
            calls.append(1)
            if len(calls) == 1:  # the first read does not see the other request's row yet
                return mock.Mock(filter=lambda **kw: mock.Mock(first=lambda: None))
            return real_select()

        with mock.patch("common.ratelimit.time", mock.Mock(time=lambda: 1_000_030.0)), \
                mock.patch.object(RateHit.objects, "select_for_update", side_effect=blind_first_read):
            self.assertTrue(ratelimit.hit("race", "ip", 5, 60))  # the real insert hits the unique key, then the retry adds to the row
        self.assertEqual(len(calls), 2)
        self.assertEqual(RateHit.objects.get().count, 2)

    def test_a_persistent_database_error_fails_open_and_logs(self):
        with mock.patch.object(RateHit.objects, "select_for_update", side_effect=RuntimeError("db down")):
            with self.assertLogs("spa99.ratelimit", level="ERROR"):
                self.assertTrue(ratelimit.hit("t", "ip", 1, 60))
                self.assertTrue(ratelimit.hit("t", "ip", 1, 60, rolling=True, lock=True))

    def test_an_expired_row_counts_as_empty(self):
        with mock.patch("common.ratelimit.time", mock.Mock(time=lambda: 1_000_000.0)):
            ratelimit.hit("roll", "ip", 1, 100, rolling=True)
        self.assertTrue(ratelimit.hit("roll", "ip", 1, 100, rolling=True))  # real now is far past the stored expiry

    def test_a_rate_limited_request_does_not_touch_the_cache_table(self):
        with CaptureQueriesContext(connection) as queries:
            ratelimit.hit("t", "ip", 1, 60)
            ratelimit.hit("t", "ip", 1, 60)
            ratelimit.hit("login", "ip", 1, 60, lock=True)
        sql = " ".join(q["sql"] for q in queries).lower()
        self.assertNotIn("spa99_cache", sql)
        self.assertIn("common_ratehit", sql)


class PruneTests(TestCase):
    def test_housekeeping_deletes_only_expired_rows_in_batches(self):
        now = timezone.now()
        for i in range(5):
            RateHit.objects.create(key=f"old{i}", expires_at=now - timedelta(minutes=1), count=1)
        RateHit.objects.create(key="live", expires_at=now + timedelta(minutes=5), count=1)
        self.assertEqual(prune_rate_hits(batch=2), 5)
        self.assertEqual(list(RateHit.objects.values_list("key", flat=True)), ["live"])

    def test_the_nightly_job_runs_it(self):
        RateHit.objects.create(key="old", expires_at=timezone.now() - timedelta(minutes=1), count=1)
        self.assertIn("'rate_hits': 1", housekeeping())
        self.assertEqual(RateHit.objects.count(), 0)
