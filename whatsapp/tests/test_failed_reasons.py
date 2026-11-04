"""A failed WhatsApp message says why in plain words (no Twilio code), and "Try again" is offered only when trying again can help. Mocked: nothing is sent."""
from whatsapp import errors, services
from whatsapp.models import Message
from whatsapp.tests.test_whatsapp import Base


class FailedReasonTests(Base):
    def failed(self, code, status="undelivered", sid="SMx"):
        return Message.objects.create(contact=self.contact, direction="out", kind="text", body="Hi", status=status, error_code=code, twilio_sid=sid)

    def test_63024_reads_plainly_with_no_code_and_never_offers_a_retry(self):
        for status, sid in (("undelivered", "SMx"), ("failed", None)):  # Twilio's callback, and a send Twilio refused at once
            data = services.message_dict(self.failed("63024", status, sid))
            self.assertEqual(data["error"]["reason"], "This number can't get WhatsApp messages. Check it's right and on WhatsApp.")
            self.assertNotIn("63024", data["error"]["reason"])
            self.assertEqual((data["error"]["can_retry"], data["retry_url"]), (False, ""))

    def test_a_retry_is_offered_only_for_reasons_it_can_fix(self):
        self.assertEqual(errors.reason("63024"), (errors.BAD_NUMBER_REASON, False))
        self.assertTrue(errors.reason("20003")[1])  # sending stopped: fixed by topping up, then it can go
        self.assertTrue(errors.reason("")[1] and errors.reason("99999")[1])  # unknown: one more try is fair
        self.assertFalse(services.message_dict(self.failed("63016", "failed", None))["error"]["can_retry"])
