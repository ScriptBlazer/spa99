"""Junk probe blocks (docs/features/analytics.md A11). Paths only bots try (WordPress, .env files, phpMyAdmin ...) get a bare 404 and
never reach a view, Sentry or the visitor counter. Caddy already does this on every host (the `(probes)` snippet in the Caddyfile);
this is the same list for local runs, CI and anything that reaches Django. /.well-known/ is never blocked.
KEEP IN STEP with the Caddyfile snippet (a test compares the two)."""
import logging
import re

from django.http import HttpResponse

logger = logging.getLogger("spa99.probes")

# Caddy path patterns, the one list both sides use. A trailing * is a prefix match, a leading * a suffix match.
PATTERNS = (
    "/.env*", "/.git*", "/.aws*", "/.ssh*", "/.DS_Store", "/wp-admin*", "/wp-login.php", "/wp-content*", "/wp-includes*", "/wp-json*",
    "/xmlrpc.php", "*.php", "/phpmyadmin*", "/pma*", "/cgi-bin*", "/vendor/*", "/server-status*", "/actuator*", "/boaform*", "/HNAP1*",
)


def _compile(patterns):
    parts = []
    for pattern in patterns:
        body = re.escape(pattern.strip("*"))
        parts.append(("^" if not pattern.startswith("*") else "") + body + ("$" if not pattern.endswith("*") else ""))
    return re.compile("|".join(parts), re.I)  # Caddy's path matching ignores case


_PROBE = _compile(PATTERNS)


def is_probe(path):
    return bool(_PROBE.search(path))


class ProbeBlockMiddleware:
    """First in the stack: a probe gets a plain 404 before anything else runs. One daily count, nothing logged above debug."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not is_probe(request.path_info):
            return self.get_response(request)
        try:
            from insights import metrics

            metrics.count(metrics.K.PROBES_BLOCKED, "", 1, counter=False)
        except Exception:  # noqa: BLE001 - counting must never matter
            logger.debug("Could not count a blocked probe", exc_info=True)
        logger.debug("Blocked probe %s", request.path_info[:100])
        return HttpResponse(status=404, content_type="text/plain")
