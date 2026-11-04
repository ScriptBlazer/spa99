"""Sticky notes (one set per person), the guide, the approach list and Message. Mocked: sync queue, in-memory media and mail."""
from io import StringIO
from unittest import mock

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import Client, override_settings
from django.utils import timezone

from common import levels
from gold import actions as gold_actions
from gold import audit, services as gold_services
from gold.models import ApplicationEvent
from gold.tests.test_gold import application_data
from mailings import optout
from office.tests.test_leads import lead, verify
from office.tests.test_office import OFFICE, OfficeTestCase, staff
from outreach import people, services
from outreach.models import OutreachEntry, PersonMessage, StickyNote
from plans.models import SiteSettings
from plans.tests.helpers import make_team_member
from users import services as user_services
from users.tests.test_register import cleaned


def call(user, method, path, data=None, **extra):
    client = Client(HTTP_HOST=OFFICE)
    client.force_login(user)
    return getattr(client, method)(path, data or {}, **extra)


class Base(OfficeTestCase):
    def setUp(self):
        self.approver = make_team_member("approver@example.test", levels.OFFICE, approver=True)
        self.reader = make_team_member("reader@example.test", levels.OFFICE)
        self.admin = make_team_member("admin@example.test", levels.ADMIN)

    def application(self, **over):
        application, _ = gold_services.submit_application(application_data(**over))
        mail.outbox.clear()
        return application


class StickyNoteTests(Base):
    def test_unverified_accounts_do_not_merge_journey_addresses_and_erasure_clears_all_addresses(self):
        lead("other@example.com")
        user = user_services.register_interest(cleaned(email="acc@example.com")).user
        from journey.models import JourneySession
        JourneySession.objects.filter(lead_email="other@example.com").update(user=user)
        self.assertEqual(people.resolve(user=user)[1], {"acc@example.com"})  # not verified
        User = type(user)
        User.objects.filter(pk=user.pk).update(email_verified_at=timezone.now())
        user.refresh_from_db()
        self.assertEqual(people.resolve(user=user)[1], {"acc@example.com", "other@example.com"})
        application = self.application(email="gold@example.com")
        type(application).objects.filter(pk=application.pk).update(user=user)
        StickyNote.objects.create(email="gold@example.com", text="n1")
        StickyNote.objects.create(email="other@example.com", text="n2")
        user_services.delete_user_data(user)
        self.assertEqual(StickyNote.objects.count(), 0)

    def test_old_gold_notes_stay_visible_until_copied_and_long_ones_copy_in_full(self):
        application = self.application(email="dan@example.com")
        long = "x" * 2000
        audit.record(application, "note_added", actor=self.approver, channel="office", message=long)
        labels = lambda: [h["label"] for h in call(self.reader, "get", f"/gold/{application.pk}/").context["application"]["events"]]
        self.assertIn("Note added", labels())
        call_command("backfill_sticky_notes", stdout=StringIO())
        self.assertEqual(StickyNote.objects.get().text, long)
        self.assertNotIn("Note added", labels())

    def test_notes_follow_the_person_across_lead_person_and_gold_pages(self):
        session = lead("hugo@example.com")
        application = self.application(email="hugo@example.com")
        self.assertEqual(call(self.approver, "post", f"/leads/{session.pk}/notes/add/", {"note": "Call him Monday"}).status_code, 302)
        self.assertContains(call(self.reader, "get", f"/gold/{application.pk}/"), "Call him Monday")  # same address on the Gold page
        user = user_services.register_interest(cleaned(email="hugo@example.com")).user
        verify(user)
        page = call(self.reader, "get", f"/people/{user.pk}/")
        self.assertContains(page, "Call him Monday")  # carried over when he registered
        self.assertEqual(page.context["notes_count"], 1)
        call(self.admin, "post", f"/people/{user.pk}/notes/add/", {"note": "Now a member"})
        self.assertEqual(StickyNote.objects.get(text="Now a member").email, "hugo@example.com")  # the account email is the main address

    def test_delete_is_soft_and_leaves_history_in_gold_and_the_timeline(self):
        application = self.application(email="dan@example.com")
        call(self.approver, "post", f"/gold/{application.pk}/notes/add/", {"note": "Owns 12 flats"})
        note = StickyNote.objects.get()
        self.assertEqual(ApplicationEvent.objects.filter(action="note_added").count(), 0)  # adding is not a history line
        response = call(self.approver, "post", f"/gold/{application.pk}/notes/{note.pk}/delete/", HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "office/_notes.html")
        note.refresh_from_db()
        self.assertIsNotNone(note.deleted_at)
        event = ApplicationEvent.objects.get(action="note_deleted")
        self.assertEqual((event.message, event.actor), ("Owns 12 flats", self.approver))
        self.assertNotContains(call(self.reader, "get", f"/gold/{application.pk}/"), 'data-note="')
        self.assertEqual(services.delete_note(note, self.approver), services.MISSING)  # twice does nothing
        entries = services.timeline_entries(["dan@example.com"])
        self.assertEqual([(k, d) for _, k, _, d, _n in entries], [("note_deleted", "Owns 12 flats")])

    def test_permissions_duplicates_and_limits(self):
        session = lead("a@example.com")
        url = f"/leads/{session.pk}/notes/add/"
        self.assertEqual(call(self.reader, "post", url, {"note": "x"}).status_code, 403)
        call(self.approver, "post", url, {"note": "Same"})
        call(self.approver, "post", url, {"note": "Same"})
        self.assertEqual(StickyNote.objects.count(), 1)
        self.assertEqual(call(self.approver, "post", url, {"note": "y" * 1001}, HTTP_HX_REQUEST="true").status_code, 400)
        self.assertEqual(call(self.admin, "post", url, {"note": "Admin may"}).status_code, 302)
        note = StickyNote.objects.get(text="Same")
        self.assertEqual(call(self.reader, "post", f"/leads/{session.pk}/notes/{note.pk}/delete/").status_code, 403)  # view-only
        other = StickyNote.objects.create(email="someone@else.com", text="not his")
        self.assertEqual(call(self.admin, "post", f"/leads/{session.pk}/notes/{other.pk}/delete/").status_code, 404)  # only this person's notes

    def test_backfill_copies_gold_notes_once_with_a_dry_run(self):
        application = self.application(email="dan@example.com")
        audit.record(application, "note_added", actor=self.approver, channel="office", message="Phone: owns 12 flats")
        out = StringIO()
        call_command("backfill_sticky_notes", "--dry-run", stdout=out)
        self.assertIn("Phone: owns 12 flats", out.getvalue())
        self.assertEqual(StickyNote.objects.count(), 0)
        call_command("backfill_sticky_notes", stdout=StringIO())
        call_command("backfill_sticky_notes", stdout=StringIO())
        note = StickyNote.objects.get()
        self.assertEqual((note.email, note.text, note.author), ("dan@example.com", "Phone: owns 12 flats", self.approver))
        page = call(self.reader, "get", f"/gold/{application.pk}/")
        self.assertNotIn("Note added", [h["label"] for h in page.context["application"]["events"]])  # old lines are hidden


class GuideTests(Base):
    def upload(self, name="guide.pdf", body=b"%PDF-1.4 test"):
        site = SiteSettings.load()
        site.gold_guide = SimpleUploadedFile(name, body, content_type="application/pdf")
        site.save()

    def test_send_guide_attaches_the_pdf_once_from_the_site_sender(self):
        application = self.application()
        self.assertEqual(gold_actions.send_guide(application, self.approver)[0], gold_actions.NO_GUIDE)
        self.upload()
        self.assertEqual(call(self.approver, "post", f"/gold/{application.pk}/send-guide/").status_code, 302)
        call(self.approver, "post", f"/gold/{application.pk}/send-guide/")  # double submit
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual((message.to, message.from_email, message.reply_to, message.extra_headers.get("X-PM-Tag")),
                         (["dan@example.com"], "Spa 99 <from@example.test>", [SiteSettings.load().contact_address], "gold-guide"))
        self.assertEqual(message.attachments[0][2], "application/pdf")
        self.assertEqual(ApplicationEvent.objects.filter(action="guide_sent").count(), 1)
        self.assertEqual(call(self.reader, "post", f"/gold/{application.pk}/send-guide/").status_code, 403)

    def test_only_pdfs_up_to_the_limit(self):
        from django.core.exceptions import ValidationError
        from common.validators import validate_pdf

        with self.assertRaises(ValidationError):
            validate_pdf(SimpleUploadedFile("a.txt", b"%PDF-"))
        with self.assertRaises(ValidationError):
            validate_pdf(SimpleUploadedFile("a.pdf", b"not a pdf"))
        big = SimpleUploadedFile("a.pdf", b"%PDF-" + b"0" * (10 * 1024 * 1024))
        with self.assertRaises(ValidationError):
            validate_pdf(big)


class ApproachListTests(Base):
    def test_add_once_from_each_page_mark_done_remove_and_the_title(self):
        session = lead("hugo@example.com")
        application = self.application(email="hugo@example.com")
        self.assertEqual(services.add_to_list(self.approver, lead_email="hugo@example.com", reason="Met at the fair")[0], services.DONE)
        self.assertEqual(services.add_to_list(self.approver, application=application)[0], services.ALREADY)  # the same person
        self.assertEqual(call(self.approver, "post", f"/leads/{session.pk}/outreach/").status_code, 302)
        self.assertEqual(OutreachEntry.objects.count(), 1)
        entry = OutreachEntry.objects.get()
        page = call(self.reader, "get", "/outreach/")
        self.assertContains(page, "Approach list")
        SiteSettings.objects.update(outreach_list_name="Barry's list")
        self.assertContains(call(self.reader, "get", "/outreach/"), "Barry&#x27;s list")
        self.assertEqual(call(self.reader, "post", f"/outreach/{entry.pk}/done/").status_code, 403)
        self.assertEqual(call(self.reader, "post", f"/outreach/{entry.pk}/remove/").status_code, 403)
        self.assertEqual(call(self.reader, "post", f"/leads/{session.pk}/outreach/").status_code, 403)
        call(self.approver, "post", f"/outreach/{entry.pk}/done/")
        self.assertEqual(len(call(self.reader, "get", "/outreach/").context["rows"]), 0)
        self.assertEqual(len(call(self.reader, "get", "/outreach/?state=done").context["rows"]), 1)
        self.assertEqual(services.add_to_list(self.approver, lead_email="hugo@example.com")[0], services.DONE)  # a done entry no longer blocks
        call(self.approver, "post", f"/outreach/{OutreachEntry.objects.get(done_at__isnull=True).pk}/remove/")
        self.assertEqual(OutreachEntry.objects.filter(done_at__isnull=True).count(), 0)

    def test_the_database_allows_one_open_entry_and_exactly_one_target(self):
        OutreachEntry.objects.create(lead_email="a@example.com")
        with self.assertRaises(IntegrityError), transaction.atomic():
            OutreachEntry.objects.create(lead_email="a@example.com")
        with self.assertRaises(IntegrityError), transaction.atomic():
            OutreachEntry.objects.create()  # no target

    def test_people_resolve_to_one_set_of_addresses(self):
        application = self.application(email="Other@Example.com")
        main, addresses, user = people.resolve(application=application)
        self.assertEqual((main, addresses, user), ("other@example.com", {"other@example.com"}, None))


@override_settings(EMAIL_SENDING_DOMAIN="spa99.uk", DEFAULT_FROM_EMAIL="Spa 99 <hello@spa99.uk>")
class EmailButtonTests(Base):
    """The Email button and its pop-up: a plain text email from the logged-in person (From and Reply-To his address, his signature), kept in the timeline. Mocked: mail goes to the test outbox."""

    def setUp(self):
        super().setUp()
        self.approver.first_name = "Barry"
        self.approver.email = "barry@spa99.uk"
        self.approver.save()
        self.session = lead("hugo@example.com")
        self.url = f"/leads/{self.session.pk}/message/"
        mail.outbox.clear()

    def send(self, text="Hello Hugo, thanks for your interest.", user=None, url=None):
        return call(user or self.approver, "post", url or self.url, {"message": text})

    def test_only_an_approver_or_admin_can_send(self):
        self.assertEqual(self.send(user=self.reader).status_code, 403)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(self.send(user=self.admin).status_code, 302)
        self.assertEqual(len(mail.outbox), 1)

    def test_from_and_reply_to_are_the_logged_in_person_with_his_signature(self):
        from notifications.models import StaffSender

        StaffSender.objects.create(user=self.approver, signature_html='<table><tr><td style="color: #492E21">Barry Cohen | Manager</td></tr></table>')
        self.send()
        sent = mail.outbox[0]
        self.assertEqual(sent.from_email, '"Barry, Spa 99" <barry@spa99.uk>')
        self.assertEqual(sent.reply_to, ["barry@spa99.uk"])
        self.assertEqual(sent.to, ["hugo@example.com"])
        self.assertIn("Hello Hugo, thanks for your interest.", sent.body)
        self.assertIn("Barry Cohen | Manager", sent.alternatives[0][0])
        self.assertNotIn("Kind regards", sent.alternatives[0][0])
        self.assertNotIn("Questions? Reply to this email or write to", sent.alternatives[0][0])

    def test_without_a_signature_it_ends_kind_regards_with_his_name_and_a_login_off_the_domain_falls_back(self):
        outside = make_team_member("barry@bmlgroup.example", levels.OFFICE, approver=True)  # not on the sending domain, no sending address set
        self.send(user=outside)
        sent = mail.outbox[0]
        self.assertEqual(sent.from_email, "Spa 99 <hello@spa99.uk>")
        self.assertEqual(sent.reply_to, [SiteSettings.load().contact_address])  # the hello@ fallback: replies go to the contact address
        self.assertIn("Kind regards", sent.alternatives[0][0])

    def test_it_is_kept_as_a_person_message_and_shows_in_the_timeline_and_a_double_click_sends_once(self):
        self.send()
        self.send()  # the same text again at once
        self.assertEqual(len(mail.outbox), 1)
        row = PersonMessage.objects.get()
        self.assertEqual((row.email, row.author, row.status, row.text), ("hugo@example.com", self.approver, PersonMessage.SENT, "Hello Hugo, thanks for your interest."))
        self.assertTrue(row.subject)
        timeline = call(self.reader, "get", f"/leads/{self.session.pk}/").context["person"]["timeline"]
        self.assertIn(("Email sent by Barry (barry@spa99.uk)", "Hello Hugo, thanks for your interest."), [(t["label"], t["detail"]) for t in timeline])

    def test_a_failed_send_shows_failed_in_the_timeline_and_the_toast_says_so(self):
        from django.contrib.messages import get_messages

        with mock.patch("django.core.mail.EmailMultiAlternatives.send", side_effect=OSError("mail server down")):
            response = self.send()
        self.assertEqual(PersonMessage.objects.get().status, PersonMessage.FAILED)
        self.assertIn("could not be sent", " ".join(str(m) for m in get_messages(response.wsgi_request)))
        timeline = call(self.reader, "get", f"/leads/{self.session.pk}/").context["person"]["timeline"]
        self.assertIn("Email failed by Barry (barry@spa99.uk)", [t["label"] for t in timeline])

    def test_a_bounced_address_is_refused_plainly_and_the_button_is_off_with_the_reason(self):
        from django.contrib.messages import get_messages

        from notifications.models import EmailSuppression

        now = timezone.now()
        EmailSuppression.objects.create(email="hugo@example.com", reason=EmailSuppression.HARD_BOUNCE, first_seen=now, last_seen=now)
        response = self.send()
        self.assertEqual((PersonMessage.objects.count(), len(mail.outbox)), (0, 0))
        self.assertIn("This address bounced", " ".join(str(m) for m in get_messages(response.wsgi_request)))
        page = call(self.approver, "get", f"/leads/{self.session.pk}/")
        self.assertContains(page, "data-email-off")
        self.assertContains(page, "This address bounced, so he cannot be emailed.")

    def test_on_a_gold_page_the_first_email_marks_new_as_contacted_once_with_a_responded_event(self):
        application = self.application(email="gold@example.com")
        url = f"/gold/{application.pk}/message/"
        self.send(url=url)
        self.send("A second note to him, a bit later.", url=url)
        application.refresh_from_db()
        self.assertEqual(application.status, "contacted")
        events = application.events.filter(action=ApplicationEvent.RESPONDED)
        self.assertEqual((events.count(), events.first().meta), (1, {"email": True}))

    def test_respond_opens_whatsapp_with_a_mobile_else_the_gold_page_with_the_email_pop_up(self):
        with_mobile = self.application(email="mob@example.com", mobile="+447400123456")
        self.assertEqual(call(self.approver, "get", f"/gold/{with_mobile.pk}/respond/")["Location"], f"/gold/{with_mobile.pk}/whatsapp/")
        none = self.application(email="nomob@example.com", mobile="")
        self.assertEqual(call(self.approver, "get", f"/gold/{none.pk}/?do=respond")["Location"], f"/gold/{none.pk}/?do=email")
        self.assertContains(call(self.approver, "get", f"/gold/{none.pk}/?do=email"), 'data-dialog="email" data-open')
