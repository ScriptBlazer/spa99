"""Send a test message and a test exception to Sentry. Never prints the DSN."""
import sentry_sdk
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Send a test message and a test exception to Sentry (needs SENTRY_DSN)."

    def handle(self, *args, **options):
        state = getattr(settings, "SENTRY_STATE", "off")
        if state == "off":
            self.stdout.write("Sentry is off: SENTRY_DSN is not set. Nothing sent.")
            return
        self.stdout.write(f"Sentry is {state}: a DSN is configured.")
        message_id = sentry_sdk.capture_message("Spa 99 Sentry test message")
        try:
            raise RuntimeError("Spa 99 Sentry test exception (safe to ignore)")
        except RuntimeError:
            error_id = sentry_sdk.capture_exception()
        sentry_sdk.flush(timeout=10)
        self.stdout.write(f"Message event id: {message_id}")
        self.stdout.write(f"Exception event id: {error_id}")
