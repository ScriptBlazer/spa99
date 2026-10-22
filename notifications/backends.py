"""Amazon SES email backend using boto3 (the server's IAM role supplies credentials; no keys in .env).

Set EMAIL_BACKEND=notifications.backends.SesBackend in the live .env once SES is confirmed (open question 2).
Never used in tests (they use the in-memory outbox). Unverified against real SES: needs a first live send.
"""
import logging

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger("spa99.email")


class SesBackend(BaseEmailBackend):
    def __init__(self, fail_silently=False, client=None, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self._client = client

    @property
    def client(self):
        if self._client is None:
            import boto3

            self._client = boto3.client("sesv2", region_name=getattr(settings, "AWS_SES_REGION_NAME", "eu-west-2"))
        return self._client

    def send_messages(self, email_messages):
        sent = 0
        for message in email_messages:
            recipients = message.recipients()
            if not recipients:
                continue
            try:
                self.client.send_email(
                    Destination={"ToAddresses": recipients},
                    Content={"Raw": {"Data": message.message().as_bytes()}},
                )
                sent += 1
            except Exception:
                logger.exception("SES send failed")
                if not self.fail_silently:
                    raise
        return sent
