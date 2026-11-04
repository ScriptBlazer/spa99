"""The fake Twilio for the end-to-end run ONLY. e2e/settings.py adds this app to INSTALLED_APPS; no other settings file does, so the switch cannot exist in production.

`whatsapp.twilio_api.request` is replaced: nothing is ever sent to Twilio. A "send a message" call is answered the way Twilio answers (a sid and status "queued") and
written, one JSON line, to twilio-calls.jsonl in the throwaway workspace, so a walk-through can check what the site would have sent (the body, the number, the media link).
His messages and the delivery ticks are posted to the site's real webhooks by the walk-through, signed with the fake Auth Token (see e2e/chatkit.py). Email: the file
backend of e2e.settings already stands in for Postmark; his replies are posted to the real inbound webhook.
"""
import json
import uuid

from django.apps import AppConfig
from django.conf import settings


def calls_path():
    return settings.WORKSPACE / "twilio-calls.jsonl"


def fake_request(method, url, **kwargs):
    data = kwargs.get("data") or {}
    if method.upper() == "POST" and url.endswith("/Messages.json"):
        sid = "SM" + uuid.uuid4().hex
        with calls_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"sid": sid, "url": url, **{k: str(v) for k, v in data.items()}}) + "\n")
        return {"sid": sid, "status": "queued"}
    return {}


def fake_fetch_media(url, limit):
    return (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, "image/png")


class FakesConfig(AppConfig):
    name = "e2e"
    label = "e2e_fakes"

    def ready(self):
        from whatsapp import twilio_api

        twilio_api.request = fake_request
        twilio_api.fetch_media = fake_fetch_media
