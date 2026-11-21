"""Real and all visitors (docs/features/analytics.md A12): a visitor is real once our page script has sent a beacon."""
import json
from datetime import datetime, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

from django.http import HttpResponse
from django.test import Client, RequestFactory, TestCase
from django.utils import timezone

from common import geoip
from insights import beacon, live, rollup, visitors
from insights.metrics import K
from insights.middleware import VisitorCounterMiddleware
from insights.models import VisitorHash
from insights.tests.test_analytics import CHROME_WIN, IPHONE, figure
from office import analytics_visitors, selectors, snapshots

LONDON = ZoneInfo("Europe/London")
REAL = visitors.REAL


class RealVisitorTests(TestCase):
    def setUp(self):
        visitors.forget_salts()
        self.factory = RequestFactory()
        self.clock = datetime(2026, 11, 21, 10, 0, tzinfo=LONDON)
        patcher = mock.patch.object(timezone, "now", side_effect=lambda: self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)
        reader = mock.Mock()
        reader.get.return_value = {"country": {"iso_code": "GB"}}
        geoip._state.update(loaded=True, reader=reader)
        self.addCleanup(geoip.reset)

    def view(self, path="/", agent=IPHONE, addr="81.2.69.142", query=""):
        request = self.factory.get(path + query, HTTP_USER_AGENT=agent, HTTP_HOST="localhost", REMOTE_ADDR=addr)
        request.urlconf = "config.urls"
        VisitorCounterMiddleware(lambda r: HttpResponse("x", content_type="text/html"))(request)

    def send(self, payload, agent=IPHONE, addr="81.2.69.142"):
        client = Client(HTTP_HOST="localhost", HTTP_USER_AGENT=agent, REMOTE_ADDR=addr)
        return client.post("/a/e/", json.dumps(payload), content_type="text/plain")

    def real(self, key, dimension=""):
        return figure(REAL + key, dimension)

    def test_the_first_beacon_makes_a_visitor_real_and_adds_what_he_already_did(self):
        self.view("/memberships/", query="?utm_source=flyer&utm_medium=print&utm_campaign=spring&utm_content=qr")
        self.assertEqual((figure(K.VISITORS), self.real(K.VISITORS), self.real(K.PAGE_VIEWS)), (1, 0, 0))  # no beacon yet: only in all
        self.assertEqual(self.send({"p": "/memberships/", "h": 1}).status_code, 204)
        self.assertTrue(VisitorHash.objects.get().human)
        self.assertEqual((self.real(K.VISITORS), self.real(K.PAGE_VIEWS), self.real(K.PAGE_VIEWS, "memberships")), (1, 1, 1))
        self.assertEqual((self.real(K.DEVICES, "mobile"), self.real(K.BROWSERS, "safari"), self.real(K.SYSTEMS, "ios"), self.real(K.COUNTRIES, "gb")), (1, 1, 1, 1))
        self.assertEqual((self.real(K.VISITS), self.real(K.BOUNCES), self.real(K.VISIT_PAGES), self.real(K.ENTRY_PAGES, "memberships")), (1, 1, 1, 1))
        self.assertEqual((self.real(K.VISITS_BY_CHANNEL, "campaign"), self.real(K.CAMPAIGN_VISITS, "flyer|print|spring|qr")), (1, 1))
        self.assertEqual(self.real(K.VISIT_HOUR, "sat:10"), 1)
        self.send({"p": "/memberships/", "h": 1})  # a second hello changes nothing
        self.assertEqual((self.real(K.VISITORS), self.real(K.PAGE_VIEWS)), (1, 1))
        self.assertEqual((figure(K.VISITORS), figure(K.PAGE_VIEWS)), (1, 1))  # all is untouched by the switch

    def test_a_visitor_with_no_beacon_is_only_in_all(self):
        self.view("/", agent=CHROME_WIN, addr="198.51.100.9")
        self.view("/plans/", agent=CHROME_WIN, addr="198.51.100.9")
        self.assertEqual((figure(K.VISITORS), figure(K.PAGE_VIEWS), figure(K.VISITS)), (1, 2, 1))
        self.assertEqual([self.real(k) for k in (K.VISITORS, K.PAGE_VIEWS, K.VISITS, K.VISIT_PAGES)], [0, 0, 0, 0])

    def test_later_hits_of_a_real_visitor_write_both_and_the_visit_closes_into_both(self):
        self.view("/memberships/")
        self.send({"p": "/memberships/", "h": 1})
        self.later(seconds=20)
        self.view("/gold-card/")  # second page: takes the bounce back in both
        self.assertEqual((figure(K.PAGE_VIEWS), self.real(K.PAGE_VIEWS), figure(K.BOUNCES), self.real(K.BOUNCES)), (2, 2, 0, 0))
        self.assertEqual((figure(K.VISIT_PAGES), self.real(K.VISIT_PAGES), self.real(K.VIEWS_BY_DEVICE, "mobile")), (2, 2, 2))
        self.send({"p": "/gold-card/", "t": 9, "s": 50, "n": 0})
        self.send({"p": "/gold-card/", "c": "whatsapp"})
        self.assertEqual((figure(K.ENGAGED_SECONDS, "gold-card"), self.real(K.ENGAGED_SECONDS, "gold-card"), figure(K.SCROLL, "gold-card:50"), self.real(K.SCROLL, "gold-card:50")), (9, 9, 1, 1))
        self.assertEqual((figure(K.CONTACT_TAPS, "whatsapp"), self.real(K.CONTACT_TAPS, "whatsapp"), self.real(K.CHANNEL_STEPS, "direct:contact")), (1, 1, 1))
        self.later(hours=1)
        rollup.run()  # closes the idle visit
        self.assertEqual((figure(K.EXIT_PAGES, "gold-card"), self.real(K.EXIT_PAGES, "gold-card"), self.real(K.VISIT_LENGTH, "10-30s")), (1, 1, 1))

    def test_a_step_credited_before_the_beacon_is_added_when_he_becomes_real(self):
        request = self.factory.get("/journey/", HTTP_USER_AGENT=IPHONE, HTTP_HOST="localhost", REMOTE_ADDR="81.2.69.142")
        request.urlconf = "config.urls"
        self.view("/journey/")
        visitors.record_step(request, "started")
        self.assertEqual(self.real(K.CHANNEL_STEPS, "direct:started"), 0)
        self.send({"p": "/journey/", "h": 1})
        self.assertEqual((figure(K.CHANNEL_STEPS, "direct:started"), self.real(K.CHANNEL_STEPS, "direct:started")), (1, 1))

    def test_a_bad_or_unknown_hello_is_ignored(self):
        self.view("/")
        for bad in ({"p": "/", "h": 2}, {"p": "/nope-not-a-page/", "h": 1}, {"h": 1}):
            self.assertEqual(self.send(bad).status_code, 204)
        self.assertFalse(VisitorHash.objects.get().human)
        self.assertEqual(self.send({"p": "/", "h": 1}, addr="198.51.100.9").status_code, 204)  # a stranger with no row today
        self.assertEqual(self.real(K.VISITORS), 0)
        self.assertEqual(beacon.parse(json.dumps({"p": "/", "h": 1})), {"group": "home", "hello": True})

    def test_live_real_and_all(self):
        self.view("/plans/")  # a bot that passes the filter: no beacon
        self.view("/", agent=CHROME_WIN, addr="198.51.100.9")
        self.send({"p": "/", "h": 1}, agent=CHROME_WIN, addr="198.51.100.9")
        self.assertEqual(live.live_now(who="all")["count"], 2)
        self.assertEqual(live.live_now(who="real")["count"], 1)
        self.assertEqual(live.live_now()["count"], 1)  # real is the default
        self.assertEqual(live.live_now(who="real")["by_device"], [{"label": "desktop", "value": 1}])

    def test_snapshots_hold_both_variants_and_who_falls_back_to_real(self):
        self.view("/memberships/")
        self.view("/", agent=CHROME_WIN, addr="198.51.100.9")
        self.send({"p": "/", "h": 1}, agent=CHROME_WIN, addr="198.51.100.9")
        rollup.run()
        every = selectors.visitors("7d", who="all")
        real = selectors.visitors("7d", who="real")
        self.assertEqual((every["who"], every["overview"]["visitors"]["value"]), ("all", 2))
        self.assertEqual((real["who"], real["overview"]["visitors"]["value"]), ("real", 1))
        self.assertEqual(selectors.visitors("7d", who="nonsense")["who"], "real")
        self.assertEqual(selectors.visitors("7d")["who"], "real")
        self.assertEqual([i["label"] for i in real["devices"] if i["value"]], ["Computer"])
        self.assertEqual(analytics_visitors.build("7d", who="real")["visitors_since"], "2026-11-21")

    def later(self, **kwargs):
        self.clock += timedelta(**kwargs)
