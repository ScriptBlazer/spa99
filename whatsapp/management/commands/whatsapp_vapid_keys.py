"""Make a VAPID key pair for Office notifications. Prints the three .env lines; nothing is stored. Run once, put the lines in the server .env."""
import base64

from cryptography.hazmat.primitives import serialization
from django.core.management.base import BaseCommand


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class Command(BaseCommand):
    help = "Print a new VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY pair for Web Push (not stored anywhere)."

    def handle(self, *args, **options):
        from py_vapid import Vapid

        vapid = Vapid()
        vapid.generate_keys()
        private = _b64(vapid.private_key.private_numbers().private_value.to_bytes(32, "big"))
        public = _b64(vapid.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
        self.stdout.write(f"VAPID_PUBLIC_KEY={public}\nVAPID_PRIVATE_KEY={private}\nVAPID_SUBJECT=mailto:hello@spa99.uk")
