from datetime import date

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from common.ratelimit import hit, rate_limited_json
from common.useragent import device_type
from common.validators import validate_adult

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "ratelimit-tests"}}


@override_settings(CACHES=LOCMEM)
class RateLimitTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_hit_allows_the_limit_then_refuses(self):
        self.assertEqual([hit("t", "ip", 3, 60) for _ in range(5)], [True, True, True, False, False])
        self.assertTrue(hit("t", "other-ip", 3, 60))  # separate per identifier

    def test_decorator_answers_429_json(self):
        view = rate_limited_json("deco", 2, 60)(lambda request: HttpResponse("ok"))
        request = RequestFactory().get("/")
        self.assertEqual([view(request).status_code for _ in range(3)], [200, 200, 429])


class SmallHelperTests(SimpleTestCase):
    def test_device_type(self):
        self.assertEqual(device_type("Mozilla/5.0 (iPhone; CPU iPhone OS 17) Mobile/15E148"), "mobile")
        self.assertEqual(device_type("Mozilla/5.0 (iPad; CPU OS 17)"), "tablet")
        self.assertEqual(device_type("Googlebot/2.1"), "bot")
        self.assertEqual(device_type("Mozilla/5.0 (Macintosh; Intel Mac OS X) Safari"), "desktop")
        self.assertEqual(device_type(""), "unknown")

    def test_adult_check_is_exact_on_the_birthday(self):
        today = date(2026, 10, 22)
        self.assertEqual(validate_adult(date(2008, 10, 22), today=today), date(2008, 10, 22))
        with self.assertRaises(ValidationError):
            validate_adult(date(2008, 10, 23), today=today)
        with self.assertRaises(ValidationError):
            validate_adult(date(2030, 1, 1), today=today)
