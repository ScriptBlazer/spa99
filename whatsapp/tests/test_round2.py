"""WhatsApp round 2 (docs/features/whatsapp.md): replies, unknown messages, video, voice notes, the microphone permission and the button state. Mocked: no Twilio call
and no ffmpeg run, except one optional real conversion that skips when ffmpeg is not installed."""
import shutil
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings

from whatsapp import services, voice
from whatsapp.models import Contact, Message
from whatsapp.tests.test_whatsapp import CONFIG, OFFICE, PHONE, PUBLIC, Base, inbound, office, twilio_post

MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"0" * 100
WEBM = b"\x1a\x45\xdf\xa3" + b"0" * 100


class ReplyTests(Base):
    def setUp(self):
        super().setUp()
        self.open_window()
        self.ours = Message.objects.create(contact=self.contact, direction="out", body="*Our* price list\nsecond line", status="delivered", twilio_sid="SMours")

    def test_his_reply_links_to_our_message_only_when_the_sid_is_ours_and_in_this_chat(self):
        twilio_post("/twilio/whatsapp/incoming/", inbound("Yes please", "SMin1", OriginalRepliedMessageSid="SMours"))
        twilio_post("/twilio/whatsapp/incoming/", inbound("Hm", "SMin2", OriginalRepliedMessageSid="SMunknown"))
        elsewhere = Contact.objects.create(phone="+447400123999")
        Message.objects.create(contact=elsewhere, direction="out", body="x", twilio_sid="SMelse")
        twilio_post("/twilio/whatsapp/incoming/", inbound("Hi", "SMin3", OriginalRepliedMessageSid="SMelse"))
        first, second, third = (Message.objects.get(twilio_sid=s) for s in ("SMin1", "SMin2", "SMin3"))
        self.assertEqual((first.reply_to_id, second.reply_to_id, third.reply_to_id), (self.ours.pk, None, None))
        self.assertEqual(services.message_dict(first)["reply_to"], {"id": self.ours.pk, "direction": "out", "kind": "text", "text": "Our price list"})
        self.assertIsNone(services.message_dict(second)["reply_to"])

    def test_staff_reply_goes_as_a_quoted_line_then_the_body_and_a_retry_sends_the_same(self):
        with mock.patch("whatsapp.twilio_api.send_message", side_effect=[{"sid": "SMa", "status": "queued"}]) as call:
            result, message = services.send_text(self.contact, self.approver, "It is £50", reply_to=self.ours.pk)
        self.assertEqual(result, services.DONE)
        self.assertEqual(call.call_args.kwargs["body"], "> Our price list\n\nIt is £50")
        message.refresh_from_db()
        self.assertEqual((message.body, message.reply_to_id), ("It is £50", self.ours.pk))  # the body stays as typed
        Message.objects.filter(pk=message.pk).update(status="failed", error_code="network", twilio_sid=None)
        with mock.patch("whatsapp.twilio_api.send_message", return_value={"sid": "SMb", "status": "queued"}) as again:
            self.assertEqual(services.retry(message, self.approver)[0], services.DONE)
        self.assertEqual(again.call_args.kwargs["body"], "> Our price list\n\nIt is £50")

    def test_a_photo_is_quoted_in_words_a_foreign_message_is_refused_and_the_limit_counts_the_final_text(self):
        photo = Message.objects.create(contact=self.contact, direction="in", kind="image", status="received", twilio_sid="SMph")
        self.assertEqual(services.quote_text(photo), "Photo")
        other = Contact.objects.create(phone="+447400123998")
        foreign = Message.objects.create(contact=other, direction="out", body="x", twilio_sid="SMf2")
        self.assertEqual(services.send_text(self.contact, self.approver, "Hi", reply_to=foreign.pk)[0], services.BAD_REPLY)
        self.assertEqual(services.send_text(self.contact, self.approver, "Hi", reply_to="abc")[0], services.BAD_REPLY)
        quote = len("> Our price list\n\n")
        self.assertEqual(services.send_text(self.contact, self.approver, "x" * (1600 - quote + 1), reply_to=self.ours.pk)[0], services.TOO_LONG)
        with mock.patch("whatsapp.twilio_api.send_message", return_value={"sid": "SMc", "status": "queued"}):
            self.assertEqual(services.send_text(self.contact, self.approver, "x" * (1600 - quote), reply_to=self.ours.pk)[0], services.DONE)

    def test_the_endpoint_takes_reply_to(self):
        with mock.patch("whatsapp.twilio_api.send_message", return_value={"sid": "SMd", "status": "queued"}):
            data = office(self.approver, "post", f"/whatsapp/{self.contact.pk}/send/", {"body": "Sure", "reply_to": self.ours.pk}).json()
        self.assertEqual(data["message"]["reply_to"]["text"], "Our price list")
        bad = office(self.approver, "post", f"/whatsapp/{self.contact.pk}/send/", {"body": "Sure!", "reply_to": 999999})
        self.assertEqual((bad.status_code, bad.json()["error"]), (400, "bad_reply"))


class UnknownAndVideoTests(Base):
    def test_a_message_with_nothing_we_know_is_a_neutral_bubble_and_only_parameter_names_are_logged(self):
        with self.assertLogs("spa99.whatsapp", "INFO") as logs:
            twilio_post("/twilio/whatsapp/incoming/", inbound("", "SMr", ReactionPayload="secret-value-123"))
        message = Message.objects.get(twilio_sid="SMr")
        self.assertEqual((message.kind, message.body), ("other", ""))
        text = "\n".join(logs.output)
        self.assertIn("ReactionPayload", text)
        self.assertNotIn("secret-value-123", text)
        self.assertNotIn(PHONE, text)

    def test_video_mp4_is_accepted_up_to_16_mb_other_containers_are_not_and_the_signed_link_says_video_mp4(self):
        self.open_window()
        with mock.patch("whatsapp.twilio_api.send_message", return_value={"sid": "SMv", "status": "queued"}) as call:
            result, message = services.send_media(self.contact, self.approver, SimpleUploadedFile("clip.mp4", MP4))
            self.assertEqual((result, message.kind, message.media_type), (services.DONE, "video", "video/mp4"))
            quicktime = SimpleUploadedFile("c.mov", b"\x00\x00\x00\x14ftypqt  " + b"0" * 50)
            self.assertEqual(services.send_media(self.contact, self.approver, quicktime)[0], services.BAD_FILE)
            big = SimpleUploadedFile("big.mp4", MP4 + b"0" * (16 * 1024 * 1024))
            self.assertEqual(services.send_media(self.contact, self.approver, big)[0], services.TOO_BIG)
        link = call.call_args.kwargs["media_url"].replace("https://spa99.uk", "")
        self.assertEqual(Client(HTTP_HOST=PUBLIC).get(link)["Content-Type"], "video/mp4")  # Twilio refuses a mismatch with what we told it


class VoiceNoteTests(Base):
    def fake_ffmpeg(self, seconds=2.0, code=0):
        def run(args, **kwargs):
            self.assertIsInstance(args, list)
            self.assertFalse(kwargs.get("shell"))
            self.assertIn("-protocol_whitelist", args)
            self.assertEqual(args[args.index("-protocol_whitelist") + 1], "file")
            self.assertIn("timeout", kwargs)
            self.ran = args
            if code == 0:
                with open(args[-1], "wb") as out:
                    out.write(b"OggS" + b"0" * 50)
            return mock.Mock(returncode=code, stdout=f"out_time_us={int(seconds * 1_000_000)}\nprogress=end\n".encode(), stderr=b"")

        return mock.patch("whatsapp.voice.subprocess.run", side_effect=run)

    def send(self, data=WEBM, **fields):
        self.open_window()
        return office(self.approver, "post", f"/whatsapp/{self.contact.pk}/send-voice/", {"file": SimpleUploadedFile("note.webm", data, "audio/webm"), "duration": "2", **fields})

    def test_a_recording_is_converted_to_ogg_opus_and_sent_as_audio(self):
        with mock.patch("whatsapp.voice.binary", return_value="/usr/bin/ffmpeg"), self.fake_ffmpeg(), \
                mock.patch("whatsapp.twilio_api.send_message", return_value={"sid": "SMvo", "status": "queued"}) as call:
            data = self.send().json()
        self.assertTrue(data["ok"])
        self.assertEqual((data["message"]["kind"], data["message"]["media"]["type"]), ("audio", "audio/ogg"))
        self.assertIn("libopus", self.ran)
        self.assertEqual(self.ran[self.ran.index("-f") + 1], "matroska,webm")  # the format came from the first bytes
        self.assertTrue(call.call_args.kwargs["media_url"].startswith("https://spa99.uk/twilio/whatsapp/media/"))

    def test_the_first_bytes_decide_not_the_browser_and_a_missing_ffmpeg_or_a_long_note_is_refused(self):
        with mock.patch("whatsapp.voice.binary", return_value="/usr/bin/ffmpeg"), self.fake_ffmpeg() as run:
            self.assertEqual(self.send(b"<html>not audio").json()["error"], "bad_file")
            self.assertEqual(self.send(duration="305").json()["error"], "voice_too_long")
            run.reset_mock()
        with mock.patch("whatsapp.voice.binary", return_value="/usr/bin/ffmpeg"), self.fake_ffmpeg(seconds=400):
            self.assertEqual(self.send().json()["error"], "voice_too_long")  # measured after conversion, whatever the browser said
        with mock.patch("whatsapp.voice.binary", return_value=None):
            gone = self.send()
            self.assertEqual((gone.status_code, gone.json()["error"]), (503, "voice_unavailable"))
            page = office(self.reader, "get", f"/whatsapp/{self.contact.pk}/")
            self.assertFalse(page.context["contact"]["voice"]["available"])  # the screen hides the microphone
        self.assertEqual(Message.objects.filter(kind="audio").count(), 0)

    def test_a_failed_or_timed_out_conversion_leaves_no_message_and_no_temp_files(self):
        import os
        import subprocess
        import tempfile

        folders = []
        real = tempfile.TemporaryDirectory

        def tracked(*args, **kwargs):
            made = real(*args, **kwargs)
            folders.append(made.name)
            return made

        with mock.patch("whatsapp.voice.binary", return_value="/usr/bin/ffmpeg"), mock.patch("whatsapp.voice.tempfile.TemporaryDirectory", side_effect=tracked):
            with self.fake_ffmpeg(code=1):
                self.assertEqual(self.send().json()["error"], "bad_file")
            with mock.patch("whatsapp.voice.subprocess.run", side_effect=subprocess.TimeoutExpired("ffmpeg", 30)):
                self.assertEqual(self.send().json()["error"], "bad_file")
        self.assertTrue(folders)
        self.assertFalse(any(os.path.exists(f) for f in folders))
        self.assertEqual(Message.objects.filter(kind="audio").count(), 0)

    @override_settings(**CONFIG)
    def test_the_context_says_whether_the_microphone_can_be_used(self):
        with mock.patch("whatsapp.voice.binary", return_value="/usr/bin/ffmpeg"):
            self.assertEqual(services.contact_dict(self.contact)["voice"], {"available": True, "max_seconds": 300, "max_bytes": 10 * 1024 * 1024})

    def test_a_real_conversion_when_ffmpeg_is_installed(self):
        path = shutil.which("ffmpeg") or ("/opt/homebrew/bin/ffmpeg" if shutil.which("/opt/homebrew/bin/ffmpeg") else None)
        if not path:
            self.skipTest("ffmpeg is not installed here")
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as folder, override_settings(FFMPEG_BIN=path):
            source = f"{folder}/t.webm"
            subprocess.run([path, "-loglevel", "error", "-f", "lavfi", "-i", "sine=duration=1", "-c:a", "libopus", source], check=True, timeout=30)
            with open(source, "rb") as handle:
                ogg, seconds = voice.convert(handle.read())
        self.assertTrue(ogg.startswith(b"OggS"))
        self.assertAlmostEqual(seconds, 1.0, delta=0.3)


class MicrophoneAndButtonTests(Base):
    def test_the_microphone_is_allowed_on_the_office_host_only(self):
        self.assertEqual(Client(HTTP_HOST=OFFICE).get("/health/")["Permissions-Policy"], "microphone=(self)")
        self.assertEqual(Client(HTTP_HOST=PUBLIC).get("/health/")["Permissions-Policy"], "microphone=()")

    def test_the_button_state_is_in_the_context_even_when_whatsapp_is_not_set_up(self):
        mobile = lambda **k: services.page_context(k.get("mobile", PHONE), self.approver, k.get("can_send", True), "/s/", "/e/")
        with override_settings(TWILIO_AUTH_TOKEN=""):
            context = mobile()
            self.assertEqual((context["configured"], context["state"], context["can_send"], context["reason"]), (False, "unconfigured", False, "WhatsApp is not set up yet."))
        self.assertEqual(mobile()["state"], "ready")
        none = mobile(mobile="")
        self.assertEqual((none["state"], none["reason"], none["can_add_number"]), ("no_mobile", "Add a number to enable WhatsApp", True))
        self.assertFalse(mobile(mobile="", can_send=False)["can_add_number"])
        self.assertEqual(mobile(can_send=False)["state"], "view_only")

    def test_the_mobile_is_optional_at_the_gate_check_but_a_typed_one_is_still_checked(self):
        client = Client(HTTP_HOST=PUBLIC)
        self.assertEqual(client.post("/validate/mobile/", {"mobile": "", "mobile_country": "GB", "optional": "1"}).json(), {"valid": True})
        self.assertFalse(client.post("/validate/mobile/", {"mobile": "", "mobile_country": "GB"}).json()["valid"])
        self.assertFalse(client.post("/validate/mobile/", {"mobile": "12", "mobile_country": "GB", "optional": "1"}).json()["valid"])



class ReviewFixTests(Base):
    """Review fixes: a lost send that a worker had claimed, and Reply on a template bubble."""

    def test_a_send_claimed_by_a_worker_that_died_says_it_may_not_have_been_sent_and_try_again_sends_once(self):
        from datetime import timedelta

        from django.utils import timezone

        self.open_window()
        at = timezone.now() - timedelta(minutes=15)
        message = Message.objects.create(contact=self.contact, direction="out", body="Hello", status="queued", claimed_at=at, updated_at=at)
        recent = Message.objects.create(contact=self.contact, direction="out", body="Hi", status="queued", claimed_at=timezone.now(), updated_at=timezone.now())
        self.assertIsNone(services.message_dict(recent)["error"])
        error = services.message_dict(message)["error"]
        self.assertIn("may not have been sent", error["reason"])
        self.assertTrue(error["can_retry"])
        with mock.patch("whatsapp.twilio_api.send_message", return_value={"sid": "SMretry", "status": "queued"}) as call:
            self.assertEqual(services.retry(message, self.approver)[0], services.DONE)
            self.assertEqual(services.retry(message, self.approver)[0], services.NOT_RETRYABLE)  # a double click
        self.assertEqual(call.call_count, 1)

    def test_a_template_bubble_can_be_replied_to_and_quotes_its_text(self):
        self.open_window()
        template = self.template()
        sent = Message.objects.create(contact=self.contact, direction="out", kind="template", body="Hi Dan, thanks.", template=template, status="delivered", twilio_sid="SMtpl")
        target, invalid = services.reply_target(self.contact, sent.pk)
        self.assertEqual((target.pk, invalid), (sent.pk, False))
        self.assertEqual(services.quote_text(sent), "Hi Dan, thanks.")
        bare = Message.objects.create(contact=self.contact, direction="out", kind="template", body="", template=template, status="delivered", twilio_sid="SMtpl2")
        self.assertEqual(services.quote_text(bare), template.label or template.name)
