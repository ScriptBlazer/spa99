"""The TwiML we answer with, built by hand (no Twilio SDK). It can never loop: the one <Record> has an explicit action that says goodbye and hangs up,
maxLength 120, and there is no <Redirect> anywhere. No transcription (it is billed per minute)."""
from django.conf import settings
from django.http import HttpResponse
from django.utils.html import escape

VOICE = "Polly.Amy"
LANGUAGE = "en-GB"
GREETING = ("Hello, and thank you for calling Spa 99. The quickest way to reach us is on WhatsApp, on this same number. "
            "Or leave your name and phone number after the tone, and we will get back to you as soon as we can.")
GOODBYE = "Thank you. Goodbye."
MAX_LENGTH = 120


def _say(text):
    return f'<Say voice="{VOICE}" language="{LANGUAGE}">{escape(text)}</Say>'


def _xml(inner):
    return HttpResponse(f'<?xml version="1.0" encoding="UTF-8"?><Response>{inner}</Response>', content_type="text/xml")


def voice():
    site = settings.SITE_URL
    record = (f'<Record maxLength="{MAX_LENGTH}" playBeep="true" trim="do-not-trim" action="{escape(site)}/phone/after-record/" '
              f'recordingStatusCallback="{escape(site)}/phone/recording/" recordingStatusCallbackEvent="completed absent" />')
    return _xml(_say(GREETING) + record)


def after_record():
    return _xml(_say(GOODBYE) + "<Hangup/>")
