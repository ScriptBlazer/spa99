from django.conf import settings

import logging

from . import visitors

logger = logging.getLogger("spa99.visitors")


class VisitorCounterMiddleware:
    """Counts public page views after the response is built. Any error is logged and swallowed: counting must never
    slow or break a page."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            if getattr(settings, "VISITOR_COUNTER", True) and visitors.should_count(request, response):
                visitors.record_page_view(request)
        except Exception:  # noqa: BLE001
            logger.warning("Visitor counter skipped a page view", exc_info=True)
        return response
