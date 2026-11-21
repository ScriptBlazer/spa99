"""Voicemail: webhooks (signature, TwiML, idempotency), processing (download, save, email once, caps), storage names, the Twilio GET-only guard, the Office
permissions and the import. Everything about Twilio is mocked; nothing here reaches the network."""
import re
from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO
from unittest import mock

from django.core import mail
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from common import levels
from phone import naming, services, signature, twilio_api
from phone.models import MAX_ATTEMPTS, Call
from plans.models import SiteSettings
from plans.tests.helpers import make_team_member

ACCOUNT = "AC" + "a" * 32
TWILIO = dict(TWILIO_ACCOUNT_SID=ACCOUNT, TWILIO_AUTH_TOKEN="secret-token", TWILIO_API_KEY_SID="SK" + "b" * 32, TWILIO_API_KEY_SECRET="key-secret", PHONE_ENABLED=True,
              PHONE_NUMBER="+442045384999", SITE_URL="https://site.example.test", OFFICE_URL="https://office.example.test")
CALL_SID, REC_SID = "CA" + "1" * 32, "RE" + "2" * 32
OFFICE = "office.localhost"


def signed_post(path, data, token="secret-token", query="", **extra):
    data = {"AccountSid": ACCOUNT, **data}  # Twilio always sends it
    pairs = [(k, v) for k, values in data.items() for v in (values if isinstance(values, list) else [values])]
    sig = signature.expected(f"{TWILIO['SITE_URL']}{path}{query}", sorted(pairs), token)
    return Client().post(path + query, data, HTTP_X_TWILIO_SIGNATURE=sig, **extra)


def make_call(**over):
    values = dict(call_sid=CALL_SID, from_number="+447368912320", to_number="+442045384999", received_at=timezone.now(), kind=Call.VOICEMAIL, recording_sid=REC_SID,
                  recording_status=Call.COMPLETED, duration_seconds=42)
    values.update(over)
    return Call.objects.create(**values)


@override_settings(**TWILIO)
class WebhookTests(TestCase):
    def test_signature_good_and_bad(self):
        data = {"CallSid": CALL_SID, "From": "+447368912320", "To": "+442045384999"}
        self.assertEqual(signed_post("/phone/voice/", data).status_code, 200)
        self.assertEqual(Call.objects.count(), 1)
        Call.objects.all().delete()
        bad = signed_post("/phone/voice/", data, token="wrong")
        self.assertEqual(bad.status_code, 403)
        self.assertEqual(Client().post("/phone/voice/", data).status_code, 403)  # no signature at all
        self.assertEqual(Call.objects.count(), 0)

    def test_post_only_and_off_means_503(self):
        self.assertEqual(Client().get("/phone/voice/").status_code, 405)
        with override_settings(PHONE_ENABLED=False, TWILIO_AUTH_TOKEN=""):
            for path in ("voice", "after-record", "recording"):
                self.assertEqual(Client().post(f"/phone/{path}/", {"CallSid": CALL_SID}).status_code, 503)
        self.assertEqual(Call.objects.count(), 0)

    def test_signature_covers_the_query_string_and_repeated_params(self):
        data = {"CallSid": CALL_SID, "From": "+447368912320", "To": "+442045384999", "Digits": ["2", "1"]}
        self.assertEqual(signed_post("/phone/voice/", data, query="?a=1&b=2").status_code, 200)
        # the same body signed for a different query is refused
        pairs = sorted((k, v) for k, vs in {"AccountSid": ACCOUNT, **data}.items() for v in (vs if isinstance(vs, list) else [vs]))
        sig = signature.expected(f"{TWILIO['SITE_URL']}/phone/voice/?a=2", pairs, "secret-token")
        self.assertEqual(Client().post("/phone/voice/?a=1", {"AccountSid": ACCOUNT, **data}, HTTP_X_TWILIO_SIGNATURE=sig).status_code, 403)

    def test_missing_account_sid_is_refused(self):
        data = {"CallSid": CALL_SID}
        sig = signature.expected(f"{TWILIO['SITE_URL']}/phone/voice/", sorted(data.items()), "secret-token")
        self.assertEqual(Client().post("/phone/voice/", data, HTTP_X_TWILIO_SIGNATURE=sig).status_code, 403)
        self.assertEqual(Call.objects.count(), 0)

    def test_a_later_voice_webhook_fills_blank_numbers(self):
        with mock.patch("common.tasks.enqueue"):
            signed_post("/phone/recording/", {"CallSid": CALL_SID, "RecordingSid": REC_SID, "RecordingStatus": "completed", "RecordingDuration": "5"})
        self.assertEqual(Call.objects.get().from_number, "")
        signed_post("/phone/voice/", {"CallSid": CALL_SID, "From": "+447368912320", "To": "+442045384999"})
        self.assertEqual(Call.objects.get().from_number, "+447368912320")

    def test_another_account_is_refused(self):
        self.assertEqual(signed_post("/phone/recording/", {"CallSid": CALL_SID, "AccountSid": "AC" + "9" * 32, "RecordingStatus": "completed"}).status_code, 403)

    def test_voice_twiml_has_the_safe_shape(self):
        response = signed_post("/phone/voice/", {"CallSid": CALL_SID, "From": "+447368912320", "To": "+442045384999"})
        xml = response.content.decode()
        self.assertEqual(response["Content-Type"], "text/xml")
        self.assertIn('voice="Polly.Amy" language="en-GB"', xml)
        self.assertIn("The quickest way to reach us is on WhatsApp", xml)
        self.assertIn('maxLength="120"', xml)
        self.assertIn('trim="do-not-trim"', xml)
        self.assertIn('action="https://site.example.test/phone/after-record/"', xml)
        self.assertIn('recordingStatusCallback="https://site.example.test/phone/recording/"', xml)
        self.assertIn('recordingStatusCallbackEvent="completed absent"', xml)
        self.assertEqual(xml.count("<Record "), 1)
        for forbidden in ("transcribe", "<Redirect", "<Dial", "<Sms", "<Message"):
            self.assertNotIn(forbidden, xml)

    def test_after_record_says_goodbye_and_hangs_up_and_never_loops(self):
        xml = signed_post("/phone/after-record/", {"CallSid": CALL_SID}).content.decode()
        self.assertIn("Thank you. Goodbye.", xml)
        self.assertTrue(xml.endswith("<Hangup/></Response>"))
        for forbidden in ("<Record", "<Redirect", "<Gather", "<Dial"):
            self.assertNotIn(forbidden, xml)

    def test_voice_is_idempotent_and_starts_as_no_message(self):
        data = {"CallSid": CALL_SID, "From": "+447368912320", "To": "+442045384999"}
        for _ in range(3):
            signed_post("/phone/voice/", data)
        call = Call.objects.get()
        self.assertEqual((call.kind, call.source, call.from_number), (Call.MISSED, Call.LIVE, "+447368912320"))

    def test_recording_callback_flips_kind_queues_once_and_repeats_change_nothing(self):
        signed_post("/phone/voice/", {"CallSid": CALL_SID, "From": "+447368912320", "To": "+442045384999"})
        data = {"CallSid": CALL_SID, "RecordingSid": REC_SID, "RecordingStatus": "completed", "RecordingDuration": "42"}
        with mock.patch("common.tasks.enqueue") as enqueue:
            first = signed_post("/phone/recording/", data)
            again = signed_post("/phone/recording/", data)
        self.assertEqual((first.status_code, again.status_code), (204, 204))
        call = Call.objects.get()
        self.assertEqual((call.kind, call.recording_sid, call.duration_seconds), (Call.VOICEMAIL, REC_SID, 42))
        self.assertEqual(enqueue.call_count, 1)  # the repeat queues nothing
        self.assertEqual(Call.objects.count(), 1)

    def test_a_second_recording_on_the_same_call_is_ignored(self):
        make_call()
        with mock.patch("common.tasks.enqueue") as enqueue:
            signed_post("/phone/recording/", {"CallSid": CALL_SID, "RecordingSid": "RE" + "3" * 32, "RecordingStatus": "completed", "RecordingDuration": "5"})
        self.assertEqual(Call.objects.get().recording_sid, REC_SID)
        enqueue.assert_not_called()

    def test_callback_before_the_voice_webhook_still_makes_the_row(self):
        with mock.patch("common.tasks.enqueue"):
            signed_post("/phone/recording/", {"CallSid": CALL_SID, "RecordingSid": REC_SID, "RecordingStatus": "completed", "RecordingDuration": "10"})
        self.assertEqual(Call.objects.get().kind, Call.VOICEMAIL)

    def test_absent_is_a_voicemail_with_no_audio_and_no_email(self):
        signed_post("/phone/voice/", {"CallSid": CALL_SID, "From": "+447368912320", "To": "+442045384999"})
        signed_post("/phone/recording/", {"CallSid": CALL_SID, "RecordingSid": REC_SID, "RecordingStatus": "absent", "RecordingDuration": "0"})  # sync queue in tests: it ran
        call = Call.objects.get()
        self.assertEqual((call.kind, call.recording_status, bool(call.audio), call.has_sound), (Call.VOICEMAIL, Call.ABSENT, False, False))
        self.assertEqual((call.emailed_at, call.email_skipped, len(mail.outbox)), (None, True, 0))  # 0 seconds: under 3, so hidden and not emailed

    def test_other_statuses_do_nothing(self):
        make_call(kind=Call.MISSED, recording_sid=None, recording_status="")
        signed_post("/phone/recording/", {"CallSid": CALL_SID, "RecordingSid": REC_SID, "RecordingStatus": "in-progress"})
        self.assertEqual(Call.objects.get().kind, Call.MISSED)


@override_settings(**TWILIO)
class ProcessingTests(TestCase):
    def process(self, call, audio=b"ID3audio"):
        with mock.patch("phone.twilio_api.download_recording", return_value=audio) as download:
            result = services.process(call.pk)
        return result, download

    def test_downloads_saves_and_emails_once(self):
        call = make_call()
        result, download = self.process(call)
        call.refresh_from_db()
        self.assertEqual(result, "done")
        download.assert_called_once_with(REC_SID)
        self.assertTrue(call.audio.name.startswith("voicemails/") and call.audio.name.endswith("_07368912320.mp3"))
        self.assertIsNotNone(call.audio_saved_at)
        self.assertTrue(default_storage.exists(call.audio.name))
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, "New voicemail from 07368 912320")
        self.assertEqual(message.to, ["from@example.test"])  # the default list: the site address
        self.assertEqual(message.attachments, [])
        self.assertIn(f"https://office.example.test/calls/{call.pk}/", message.body + message.alternatives[0][0])
        self.assertEqual(self.process(call)[0], "nothing to do")  # run again: nothing downloaded, nothing sent
        self.assertEqual(len(mail.outbox), 1)

    def test_no_email_for_a_call_with_no_message_or_an_import(self):
        quiet = make_call(call_sid="CA" + "4" * 32, kind=Call.MISSED, recording_sid=None, recording_status="")
        imported = make_call(call_sid="CA" + "5" * 32, recording_sid="RE" + "5" * 32, source=Call.IMPORT)
        self.assertEqual(services.process(quiet.pk), "nothing to do")
        self.process(imported)
        imported.refresh_from_db()
        self.assertTrue(imported.audio)
        self.assertEqual(len(mail.outbox), 0)

    def test_empty_recipient_list_skips_and_says_so(self):
        SiteSettings.objects.update_or_create(defaults={"voicemail_email_to": ""}, pk=SiteSettings.load().pk)
        call = make_call()
        self.process(call)
        call.refresh_from_db()
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(call.email_skipped)
        self.assertIn("No one is on the", call.last_error)
        self.assertTrue(call.audio)

    def test_a_voicemail_under_3_seconds_is_saved_but_not_emailed(self):
        call = make_call(duration_seconds=2)
        self.process(call)
        call.refresh_from_db()
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(call.email_skipped)
        self.assertIn("Shorter than 3 seconds", call.last_error)
        self.assertTrue(call.audio)
        call.audio.delete(save=False)  # InMemoryStorage outlives the test: free the name for the others

    def test_failure_is_recorded_backs_off_and_stops_at_the_cap(self):
        call = make_call()
        with mock.patch("phone.twilio_api.download_recording", side_effect=twilio_api.TwilioError("Twilio answered 500")) as download:
            services.process(call.pk)
            call.refresh_from_db()
            self.assertEqual(call.attempts, 1)
            self.assertIn("Twilio answered 500", call.last_error)
            self.assertGreater(call.next_attempt_at, timezone.now())
            self.assertEqual(services.process(call.pk), "skipped")  # still backing off: no new attempt, no download
            self.assertEqual(download.call_count, 1)
            for _ in range(20):  # however often it is asked, never past the cap
                Call.objects.filter(pk=call.pk).update(next_attempt_at=None, claimed_until=None)
                services.process(call.pk)
        call.refresh_from_db()
        self.assertEqual(call.attempts, MAX_ATTEMPTS)
        self.assertEqual(download.call_count, MAX_ATTEMPTS)
        self.assertEqual(len(mail.outbox), 1)  # the email went out once even though the audio never came

    def test_a_failed_email_gives_emailed_at_back_and_never_duplicates(self):
        call = make_call(audio="voicemails/x.mp3", audio_saved_at=timezone.now())
        with mock.patch("django.core.mail.EmailMultiAlternatives.send", side_effect=OSError("smtp down")):
            self.assertTrue(services.process(call.pk).startswith("failed"))
        call.refresh_from_db()
        self.assertIsNone(call.emailed_at)
        Call.objects.filter(pk=call.pk).update(next_attempt_at=None)
        services.process(call.pk)
        services.process(call.pk)
        self.assertEqual(len(mail.outbox), 1)

    def test_sweep_is_bounded_and_skips_finished_and_exhausted_rows(self):
        for n in range(services.SWEEP_BATCH + 5):
            make_call(call_sid=f"CA{n:032d}", recording_sid=f"RE{n:032d}", audio="a.mp3", emailed_at=timezone.now())  # finished
        waiting = [make_call(call_sid=f"CB{n:032d}", recording_sid=f"RF{n:032d}") for n in range(services.SWEEP_BATCH + 5)]
        make_call(call_sid="CC" + "0" * 32, recording_sid="RG" + "0" * 32, attempts=MAX_ATTEMPTS)
        with mock.patch("phone.twilio_api.download_recording", return_value=b"x") as download:
            services.sweep()
        self.assertEqual(download.call_count, services.SWEEP_BATCH)
        self.assertEqual(Call.objects.filter(pk__in=[c.pk for c in waiting], audio="").count(), 5)

    def test_audio_rows_do_not_crowd_the_sweep_when_the_api_key_is_missing(self):
        for n in range(services.SWEEP_BATCH + 3):
            make_call(call_sid=f"CA{n:032d}", recording_sid=f"RE{n:032d}", received_at=timezone.now() - timedelta(days=2), emailed_at=timezone.now())  # oldest, only the audio waiting
        emailed_only = make_call(call_sid="CZ" + "0" * 32, recording_sid="RZ" + "0" * 32, audio="a.mp3")  # newest, only the email is waiting
        with override_settings(TWILIO_API_KEY_SID="", TWILIO_API_KEY_SECRET=""):
            ids = list(Call.objects.filter(services.pending_q(timezone.now())).values_list("pk", flat=True))
            services.sweep()
        emailed_only.refresh_from_db()
        self.assertIsNotNone(emailed_only.emailed_at)
        self.assertTrue(all(Call.objects.get(pk=pk).attempts <= 1 for pk in ids))
        self.assertFalse(Call.objects.filter(attempts__gt=1).exists())

    def test_audio_alone_with_no_api_key_costs_no_attempt(self):
        call = make_call(source=Call.IMPORT)
        with override_settings(TWILIO_API_KEY_SID=""):
            self.assertEqual(services.process(call.pk), "off")
        call.refresh_from_db()
        self.assertEqual((call.attempts, call.last_error), (0, ""))

    def test_sweep_stops_taking_rows_when_the_time_budget_is_spent(self):
        for n in range(5):
            make_call(call_sid=f"CA{n:032d}", recording_sid=f"RE{n:032d}", received_at=timezone.now() - timedelta(hours=n + 1))
        ticks = iter([0, 0, 50, 100, 200, 300, 400])
        with mock.patch("phone.twilio_api.download_recording", return_value=b"x") as download:
            result = services.sweep(clock=lambda: next(ticks))
        self.assertEqual(download.call_count, 2)  # rows at 0 s and 50 s; the next check, at 100 s, is past 90 s
        self.assertIn("2 looked at", result)

    def test_two_copies_of_the_callback_only_one_queues(self):
        make_call(kind=Call.MISSED, recording_sid=None, recording_status="")
        with mock.patch("phone.services.Call.objects.filter", wraps=Call.objects.filter):
            first = services.record_callback(CALL_SID, REC_SID, "completed", "7")
            second = services.record_callback(CALL_SID, REC_SID, "completed", "7")
        self.assertIsNotNone(first)
        self.assertIsNone(second)

    def test_missed_call_row_with_a_late_callback_becomes_a_voicemail(self):
        make_call(kind=Call.MISSED, recording_sid=None, recording_status="")
        with mock.patch("phone.twilio_api.download_recording", return_value=b"x"):
            services.record_callback(CALL_SID, REC_SID, "completed", "7")
        self.assertEqual(Call.objects.get().kind, Call.VOICEMAIL)


class StorageNameTests(TestCase):
    def test_key_is_readable_london_time_and_national_digits(self):
        moment = datetime(2026, 7, 1, 13, 5, tzinfo=dt_timezone.utc)  # 14:05 in London (BST)
        self.assertEqual(naming.base_key(moment, "+447368912320"), "voicemails/2026/07/2026-07-01_14-05_07368912320")
        self.assertTrue(naming.base_key(moment, "+33612345678").endswith("_0033612345678"))
        for odd in ("", "anonymous", "+44******912320", "+266696687"):
            self.assertTrue(naming.base_key(moment, odd).endswith("_unknown"), odd)

    def test_clash_gets_2_then_3(self):
        moment = datetime(2026, 1, 5, 9, 30, tzinfo=dt_timezone.utc)
        keys = []
        for _ in range(3):
            key = naming.free_key(moment, "+447368912320")
            default_storage.save(key, __import__("django.core.files.base", fromlist=["ContentFile"]).ContentFile(b"x"))
            keys.append(key)
        self.assertEqual([k.rsplit("/", 1)[1] for k in keys], ["2026-01-05_09-30_07368912320.mp3", "2026-01-05_09-30_07368912320_2.mp3", "2026-01-05_09-30_07368912320_3.mp3"])

    def test_a_racing_save_that_gets_a_random_name_is_cleaned_up_and_the_next_suffix_used(self):
        class Racy:
            def __init__(self):
                self.files, self.first = {}, True

            def exists(self, key):
                return key in self.files

            def save(self, key, content):
                if self.first:  # someone else took the key between the check and the save: the storage invents a name
                    self.first = False
                    self.files[key] = b"other"
                    name = key.replace(".mp3", "_Xy7kQ2z.mp3")
                else:
                    name = key
                self.files[name] = content.read()
                return name

            def delete(self, name):
                self.files.pop(name, None)

        storage = Racy()
        name = naming.store(b"mine", datetime(2026, 1, 5, 9, 30, tzinfo=dt_timezone.utc), "+447368912320", storage=storage)
        self.assertEqual(name, "voicemails/2026/01/2026-01-05_09-30_07368912320_2.mp3")
        self.assertEqual(sorted(storage.files), ["voicemails/2026/01/2026-01-05_09-30_07368912320.mp3", name])  # no stray random file left behind

    def test_friendly_number(self):
        self.assertEqual(naming.friendly_number("+447368912320"), "07368 912320")
        self.assertEqual(naming.friendly_number("+33612345678"), "+33612345678")


@override_settings(**TWILIO)
class TwilioGuardTests(TestCase):
    def test_only_get_ever_leaves(self):
        with mock.patch("phone.twilio_api._open") as opened:
            for method in ("POST", "DELETE", "PUT", "PATCH"):
                with self.assertRaises(twilio_api.Refused):
                    twilio_api._send(method, "https://api.twilio.com/2010-04-01/Accounts/x/Messages.json")
            opened.assert_not_called()

    def test_paths_are_a_short_list_for_this_account(self):
        calls = f"/2010-04-01/Accounts/{ACCOUNT}"
        for ok in (f"{calls}/Calls.json", f"{calls}/Calls/{CALL_SID}/Recordings.json", f"{calls}/Recordings/{REC_SID}.mp3"):
            self.assertTrue(twilio_api.allowed_path(ok), ok)
        for bad in (f"{calls}/Messages.json", f"{calls}/Calls.json/x", f"{calls}/Transcriptions.json", f"{calls}/Recordings/{REC_SID}.json", "/2010-04-01/Accounts/ACother/Calls.json"):
            self.assertFalse(twilio_api.allowed_path(bad), bad)
            with self.assertRaises(twilio_api.Refused), mock.patch("phone.twilio_api._open") as opened:
                twilio_api.get(bad)
            opened.assert_not_called()

    class Reply:
        """A fake HTTP response that hands its body out in small pieces, like a real socket."""

        def __init__(self, status, body=b"", headers=None):
            import io

            self.status, self.headers, self._body = status, headers or {}, io.BytesIO(body)

        def read(self, n=-1):
            return self._body.read(min(n, 3) if n and n > 0 else -1)

        def close(self):
            pass

    def test_body_read_in_pieces_and_cut_off_answer_refused(self):
        with mock.patch("phone.twilio_api._open", return_value=self.Reply(200, b"0123456789", {"Content-Length": "10"})):
            self.assertEqual(twilio_api.download_recording(REC_SID), b"0123456789")
        with mock.patch("phone.twilio_api._open", return_value=self.Reply(200, b"01234", {"Content-Length": "10"})), self.assertRaises(twilio_api.TwilioError):
            twilio_api.download_recording(REC_SID)

    def test_download_is_one_get_with_the_key_and_redirects_drop_it(self):
        Reply = self.Reply
        replies = [Reply(302, headers={"Location": "https://media.example.test/signed"}), Reply(200, b"MP3DATA")]
        with mock.patch("phone.twilio_api._open", side_effect=replies) as opened:
            self.assertEqual(twilio_api.download_recording(REC_SID), b"MP3DATA")
        first, second = (c.args[0] for c in opened.call_args_list)
        self.assertEqual((first.get_method(), second.get_method()), ("GET", "GET"))
        self.assertTrue(first.has_header("Authorization"))
        self.assertFalse(second.has_header("Authorization"))  # the key never goes to another host
        self.assertTrue(all(c.args[1] == twilio_api.TIMEOUT for c in opened.call_args_list))

    def test_q_cluster_cannot_retry_forever(self):
        from django.conf import settings

        self.assertGreater(settings.Q_CLUSTER["retry"], settings.Q_CLUSTER["timeout"])
        self.assertGreater(settings.Q_CLUSTER["max_attempts"], 0)


class OfficeTests(TestCase):
    def setUp(self):
        self.call = make_call(audio="voicemails/2026/11/test.mp3")
        default_storage.save("voicemails/2026/11/test.mp3", __import__("django.core.files.base", fromlist=["ContentFile"]).ContentFile(b"0123456789"))
        Call.objects.create(call_sid="CA" + "7" * 32, from_number="+447000000000", received_at=timezone.now() - timedelta(hours=1), kind=Call.MISSED)

    def login(self, level):
        client = Client(HTTP_HOST=OFFICE)
        client.force_login(make_team_member(f"{level}@example.test", level))
        return client

    def test_viewer_is_refused_and_office_can_see_everything(self):
        pk = self.call.pk
        viewer = self.login(levels.VIEWER)
        for path in ("/calls/", f"/calls/{pk}/", f"/calls/{pk}/audio/"):
            self.assertEqual(viewer.get(path).status_code, 403, path)
        self.assertEqual(viewer.post(f"/calls/{pk}/heard/").status_code, 403)
        for level in (levels.OFFICE, levels.ADMIN, levels.DEVELOPER, levels.SUPERUSER):
            client = self.login(level)
            self.assertEqual(client.get("/calls/").status_code, 200, level)
            self.assertEqual(client.get(f"/calls/{pk}/").status_code, 200, level)

    def test_the_two_views_and_the_unheard_badge(self):
        client = self.login(levels.OFFICE)
        voicemails = client.get("/calls/")
        self.assertEqual([c.pk for c in voicemails.context["rows"]], [self.call.pk])
        self.assertEqual(voicemails.context["unheard"], 1)
        self.assertEqual(voicemails.context["office_voicemails_unheard"], 1)
        every = client.get("/calls/?view=all")
        self.assertEqual(len(every.context["rows"]), 2)
        self.assertEqual(every.context["rows"][0].pk, self.call.pk)  # newest first
        self.assertContains(every, "No message")

    def test_short_voicemails_have_their_own_page_and_never_count(self):
        short = make_call(call_sid="CA" + "e" * 32, recording_sid="RE" + "e" * 32, duration_seconds=2)
        client = self.login(levels.OFFICE)
        main = client.get("/calls/")
        self.assertEqual([c.pk for c in main.context["rows"]], [self.call.pk])
        self.assertEqual((main.context["short"], main.context["counts"]["voicemails"], main.context["unheard"]), (1, 1, 1))
        self.assertContains(main, "?view=short")
        page = client.get("/calls/?view=short")
        self.assertEqual([c.pk for c in page.context["rows"]], [short.pk])
        self.assertEqual(page.context["counts"]["voicemails"], 1)  # the tab shows the short count on this page
        self.assertContains(page, "Back to real voicemails")
        self.assertEqual(len(client.get("/calls/?view=all").context["rows"]), 3)  # All calls lists everything

    def test_no_sound_voicemails_never_count_as_unheard_and_opening_one_marks_it_heard(self):
        silent = make_call(call_sid="CA" + "d" * 32, recording_sid="RE" + "d" * 32, recording_status=Call.ABSENT)
        self.assertEqual(services.unheard_count(), 1)  # only the one with sound
        client = self.login(levels.OFFICE)
        client.get(f"/calls/{silent.pk}/")
        silent.refresh_from_db()
        self.assertIsNotNone(silent.heard_at)
        self.assertEqual(services.unheard_count(), 1)

    def test_heard_is_set_once_by_the_first_person(self):
        first, second = self.login(levels.OFFICE), self.login(levels.ADMIN)
        first.post(f"/calls/{self.call.pk}/heard/")
        self.call.refresh_from_db()
        heard_at, by = self.call.heard_at, self.call.heard_by
        self.assertIsNotNone(heard_at)
        second.post(f"/calls/{self.call.pk}/heard/")
        self.call.refresh_from_db()
        self.assertEqual((self.call.heard_at, self.call.heard_by), (heard_at, by))
        self.assertEqual(services.unheard_count(), 0)

    def test_audio_streams_as_mpeg_with_range(self):
        client = self.login(levels.OFFICE)
        whole = client.get(f"/calls/{self.call.pk}/audio/")
        self.assertEqual((whole.status_code, whole["Content-Type"], whole.content), (200, "audio/mpeg", b"0123456789"))
        part = client.get(f"/calls/{self.call.pk}/audio/", HTTP_RANGE="bytes=2-4")
        self.assertEqual((part.status_code, part.content, part["Content-Range"]), (206, b"234", "bytes 2-4/10"))
        self.assertEqual(client.get(f"/calls/{Call.objects.exclude(pk=self.call.pk).get().pk}/audio/").status_code, 404)

    def test_audio_redirects_to_a_short_signed_link_on_s3(self):
        from django.core.files.storage import InMemoryStorage

        urls = []

        def url(self_, name, expire=None):
            urls.append((name, expire))
            return "https://bucket.example.test/signed"

        with mock.patch.object(InMemoryStorage, "bucket_name", "bucket", create=True), mock.patch.object(InMemoryStorage, "url", url):
            response = self.login(levels.OFFICE).get(f"/calls/{self.call.pk}/audio/")
        self.assertEqual((response.status_code, response["Location"]), (302, "https://bucket.example.test/signed"))
        self.assertEqual(urls, [("voicemails/2026/11/test.mp3", 300)])

    def test_range_from_the_end_and_past_the_end(self):
        client = self.login(levels.OFFICE)
        tail = client.get(f"/calls/{self.call.pk}/audio/", HTTP_RANGE="bytes=-4")
        self.assertEqual((tail.status_code, tail.content, tail["Content-Range"]), (206, b"6789", "bytes 6-9/10"))
        open_end = client.get(f"/calls/{self.call.pk}/audio/", HTTP_RANGE="bytes=7-")
        self.assertEqual((open_end.status_code, open_end.content), (206, b"789"))
        self.assertEqual(client.get(f"/calls/{self.call.pk}/audio/", HTTP_RANGE="bytes=50-").status_code, 416)

    def test_callers_match_leads_gold_applicants_and_people(self):
        from django.contrib.auth import get_user_model

        from gold.models import GoldApplication
        from journey.models import JourneySession

        JourneySession.objects.create(lead_email="lee@example.test", lead_mobile="+447111111111", lead_first_name="Lee", lead_at=timezone.now())
        GoldApplication.objects.create(first_name="Gina", last_name="Gold", email="gina@example.test", mobile="+447222222222")
        get_user_model().objects.create_user("p@example.test", "x", first_name="Pat", last_name="Person", mobile="+447333333333")
        rows = [Call(from_number=n) for n in ("+447111111111", "+447222222222", "+447333333333", "+447999999999", "anonymous")]
        from django.urls import set_urlconf

        set_urlconf("config.urls_office")  # as the Office host does for a request
        self.addCleanup(set_urlconf, None)
        with self.assertNumQueries(3):
            found = services.callers(rows)
        self.assertEqual([(found[n]["name"], found[n]["kind"]) for n in ("+447111111111", "+447222222222", "+447333333333")],
                         [("Lee", "Lead"), ("Gina Gold", "Gold applicant"), ("Pat Person", "Registered")])
        self.assertNotIn("+447999999999", found)

    def test_caller_is_matched_to_a_person_by_mobile(self):
        from django.contrib.auth import get_user_model

        get_user_model().objects.create_user("james@example.test", "x", first_name="James", last_name="Smith", mobile="+447368912320")
        row = self.login(levels.OFFICE).get("/calls/").context["rows"][0]
        self.assertEqual(row.person["name"], "James Smith")


@override_settings(**TWILIO)
class ImportTests(TestCase):
    def fake(self, path, params=None):
        calls = f"/2010-04-01/Accounts/{ACCOUNT}"
        if path == f"{calls}/Calls.json":
            return {"calls": [
                {"sid": CALL_SID, "to": "+442045384999", "from": "+44******912320", "start_time": "Wed, 18 Nov 2026 10:00:00 +0000"},
                {"sid": "CA" + "8" * 32, "to": "+442045384999", "from": "+44******111111", "start_time": "Wed, 18 Nov 2026 11:00:00 +0000"},
                {"sid": "CA" + "9" * 32, "to": "+441111111111", "from": "+44******222222", "start_time": "Wed, 18 Nov 2026 12:00:00 +0000"}], "next_page_uri": None}
        if path.endswith(f"{CALL_SID}/Recordings.json"):
            return {"recordings": [{"sid": REC_SID, "source": "RecordVerb", "status": "completed", "duration": "12"},
                                   {"sid": "RE" + "6" * 32, "source": "OutboundAPI", "status": "completed", "duration": "3"}]}
        return {"recordings": []}

    def run_import(self, *args):
        out = StringIO()
        with mock.patch("phone.twilio_api.get_json", side_effect=self.fake), mock.patch("phone.twilio_api.download_recording", return_value=b"mp3") as download:
            call_command("import_twilio_voicemails", *args, stdout=out)
        return out.getvalue(), download

    def test_dry_run_is_the_default_writes_nothing_and_masks_numbers(self):
        for args in ((), ("--dry-run",)):
            output, download = self.run_import(*args)
            self.assertEqual(Call.objects.count(), 0)
            download.assert_not_called()
            self.assertIn("voicemails 1", output)
            self.assertIn("no message 1", output)
            self.assertIn("***320", output)
            self.assertNotIn("912320", output)

    def test_apply_imports_without_email_and_twice_is_safe(self):
        output, download = self.run_import("--apply")
        voicemail, quiet = Call.objects.get(call_sid=CALL_SID), Call.objects.exclude(call_sid=CALL_SID).get()
        self.assertEqual((voicemail.source, voicemail.kind, voicemail.recording_sid, voicemail.duration_seconds), (Call.IMPORT, Call.VOICEMAIL, REC_SID, 12))
        self.assertTrue(voicemail.audio)
        self.assertEqual((quiet.kind, quiet.source), (Call.MISSED, Call.IMPORT))
        self.assertTrue(voicemail.audio.name.endswith("_unknown.mp3"))  # a masked number cannot name the file
        self.assertEqual(Call.objects.count(), 2)  # the call to another number was never touched
        self.assertEqual(len(mail.outbox), 0)
        again, download = self.run_import("--apply")
        self.assertEqual(Call.objects.count(), 2)
        download.assert_not_called()
        self.assertIn("already there 2", again)

    def test_a_negative_twilio_duration_is_stored_as_zero(self):
        real = self.fake

        def fake(path, params=None):
            data = real(path, params)
            for recording in data.get("recordings", []):
                recording["duration"] = "-1"  # Twilio's "no length"
            return data

        self.fake = fake
        self.run_import("--apply")
        call = Call.objects.get(call_sid=CALL_SID)
        self.assertEqual(call.duration_seconds, 0)
        call.audio.delete(save=False)  # the in-memory storage outlives the test: leave the name free for the others

    @override_settings(PHONE_ENABLED=False, TWILIO_AUTH_TOKEN="")
    def test_import_works_on_a_mac_with_only_the_api_key_and_a_new_call_is_picked_up_later(self):
        self.run_import("--apply")
        self.assertEqual(Call.objects.count(), 2)
        self.assertEqual(Client().post("/phone/voice/", {"CallSid": "x"}).status_code, 503)  # the webhooks stay off
        newer = self.fake

        def with_new_call(path, params=None):
            data = newer(path, params)
            if path.endswith("/Calls.json"):
                data["calls"].insert(0, {"sid": "CA" + "c" * 32, "to": "+442045384999", "from": "+447368912320", "start_time": "Thu, 19 Nov 2026 09:00:00 +0000"})
            return data

        self.fake = with_new_call
        output, _ = self.run_import("--apply")
        self.assertEqual(Call.objects.count(), 3)
        self.assertIn("already there 2", output)

    def test_paging_follows_next_page_uri_and_the_limit_stops_it(self):
        base = f"/2010-04-01/Accounts/{ACCOUNT}"
        pages = {f"{base}/Calls.json": {"calls": [{"sid": f"CA{n:032d}", "to": "+442045384999", "from": "+44******000000", "start_time": "Wed, 18 Nov 2026 10:00:00 +0000"} for n in (1, 2)],
                                        "next_page_uri": f"{base}/Calls.json?To=%2B442045384999&Page=1&PageSize=50&PageToken=abc"},
                 f"{base}/Calls.json?To=%2B442045384999&Page=1&PageSize=50&PageToken=abc": {"calls": [{"sid": f"CA{n:032d}", "to": "+442045384999", "from": "+44******000000",
                                                                                                        "start_time": "Tue, 17 Nov 2026 10:00:00 +0000"} for n in (3, 4)], "next_page_uri": None}}
        asked = []

        def fake(path, params=None):
            asked.append(path)
            return pages.get(path, {"recordings": []})

        for limit, expected in (("3", 3), ("100", 4)):
            Call.objects.all().delete()
            asked.clear()
            with mock.patch("phone.twilio_api.get_json", side_effect=fake):
                call_command("import_twilio_voicemails", "--apply", "--limit", limit, stdout=StringIO())
            self.assertEqual(Call.objects.count(), expected)
        self.assertTrue(any("PageToken=abc" in p for p in asked))  # the second page really was followed

    def test_mark_heard_is_off_by_default_and_on_when_asked(self):
        self.run_import("--apply")
        self.assertIsNone(Call.objects.get(call_sid=CALL_SID).heard_at)
        Call.objects.all().delete()
        self.run_import("--apply", "--mark-heard")
        voicemail = Call.objects.get(call_sid=CALL_SID)
        self.assertIsNotNone(voicemail.heard_at)
        self.assertIsNone(voicemail.heard_by)
        self.assertEqual(services.unheard_count(), 0)

    def test_limit_caps_the_calls_looked_at(self):
        output, _ = self.run_import("--limit", "1")
        self.assertIn("looked at 1", output)


class RecipientSettingTests(TestCase):
    def form(self, data):
        from system.forms import EmailsForm

        site = SiteSettings.load()
        form = EmailsForm({"gold_approver_cc": "", "contact_email": "", "lead_next_morning_on": "", **data, "row_token": EmailsForm(instance=site).initial["row_token"]}, instance=site)
        return form

    def test_default_is_the_site_address_a_list_is_validated_and_a_missing_field_keeps_it(self):
        site = SiteSettings.load()
        self.assertEqual(site.voicemail_to_list, ["from@example.test"])
        bad = self.form({"voicemail_email_to": "a@example.test, nonsense"})
        self.assertFalse(bad.is_valid())
        self.assertIn("voicemail_email_to", bad.errors)
        good = self.form({"voicemail_email_to": "a@example.test, b@example.test"})
        self.assertTrue(good.is_valid(), good.errors)
        self.assertEqual(good.cleaned_data["voicemail_email_to"], "a@example.test, b@example.test")
        absent = self.form({})
        self.assertTrue(absent.is_valid(), absent.errors)
        self.assertEqual(absent.cleaned_data["voicemail_email_to"], "from@example.test")


class SetRecipientsCommandTests(TestCase):
    def test_fills_only_a_blank_list_and_dry_run_writes_nothing(self):
        SiteSettings.objects.filter(pk=SiteSettings.load().pk).update(voicemail_email_to="")
        call_command("set_voicemail_recipients", "--dry-run", stdout=StringIO())
        self.assertEqual(SiteSettings.load().voicemail_email_to, "")
        call_command("set_voicemail_recipients", stdout=StringIO())
        self.assertEqual(SiteSettings.load().voicemail_email_to, "from@example.test")
        SiteSettings.objects.filter(pk=SiteSettings.load().pk).update(voicemail_email_to="x@example.test")
        call_command("set_voicemail_recipients", stdout=StringIO())
        self.assertEqual(SiteSettings.load().voicemail_email_to, "x@example.test")
