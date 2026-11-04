"""Emails sent directly to staff (docs/features/office-email-chat.md, "Emails sent directly to staff"): a staff mailbox forwards to inbox+<token>@<inbound domain> and the webhook decides.
Mocked: Postmark payloads written by hand, mail goes to the in-memory outbox, push is a mock. Nothing real is sent."""
import json
from unittest import mock

from django.core import mail
from django.test import override_settings

from emailchat import direct, services, tasks
from emailchat.models import Attachment, Message, StaffSender, Thread
from emailchat.tests.test_emailchat import DOMAIN, PNG, Base, b64, inbound_post, office
from emailchat.tests.test_office_sender import SENDING, set_copy, staff
from whatsapp.models import PushSubscription

BARRY, MOISHE = "barry@staff.example.test", "moishe@staff.example.test"


def forward(token, sender="dan@client.example", to=(BARRY,), cc=(), mid="pm-d1", rfc="<d1@client.example>", headers=(), **extra):
    """What Postmark posts for mail a staff mailbox forwarded to inbox+<token>: the original To and Cc are kept."""
    full = lambda addrs: [{"Email": a, "Name": ""} for a in addrs]  # noqa: E731
    return {"OriginalRecipient": f"inbox+{token}@{DOMAIN}", "MailboxHash": token, "From": sender, "FromFull": {"Email": sender.title().lower(), "Name": "Dan Client"}, "To": ", ".join(to),
            "ToFull": full(to), "CcFull": full(cc), "Subject": "A question", "MessageID": mid, "TextBody": "Can I book Friday?",
            "Headers": [{"Name": "Message-ID", "Value": rfc}, *headers], "Attachments": [], **extra}


def header(name, value):
    return {"Name": name, "Value": value}


@override_settings(EMAIL_STAFF_GROUP_ADDRESS="staff@staff.example.test", **SENDING)
class DirectMailTests(Base):
    def setUp(self):
        super().setUp()
        self.barry, self.moishe = staff(BARRY, "Barry"), staff(MOISHE, "Moishe")
        self.tb, self.tm = (direct.ensure_token(StaffSender.objects.get_or_create(user=u)[0]) for u in (self.barry, self.moishe))
        set_copy("team@example.test")

    def post(self, payload):
        return inbound_post(payload)

    def stored(self):
        return Message.objects.filter(direction="in").exclude(direct_to="")

    def test_a_direct_mail_starts_a_thread_with_a_push_naming_both_and_no_group_copy_and_no_owner(self):
        PushSubscription.objects.create(user=self.approver, endpoint="https://push.example/1", p256dh="k", auth="a")
        attached = {"Attachments": [{"Name": "photo.png", "Content": b64(PNG), "ContentType": "image/png"}]}
        with mock.patch("whatsapp.push.webpush") as sent:
            self.assertEqual(self.post(forward(self.tb, **attached)).status_code, 200)
            self.assertEqual(self.post(forward(self.tb, **attached)).status_code, 200)  # Postmark's retry: same MessageID
            title = json.loads(sent.call_args.kwargs["data"])["title"]
        self.assertEqual(sent.call_count, 1)
        self.assertEqual(title, "To Barry: Dan Client")
        message = Message.objects.get()
        thread = message.thread
        self.assertEqual((thread.email, thread.subject, thread.direct_to, thread.direct_name, message.direct_to), ("dan@client.example", "A question", BARRY, "Barry", "Barry"))
        self.assertEqual((thread.user_id, thread.lead_email, thread.application_id), (None, "", None))  # his From is unproven: nothing is linked by it
        self.assertEqual([m for m in mail.outbox if m.extra_headers.get("X-Spa99-Group-Copy")], [])  # no copy: the app and the push are enough
        self.assertIn("no group copy", tasks.process_inbound(message.pk))
        self.assertEqual(Attachment.objects.filter(message=message).count(), 1)
        row = services.inbox_rows([thread], self.reader)[0]
        self.assertEqual((row["sent_to"], row["unread"]), ("Barry", 1))
        data = services.thread_dict(thread)
        self.assertEqual((data["sent_to"], data["sent_to_address"]), ("Barry", BARRY))
        self.assertEqual(services.message_dict(message)["direct_to"], "Barry")
        page = office(self.reader, "get", f"/email/{thread.pk}/")
        self.assertContains(page, "Sent to Barry")
        self.assertContains(office(self.reader, "get", "/email/"), "Sent to Barry")

    def test_a_reply_from_the_office_goes_to_the_sender_from_the_staff_member_with_the_token(self):
        self.post(forward(self.tb))
        thread = Thread.objects.get(direct_to=BARRY)
        self.assertEqual(self.send(thread=thread).status_code, 200)
        sent = mail.outbox[-1]
        self.assertEqual(sent.to, ["dan@client.example"])
        self.assertIn(f"reply+{thread.token}@{DOMAIN}", sent.reply_to[0])

    def test_unknown_tokens_and_mail_not_addressed_directly_store_nothing(self):
        for n, token in enumerate(("0" * 24, "nonsense", "")):
            self.assertEqual(self.post(forward(token, mid=f"u{n}")).status_code, 200)
        self.assertEqual(self.post(forward(self.tm, to=(BARRY,), mid="not-his")).status_code, 200)  # Moishe's mailbox forwarded a mail that is only to Barry (a Bcc)
        self.assertEqual(self.post(forward(self.tb, to=("someone@client.example",), mid="bcc")).status_code, 200)
        self.assertEqual(self.post({**forward(self.tb, mid="blank"), "ToFull": [], "To": "", "CcFull": []}).status_code, 200)  # the original To cannot be told
        self.assertEqual(Message.objects.count() + Thread.objects.filter(direct_to__gt="").count(), 0)

    def test_hello_the_staff_group_and_the_group_copy_address_keep_a_mail_out_but_cc_to_staff_is_fine(self):
        hello = "from@example.test"  # the site address in the test settings
        for n, other in enumerate((hello, "staff@staff.example.test", "team@example.test")):
            self.assertEqual(self.post(forward(self.tb, to=(BARRY, other), mid=f"k{n}", rfc=f"<k{n}@x>")).status_code, 200)
            self.assertEqual(self.post(forward(self.tb, to=("a@client.example",), cc=(BARRY, other), mid=f"c{n}", rfc=f"<c{n}@x>")).status_code, 200)
        self.assertEqual(self.stored().count(), 0)
        self.post(forward(self.tb, to=("a@client.example",), cc=(BARRY,), mid="cc-ok", rfc="<cc-ok@x>"))
        self.assertEqual(self.stored().count(), 1)

    def test_a_forward_that_rewrote_to_is_read_from_the_original_headers_and_without_them_it_is_not_stored(self):
        rewritten = forward(self.tb, to=(f"inbox+{self.tb}@{DOMAIN}",), mid="rw", rfc="<rw@x>", headers=[header("To", f"Barry <{BARRY}>"), header("Cc", "Other <o@client.example>")])
        self.post(rewritten)
        self.assertEqual(self.stored().count(), 1)
        hello_too = forward(self.tb, to=(f"inbox+{self.tb}@{DOMAIN}",), mid="rw2", rfc="<rw2@x>", headers=[header("To", f"{BARRY}, from@example.test")])
        self.post(hello_too)
        bare = forward(self.tb, to=(f"inbox+{self.tb}@{DOMAIN}",), mid="rw3", rfc="<rw3@x>")
        with self.assertLogs("spa99.emailchat", "WARNING") as log:
            self.post(bare)
        self.assertIn("original To could not be determined", log.output[0])
        self.assertNotIn("dan@", log.output[0])  # no personal data in the log
        self.assertEqual(self.stored().count(), 1)

    @override_settings(EMAIL_INTERNAL_DOMAIN="bml.example.test")
    def test_internal_and_automatic_mail_stays_in_outlook(self):
        for n, sender in enumerate((MOISHE, "x@staff.example.test", "boss@bml.example.test", "someone@sub.bml.example.test", "reader@example.test")):
            self.post(forward(self.tb, sender=sender, mid=f"i{n}", rfc=f"<i{n}@x>"))
        for n, extra in enumerate(({"Auto-Submitted": "auto-replied"}, {"Precedence": "bulk"}, {"List-Id": "<news.example>"}, {"X-Auto-Response-Suppress": "All"})):
            name, value = next(iter(extra.items()))
            self.post(forward(self.tb, mid=f"a{n}", rfc=f"<a{n}@x>", headers=[header(name, value)]))
        self.post(forward(self.tb, sender="mailer-daemon@client.example", mid="bounce", rfc="<b@x>"))
        self.assertEqual(self.stored().count(), 0)
        self.post(forward(self.tb, sender="dan@client.example", mid="fine", rfc="<fine@x>", headers=[header("Auto-Submitted", "no")]))
        self.assertEqual(self.stored().count(), 1)
        with override_settings(EMAIL_INTERNAL_DOMAIN=""):  # blank: no BML rule
            self.post(forward(self.tb, sender="boss@bml.example.test", mid="bml", rfc="<bml@x>"))
        self.assertEqual(self.stored().count(), 2)

    def test_the_same_email_forwarded_from_two_mailboxes_is_one_message_naming_both_staff(self):
        PushSubscription.objects.create(user=self.approver, endpoint="https://push.example/1", p256dh="k", auth="a")
        with mock.patch("whatsapp.push.webpush") as sent:
            self.post(forward(self.tb, to=(BARRY, MOISHE), mid="pm-b"))
            self.post(forward(self.tm, to=(BARRY, MOISHE), mid="pm-m"))  # another Postmark MessageID, the same Message-ID header
            self.post(forward(self.tm, to=(BARRY, MOISHE), mid="pm-m"))
        self.assertEqual((Thread.objects.count() - 1, self.stored().count(), sent.call_count), (1, 1, 1))
        self.assertEqual(self.stored().get().direct_to, "Barry, Moishe")
        self.assertEqual(services.message_dict(self.stored().get())["direct_to"], "Barry, Moishe")

    def test_a_reply_to_something_we_sent_joins_that_thread_but_the_same_subject_alone_never_does(self):
        self.send()  # an Office email in self.thread, with its own Message-ID
        ours = Message.objects.get(direction="out")
        self.assertTrue(ours.rfc_message_id)
        self.post(forward(self.tb, sender="him@example.com", mid="r1", rfc="<r1@x>", headers=[header("In-Reply-To", ours.rfc_message_id)], Subject="Re: Hello"))
        message = Message.objects.get(provider_id="r1")
        self.assertEqual((message.thread_id, message.direct_to, Thread.objects.count()), (self.thread.pk, "Barry", 1))
        self.assertEqual(self.thread.messages.count(), 2)
        self.post(forward(self.tb, sender="stranger@client.example", mid="r2", rfc="<r2@x>", Subject="Hello"))  # same subject, no header: a new thread
        self.post(forward(self.tb, sender="stranger@client.example", mid="r3", rfc="<r3@x>", headers=[header("References", "<unknown@x> <r2@x>")]))  # answers his own earlier mail: joined
        self.post(forward(self.tb, sender="other@client.example", mid="r4", rfc="<r4@x>", headers=[header("In-Reply-To", "<r2@x>")]))  # somebody else naming that id: not joined
        self.assertEqual(Thread.objects.count(), 3)
        self.assertEqual(Message.objects.get(provider_id="r3").thread.email, "stranger@client.example")
        self.assertNotEqual(Message.objects.get(provider_id="r4").thread, Message.objects.get(provider_id="r2").thread)

    def test_spam_and_failed_sender_checks_are_stored_flagged_never_pushed(self):
        PushSubscription.objects.create(user=self.approver, endpoint="https://push.example/1", p256dh="k", auth="a")
        with mock.patch("whatsapp.push.webpush") as sent:
            self.post(forward(self.tb, mid="s1", rfc="<s1@x>", sender="a@client.example", headers=[header("X-Spam-Status", "Yes, score=9")]))
            self.post(forward(self.tb, mid="s2", rfc="<s2@x>", sender="b@client.example", headers=[header("Authentication-Results", "spf=pass; dkim=fail; dmarc=fail")]))
            self.post(forward(self.tb, mid="s3", rfc="<s3@x>", sender="c@client.example", headers=[header("Received-SPF", "Fail (sender not authorised)")]))
            self.assertEqual(sent.call_count, 0)
            self.post(forward(self.tb, mid="ok1", rfc="<ok1@x>", sender="d@client.example", headers=[header("Authentication-Results", "spf=fail; dkim=pass; dmarc=pass")]))  # forwarding broke SPF only
            self.post(forward(self.tb, mid="ok2", rfc="<ok2@x>", sender="e@client.example", headers=[header("Authentication-Results", "spf=pass; dkim=pass"), header("Received-SPF", "Fail")]))
            self.assertEqual(sent.call_count, 2)
        self.assertEqual([Message.objects.get(provider_id=p).spam for p in ("s1", "s2", "s3", "ok1", "ok2")], [True, True, True, False, False])
        flagged = Message.objects.get(provider_id="s2")
        self.assertIn("sender checks", flagged.note)
        self.assertEqual(services.unread_total(self.reader), 2)  # only the two that passed count as unread
        self.assertTrue(flagged.thread.last_message_at)  # the flagged one is in the inbox so staff can see it
        self.assertEqual([m for m in mail.outbox if m.extra_headers.get("X-Spa99-Group-Copy")], [])

    def test_our_own_group_copy_and_a_failed_file_store_leave_nothing_behind(self):
        self.assertEqual(self.post(forward(self.tb, mid="loop", headers=[header("X-Spa99-Group-Copy", "1")])).status_code, 200)
        self.assertEqual(Message.objects.count(), 0)
        with mock.patch("emailchat.services.store_inbound_files", side_effect=OSError("disk")):
            self.assertEqual(self.post(forward(self.tb, mid="boom", rfc="<boom@x>")).status_code, 500)
        self.assertEqual((Message.objects.count(), Thread.objects.filter(direct_to__gt="").count()), (0, 0))  # no empty thread for the retry to repeat
        self.assertEqual(self.post(forward(self.tb, mid="boom", rfc="<boom@x>")).status_code, 200)  # Postmark's retry stores it whole
        self.assertEqual(self.stored().count(), 1)

    def test_erasing_the_sender_removes_the_thread_messages_and_files(self):
        self.post(forward(self.tb, Attachments=[{"Name": "photo.png", "Content": b64(PNG), "ContentType": "image/png"}]))
        thread = Thread.objects.get(direct_to=BARRY)
        self.assertEqual(len(services.export_for([thread])), 1)
        keys = list(Attachment.objects.values_list("key", flat=True))
        counts = services.erase_threads([thread])
        self.assertEqual((counts["email_threads"], counts["email_messages"], counts["email_files"]), (1, 1, 1))
        self.assertEqual((Thread.objects.filter(pk=thread.pk).count(), Message.objects.filter(thread_id=thread.pk).count(), Attachment.objects.filter(key__in=keys).count()), (0, 0, 0))

    def test_a_verified_account_finds_the_thread_by_its_address_and_an_unverified_one_does_not(self):
        from office.tests.test_leads import verify
        from users import services as user_services
        from users.tests.test_register import cleaned

        self.post(forward(self.tb, sender="member@client.example"))
        thread = Thread.objects.get(direct_to=BARRY)
        account = user_services.register_interest(cleaned(email="member@client.example")).user
        self.assertEqual(list(services.threads_for_person(account, ["member@client.example"])), [])  # the address is not proof until the account is verified (common.ownership)
        verify(account)
        account.refresh_from_db()
        self.assertEqual(list(services.threads_for_person(account, ["member@client.example"])), [thread])

    def test_the_inbox_token_is_made_on_save_shown_in_team_and_never_changes(self):
        from system.tests.test_system import unlocked_client
        from system.tests.test_team import at

        dev, admin = at("developer", "dev@example.com"), at("admin", "admin@example.com")
        client = unlocked_client(dev)
        url = f"/team/{admin.pk}/email/"
        self.assertContains(client.get(url), "Press Save and it appears here")
        client.post(url, {"sending_address": "", "signature": ""})
        token = StaffSender.objects.get(user=admin).inbox_token
        self.assertRegex(token, r"^[0-9a-f]{24}$")
        self.assertContains(client.get(url), f"inbox+{token}@{DOMAIN}")
        client.post(url, {"sending_address": "", "signature": "<p>x</p>"})
        self.assertEqual(StaffSender.objects.get(user=admin).inbox_token, token)
        self.assertNotEqual(token, self.tb)
        self.assertEqual(direct.inbox_address(StaffSender.objects.get(user=admin)), f"inbox+{token}@{DOMAIN}")
