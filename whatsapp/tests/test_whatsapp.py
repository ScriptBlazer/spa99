"""WhatsApp (docs/features/whatsapp.md). Mocked: no real Twilio or push call is ever made; the queue runs inline, media is in memory."""
import json
import uuid
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from common import levels, phone
from gold import services as gold_services
from gold.models import ApplicationEvent, GoldApplication
from gold.tests.test_gold import application_data
from journey import services as journey
from office.tests.test_leads import lead, verify
from office.tests.test_office import OfficeTestCase
from outreach import nextmorning
from outreach.models import NextMorningEmail
from outreach import services as outreach
from plans.tests.helpers import make_team_member
from users import services as user_services
from users.tests.test_register import cleaned
from whatsapp import formatting, push, services, signature, twilio_api
from whatsapp.models import Contact, ContactRead, Message, PushSubscription, Template, WhatsAppPrefs

User = get_user_model()
OFFICE = "office.localhost"
PUBLIC = "localhost"
SENDER = "+442045384999"
PHONE = "+447400123450"
CONFIG = dict(SITE_URL="https://spa99.uk", TWILIO_ACCOUNT_SID="ACtest", TWILIO_API_KEY_SID="SKtest", TWILIO_API_KEY_SECRET="secret", TWILIO_AUTH_TOKEN="token123", TWILIO_WHATSAPP_FROM=SENDER,
              VAPID_PUBLIC_KEY="pub", VAPID_PRIVATE_KEY="priv", VAPID_SUBJECT="mailto:hello@example.test")
PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + (640).to_bytes(4, "big") + (480).to_bytes(4, "big") + b"\x08\x02\x00\x00\x00"


def office(user, method, path, data=None, **extra):
    client = Client(HTTP_HOST=OFFICE)
    client.force_login(user)
    return getattr(client, method)(path, data or {}, **extra)


def twilio_post(path, params, token="token123", sign=True):
    url = f"https://spa99.uk{path}"
    headers = {"HTTP_X_TWILIO_SIGNATURE": signature.expected(url, sorted(params.items()), token)} if sign else {}
    return Client(HTTP_HOST=PUBLIC).post(path, params, **headers)


def inbound(body="Hello", sid="SM1", phone_=PHONE, **extra):
    return {"MessageSid": sid, "From": f"whatsapp:{phone_}", "To": f"whatsapp:{SENDER}", "Body": body, "NumMedia": "0", "ProfileName": "Daniel", **extra}


@override_settings(**CONFIG)
class Base(OfficeTestCase):
    def setUp(self):
        send = mock.patch("whatsapp.twilio_api.send_message", side_effect=lambda *a, **k: {"sid": f"SM{uuid.uuid4().hex[:24]}", "status": "queued"})
        media = mock.patch("whatsapp.twilio_api.fetch_media", side_effect=AssertionError("no real Twilio call in tests"))
        for patcher in (send, media):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.approver = make_team_member("approver@example.test", levels.OFFICE, approver=True)
        self.reader = make_team_member("reader@example.test", levels.OFFICE)
        self.contact = Contact.objects.create(phone=PHONE, name="Daniel")

    def open_window(self):
        Contact.objects.filter(pk=self.contact.pk).update(last_inbound_at=timezone.now() - timedelta(hours=1), last_message_at=timezone.now())
        self.contact.refresh_from_db()

    def template(self, status="approved", name="spa99_lead_follow_up"):
        return Template.objects.create(content_sid="HX1", name=name, approval_status=status, body="Hi {{1}}, thanks.", variables=["1"], variable_labels={"1": "First name"})


class SignatureAndWebhookTests(Base):
    def test_twilios_own_example_signature_matches(self):
        params = [("CallSid", "CA1234567890ABCDE"), ("Caller", "+12349013030"), ("Digits", "1234"), ("From", "+12349013030"), ("To", "+18005551212")]
        self.assertEqual(signature.expected("https://mycompany.com/myapp.php?foo=1&bar=2", params, "12345"), "0/KCTR6DLpKmkAf8muzZqo1nDgQ=")

    @override_settings(TWILIO_AUTH_TOKEN="")
    def test_webhooks_are_404_until_configured(self):
        self.assertEqual(twilio_post("/twilio/whatsapp/incoming/", inbound(), sign=False).status_code, 404)

    def test_bad_or_missing_signature_is_403_and_stores_nothing(self):
        self.assertEqual(twilio_post("/twilio/whatsapp/incoming/", inbound(), sign=False).status_code, 403)
        self.assertEqual(twilio_post("/twilio/whatsapp/incoming/", inbound(), token="wrong").status_code, 403)
        self.assertEqual(Message.objects.count(), 0)

    def test_incoming_stores_once_opens_the_window_and_answers_empty_twiml(self):
        with mock.patch("whatsapp.push.webpush") as sent:
            first = twilio_post("/twilio/whatsapp/incoming/", inbound("Hi there"))
            again = twilio_post("/twilio/whatsapp/incoming/", inbound("Hi there"))  # Twilio retries: same MessageSid
        self.assertEqual((first.status_code, again.status_code), (200, 200))
        self.assertIn("<Response/>", first.content.decode())
        self.assertEqual(Message.objects.filter(direction="in").count(), 1)
        self.contact.refresh_from_db()
        self.assertTrue(services.window_open(self.contact))
        self.assertEqual((self.contact.profile_name, self.contact.last_preview), ("Daniel", "Hi there"))
        self.assertEqual(sent.call_count, 0)  # nobody subscribed

    def test_messages_for_another_number_on_the_shared_account_are_ignored(self):
        twilio_post("/twilio/whatsapp/incoming/", {**inbound(), "To": "whatsapp:+442071014800"})  # BML's number
        self.assertEqual(Message.objects.count(), 0)

    def test_stop_opts_out_a_normal_reply_does_not_clear_it_and_start_does(self):
        post = lambda body, sid: twilio_post("/twilio/whatsapp/incoming/", inbound(body, sid))
        post("stop", "SM1")
        self.contact.refresh_from_db()
        self.assertTrue(self.contact.opted_out)
        post("Sorry, one more thing", "SM2")  # his message still shows, he stays opted out
        post("yes please", "SM3")
        self.contact.refresh_from_db()
        self.assertTrue(self.contact.opted_out)
        self.assertEqual(Message.objects.filter(direction="in").count(), 3)
        post("START", "SM4")
        self.contact.refresh_from_db()
        self.assertFalse(self.contact.opted_out)

    def test_status_callbacks_move_ticks_forward_only_and_record_failures(self):
        self.open_window()
        _, sent = services.send_text(self.contact, self.approver, "Hello")
        Message.objects.filter(pk=sent.pk).update(twilio_sid="SMout", status="queued")
        tick = lambda status, **extra: twilio_post("/twilio/whatsapp/status/", {"MessageSid": "SMout", "MessageStatus": status, "From": f"whatsapp:{SENDER}", **extra})
        tick("delivered")
        tick("sent")  # late: never backwards
        sent.refresh_from_db()
        self.assertEqual(sent.status, "delivered")
        tick("read")
        sent.refresh_from_db()
        self.assertEqual(sent.status, "read")
        other = Message.objects.create(contact=self.contact, direction="out", twilio_sid="SMbad", status="sent")
        twilio_post("/twilio/whatsapp/status/", {"MessageSid": "SMbad", "MessageStatus": "failed", "ErrorCode": "63016", "From": f"whatsapp:{SENDER}"})
        other.refresh_from_db()
        self.assertEqual((other.status, other.error_code), ("failed", "63016"))
        self.assertEqual(twilio_post("/twilio/whatsapp/status/", {"MessageSid": "SMnone", "MessageStatus": "sent", "From": f"whatsapp:{SENDER}"}).status_code, 200)

    def test_his_photo_is_copied_to_storage_and_a_huge_file_is_refused(self):
        with mock.patch("whatsapp.twilio_api.fetch_media", return_value=(PNG, "image/png")):
            twilio_post("/twilio/whatsapp/incoming/", inbound("", "SMimg", NumMedia="1", MediaUrl0="https://api.twilio.com/m/1", MediaContentType0="image/png"))
        photo = Message.objects.get(twilio_sid="SMimg")
        self.assertEqual((photo.kind, photo.media_width, photo.media_height, photo.media_source_url), ("image", 640, 480, ""))
        self.assertTrue(default_storage.exists(photo.media_key))
        with mock.patch("whatsapp.twilio_api.fetch_media", return_value=None):
            twilio_post("/twilio/whatsapp/incoming/", inbound("", "SMbig", NumMedia="1", MediaUrl0="https://api.twilio.com/m/2", MediaContentType0="video/mp4"))
        big = Message.objects.get(twilio_sid="SMbig")
        self.assertEqual((big.media_key, big.kind), ("", "other"))
        self.assertIn("too big", big.body)

    def test_voice_notes_and_other_files_keep_their_kind(self):
        for sid, ctype, kind in (("SMa", "audio/ogg", "audio"), ("SMv", "video/mp4", "video"), ("SMf", "application/zip", "file")):
            with mock.patch("whatsapp.twilio_api.fetch_media", return_value=(b"data", ctype)):
                twilio_post("/twilio/whatsapp/incoming/", inbound("", sid, NumMedia="1", MediaUrl0="https://api.twilio.com/m/x", MediaContentType0=ctype))
            self.assertEqual(Message.objects.get(twilio_sid=sid).kind, kind)


class SendingTests(Base):
    def twilio(self, **result):
        count = iter(range(1, 1000))  # the first send is SMnew, the next SMnew2 ...: a sid is unique on a message

        def reply(*args, **kwargs):
            n = next(count)
            return {"sid": "SMnew" if n == 1 else f"SMnew{n}", "status": "queued", **result}

        return mock.patch("whatsapp.twilio_api.send_message", side_effect=reply)

    def test_text_goes_inside_the_window_with_a_status_callback_and_is_recorded(self):
        self.open_window()
        with self.twilio() as call:
            result, message = services.send_text(self.contact, self.approver, "Hello *Daniel*")
        self.assertEqual(result, services.DONE)
        kwargs = call.call_args.kwargs
        self.assertEqual((call.call_args.args[0], kwargs["body"], kwargs["status_callback"]), (PHONE, "Hello *Daniel*", f"https://spa99.uk/twilio/whatsapp/status/?m={message.pk}"))  # the message id rides in the address
        message.refresh_from_db()
        self.assertEqual((message.twilio_sid, message.status), ("SMnew", "queued"))

    def test_free_text_needs_the_window_and_nothing_goes_after_stop(self):
        self.assertEqual(services.send_text(self.contact, self.approver, "Hello")[0], services.WINDOW_CLOSED)
        self.open_window()
        Contact.objects.filter(pk=self.contact.pk).update(opted_out_at=timezone.now())
        self.contact.refresh_from_db()
        self.assertEqual(services.send_text(self.contact, self.approver, "Hello")[0], services.OPTED_OUT)
        self.assertEqual(Message.objects.count(), 0)

    def test_limits_empty_and_double_submit(self):
        self.open_window()
        self.assertEqual(services.send_text(self.contact, self.approver, "  ")[0], services.EMPTY)
        self.assertEqual(services.send_text(self.contact, self.approver, "x" * 1601)[0], services.TOO_LONG)
        with self.twilio():
            self.assertEqual(services.send_text(self.contact, self.approver, "Once")[0], services.DONE)
            self.assertEqual(services.send_text(self.contact, self.approver, "Once")[0], services.DUPLICATE)
        self.assertEqual(Message.objects.filter(direction="out").count(), 1)

    def test_a_twilio_failure_is_recorded_with_a_plain_reason_and_only_a_retryable_one_can_be_retried(self):
        self.open_window()
        with mock.patch("whatsapp.twilio_api.send_message", side_effect=twilio_api.TwilioError("boom", code="63016", status=400)):
            _, closed = services.send_text(self.contact, self.approver, "Hello")
        closed.refresh_from_db()
        self.assertEqual((closed.status, closed.error_code), ("failed", "63016"))
        shown = services.message_dict(closed)
        self.assertEqual((shown["error"]["reason"], shown["error"]["can_retry"], shown["retry_url"]), ("Not sent. The window has closed.", False, ""))
        self.assertEqual(services.retry(closed, self.approver)[0], services.NOT_RETRYABLE)  # a retry cannot succeed: refused
        with mock.patch("whatsapp.twilio_api.send_message", side_effect=twilio_api.TwilioError("down")):  # no answer from Twilio: worth trying again
            _, lost = services.send_text(self.contact, self.approver, "Hello again")
        lost.refresh_from_db()
        self.assertEqual((lost.status, services.message_dict(lost)["error"]["can_retry"]), ("failed", True))
        with self.twilio():
            self.assertEqual(services.retry(lost, self.approver)[0], services.DONE)
        lost.refresh_from_db()
        self.assertEqual((lost.status, lost.twilio_sid, lost.error_code), ("queued", "SMnew", ""))

    def test_a_message_twilio_accepted_is_never_sent_again_and_a_double_click_sends_once(self):
        self.open_window()
        with self.twilio():
            _, taken = services.send_text(self.contact, self.approver, "Hello")
        Message.objects.filter(pk=taken.pk).update(status="failed", error_code="30008")  # failed later, by Twilio's callback: the sid is set
        taken.refresh_from_db()
        self.assertEqual(services.retry(taken, self.approver)[0], services.NOT_RETRYABLE)
        Message.objects.filter(pk=taken.pk).update(twilio_sid=None)
        taken.refresh_from_db()
        with self.twilio() as call:
            first = services.retry(taken, self.approver)
            second = services.retry(taken, self.approver)  # the double click: the status has moved on
        self.assertEqual((first[0], second[0], call.call_count), (services.DONE, services.NOT_RETRYABLE, 1))

    def test_a_message_the_queue_lost_can_be_tried_again_after_a_few_minutes_only(self):
        self.open_window()
        message = Message.objects.create(contact=self.contact, direction="out", status="queued", body="Lost", author=self.approver)
        self.assertEqual(services.message_dict(message)["error"], None)  # still within the first minutes
        Message.objects.filter(pk=message.pk).update(updated_at=timezone.now() - timedelta(minutes=10))
        message.refresh_from_db()
        shown = services.message_dict(message)
        self.assertEqual((shown["error"]["reason"], shown["error"]["can_retry"]), ("Not sent. Try again.", True))
        with self.twilio():
            self.assertEqual(services.retry(message, self.approver)[0], services.DONE)

    def test_the_worker_rechecks_stop_before_it_sends(self):
        self.open_window()
        with self.twilio() as call:
            Message.objects.all().delete()
            message = Message.objects.create(contact=self.contact, direction="out", status="queued", body="Hello")
            Contact.objects.filter(pk=self.contact.pk).update(opted_out_at=timezone.now())  # he replied STOP after it was queued
            from whatsapp import tasks
            tasks.send_message(message.pk)
        message.refresh_from_db()
        self.assertEqual((call.call_count, message.status, message.error_code), (0, "failed", "opted_out"))
        self.assertEqual(services.message_dict(message)["error"]["reason"], "Not sent. He replied STOP.")

    def test_the_worker_never_sends_a_message_twice(self):
        self.open_window()
        with self.twilio() as call:
            _, message = services.send_text(self.contact, self.approver, "Hello")
            from whatsapp import tasks
            self.assertEqual(tasks.send_message(message.pk), "skipped")
        self.assertEqual(call.call_count, 1)

    def test_only_approved_spa99_templates_are_sent_and_every_variable_is_needed(self):
        template = self.template()
        with self.twilio() as call:
            self.assertEqual(services.send_template(self.contact, self.approver, template.pk, {})[0], services.MISSING_VARIABLES)
            result, message = services.send_template(self.contact, self.approver, template.pk, {"1": " Daniel\n "})  # any time, no window
        self.assertEqual((result, message.body, message.kind), (services.DONE, "Hi Daniel, thanks.", "template"))
        self.assertEqual((call.call_args.kwargs["content_sid"], json.loads(call.call_args.kwargs["content_variables"])), ("HX1", {"1": "Daniel"}))
        bml = Template.objects.create(content_sid="HX2", name="bml_property_update", approval_status="approved", body="x", variables=[])
        pending = Template.objects.create(content_sid="HX3", name="spa99_wait", approval_status="pending", body="x", variables=[])
        self.assertEqual(services.send_template(self.contact, self.approver, bml.pk, {})[0], services.BAD_TEMPLATE)  # BML's can never go from Spa 99
        self.assertEqual(services.send_template(self.contact, self.approver, pending.pk, {})[0], services.BAD_TEMPLATE)

    def test_template_preview_has_a_span_per_variable_and_formats_safely(self):
        template = Template.objects.create(content_sid="HX9", name="spa99_x", approval_status="approved", body="*Hi* {{1}} <b>", variables=["1"], variable_labels={"1": "First name"})
        html = str(services.template_html(template))
        self.assertIn('<strong>Hi</strong> <span data-var="1" data-label="First name">[First name]</span> &lt;b&gt;', html)

    def test_photos_and_pdfs_only_checked_by_content_with_size_limits(self):
        self.open_window()
        with self.twilio():
            ok = services.send_media(self.contact, self.approver, SimpleUploadedFile("holiday.jpg", PNG + b"x", content_type="image/jpeg"), "Look")
            self.assertEqual(ok[0], services.DONE)
            self.assertEqual((ok[1].kind, ok[1].media_type, ok[1].media_width, ok[1].media_height), ("image", "image/png", 640, 480))  # the bytes decide, not the name
            self.assertEqual(services.send_media(self.contact, self.approver, SimpleUploadedFile("a.exe", b"MZ..."))[0], services.BAD_FILE)
            big = SimpleUploadedFile("a.png", PNG + b"0" * (5 * 1024 * 1024))
            self.assertEqual(services.send_media(self.contact, self.approver, big)[0], services.TOO_BIG)
            pdf = SimpleUploadedFile("guide.pdf", b"%PDF-1.4 " + b"0" * (6 * 1024 * 1024))
            self.assertEqual(services.send_media(self.contact, self.approver, pdf)[0], services.DONE)  # PDFs may be up to 16 MB

    def test_the_signed_media_link_serves_the_file_and_expires(self):
        self.open_window()
        with self.twilio() as call:
            _, message = services.send_media(self.contact, self.approver, SimpleUploadedFile("g.pdf", b"%PDF-1.4 hello"))
        url = call.call_args.kwargs["media_url"]
        self.assertTrue(url.startswith("https://spa99.uk/twilio/whatsapp/media/"))
        path = url.replace("https://spa99.uk", "")
        response = Client(HTTP_HOST=PUBLIC).get(path)
        self.assertEqual((response.status_code, response["Content-Type"]), (200, "application/pdf"))
        self.assertEqual(Client(HTTP_HOST=PUBLIC).get("/twilio/whatsapp/media/bad:token/").status_code, 404)
        with mock.patch("django.core.signing.time.time", return_value=timezone.now().timestamp() + 7200):
            self.assertEqual(Client(HTTP_HOST=PUBLIC).get(path).status_code, 404)


class TemplatesAndFormattingTests(Base):
    def test_sync_keeps_only_spa99_templates_with_approval_labels_and_keeps_edited_labels(self):
        contents = [{"sid": "HX1", "friendly_name": "spa99_lead_follow_up", "language": "en", "variables": {"1": "Alex"}, "types": {"twilio/text": {"body": "Hi {{1}}"}},
                     "approval_requests": {"whatsapp": {"status": "approved", "category": "MARKETING"}}},
                    {"sid": "HX2", "friendly_name": "bml_property_update", "types": {"twilio/text": {"body": "BML"}}, "approval_requests": {"whatsapp": {"status": "approved"}}}]
        with mock.patch("whatsapp.twilio_api.list_contents", return_value=contents):
            self.assertEqual(services.sync_templates(), {"created": 1, "updated": 0, "removed": 0})
            Template.objects.filter(content_sid="HX1").update(variable_labels={"1": "Name to greet"})
            services.sync_templates()
        row = Template.objects.get()
        self.assertEqual((row.name, row.approval_status, row.category, row.variables, row.variable_labels), ("spa99_lead_follow_up", "approved", "marketing", ["1"], {"1": "Name to greet"}))
        self.assertEqual([t.name for t in services.usable_templates()], ["spa99_lead_follow_up"])
        with mock.patch("whatsapp.twilio_api.list_contents", return_value=[]):
            self.assertEqual(services.sync_templates()["removed"], 1)
        self.assertEqual(services.usable_templates(), [])

    def test_formatting_escapes_first_then_marks_up(self):
        render = lambda text: str(formatting.render(text))
        self.assertEqual(render("<script>x</script>"), "&lt;script&gt;x&lt;/script&gt;")
        self.assertEqual(render("*b* _i_ ~s~ `c *no*`"), "<strong>b</strong> <em>i</em> <s>s</s> <code>c *no*</code>")
        self.assertEqual(render("snake_case_word 2*3*4"), "snake_case_word 2*3*4")
        self.assertEqual(render("- a\n- b"), "<ul><li>a</li><li>b</li></ul>")
        self.assertEqual(render("1. a\n2. b"), "<ol><li>a</li><li>b</li></ol>")
        self.assertEqual(render("> q\n> r"), "<blockquote>q<br>r</blockquote>")
        self.assertEqual(render("```\n*x*\n```"), "<pre>*x*</pre>")
        link = render("see https://x.com/a_b. ok")
        self.assertIn('<a href="https://x.com/a_b" target="_blank" rel="noopener noreferrer nofollow">', link)
        self.assertNotIn("<a ", render("javascript:alert(1) [x](javascript:alert(1))"))  # only http(s) and www. become links
        self.assertEqual(formatting.plain("*Hello* there\nmore"), "Hello there")


class ContactTests(Base):
    def test_numbers_find_the_lead_the_account_and_the_staff_name_wins_over_the_profile_name(self):
        session = lead("hugo@example.com")
        outreach.set_lead_contact("hugo@example.com", self.approver, first_name="Hugo", mobile="07400 123456")
        contact = services.get_or_create_contact("+447400123456", "Hugo the Great")
        self.assertEqual((contact.name, contact.profile_name, contact.lead_email, contact.display_name), ("Hugo", "Hugo the Great", "hugo@example.com", "Hugo"))
        user = user_services.register_interest(cleaned(email="acc@example.com", mobile="07400123789", first_name="Acc", last_name="Ount")).user
        self.assertIsNone(services.get_or_create_contact("+447400123789").user_id)  # an unverified account's number is unproven
        verify(user)
        linked = services.get_or_create_contact("+447400123789")
        self.assertEqual((linked.user_id, linked.name), (user.pk, "Acc Ount"))
        self.assertEqual(services.get_or_create_contact("+447400123999", "Just Profile").display_name, "Just Profile")
        self.assertTrue(session)

    def test_unread_is_per_staff_member_until_they_read(self):
        Message.objects.create(contact=self.contact, direction="in", status="received", body="Hi")
        self.assertEqual(services.unread_counts(self.approver, [self.contact.pk]), {self.contact.pk: 1})
        services.mark_read(self.contact, self.approver)
        self.assertEqual(services.unread_counts(self.approver, [self.contact.pk]), {})
        self.assertEqual(services.unread_counts(self.reader, [self.contact.pk]), {self.contact.pk: 1})
        self.assertEqual(services.unread_total(self.reader), 1)

    def test_phone_helper_and_country_list(self):
        self.assertEqual(phone.normalise("07441 919990"), "+447441919990")
        self.assertEqual(phone.normalise("7441919990", "gb"), "+447441919990")
        self.assertEqual(phone.normalise("06 12 34 56 78", "FR"), "+33612345678")
        self.assertEqual(phone.normalise("+353 87 123 4567", "GB"), "+353871234567")
        for bad in ("0207 946 0000", "12", "abc", ""):
            with self.assertRaises(Exception):
                phone.normalise(bad)
        names = [c["iso"] for c in phone.countries()]
        self.assertEqual(names[:9], ["GB", "IE", "IL", "US", "CA", "BE", "FR", "DE", "NL"])


class OfficeViewTests(Base):
    def setUp(self):
        super().setUp()
        self.open_window()
        Message.objects.create(contact=self.contact, direction="in", status="received", body="Hi from him")
        Contact.objects.filter(pk=self.contact.pk).update(last_preview="Hi from him", last_message_at=timezone.now())

    def test_read_only_people_read_but_cannot_send_and_strangers_get_nothing(self):
        self.assertEqual(office(self.reader, "get", "/whatsapp/").status_code, 200)
        self.assertEqual(office(self.reader, "get", f"/whatsapp/{self.contact.pk}/").status_code, 200)
        self.assertEqual(office(self.reader, "post", f"/whatsapp/{self.contact.pk}/send/", {"body": "x"}).status_code, 403)
        self.assertEqual(office(self.reader, "post", f"/whatsapp/{self.contact.pk}/send-template/", {}).status_code, 403)
        self.assertEqual(Client(HTTP_HOST=OFFICE).get("/whatsapp/").status_code, 302)  # not signed in
        outsider = User.objects.create_user("nobody@example.test", "x-Pass-123456")
        self.assertEqual(office(outsider, "get", "/whatsapp/").status_code, 404)

    def test_inbox_searches_by_name_and_number_shows_unread_and_pages_without_counts(self):
        page = office(self.approver, "get", "/whatsapp/?q=dan")
        self.assertEqual([r["name"] for r in page.context["rows"]], ["Daniel"])
        self.assertEqual(page.context["rows"][0]["unread"], 1)
        self.assertEqual(len(office(self.approver, "get", "/whatsapp/?q=7400123").context["rows"]), 1)
        self.assertEqual(len(office(self.approver, "get", "/whatsapp/?q=zzz").context["rows"]), 0)
        self.assertEqual(len(office(self.approver, "get", "/whatsapp/?unread=1").context["rows"]), 1)
        office(self.approver, "post", f"/whatsapp/{self.contact.pk}/read/")
        self.assertEqual(len(office(self.approver, "get", "/whatsapp/?unread=1").context["rows"]), 0)
        for i in range(31):
            Contact.objects.create(phone=f"+4477009{i:05d}", last_message_at=timezone.now())
        full = office(self.approver, "get", "/whatsapp/")
        self.assertEqual((len(full.context["rows"]), full.context["has_next"]), (30, True))

    def test_thread_pages_newest_first_and_the_poll_returns_new_messages_and_changed_ticks(self):
        for i in range(35):
            Message.objects.create(contact=self.contact, direction="in", status="received", body=f"m{i}")
        page = office(self.approver, "get", f"/whatsapp/{self.contact.pk}/")
        ctx = page.context
        self.assertEqual((len(ctx["chat_messages"]), ctx["has_older"], ctx["chat_messages"][-1]["body"]), (30, True, "m34"))  # not "messages": that is Django's own name, which the toasts read
        older = json.loads(office(self.approver, "get", ctx["older_url"]).content)
        self.assertEqual((len(older["messages"]), older["has_older"]), (6, False))
        last, cursor = ctx["last_id"], ctx["cursor"]
        out = Message.objects.create(contact=self.contact, direction="out", status="sent", body="reply", twilio_sid="SMx")
        Message.objects.filter(pk=Message.objects.filter(direction="in").first().pk).update(updated_at=timezone.now() + timedelta(seconds=5))
        answer = json.loads(office(self.approver, "get", f"/whatsapp/{self.contact.pk}/poll/", {"after": last, "since": cursor}).content)
        self.assertEqual([m["id"] for m in answer["messages"]], [out.pk])
        self.assertEqual(len(answer["updates"]), 1)
        services.apply_status({"MessageSid": "SMx", "MessageStatus": "delivered"})
        later = json.loads(office(self.approver, "get", f"/whatsapp/{self.contact.pk}/poll/", {"after": out.pk, "since": answer["cursor"]}).content)
        self.assertIn("delivered", [u["status"] for u in later["updates"]])

    def test_sending_text_media_and_template_through_the_endpoints(self):
        template = self.template()
        with mock.patch("whatsapp.twilio_api.send_message", side_effect=lambda *a, **k: {"sid": f"SM{uuid.uuid4().hex[:24]}", "status": "queued"}):
            sent = office(self.approver, "post", f"/whatsapp/{self.contact.pk}/send/", {"body": "Hello"})
            self.assertEqual((sent.status_code, json.loads(sent.content)["message"]["body"]), (200, "Hello"))
            photo = office(self.approver, "post", f"/whatsapp/{self.contact.pk}/send-media/", {"file": SimpleUploadedFile("p.png", PNG), "body": "cap"})
            self.assertEqual(json.loads(photo.content)["message"]["media"]["width"], 640)
            bad = office(self.approver, "post", f"/whatsapp/{self.contact.pk}/send-template/", {"template": str(template.pk)})
            self.assertEqual((bad.status_code, json.loads(bad.content)["missing"]), (400, ["1"]))
            ok = office(self.approver, "post", f"/whatsapp/{self.contact.pk}/send-template/", {"template": str(template.pk), "var_1": "Daniel"})
            self.assertEqual(json.loads(ok.content)["message"]["template"]["label"], "Lead follow up")
        listed = json.loads(office(self.reader, "get", f"/whatsapp/templates/?contact={self.contact.pk}").content)["templates"]
        self.assertEqual(listed[0]["variables"], [{"key": "1", "label": "First name", "prefill": "Daniel"}])
        window_closed = Contact.objects.create(phone="+447400123555", name="Closed")
        self.assertEqual(office(self.approver, "post", f"/whatsapp/{window_closed.pk}/send/", {"body": "x"}).status_code, 409)

    def test_staff_can_open_his_photo_and_others_download(self):
        key = default_storage.save("whatsapp/x/a.png", ContentFile(PNG))
        shown = Message.objects.create(contact=self.contact, direction="in", kind="image", media_key=key, media_type="image/png", media_filename="a.png", status="received")
        got = office(self.reader, "get", f"/whatsapp/media/{shown.pk}/")
        self.assertEqual((got.status_code, got["Content-Type"]), (200, "image/png"))
        self.assertNotIn("attachment", got["Content-Disposition"])
        key2 = default_storage.save("whatsapp/x/b.zip", ContentFile(b"zip"))
        zipped = Message.objects.create(contact=self.contact, direction="in", kind="file", media_key=key2, media_type="application/zip", media_filename="b.zip", status="received")
        self.assertIn("attachment", office(self.reader, "get", f"/whatsapp/media/{zipped.pk}/")["Content-Disposition"])
        self.assertEqual(Client(HTTP_HOST=OFFICE).get(f"/whatsapp/media/{shown.pk}/").status_code, 302)


class PagesAndGoldTests(Base):
    def test_lead_page_context_and_the_message_button_starts_the_chat_or_asks_for_a_mobile(self):
        session = lead("hugo@example.com")
        ctx = office(self.approver, "get", f"/leads/{session.pk}/").context
        self.assertFalse(ctx["whatsapp"]["has_mobile"])
        self.assertEqual(office(self.approver, "get", f"/leads/{session.pk}/whatsapp/").status_code, 302)  # back to the page
        outreach.set_lead_contact("hugo@example.com", self.approver, first_name="Hugo", mobile="07400 123456")
        ctx = office(self.approver, "get", f"/leads/{session.pk}/").context["whatsapp"]
        self.assertEqual((ctx["has_mobile"], ctx["can_send"], ctx["window_open"], ctx["opted_out"], ctx["unread"]), (True, True, False, False, 0))
        go = office(self.approver, "get", f"/leads/{session.pk}/whatsapp/")
        contact = Contact.objects.get(phone="+447400123456")
        self.assertEqual(go.url, f"/whatsapp/{contact.pk}/?picker=1")
        self.assertEqual(office(self.reader, "get", f"/leads/{session.pk}/").context["whatsapp"]["can_send"], False)

    def test_gold_whatsapp_marks_contacted_once_with_an_audit_event_and_respond_redirects(self):
        application, _ = gold_services.submit_application(application_data(email="dan@example.com", mobile="+447400123321"))
        go = office(self.approver, "get", f"/gold/{application.pk}/whatsapp/")
        contact = Contact.objects.get(phone="+447400123321")
        self.assertEqual(go.url, f"/whatsapp/{contact.pk}/?gold={application.pk}&picker=1")
        self.assertEqual(contact.application_id, application.pk)
        template = self.template()
        office(self.approver, "post", f"/whatsapp/{contact.pk}/send-template/", {"template": str(template.pk), "var_1": "Dan", "gold": str(application.pk)})
        office(self.approver, "post", f"/whatsapp/{contact.pk}/send-template/", {"template": str(template.pk), "var_1": "Danny", "gold": str(application.pk)})
        application.refresh_from_db()
        self.assertEqual(application.status, GoldApplication.CONTACTED)
        events = ApplicationEvent.objects.filter(application=application, action="responded")
        self.assertEqual((events.count(), events[0].to_status, events[0].meta, events[0].actor), (1, "contacted", {"whatsapp": True}, self.approver))
        self.assertEqual(office(self.approver, "get", f"/gold/{application.pk}/?do=respond").url, f"/gold/{application.pk}/whatsapp/")
        self.assertEqual(office(self.approver, "post", f"/gold/{application.pk}/respond/", {"message": "x"}).url, f"/gold/{application.pk}/whatsapp/")

    def test_staff_edit_of_a_lead_name_and_mobile_is_audited_and_refuses_a_number_that_is_taken(self):
        session = lead("hugo@example.com")
        done = office(self.approver, "post", f"/leads/{session.pk}/contact/", {"first_name": "Hugo", "mobile_country": "GB", "mobile": "07400 123456"}, HTTP_ACCEPT="application/json")
        self.assertEqual(json.loads(done.content)["result"], "done")
        self.assertEqual(office(self.reader, "post", f"/leads/{session.pk}/contact/", {"mobile": "07400 123411"}).status_code, 403)
        other = lead("other@example.com")
        taken = office(self.approver, "post", f"/leads/{other.pk}/contact/", {"mobile_country": "GB", "mobile": "07400123456"}, HTTP_ACCEPT="application/json")
        body = json.loads(taken.content)
        self.assertEqual((taken.status_code, body["errors"]["mobile"], body["errors"]["owner"]["name"]), (400, "This number is already on Hugo.", "Hugo"))
        bad = json.loads(office(self.approver, "post", f"/leads/{other.pk}/contact/", {"mobile": "123"}, HTTP_ACCEPT="application/json").content)
        self.assertEqual(bad["errors"]["mobile"], "That doesn't look like a valid mobile number.")
        labels = [e["label"] for e in office(self.reader, "get", f"/leads/{session.pk}/").context["person"]["timeline"]]
        self.assertIn(f"First name added by {self.approver.email}", labels)
        self.assertIn(f"Mobile added by {self.approver.email}", labels)

    def test_person_mobile_edit_and_timeline_lines_for_a_chat(self):
        user = user_services.register_interest(cleaned(email="acc@example.com", mobile="07400123789")).user
        verify(user)
        interest_user = User.objects.get(pk=user.pk)
        office(self.approver, "post", f"/people/{interest_user.pk}/mobile/", {"mobile_country": "GB", "mobile": "07400 123790"})
        interest_user.refresh_from_db()
        self.assertEqual(interest_user.mobile, "+447400123790")
        contact = services.get_or_create_contact("+447400123790")
        Message.objects.create(contact=contact, direction="out", status="sent", body="Hi", author_label="Moishe (m@x.test)")
        Message.objects.create(contact=contact, direction="in", status="received", body="Thanks!")
        Message.objects.create(contact=contact, direction="in", status="received", body="STOP")
        timeline = office(self.reader, "get", f"/people/{interest_user.pk}/").context["person"]["timeline"]
        labels = [e["label"] for e in timeline]
        self.assertIn("First WhatsApp sent by Moishe", labels)
        self.assertIn("WhatsApp: 2 from him, 1 from us", labels)
        self.assertIn("He replied STOP", labels)
        self.assertTrue(any(l.startswith("Mobile changed by") for l in labels))


class UiSupportTests(Base):
    """What the chat page needs on top of the first backend: inbox row extras, the no-reply filter, the manifest icons, any-country live mobile check."""

    def test_inbox_rows_carry_the_tick_gold_and_no_reply_and_the_filter_finds_them(self):
        old = services.get_or_create_contact("+447400123811")
        Message.objects.create(contact=old, direction="out", status="delivered", body="Hi", created_at=timezone.now() - timedelta(days=5))
        Contact.objects.filter(pk=old.pk).update(last_message_at=timezone.now() - timedelta(days=5), last_direction="out", last_preview="Hi", last_kind="text")
        rows = office(self.reader, "get", "/whatsapp/").context["rows"]
        row = next(r for r in rows if r["id"] == str(old.pk))
        self.assertEqual((row["status"], row["no_reply"], row["gold"]), ("delivered", True, False))
        found = office(self.reader, "get", "/whatsapp/?noreply=1").context["rows"]
        self.assertEqual([r["id"] for r in found], [str(old.pk)])

    def test_the_thread_page_does_not_put_chat_messages_where_the_toasts_read(self):
        self.open_window()
        Message.objects.create(contact=self.contact, direction="in", status="received", body="Secret text")
        page = office(self.reader, "get", f"/whatsapp/{self.contact.pk}/")
        self.assertNotIn("data-server-messages", page.content.decode())
        self.assertEqual(page.context["wa"]["messages"][-1]["body"], "Secret text")

    def test_the_manifest_lists_the_app_icons(self):
        icons = json.loads(Client(HTTP_HOST=OFFICE).get("/manifest.webmanifest").content)["icons"]
        self.assertEqual({(i["sizes"], i["purpose"]) for i in icons}, {("192x192", "any"), ("512x512", "any"), ("512x512", "maskable")})
        self.assertTrue(all(i["src"].startswith("/static/") and i["src"].endswith(".png") for i in icons))

    def test_the_live_mobile_check_takes_a_country_and_gold_stays_uk_only(self):
        client = Client(HTTP_HOST=PUBLIC)
        self.assertTrue(json.loads(client.post("/validate/mobile/", {"mobile": "6 12 34 56 78", "mobile_country": "FR"}).content)["valid"])
        self.assertFalse(json.loads(client.post("/validate/mobile/", {"mobile": "6 12 34 56 78"}).content)["valid"])  # no country: the UK rules, as Gold uses


class PushAndPwaTests(Base):
    def subscribe(self, user, endpoint="https://push.example.test/abc"):
        return office(user, "post", "/whatsapp/push/subscribe/", json.dumps({"endpoint": endpoint, "keys": {"p256dh": "k", "auth": "a"}}), content_type="application/json")

    def test_subscribe_unsubscribe_mute_and_the_config_for_the_frontend(self):
        self.assertEqual(self.subscribe(self.reader).status_code, 200)
        self.subscribe(self.reader)  # again: still one device
        config = json.loads(office(self.reader, "get", "/whatsapp/push/config/").content)
        self.assertEqual((config["configured"], config["vapid_public_key"], config["muted"], config["devices"]), (True, "pub", False, 1))
        self.assertEqual(office(self.reader, "post", "/whatsapp/push/subscribe/", json.dumps({"endpoint": "http://x", "keys": {}}), content_type="application/json").status_code, 400)
        office(self.reader, "post", "/whatsapp/push/mute/", json.dumps({"muted": True}), content_type="application/json")
        self.assertTrue(WhatsAppPrefs.objects.get(user=self.reader).muted)
        office(self.reader, "post", "/whatsapp/push/unsubscribe/", json.dumps({"endpoint": "https://push.example.test/abc"}), content_type="application/json")
        self.assertEqual(PushSubscription.objects.count(), 0)

    def test_an_inbound_message_pushes_to_unmuted_staff_and_dead_devices_are_removed(self):
        self.subscribe(self.reader, "https://push.example.test/reader")
        self.subscribe(self.approver, "https://push.example.test/approver")
        gone = PushSubscription.objects.create(user=self.approver, endpoint="https://push.example.test/dead", p256dh="k", auth="a")
        WhatsAppPrefs.objects.create(user=self.reader, muted=True)

        def fake(subscription_info, **kwargs):
            if subscription_info["endpoint"].endswith("dead"):
                error = push.WebPushException("gone")
                error.response = mock.Mock(status_code=410)
                raise error
            return mock.Mock()

        with mock.patch("whatsapp.push.webpush", side_effect=fake) as sent:
            twilio_post("/twilio/whatsapp/incoming/", inbound("*Hello* there", "SMp"))
        endpoints = sorted(c.kwargs["subscription_info"]["endpoint"] for c in sent.call_args_list)
        self.assertEqual(endpoints, ["https://push.example.test/approver", "https://push.example.test/dead"])  # the muted one gets nothing
        payload = json.loads(sent.call_args_list[0].kwargs["data"])
        self.assertEqual((payload["title"], payload["body"], payload["tag"]), ("Daniel", "Hello there", str(self.contact.pk)))
        self.assertTrue(payload["url"].startswith("/whatsapp/"))
        self.assertFalse(PushSubscription.objects.filter(pk=gone.pk).exists())

    def test_the_manifest_and_service_worker_exist_on_the_office_host_only(self):
        office_client, public = Client(HTTP_HOST=OFFICE), Client(HTTP_HOST=PUBLIC)
        manifest = office_client.get("/manifest.webmanifest")  # public file: the browser fetches it without cookies
        self.assertEqual((manifest.status_code, json.loads(manifest.content)["scope"]), (200, "/"))
        worker = office_client.get("/sw.js")
        self.assertEqual((worker.status_code, worker["Service-Worker-Allowed"], "no-cache" in worker["Cache-Control"]), (200, "/", True))
        for host_name in (PUBLIC, "control.localhost", "system.localhost"):
            for path in ("/manifest.webmanifest", "/sw.js"):
                self.assertEqual(Client(HTTP_HOST=host_name).get(path).status_code, 404, (host_name, path))
        self.assertNotIn("manifest", public.get("/").content.decode())


class ErasureAndSystemTests(Base):
    def make_chat(self, phone_):
        contact = services.get_or_create_contact(phone_)
        key = default_storage.save("whatsapp/e/p.png", ContentFile(PNG))
        Message.objects.create(contact=contact, direction="in", kind="image", media_key=key, status="received", body="hi")
        return contact, key

    def test_deleting_a_person_removes_his_chat_messages_and_files_and_export_includes_them(self):
        user = user_services.register_interest(cleaned(email="acc@example.com", mobile="07400123789")).user
        verify(user)
        contact, key = self.make_chat("+447400123789")
        exported = user_services.export_user_data(user, include_chats=True)["whatsapp"]
        self.assertEqual((exported[0]["phone"], exported[0]["messages"][0]["text"]), ("+447400123789", "hi"))
        user_services.delete_user_data(user, include_chats=True)
        self.assertFalse(Contact.objects.filter(pk=contact.pk).exists())
        self.assertEqual(Message.objects.filter(contact_id=contact.pk).count(), 0)
        self.assertFalse(default_storage.exists(key))
        self.assertTrue(Contact.objects.filter(pk=self.contact.pk).exists())  # someone else's chat stays

    def test_deleting_a_lead_removes_his_chat(self):
        admin = make_team_member("admin@example.test", levels.ADMIN)
        session = lead("hugo@example.com")
        outreach.set_lead_contact("hugo@example.com", admin, mobile="07400 123456")
        contact, key = self.make_chat("+447400123456")
        export = json.loads(office(admin, "get", f"/leads/{session.pk}/export/").content)
        self.assertEqual(export["whatsapp"][0]["phone"], "+447400123456")
        office(admin, "post", f"/leads/{session.pk}/delete/")
        self.assertFalse(Contact.objects.filter(pk=contact.pk).exists())
        self.assertFalse(default_storage.exists(key))

    def test_system_page_check_and_sync_are_mocked_and_never_show_secrets(self):
        from system.tests.test_system import make_user, unlocked_client

        client = unlocked_client(make_user("dev@example.com"))
        page = client.get("/whatsapp/")
        self.assertContains(page, "https://spa99.uk/twilio/whatsapp/incoming/")
        self.assertNotContains(page, "token123")
        self.assertNotContains(page, "secret")
        with mock.patch("whatsapp.twilio_api.sender_status", return_value={"found": True, "status": "ONLINE", "name": "Spa 99", "quality": ""}) as senders:
            client.post("/whatsapp/check/")  # through the Senders API only: a Standard API key cannot read Accounts
        self.assertEqual(senders.call_count, 1)
        self.assertFalse(hasattr(twilio_api, "account"))
        self.assertContains(client.get("/whatsapp/"), "Spa 99: Online")
        contents = [{"sid": "HX1", "friendly_name": "spa99_a", "types": {"twilio/text": {"body": "Hi"}}, "approval_requests": {"whatsapp": {"status": "approved"}}}]
        with mock.patch("whatsapp.twilio_api.list_contents", return_value=contents):
            client.post("/whatsapp/sync/")
        self.assertEqual(Template.objects.get().name, "spa99_a")
        with override_settings(TWILIO_AUTH_TOKEN=""):
            self.assertFalse(services.check_twilio()["ok"])
        self.assertEqual(Client(HTTP_HOST="system.localhost").get("/whatsapp/").status_code, 404)  # a stranger gets nothing


class GateTests(Base):
    def test_the_email_step_takes_name_email_and_mobile_and_reports_every_field_error(self):
        client = Client(HTTP_HOST=PUBLIC, enforce_csrf_checks=False)
        client.get("/journey/state/")
        post = lambda data: client.post("/journey/lead/", json.dumps(data), content_type="application/json")
        bad = post({"first_name": "", "email": "nope", "mobile": "123", "consent": False})
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(sorted(bad.json()["errors"]), ["consent", "email", "first_name", "mobile"])
        ok = post({"first_name": "  Hugo ", "email": "Hugo@Example.com", "mobile_country": "FR", "mobile": "06 12 34 56 78", "consent": True})
        self.assertEqual(ok.status_code, 200)
        from journey.models import JourneySession
        row = JourneySession.objects.get(lead_email="hugo@example.com")
        self.assertEqual((row.lead_first_name, row.lead_mobile, row.lead_consent_version), ("Hugo", "+33612345678", journey.CONSENT_VERSION))

    def test_leads_show_name_and_mobile_search_matches_them_the_csv_has_them_and_a_restart_carries_them(self):
        from journey.models import JourneySession
        session = lead("hugo@example.com")
        outreach.set_lead_contact("hugo@example.com", self.approver, first_name="Hugo", mobile="07400 123456")
        admin = make_team_member("admin@example.test", levels.ADMIN)
        rows = lambda q: office(admin, "get", "/leads/", {"q": q}).context["rows"]
        self.assertEqual((rows("hug")[0]["name"], rows("hug")[0]["mobile"]), ("Hugo", "+447400123456"))
        self.assertEqual(len(rows("07400 123456")), 1)
        self.assertEqual(len(rows("7400123")), 1)
        self.assertEqual(len(rows("nobody")), 0)
        csv_text = office(admin, "get", "/leads/export.csv").content.decode()
        self.assertIn("email,first_name,mobile", csv_text.splitlines()[0])
        self.assertIn("hugo@example.com,Hugo,'+447400123456", csv_text)  # the sheet's formula guard puts an apostrophe before a leading +
        fresh = journey.create_session("Mozilla/5.0", previous=JourneySession.objects.get(pk=session.pk))
        self.assertEqual((fresh.lead_first_name, fresh.lead_mobile), ("Hugo", "+447400123456"))
        alone = journey.create_session("Mozilla/5.0", previous=None)
        self.assertEqual((alone.lead_first_name, alone.lead_mobile), ("", ""))  # "Not you?"

    def test_register_is_prefilled_from_the_gate_and_the_next_morning_email_uses_the_first_name(self):
        from outreach import nextmorning
        session = lead("hugo@example.com")
        outreach.set_lead_contact("hugo@example.com", self.approver, first_name="Hugo", mobile="07400 123456")
        self.assertEqual(nextmorning._first_name("hugo@example.com"), "Hugo")
        client = Client(HTTP_HOST=PUBLIC)
        client.cookies[journey.COOKIE_NAME] = session.key
        form = client.get("/register/").context["form"]
        self.assertEqual((form.initial["first_name"], form.initial["mobile"], form.initial["mobile_country"]), ("Hugo", "07400 123456", "GB"))


class ReviewFixTests(Base):
    """The review of 2026-11-04: numbers are unproven, links go stale, rollback, small hardening."""

    def lead_chat(self, mobile="07400 123456", email="hugo@example.com"):
        lead(email)
        outreach.set_lead_contact(email, self.approver, first_name="Hugo", mobile=mobile)
        contact = services.get_or_create_contact(phone.normalise(mobile))
        Message.objects.create(contact=contact, direction="in", status="received", body="Private words from Hugo")
        return contact

    def test_an_account_with_a_leads_number_cannot_export_or_erase_his_chat_but_staff_can(self):
        chat = self.lead_chat()
        probe = user_services.register_interest(cleaned(email="probe@example.com", mobile="07400 123456", first_name="Probe")).user  # nobody proved this number is his
        verify(probe)
        probe.set_password("a-Long-pass-123")
        probe.save()
        client = Client(HTTP_HOST=PUBLIC)
        client.force_login(probe)
        exported = client.get("/account/export/")
        self.assertNotIn("whatsapp", json.loads(exported.content))
        self.assertNotIn(b"Private words", exported.content)
        self.assertNotIn("whatsapp", user_services.export_user_data(probe))  # the service default is the safe one
        client.post("/account/delete/", {"password": "a-Long-pass-123"})
        self.assertFalse(User.objects.filter(pk=probe.pk).exists())
        self.assertTrue(Contact.objects.filter(pk=chat.pk).exists())  # his own deletion never reaches Hugo's chat
        self.assertEqual(Message.objects.filter(contact=chat).count(), 1)
        other = user_services.register_interest(cleaned(email="staffcase@example.com", mobile="07400 123456", first_name="Other")).user
        self.assertEqual(user_services.export_user_data(other, include_chats=True)["whatsapp"], [])  # staff-run too: an unverified account's number proves nothing
        user_services.delete_user_data(other, include_chats=True)
        self.assertTrue(Contact.objects.filter(pk=chat.pk).exists())  # staff erasure of the account never deletes the lead's chat

    def test_an_old_page_posting_only_the_email_is_told_to_refresh_and_odd_input_is_refused(self):
        client = Client(HTTP_HOST=PUBLIC)
        client.get("/journey/state/")
        post = lambda data: client.post("/journey/lead/", json.dumps(data), content_type="application/json")
        old = post({"email": "a@example.com", "consent": True})
        self.assertEqual((old.status_code, old.json()["errors"]["email"]), (400, "Please refresh the page and try again."))
        self.assertEqual(post({"email": 12345, "first_name": "A", "mobile": "07400 123450", "consent": True}).status_code, 400)  # not a 500
        self.assertEqual(post({"email": ["a@example.com"], "first_name": "A", "mobile": "07400 123450", "consent": True}).status_code, 400)
        for bad in ("see http://spam.example", "<b>Hugo</b>", "a" * 101):
            self.assertIn("first_name", post({"first_name": bad, "email": "a@example.com", "mobile": "07400 123450", "consent": True}).json()["errors"])

    def test_the_consent_version_is_kept_when_the_chat_saves_the_same_email_again(self):
        session = journey.create_session("Mozilla/5.0")
        journey.save_lead(session, "a@example.com", True, first_name="A", mobile="07400 123450", require_details=True)
        journey.save_lead(session, "a@example.com", True)  # the Ask us chat: email only
        session.refresh_from_db()
        self.assertEqual((session.lead_consent_version, session.lead_first_name, session.lead_mobile), (journey.CONSENT_VERSION, "A", "+447400123450"))

    def test_he_writes_first_then_applies_for_gold_and_the_chat_finds_the_application(self):
        twilio_post("/twilio/whatsapp/incoming/", inbound("Hello", "SMfirst", phone_="+447400123321"))
        contact = Contact.objects.get(phone="+447400123321")
        self.assertIsNone(contact.application_id)
        application, _ = gold_services.submit_application(application_data(email="dan@example.com", mobile="+447400123321"))
        contact.refresh_from_db()
        self.assertEqual((contact.application_id, contact.name), (application.pk, application.full_name))
        go = office(self.approver, "get", f"/gold/{application.pk}/whatsapp/")
        self.assertEqual(go.url, f"/whatsapp/{contact.pk}/?gold={application.pk}")
        template = self.template()
        office(self.approver, "post", f"/whatsapp/{contact.pk}/send-template/", {"template": str(template.pk), "var_1": "Dan", "gold": str(application.pk)})
        application.refresh_from_db()
        self.assertEqual(application.status, GoldApplication.CONTACTED)

    def test_he_writes_first_then_registers_or_becomes_a_lead_and_the_links_follow(self):
        twilio_post("/twilio/whatsapp/incoming/", inbound("Hi", "SMa", phone_="+447400123789"))
        twilio_post("/twilio/whatsapp/incoming/", inbound("Hi", "SMb", phone_="+447400123790"))
        user = user_services.register_interest(cleaned(email="acc@example.com", mobile="07400 123789", first_name="Acc", last_name="Ount")).user
        self.assertIsNone(Contact.objects.get(phone="+447400123789").user_id)  # not until the address is verified
        verify(user)
        self.assertEqual(Contact.objects.get(phone="+447400123789").user_id, user.pk)
        session = journey.create_session("Mozilla/5.0")
        journey.save_lead(session, "lead@example.com", True, first_name="Leo", mobile="07400 123790", require_details=True)
        linked = Contact.objects.get(phone="+447400123790")
        self.assertEqual((linked.lead_email, linked.name), ("lead@example.com", "Leo"))

    def test_changing_a_mobile_keeps_the_old_chat_findable_for_erasure(self):
        chat = self.lead_chat("07400 123456", "hugo@example.com")
        session = journey.JourneySession.objects.get(lead_email="hugo@example.com")
        self.assertEqual(outreach.set_lead_contact("hugo@example.com", self.approver, mobile="07400 123499")[0], outreach.DONE)
        chat.refresh_from_db()
        self.assertEqual(chat.lead_email, "hugo@example.com")  # the stored owner link stays
        self.assertEqual(list(services.contacts_for_person(None, {"hugo@example.com"}, services.person_phones(None, {"hugo@example.com"}))), [chat])
        admin = make_team_member("admin@example.test", levels.ADMIN)
        office(admin, "post", f"/leads/{session.pk}/delete/")
        self.assertFalse(Contact.objects.filter(pk=chat.pk).exists())  # the old chat went with him

    def test_correcting_the_email_relinks_his_chat_and_moves_his_ask_us_chat_and_clears_the_old_mails(self):
        from chat.models import Conversation
        from notifications.models import EmailLog

        chat = self.lead_chat("07400 123456", "typo@example.com")
        conversation = Conversation.objects.create(lead_email="typo@example.com")
        EmailLog.objects.create(to="typo@example.com", template="lead_next_morning", subject="Hi", status="bounced")
        self.assertEqual(outreach.correct_lead_email("typo@example.com", "fixed@example.com", self.approver)[0], outreach.DONE)
        chat.refresh_from_db()
        conversation.refresh_from_db()
        self.assertEqual((chat.lead_email, conversation.lead_email), ("fixed@example.com", "fixed@example.com"))
        self.assertFalse(EmailLog.objects.filter(to="typo@example.com").exists())

    def test_the_resend_has_one_winner(self):
        lead("fixed@example.com")
        from plans.models import SiteSettings
        SiteSettings.objects.update(auto_email_from_address="barry@spa99.test", auto_email_from_name="Barry")
        from django.core import mail
        results = []
        real = nextmorning.send_one
        with mock.patch.object(nextmorning, "send_one", side_effect=lambda *a, **k: results.append(1) or real(*a, **k)):
            first = outreach.resend_follow_up("fixed@example.com", self.approver)
            second = outreach.resend_follow_up("fixed@example.com", self.approver)
        self.assertEqual((first[0], second[0], len(results), len(mail.outbox)), (outreach.SENT, outreach.ALREADY, 1, 1))
        # a worker takes the row between the read and the claim: the conditional update on claimed_at loses, so nothing is sent
        row = NextMorningEmail.objects.get()
        NextMorningEmail.objects.filter(pk=row.pk).update(sent_at=None, skipped_at=timezone.now(), claimed_at=timezone.now() - timedelta(minutes=1))
        original = NextMorningEmail.objects.filter

        def worker_wins(*args, **kwargs):
            original(pk=row.pk).update(claimed_at=timezone.now())
            return original(*args, **kwargs)

        results.clear()
        with mock.patch.object(NextMorningEmail.objects, "filter", side_effect=worker_wins), mock.patch.object(nextmorning, "send_one", side_effect=lambda *a, **k: results.append(1)):
            self.assertEqual(outreach.resend_follow_up("fixed@example.com", self.approver)[0], outreach.ALREADY)
        self.assertEqual(results, [])

    def test_the_approval_may_sit_on_the_content_or_under_whatsapp(self):
        flat = {"sid": "HX1", "friendly_name": "spa99_flat", "types": {"twilio/text": {"body": "Hi"}}, "approval_requests": {"status": "approved", "category": "UTILITY"}}
        with mock.patch("whatsapp.twilio_api.list_contents", return_value=[flat]):
            services.sync_templates()
        self.assertEqual((Template.objects.get().approval_status, Template.objects.get().category), ("approved", "utility"))

    def test_push_calls_time_out(self):
        PushSubscription.objects.create(user=self.approver, endpoint="https://push.example.test/x", p256dh="k", auth="a")
        with mock.patch("whatsapp.push.webpush") as sent:
            twilio_post("/twilio/whatsapp/incoming/", inbound("Hi", "SMt"))
        self.assertEqual(sent.call_args.kwargs["timeout"], 10)

    def test_odd_ids_are_not_a_500_and_a_00_prefix_is_international(self):
        self.assertEqual(office(self.approver, "get", "/whatsapp/templates/?contact=not-a-uuid").status_code, 200)
        self.open_window()
        self.assertEqual(services.send_template(self.contact, self.approver, "not-a-uuid", {})[0], services.BAD_TEMPLATE)
        self.assertEqual(phone.normalise("0033 6 12 34 56 78", "GB"), "+33612345678")
        self.assertEqual(phone.normalise("0044 7400 123456", "FR"), "+447400123456")

    def test_a_storage_failure_on_his_file_does_not_lose_the_message_or_the_push(self):
        with mock.patch("whatsapp.twilio_api.fetch_media", return_value=(PNG, "image/png")), mock.patch("whatsapp.services.default_storage.save", side_effect=OSError("disk")), \
                mock.patch("whatsapp.push.webpush") as sent:
            PushSubscription.objects.create(user=self.approver, endpoint="https://push.example.test/y", p256dh="k", auth="a")
            twilio_post("/twilio/whatsapp/incoming/", inbound("", "SMimg2", NumMedia="1", MediaUrl0="https://api.twilio.com/m/9", MediaContentType0="image/png"))
        message = Message.objects.get(twilio_sid="SMimg2")
        self.assertEqual((message.kind, message.media_key, sent.call_count), ("other", "", 1))

    def test_links_never_carry_a_quote_or_a_backtick_and_the_fuzz_finds_no_unsafe_html(self):
        import random
        import re
        from html.parser import HTMLParser

        self.assertIn('<a href="https://x.com/a" ', str(formatting.render('"https://x.com/a"')))
        self.assertNotIn("&quot;", re.search(r'href="([^"]*)"', str(formatting.render('"https://x.com/a"'))).group(1))
        self.assertIn("<code>https://y.com</code>", str(formatting.render("`https://y.com`")))
        ok_tags = {"a", "strong", "em", "s", "code", "pre", "ul", "ol", "li", "blockquote", "br"}
        bad = []

        class Check(HTMLParser):
            def handle_starttag(self, tag, attrs):
                if tag not in ok_tags:
                    bad.append(tag)
                elif tag == "a":
                    found = dict(attrs)
                    if set(found) != {"href", "target", "rel"} or not re.fullmatch(r"https?://[^\s<>\"'`]*", found["href"]):
                        bad.append(found)
                elif attrs:
                    bad.append(attrs)

        random.seed(11)
        alphabet = list("*_~`<>\"'&/:.-#() \n\\") + ["http://", "https://", "www.", "```", "> ", "- ", "1. ", "javascript:", "onmouseover=", "<script>", "&lt;", "", "", "a"]
        for _ in range(3000):
            text = "".join(random.choice(alphabet) for _ in range(random.randint(1, 40)))
            html_out = str(formatting.render(text))
            Check().feed(html_out)
            self.assertFalse(bad, (text, html_out, bad))
            self.assertTrue("" not in html_out and "" not in html_out and "<script" not in html_out.lower(), (text, html_out))

    def test_the_gold_form_takes_a_non_uk_number_with_the_country_select(self):
        from gold.forms import GoldApplicationForm

        form = GoldApplicationForm({"mobile": "06 12 34 56 78", "mobile_country": "FR"})
        form.is_valid()
        self.assertEqual(form.cleaned_data["mobile"], "+33612345678")
        form = GoldApplicationForm({"mobile": "07400 123450"})  # no country: the UK, a leading 0 dropped
        form.is_valid()
        self.assertEqual(form.cleaned_data["mobile"], "+447400123450")
        form = GoldApplicationForm({"mobile": "123"})
        form.is_valid()
        self.assertIn("mobile", form.errors)
