"""Junk probe blocks (docs/features/analytics.md A11): bare 404, never counted as a visit, the Caddy list and the Django list agree."""
import re
from pathlib import Path

from django.conf import settings
from django.test import Client, SimpleTestCase, TestCase

from common import probes
from insights import metrics
from insights.metrics import K
from insights.models import DailyMetric, VisitorHash

SAFARI = "Mozilla/5.0 (Macintosh) Version/17 Safari/605.1"
JUNK = ["/.env", "/.env.production", "/.git/config", "/.aws/credentials", "/.ssh/id_rsa", "/.DS_Store", "/wp-admin/", "/wp-login.php",
        "/wp-content/plugins/x", "/wp-includes/x.js", "/wp-json/wp/v2/users", "/xmlrpc.php", "/anything/shell.PHP", "/phpmyadmin/", "/pma/", "/cgi-bin/x",
        "/vendor/phpunit/x", "/server-status", "/actuator/health", "/boaform/admin/formLogin", "/HNAP1/"]
FINE = ["/", "/memberships/", "/.well-known/security.txt", "/.well-known/acme-challenge/x", "/health/", "/gold-card/", "/vendors-guide/"]


class ProbeListTests(SimpleTestCase):
    def test_the_list_blocks_junk_and_never_well_known(self):
        for path in JUNK:
            self.assertTrue(probes.is_probe(path), path)
        for path in FINE:
            self.assertFalse(probes.is_probe(path), path)

    def test_caddy_has_every_pattern_on_every_site(self):
        caddy = (Path(settings.BASE_DIR) / "Caddyfile").read_text()
        snippet = re.search(r"\(probes\) \{(.*?)\n\}", caddy, re.S).group(1)
        for pattern in probes.PATTERNS:
            if pattern == "*.php":
                self.assertIn(r"path_regexp (?i)\.php$", snippet)  # Caddy's own suffix rule for any .php
            else:
                self.assertIn(f" {pattern}", snippet.replace("\n", " "))
        self.assertNotIn(".well-known", snippet)
        sites = re.findall(r"^(\S+\{\$?[A-Z_]+\}|\{\$[A-Z_]+\}|www\.\{\$DOMAIN\}) \{", caddy, re.M)
        self.assertEqual(caddy.count("\timport probes"), len(sites) - 1)  # every site block imports it, except www (it only redirects)
        self.assertGreaterEqual(len(sites), 5)


class ProbeMiddlewareTests(TestCase):
    def test_probes_get_a_bare_404_on_any_host_and_only_the_daily_count_changes(self):
        for host in ("localhost", "office.localhost", "system.localhost"):
            client = Client(HTTP_HOST=host, HTTP_USER_AGENT=SAFARI)
            for path in ("/wp-login.php", "/.env"):
                response = client.get(path)
                self.assertEqual((response.status_code, response.content), (404, b""))
        self.assertEqual(DailyMetric.objects.get(date=metrics.day(), key=K.PROBES_BLOCKED, dimension="").value, 6)
        self.assertFalse(VisitorHash.objects.exists())
        self.assertFalse(DailyMetric.objects.filter(key__in=(K.VISITORS, K.PAGE_VIEWS)).exists())
        self.assertEqual(Client(HTTP_HOST="localhost").get("/health/").status_code, 200)
