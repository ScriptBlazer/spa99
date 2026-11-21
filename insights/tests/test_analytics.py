"""Analytics plus (docs/features/analytics.md): user agent parsing, country, visits and bounces, the page beacon, utm and channels,
same-day campaign steps, caps, nothing personal stored, live now, the link maker."""
import json
from datetime import datetime, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

from django.http import HttpResponse
from django.test import Client, RequestFactory, SimpleTestCase, TestCase
from django.utils import timezone

from common import geoip
from common.useragent import browser_family, device_type, os_family
from insights import beacon, campaigns, live, metrics, rollup, visitors
from insights.metrics import K
from insights.middleware import VisitorCounterMiddleware
from insights.models import DailyMetric, MetricCounter, VisitorHash, VisitorSalt

LONDON = ZoneInfo("Europe/London")
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
CHROME_WIN = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
GOOGLEBOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"


def figure(key, dimension="", on=None):
    row = DailyMetric.objects.filter(date=on or metrics.day(), key=key, dimension=dimension).first()
    return row.value if row else 0


class UserAgentTests(SimpleTestCase):
    def test_device_browser_and_system_table(self):
        table = [
            (IPHONE, ("mobile", "safari", "ios")),
            (CHROME_WIN, ("desktop", "chrome", "windows")),
            ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram 330.0", ("mobile", "instagram", "ios")),
            ("Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/450.0]", ("mobile", "facebook", "android")),
            ("Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/24.0 Chrome/117.0 Mobile Safari/537.36", ("mobile", "samsung", "android")),
            ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36 Edg/126.0", ("desktop", "edge", "windows")),
            ("Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0", ("desktop", "firefox", "linux")),
            ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15", ("desktop", "safari", "macos")),
            ("Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/126 Safari/537.36 OPR/110.0", ("desktop", "other", "windows")),
            (GOOGLEBOT, ("bot", "other", "other")),
            ("", ("unknown", "other", "other")),
        ]
        for agent, expected in table:
            self.assertEqual((device_type(agent), browser_family(agent), os_family(agent)), expected, agent)


class GeoIpTests(SimpleTestCase):
    def tearDown(self):
        geoip.reset()

    def test_a_missing_file_gives_unknown_and_a_mocked_reader_gives_the_lower_case_code(self):
        geoip.reset()
        with self.settings(GEOIP_DB_PATH="/nonexistent/file.mmdb"):
            self.assertEqual(geoip.country_code("81.2.69.142"), "unknown")
        reader = mock.Mock()
        reader.get.return_value = {"country": {"iso_code": "GB"}}
        geoip._state.update(loaded=True, reader=reader)
        self.assertEqual(geoip.country_code("81.2.69.142"), "gb")
        reader.get.return_value = None
        self.assertEqual(geoip.country_code("10.0.0.1"), "unknown")
        reader.get.side_effect = ValueError("bad address")
        self.assertEqual(geoip.country_code("not an ip"), "unknown")
        self.assertEqual(geoip.country_code(None), "unknown")


class CampaignRuleTests(SimpleTestCase):
    def test_utm_values_are_cleaned_and_cut(self):
        self.assertEqual(campaigns.clean_utm("Summer Offer!! <b>2026</b>"), "summer-offer-b2026b")
        self.assertEqual(campaigns.clean_utm("x" * 90), "x" * 60)
        utm = campaigns.utm_from_query({"utm_source": "IG", "utm_medium": "Social", "utm_campaign": "A" * 50, "utm_content": "", "other": "kept?"})
        self.assertEqual(campaigns.campaign_key(utm), "ig|social|" + "a" * 30 + "|")
        self.assertLessEqual(len(campaigns.campaign_key(utm)) + len(":registered"), 100)
        self.assertEqual(campaigns.campaign_key(campaigns.utm_from_query({})), "")

    def test_channel_rules(self):
        none = campaigns.utm_from_query({})
        table = [
            (campaigns.utm_from_query({"utm_source": "flyer", "utm_medium": "print"}), "direct", "", "campaign"),
            (campaigns.utm_from_query({"utm_source": "news", "utm_medium": "email"}), "direct", "", "email"),
            (none, "www.google.co.uk", "", "search"), (none, "duckduckgo.com", "", "search"), (none, "bing.com", "", "search"),
            (none, "l.instagram.com", "", "social"), (none, "t.co", "", "social"), (none, "m.facebook.com", "", "social"),
            (none, "mail.google.com", "", "email"), (none, "outlook.live.com", "", "email"),
            (none, "someblog.example", "", "referral"), (none, "direct", "", "direct"), (none, "direct", "instagram", "social"),
        ]
        for utm, host, browser, expected in table:
            self.assertEqual(campaigns.channel_for(utm, host, browser)[0], expected, (utm, host))

    def test_link_maker_builds_a_clean_tagged_path(self):
        url = campaigns.build_link("/plans/?x=1&utm_source=old", "instagram-story", "Summer Offer", base="https://spa99.uk/")
        self.assertEqual(url, "https://spa99.uk/plans/?x=1&utm_source=instagram&utm_medium=social&utm_campaign=summer-offer&utm_content=story")
        self.assertEqual(campaigns.build_link("/", "whatsapp", "x"), "/?utm_source=whatsapp&utm_medium=message&utm_campaign=x")
        self.assertEqual(campaigns.build_link("/gold/", "flyer-qr", "x"), "/gold/?utm_source=flyer&utm_medium=print&utm_campaign=x&utm_content=qr")
        for bad in (("https://evil.example/", "email", "x"), ("//evil.example/", "email", "x"), ("/", "nope", "x"), ("/", "email", "!!!")):
            with self.assertRaises(ValueError):
                campaigns.build_link(*bad)
        self.assertEqual(campaigns.placement_label("instagram|social|summer|story"), "Instagram story")
        self.assertIsNone(campaigns.placement_label("a|b|c|d"))


class CapTests(TestCase):
    def test_a_key_keeps_100_dimensions_a_day_then_adds_to_other(self):
        for i in range(105):
            metrics.count_capped(K.REFERRERS, f"site{i}.example", 1)
        metrics.count_capped(K.REFERRERS, "site0.example", 1)  # an existing dimension keeps counting
        rows = DailyMetric.objects.filter(date=metrics.day(), key=K.REFERRERS)
        self.assertEqual(rows.count(), 101)
        self.assertEqual(figure(K.REFERRERS, "other"), 5)
        self.assertEqual(figure(K.REFERRERS, "site0.example"), 2)
        metrics.count_capped(K.DEVICES, "Mobile Phone!!", 1)  # lower-cased and cleaned
        self.assertEqual(figure(K.DEVICES, "mobilephone"), 1)


class VisitTests(TestCase):
    """Page views through the real counter middleware, with the clock under the test's control."""

    def setUp(self):
        self.factory = RequestFactory()
        visitors.forget_salts()
        self.clock = datetime(2026, 11, 21, 10, 0, tzinfo=LONDON)
        patcher = mock.patch.object(timezone, "now", side_effect=lambda: self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)
        reader = mock.Mock()
        reader.get.side_effect = lambda ip: {"country": {"iso_code": "GB" if ip == "81.2.69.142" else "US"}}
        geoip._state.update(loaded=True, reader=reader)
        self.addCleanup(geoip.reset)

    def view(self, path="/", agent=IPHONE, addr="81.2.69.142", referer="", query=""):
        extra = {"HTTP_USER_AGENT": agent, "HTTP_HOST": "localhost", "REMOTE_ADDR": addr}
        if referer:
            extra["HTTP_REFERER"] = referer
        request = self.factory.get(path + query, **extra)
        request.urlconf = "config.urls"
        VisitorCounterMiddleware(lambda r: HttpResponse("x", content_type="text/html"))(request)
        return request

    def later(self, **kwargs):
        self.clock += timedelta(**kwargs)

    def test_a_visitor_is_counted_once_with_device_browser_system_and_country_and_views_each_time(self):
        self.view("/", referer="https://www.google.com/search?q=secret")
        self.view("/plans/")
        self.view("/", addr="198.51.100.9", agent=CHROME_WIN)
        self.assertEqual((figure(K.VISITORS), figure(K.PAGE_VIEWS)), (2, 3))
        self.assertEqual((figure(K.DEVICES, "mobile"), figure(K.DEVICES, "desktop")), (1, 1))
        self.assertEqual((figure(K.BROWSERS, "safari"), figure(K.BROWSERS, "chrome"), figure(K.SYSTEMS, "ios"), figure(K.SYSTEMS, "windows")), (1, 1, 1, 1))
        self.assertEqual((figure(K.COUNTRIES, "gb"), figure(K.COUNTRIES, "us")), (1, 1))
        self.assertEqual((figure(K.VIEWS_BY_DEVICE, "mobile"), figure(K.VIEWS_BY_BROWSER, "safari")), (2, 2))  # per page view
        self.assertEqual(figure(K.VISITS_BY_CHANNEL, "search"), 1)

    def test_visit_start_bounce_and_the_second_page_taking_it_back(self):
        self.view("/plans/")
        self.assertEqual((figure(K.VISITS), figure(K.BOUNCES), figure(K.VISIT_PAGES), figure(K.ENTRY_PAGES, "plans")), (1, 1, 1, 1))
        self.later(minutes=1)
        self.view("/gold/")
        self.assertEqual((figure(K.VISITS), figure(K.BOUNCES), figure(K.VISIT_PAGES)), (1, 0, 2))
        self.later(minutes=1)
        self.view("/")
        self.assertEqual((figure(K.VISITS), figure(K.BOUNCES), figure(K.VISIT_PAGES)), (1, 0, 3))  # taken back once only
        self.assertEqual(figure(K.VISIT_HOUR, "sat:10"), 1)  # London weekday and hour of the new visit

    def test_a_30_minute_gap_closes_the_visit_and_starts_another(self):
        self.view("/plans/")
        self.later(minutes=2)
        self.view("/gold/")
        self.later(minutes=29)
        self.view("/")  # 29 minutes after the last page: the same visit
        self.assertEqual(figure(K.VISITS), 1)
        self.later(minutes=31)
        self.view("/contact/")
        self.assertEqual((figure(K.VISITS), figure(K.BOUNCES), figure(K.VISITORS)), (2, 1, 1))
        self.assertEqual((figure(K.EXIT_PAGES, "home"), figure(K.VISIT_LENGTH, "10m+"), figure(K.VISIT_SECONDS)), (1, 1, 31 * 60))
        self.assertEqual((figure(K.ENTRY_PAGES, "plans"), figure(K.ENTRY_PAGES, "contact")), (1, 1))

    def test_the_roll_up_closes_idle_visits_and_midnight_closes_the_rest_on_their_own_day(self):
        self.view("/plans/")
        self.later(minutes=10)
        self.view("/gold/")
        self.later(minutes=10)
        self.assertEqual(rollup.run(today=metrics.day())["closed_visits"], 0)  # only 10 minutes idle: still open
        self.later(minutes=25)
        rollup.run(today=metrics.day())
        self.assertEqual((figure(K.EXIT_PAGES, "gold"), figure(K.VISIT_LENGTH, "10m+")), (1, 1))  # 20 minutes of pages
        self.assertEqual(rollup.run(today=metrics.day())["closed_visits"], 0)  # a second run changes nothing
        self.assertEqual(figure(K.EXIT_PAGES, "gold"), 1)
        # an open visit at midnight is closed by the next roll-up and booked to its own day
        self.clock = datetime(2026, 11, 21, 23, 50, tzinfo=LONDON)
        self.view("/", addr="198.51.100.9")
        self.clock = datetime(2026, 11, 22, 0, 5, tzinfo=LONDON)
        rollup.run(today=metrics.day())
        self.assertEqual(figure(K.EXIT_PAGES, "home", on=datetime(2026, 11, 21).date()), 1)
        self.assertEqual(figure(K.EXIT_PAGES, "home"), 0)

    def test_the_roll_up_wipes_finished_days_visit_rows(self):
        self.view("/")
        self.assertEqual(VisitorHash.objects.count(), 1)
        self.clock += timedelta(days=1)
        rollup.run(today=metrics.day())
        self.assertFalse(VisitorHash.objects.exists())
        self.assertFalse(VisitorSalt.objects.filter(date__lt=metrics.day()).exists())
        self.assertEqual(figure(K.VISITS, on=datetime(2026, 11, 21).date()), 1)  # the counts stay

    def test_bots_prefetches_and_staff_hosts_are_not_counted(self):
        self.view("/", agent=GOOGLEBOT)
        request = self.factory.get("/", HTTP_USER_AGENT=IPHONE, HTTP_HOST="office.localhost", REMOTE_ADDR="81.2.69.142")
        request.urlconf = "config.urls_office"
        VisitorCounterMiddleware(lambda r: HttpResponse("x", content_type="text/html"))(request)
        self.assertEqual((figure(K.VISITORS), figure(K.VISITS), VisitorHash.objects.count()), (0, 0, 0))

    def test_campaign_visits_and_same_day_steps_go_to_the_visits_campaign_and_channel(self):
        request = self.view("/plans/", query="?utm_source=Flyer&utm_medium=print&utm_campaign=Spring-Offer&utm_content=qr&junk=1")
        key = "flyer|print|spring-offer|qr"
        self.assertEqual((figure(K.CAMPAIGN_VISITS, key), figure(K.VISITS_BY_CHANNEL, "campaign"), figure(K.VISIT_SOURCES, "flyer")), (1, 1, 1))
        for step in ("started", "started", "finished", "registered", "gold"):  # a step counts once per visit
            visitors.record_step(request, step)
        self.assertEqual([figure(K.CAMPAIGN_STEPS, f"{key}:{s}") for s in ("started", "finished", "registered", "gold")], [1, 1, 1, 1])
        self.assertEqual(figure(K.CHANNEL_STEPS, "campaign:started"), 1)
        # another visitor who came direct: no campaign step, his channel still gets it
        other = self.view("/", addr="198.51.100.9")
        visitors.record_step(other, "finished")
        self.assertEqual((figure(K.CAMPAIGN_STEPS, f"{key}:finished"), figure(K.CHANNEL_STEPS, "direct:finished")), (1, 1))
        # no row today (a step the next day, or a visitor never counted) credits nothing
        visitors.forget_salts()
        self.clock += timedelta(days=1)
        visitors.record_step(request, "gold")
        self.assertEqual(figure(K.CAMPAIGN_STEPS, f"{key}:gold", on=datetime(2026, 11, 21).date()), 1)  # the first day's, once
        self.assertEqual(DailyMetric.objects.filter(date=metrics.day()).count(), 0)  # nothing on the next day

    def test_a_journey_start_adds_a_visitor_and_credits_the_visits_campaign(self):
        request = self.view("/", query="?utm_source=ig&utm_medium=social&utm_campaign=x")
        visitors.record_journey_start(request)
        self.assertEqual((figure(K.VISITORS), figure(K.CAMPAIGN_STEPS, "ig|social|x|:started")), (1, 1))
        fresh = self.factory.get("/journey/", HTTP_USER_AGENT=IPHONE, HTTP_HOST="localhost", REMOTE_ADDR="203.0.113.50")
        fresh.urlconf = "config.urls"
        visitors.record_journey_start(fresh)  # no page view first: a visitor, but no visit to credit
        self.assertEqual((figure(K.VISITORS), figure(K.VISITS)), (2, 1))

    def test_nothing_personal_is_stored_anywhere(self):
        self.view("/plans/tier-2/", referer="https://www.google.com/search?q=secret-search", query="?utm_source=ig&email=a@b.co&utm_campaign=x")
        self.view("/plans/", addr="198.51.100.9", agent=CHROME_WIN)
        everything = " ".join(str(v) for model in (VisitorHash, VisitorSalt, DailyMetric, MetricCounter) for v in model.objects.values_list())
        for secret in ("81.2.69.142", "198.51.100.9", "Mozilla", "Safari", "iPhone", "Windows NT", "secret-search", "a@b.co", "email=", "tier-2", "http"):
            self.assertNotIn(secret, everything)

    def test_live_now_counts_visitors_seen_in_the_last_five_minutes_in_one_query(self):
        self.view("/plans/")
        self.view("/", addr="198.51.100.9", agent=CHROME_WIN)
        self.later(minutes=4)
        self.view("/gold/", addr="198.51.100.9", agent=CHROME_WIN)
        with self.assertNumQueries(1):
            data = live.live_now()
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["by_page"], [{"label": "gold", "value": 1}, {"label": "plans", "value": 1}])
        self.assertEqual(data["by_country"], [{"label": "gb", "value": 1}, {"label": "us", "value": 1}])
        self.assertEqual(data["by_device"], [{"label": "desktop", "value": 1}, {"label": "mobile", "value": 1}])
        self.later(minutes=2)  # the first has now been quiet for 6 minutes
        self.assertEqual(live.live_now()["count"], 1)
        self.assertEqual(set(data), {"count", "window_minutes", "as_of", "by_page", "by_country", "by_device", "by_channel"})


class BeaconTests(TestCase):
    def setUp(self):
        visitors.forget_salts()
        self.client = Client(HTTP_HOST="localhost", HTTP_USER_AGENT=IPHONE, REMOTE_ADDR="81.2.69.142")
        self.factory = RequestFactory()
        request = self.factory.get("/memberships/", HTTP_USER_AGENT=IPHONE, HTTP_HOST="localhost", REMOTE_ADDR="81.2.69.142")
        request.urlconf = "config.urls"
        VisitorCounterMiddleware(lambda r: HttpResponse("x", content_type="text/html"))(request)

    def send(self, payload, client=None, raw=None):
        body = raw if raw is not None else json.dumps(payload)
        return (client or self.client).post("/a/e/", body, content_type="text/plain")

    def test_parse_accepts_good_beacons_and_ignores_odd_ones(self):
        good = beacon.parse(json.dumps({"p": "/memberships/", "t": 12, "s": 50, "n": 0}))
        self.assertEqual(good, {"group": "memberships", "seconds": 12, "scroll": 50, "first": True})
        self.assertEqual(beacon.parse(json.dumps({"p": "/memberships/", "t": 99999, "s": 0, "n": 1}))["seconds"], 1800)  # capped at 30 minutes
        self.assertEqual(beacon.parse(json.dumps({"p": "/", "c": "WhatsApp"})), {"group": "home", "contact": "whatsapp"})
        bad = [
            "not json", "[]", "{}", json.dumps({"p": "/memberships/"}), json.dumps({"p": "memberships", "t": 1}), json.dumps({"p": "/nope-not-a-page/", "t": 1}),
            json.dumps({"p": "/static/x.css", "t": 1}), json.dumps({"p": "/memberships/", "t": -1}), json.dumps({"p": "/memberships/", "t": "9"}),
            json.dumps({"p": "/memberships/", "t": True}), json.dumps({"p": "/memberships/", "t": 3, "s": 33}), json.dumps({"p": "/", "c": "bad kind!"}),
            json.dumps({"p": "/", "c": 5}),
        ]
        for raw in bad:
            self.assertIsNone(beacon.parse(raw), raw)

    def test_time_scroll_and_contact_taps_are_counted_and_the_answer_is_always_204(self):
        self.assertEqual(self.send({"p": "/memberships/", "t": 40, "s": 75, "n": 0}).status_code, 204)
        self.assertEqual(self.send({"p": "/memberships/", "t": 20, "s": 100, "n": 1}).status_code, 204)  # a later beacon: seconds only
        self.assertEqual((figure(K.ENGAGED_SECONDS, "memberships"), figure(K.ENGAGED_VIEWS, "memberships"), figure(K.SCROLL, "memberships:75"), figure(K.SCROLL, "memberships:100")), (60, 1, 1, 0))
        row = VisitorHash.objects.get()
        self.assertEqual(row.visit_seconds, 60)
        self.send({"p": "/memberships/", "c": "whatsapp"})
        self.send({"p": "/memberships/", "c": "whatsapp"})
        self.assertEqual((figure(K.CONTACT_TAPS, "whatsapp"), figure(K.CONTACT_TAPS_PAGE, "whatsapp:memberships"), figure(K.CHANNEL_STEPS, "direct:contact")), (2, 2, 2))
        for odd in ("garbage", json.dumps({"p": "/memberships/", "t": -5})):
            self.assertEqual(self.send(None, raw=odd).status_code, 204)
        self.assertEqual(self.send(None, raw=json.dumps({"p": "/memberships/", "t": 5, "pad": "x" * 3000})).status_code, 204)  # over 2 KB: ignored
        self.assertEqual(figure(K.ENGAGED_SECONDS, "memberships"), 60)
        self.assertEqual(self.client.get("/a/e/").status_code, 405)

    def test_a_beacon_without_a_counted_visitor_a_bot_or_on_a_staff_host_counts_nothing(self):
        stranger = Client(HTTP_HOST="localhost", HTTP_USER_AGENT=IPHONE, REMOTE_ADDR="198.51.100.9")
        bot = Client(HTTP_HOST="localhost", HTTP_USER_AGENT=GOOGLEBOT, REMOTE_ADDR="81.2.69.142")
        for client in (stranger, bot):
            self.assertEqual(self.send({"p": "/memberships/", "t": 9, "s": 25, "n": 0}, client=client).status_code, 204)
        staff_host = Client(HTTP_HOST="office.localhost", HTTP_USER_AGENT=IPHONE, REMOTE_ADDR="81.2.69.142")
        self.assertEqual(staff_host.post("/a/e/", "{}", content_type="text/plain").status_code, 404)  # not routed on staff hosts
        self.assertEqual(figure(K.ENGAGED_VIEWS, "memberships"), 0)

    def test_the_rate_limit_is_per_visitor_and_still_answers_204(self):
        with mock.patch.object(beacon, "RATE_LIMIT", 3):
            for _ in range(6):
                self.assertEqual(self.send({"p": "/memberships/", "t": 1, "s": 0, "n": 1}).status_code, 204)
        self.assertEqual(figure(K.ENGAGED_SECONDS, "memberships"), 3)

    def test_the_script_is_on_public_pages_only(self):
        from plans.management.commands.seed_phase1 import seed_all

        seed_all()
        self.assertContains(self.client.get("/"), "common/js/beacon.js")
        self.assertNotContains(Client(HTTP_HOST="office.localhost").get("/login/"), "beacon.js")
