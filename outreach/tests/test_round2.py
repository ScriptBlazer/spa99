"""Round 2 of the office outreach: list sorting, Gold delete, approach list tabs, archived leads, restore a note, the next-morning email.
Mocked: sync queue and in-memory mail."""
import json
from datetime import datetime, time, timedelta, timezone as tz
from unittest import mock
from zoneinfo import ZoneInfo

from django.core import mail
from django.test import override_settings
from django.utils import timezone

from common import levels
from gold.models import ApplicationEvent, GoldApplication
from journey.models import JourneySession
from mailings.models import EmailOptOut
from notifications.models import EmailBounce, EmailLog
from office import leads as lead_lists
from office.tests.test_leads import lead, verify
from outreach import nextmorning, services
from outreach.models import ArchivedLead, NextMorningEmail, NoteEvent, OutreachEntry, PersonEdit, StickyNote
from outreach.tests.test_outreach import Base, call
from plans.models import SiteSettings
from system.models import SystemChange
from users import services as user_services
from users.tests.test_register import cleaned

LONDON = ZoneInfo("Europe/London")


def london(*args):
    return datetime(*args, tzinfo=LONDON)


class SortingTests(Base):
    def test_every_list_sorts_both_ways_over_the_whole_list_and_ignores_unknown_keys(self):
        for email in ("c@example.com", "a@example.com", "b@example.com"):
            lead(email)
        emails = lambda q: [r["email"] for r in call(self.reader, "get", f"/leads/?{q}").context["rows"]]
        self.assertEqual(emails("sort=email&dir=asc"), ["a@example.com", "b@example.com", "c@example.com"])
        self.assertEqual(emails("sort=email&dir=desc"), ["c@example.com", "b@example.com", "a@example.com"])
        self.assertEqual(len(emails("sort=nonsense&dir=asc")), 3)  # falls back to the default
        columns = {c["key"]: c for c in call(self.reader, "get", "/leads/?sort=email&dir=asc").context["columns"]}
        self.assertTrue(columns["email"]["active"] and not columns["wants"]["sortable"])
        self.assertIn("Best fit", [c["label"] for c in columns.values()])
        for path in ("/people/?sort=registered&dir=asc", "/gold/?sort=applied", "/chats/?sort=started&dir=asc", "/chats/?sort=cost",
                     "/outreach/?sort=name", "/outreach/?state=done&sort=done", "/outreach/?state=registered"):
            self.assertEqual(call(self.admin, "get", path).status_code, 200, path)

    def test_chat_cost_is_not_sortable_below_developer_level(self):
        keys = lambda user: [c["key"] for c in call(user, "get", "/chats/").context["columns"]]
        self.assertNotIn("cost", keys(self.reader))

    def test_csv_follows_the_same_order(self):
        for email in ("c@example.com", "a@example.com"):
            lead(email)
        body = call(self.admin, "get", "/leads/export.csv?sort=email&dir=asc").content.decode()
        self.assertLess(body.index("a@example.com"), body.index("c@example.com"))
        self.assertIn("best_fit", body.splitlines()[0])


class GoldDeleteTests(Base):
    def test_admin_only_removes_everything_and_writes_the_change_log(self):
        application = self.application(email="junk@example.com")
        StickyNote.objects.create(email="junk@example.com", text="stays")
        url = f"/gold/{application.pk}/delete/"
        self.assertEqual(call(self.approver, "post", url).status_code, 403)
        self.assertEqual(call(self.reader, "post", url).status_code, 403)
        self.assertTrue(call(self.admin, "get", f"/gold/{application.pk}/").context["can_delete_gold"])
        self.assertFalse(call(self.approver, "get", f"/gold/{application.pk}/").context["can_delete_gold"])
        response = call(self.admin, "post", url)
        self.assertRedirects(response, "/gold/", fetch_redirect_response=False)
        self.assertFalse(GoldApplication.objects.exists() or ApplicationEvent.objects.exists() or GoldApplication.history.exists())
        self.assertEqual(StickyNote.objects.count(), 1)  # notes belong to the person
        change = SystemChange.objects.get(kind=SystemChange.DELETED, model_label="gold.goldapplication")
        self.assertIn(application.reference, change.sentence)
        self.assertEqual((change.user_label, "junk@example.com" in change.sentence), ("admin@example.test", True))


class ApproachListTests(Base):
    def test_registering_takes_a_lead_off_the_list_by_itself_and_done_is_unaffected(self):
        lead("a@example.com"), lead("b@example.com"), lead("c@example.com")
        for who in ("a", "b", "c"):
            services.add_to_list(self.admin, lead_email=f"{who}@example.com")
        user = user_services.register_interest(cleaned(email="A@example.com")).user  # unverified: still on the list
        counts = lambda: {k: v for k, v in call(self.admin, "get", "/outreach/").context["counts"].items()}
        self.assertEqual(counts(), {"open": 3, "done": 0})
        verify(user)  # his account is proven after he was added: he has left the list, nothing was rewritten
        self.assertEqual(counts(), {"open": 2, "done": 0})
        self.assertEqual(sorted(r["email"] for r in call(self.admin, "get", "/outreach/").context["rows"]), ["b@example.com", "c@example.com"])
        self.assertEqual(OutreachEntry.objects.filter(lead_email="a@example.com").count(), 1)  # the row is still there (no data rewrite)
        entry = OutreachEntry.objects.get(lead_email="b@example.com")
        services.mark_done(entry, self.admin)
        self.assertEqual(counts(), {"open": 1, "done": 1})
        self.assertEqual(len(call(self.admin, "get", "/outreach/?state=done").context["rows"]), 1)
        self.assertEqual(call(self.admin, "get", "/outreach/?state=registered").context["state"], "open")  # the old tab is gone

    def test_someone_already_registered_when_added_stays_open(self):
        lead("early@example.com")
        user = user_services.register_interest(cleaned(email="early@example.com")).user
        verify(user)
        services.add_to_list(self.admin, user=user)
        counts = call(self.admin, "get", "/outreach/").context["counts"]
        self.assertEqual(counts["open"], 1)
        row = call(self.admin, "get", "/outreach/").context["rows"][0]
        self.assertEqual(row["source"], "Person")


class ArchiveTests(Base):
    def test_archive_hides_from_leads_counts_csv_hot_and_moves_back_with_timeline_lines(self):
        session = lead("a@example.com")
        lead("b@example.com")
        url = f"/leads/{session.pk}/archive/"
        self.assertEqual(call(self.reader, "post", url).status_code, 403)
        self.assertEqual(call(self.approver, "post", url, {"reason": "x" * 301}).status_code, 302)
        self.assertFalse(ArchivedLead.objects.exists())  # refused, nothing saved
        call(self.approver, "post", url, {"reason": "not a fit"})
        call(self.approver, "post", url, {"reason": "again"})  # idempotent
        self.assertEqual(ArchivedLead.objects.get().reason, "not a fit")
        listed = lambda q="": [r["email"] for r in call(self.reader, "get", f"/leads/{q}").context["rows"]]
        self.assertEqual(listed(), ["b@example.com"])
        self.assertEqual(listed("?view=archived&sort=archived"), ["a@example.com"])
        self.assertNotIn("a@example.com", call(self.admin, "get", "/leads/export.csv").content.decode())
        self.assertEqual(lead_lists.lead_queryset().count(), 1)
        self.assertEqual(lead_lists.hot_leads_queryset().filter(email_key="a@example.com").count(), 0)
        page = call(self.reader, "get", f"/leads/{session.pk}/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Archived by", str(page.context["timeline_days"]))
        call(self.approver, "post", f"/leads/{session.pk}/unarchive/")
        self.assertEqual(sorted(listed()), ["a@example.com", "b@example.com"])
        self.assertIn("Moved back by", str(call(self.reader, "get", f"/leads/{session.pk}/").context["timeline_days"]))

    def test_an_archived_lead_who_registers_is_a_registered_person_and_erasure_removes_the_row(self):
        lead("a@example.com")
        services.archive_lead("a@example.com", self.admin)
        user = user_services.register_interest(cleaned(email="a@example.com")).user
        verify(user)
        self.assertEqual(lead_lists.lead_queryset().count(), 0)
        self.assertEqual(lead_lists.lead_queryset(archived=True).count(), 0)
        services.erase_email("a@example.com")
        self.assertFalse(ArchivedLead.objects.exists() or services.LeadArchiveEvent.objects.exists())


class RestoreNoteTests(Base):
    def test_restore_brings_the_note_back_once_with_history_lines_and_the_right_urls(self):
        application = self.application(email="dan@example.com")
        status, note = services.add_note("dan@example.com", self.approver, "Owns flats")
        services.delete_note(note, self.approver)
        gold = call(self.approver, "get", f"/gold/{application.pk}/").context["application"]["events"]
        restore = [e["restore_url"] for e in gold if e["action"] == "note_deleted"]
        self.assertEqual(restore, [f"/gold/{application.pk}/notes/{note.pk}/restore/"])
        self.assertEqual([e["restore_url"] for e in call(self.reader, "get", f"/gold/{application.pk}/").context["application"]["events"] if e["action"] == "note_deleted"], [""])
        self.assertEqual(call(self.reader, "post", restore[0]).status_code, 403)
        call(self.approver, "post", restore[0])
        call(self.approver, "post", restore[0])  # twice does nothing
        note.refresh_from_db()
        self.assertIsNone(note.deleted_at)
        self.assertEqual((note.author_label, ApplicationEvent.objects.filter(action="note_restored").count(), NoteEvent.objects.filter(kind="restored").count()), (note.author_label, 1, 1))
        gold = call(self.approver, "get", f"/gold/{application.pk}/").context["application"]["events"]
        self.assertEqual([e["restore_url"] for e in gold if e["action"] == "note_deleted"], [""])  # already restored
        labels = [e[2] for e in services.timeline_entries(["dan@example.com"])]
        self.assertTrue(any(x.startswith("Note deleted by") for x in labels) and any(x.startswith("Note restored by") for x in labels))

    def test_person_and_lead_timelines_carry_restore_url(self):
        session = lead("hugo@example.com")
        _, note = services.add_note("hugo@example.com", self.approver, "Hot")
        services.delete_note(note, self.approver)
        items = lambda user: [i for d in call(user, "get", f"/leads/{session.pk}/").context["timeline_days"] for i in d["items"] if i["kind"] == "note_deleted"]
        self.assertEqual([i["restore_url"] for i in items(self.approver)], [f"/leads/{session.pk}/notes/{note.pk}/restore/"])
        self.assertEqual([i["restore_url"] for i in items(self.reader)], [""])
        call(self.approver, "post", f"/leads/{session.pk}/notes/{note.pk}/restore/")
        self.assertEqual([i["restore_url"] for i in items(self.approver)], [""])


class DueTimeTests(Base):
    def test_default_ten_oclock_at_least_eight_hours_later(self):
        for given, due in [((2026, 11, 10, 2, 0), (2026, 11, 10, 10, 0)), ((2026, 11, 10, 9, 30), (2026, 11, 11, 10, 0)),
                           ((2026, 11, 10, 23, 0), (2026, 11, 11, 10, 0)), ((2026, 11, 10, 1, 59), (2026, 11, 10, 10, 0))]:
            self.assertEqual(nextmorning.due_time(london(*given)), london(*due), given)

    def test_clock_change_days_still_land_on_local_ten(self):
        # spring forward 2027-03-28 (01:00 UTC): 23:00 GMT on the 27th -> 10:00 BST = 09:00 UTC
        self.assertEqual(nextmorning.due_time(london(2027, 3, 27, 23, 0)), datetime(2027, 3, 28, 9, 0, tzinfo=tz.utc))
        self.assertEqual(nextmorning.due_time(london(2027, 3, 28, 0, 30)), datetime(2027, 3, 28, 9, 0, tzinfo=tz.utc))
        # fall back 2026-10-25: 23:00 BST on the 24th -> 10:00 GMT = 10:00 UTC
        self.assertEqual(nextmorning.due_time(london(2026, 10, 24, 23, 0)), datetime(2026, 10, 25, 10, 0, tzinfo=tz.utc))
        self.assertEqual(nextmorning.due_time(london(2026, 10, 25, 1, 30)), datetime(2026, 10, 25, 10, 0, tzinfo=tz.utc))  # 8 h later is 9:30 GMT: still today

    def test_hours_are_absolute_across_a_clock_change(self):
        # 00:30 GMT on the day the clocks go forward: +8 real hours is 09:30 BST, past a 09:00 send time, so tomorrow (wall-clock maths would say today)
        self.assertEqual(nextmorning.due_time(london(2027, 3, 28, 0, 30), time(9, 0), 8), london(2027, 3, 29, 9, 0))
        # the day they go back: 00:30 BST + 8 real hours = 07:30 GMT, before 08:15, so today (wall-clock maths would say 08:30 and push to tomorrow)
        self.assertEqual(nextmorning.due_time(london(2026, 10, 25, 0, 30), time(8, 15), 8), datetime(2026, 10, 25, 8, 15, tzinfo=tz.utc))

    def test_custom_time_and_hours(self):
        at = time(7, 30)
        self.assertEqual(nextmorning.due_time(london(2026, 11, 10, 7, 29), at, 0), london(2026, 11, 10, 7, 30))
        self.assertEqual(nextmorning.due_time(london(2026, 11, 10, 7, 29), at, 1), london(2026, 11, 11, 7, 30))
        self.assertEqual(nextmorning.due_time(london(2026, 11, 10, 22, 0), time(10, 0), 24), london(2026, 11, 12, 10, 0))
        self.assertEqual(nextmorning.due_time(london(2027, 3, 27, 23, 0), at, 8), datetime(2027, 3, 29, 6, 30, tzinfo=tz.utc))  # 23:00 GMT + 8 real hours = 08:00 BST, past 07:30 BST: the 29th


@override_settings(DEFAULT_FROM_EMAIL="Spa 99 <hello@spa99.test>")
class NextMorningTests(Base):
    def setUp(self):
        super().setUp()
        SiteSettings.load()
        self.site = SiteSettings.load()
        self.site.auto_email_from_name, self.site.auto_email_from_address = "Barry Lobenstein", "barry@spa99.test"
        self.site.lead_next_morning_on = True
        self.site.save()
        self.now = timezone.now()

    def given(self, email, hours_ago=0):
        session = lead(email)
        JourneySession.objects.filter(pk=session.pk).update(lead_at=self.now - timedelta(hours=hours_ago))
        return session

    def run_job(self, hours_ahead=30):
        return nextmorning.run(self.now + timedelta(hours=hours_ahead))

    def test_settings_rules_domain_address_and_since(self):
        site = SiteSettings.load()
        site.auto_email_from_address, site.lead_next_morning_on = "", True
        site.full_clean()  # no sender address is needed any more: the email goes from hello@ unless a staff member is picked on its page
        site.auto_email_from_address = "barry@other.com"
        with self.assertRaises(Exception):
            site.full_clean()
        self.assertIsNotNone(SiteSettings.load().lead_next_morning_since)  # stamped when it was switched on

    def test_sends_once_from_the_sender_with_unsubscribe_and_shows_in_the_timeline(self):
        session = self.given("new@example.com", hours_ago=-1)
        self.run_job(), self.run_job()  # twice: once only
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual((message.from_email, message.reply_to, message.extra_headers["X-PM-Tag"]), ("Barry Lobenstein <barry@spa99.test>", ["barry@spa99.test"], "lead-next-morning"))
        self.assertIn("List-Unsubscribe", message.extra_headers)
        self.assertIn("Unsubscribe", message.alternatives[0][0])
        self.assertEqual(NextMorningEmail.objects.get().sent_at is not None, True)
        self.assertIn("Next-morning email sent", str(call(self.reader, "get", f"/leads/{session.pk}/").context["timeline_days"]))

    # The email follows its own System > Emails settings: person sender and no contact line by default.
    def test_defaults_then_the_site_sender_and_shared_footer_when_chosen(self):
        from notifications.models import NotificationTemplate

        self.given("a@example.com", hours_ago=-1)
        self.run_job()
        first = mail.outbox[-1]
        self.assertEqual(first.from_email, "Barry Lobenstein <barry@spa99.test>")
        self.assertNotIn("Questions? Reply", first.alternatives[0][0])
        NotificationTemplate.objects.filter(key="lead_next_morning").update(sender="site", footer_mode="shared")
        self.site.auto_email_from_address = ""  # a site-sender email needs no person address
        SiteSettings.objects.update(auto_email_from_address="")
        self.given("b@example.com", hours_ago=-1)
        self.run_job()
        second = mail.outbox[-1]
        self.assertEqual(second.from_email, "Spa 99 <hello@spa99.test>")
        self.assertIn("Questions? Reply", second.alternatives[0][0])

    def test_only_leads_given_after_the_switch_and_not_the_old_ones(self):
        self.given("old@example.com", hours_ago=5000)
        self.run_job()
        self.assertEqual((NextMorningEmail.objects.count(), len(mail.outbox)), (0, 0))

    def test_a_lead_given_just_before_the_switch_went_on_is_not_emailed(self):
        since = SiteSettings.load().lead_next_morning_since
        session = lead("early@example.com")
        JourneySession.objects.filter(pk=session.pk).update(lead_at=since - timedelta(hours=1))  # inside the look-back window, but before the switch
        mail.outbox.clear()
        self.run_job()
        self.assertEqual((NextMorningEmail.objects.count(), len(mail.outbox)), (0, 0))

    def test_every_skip_rule_is_logged_and_not_retried(self):
        for email in ("account@example.com", "archived@example.com", "optout@example.com", "bounce@example.com", "ok@example.com"):
            self.given(email, hours_ago=-1)
        verify(user_services.register_interest(cleaned(email="account@example.com")).user)
        services.archive_lead("archived@example.com", self.admin)
        EmailOptOut.objects.create(email="optout@example.com")
        EmailBounce.objects.create(email="bounce@example.com", kind=EmailBounce.HARD, received_at=self.now)
        mail.outbox.clear()
        self.run_job()
        reasons = dict(NextMorningEmail.objects.values_list("email", "skip_reason"))
        self.assertEqual(reasons, {"account@example.com": "has an account", "archived@example.com": "archived", "optout@example.com": "unsubscribed",
                                   "bounce@example.com": "hard bounce", "ok@example.com": ""})
        self.assertEqual([m.to for m in mail.outbox], [["ok@example.com"]])
        self.run_job()
        self.assertEqual(len(mail.outbox), 1)

    def test_switch_off_sends_nothing_and_late_rows_are_skipped(self):
        self.given("a@example.com", hours_ago=-1)
        self.run_job(hours_ahead=0)  # discovered, not due yet
        self.site.lead_next_morning_on = False
        self.site.save()
        self.run_job()
        self.assertEqual((len(mail.outbox), NextMorningEmail.objects.get().skip_reason), (0, "switch off"))
        self.site.lead_next_morning_on = True
        self.site.save()
        self.given("b@example.com", hours_ago=-1)
        self.run_job(hours_ahead=24 * 3)  # the worker was down: more than a day overdue
        self.assertEqual(NextMorningEmail.objects.get(email="b@example.com").skip_reason, "too late")
        self.assertEqual(len(mail.outbox), 0)

    def test_timing_changes_apply_to_unsent_rows(self):
        self.given("a@example.com", hours_ago=-1)
        self.run_job(hours_ahead=0)
        before = NextMorningEmail.objects.get().due_at
        self.site.lead_next_morning_at, self.site.lead_next_morning_min_hours = time(15, 0), 0
        self.site.save()
        self.run_job(hours_ahead=0)
        row = NextMorningEmail.objects.get()
        self.assertNotEqual(row.due_at, before)
        self.assertEqual(row.due_at, nextmorning.due_time(row.lead_at, time(15, 0), 0))

    def test_the_job_is_scheduled_every_15_minutes_once(self):
        from io import StringIO
        from django.core.management import call_command
        from django_q.models import Schedule
        call_command("register_schedules", stdout=StringIO()), call_command("register_schedules", stdout=StringIO())
        job = Schedule.objects.get(name="lead-next-morning")
        self.assertEqual((job.func, job.schedule_type, job.minutes), ("outreach.nextmorning.scheduled", Schedule.MINUTES, 15))



@override_settings(DEFAULT_FROM_EMAIL="Spa 99 <hello@spa99.test>")
class BouncedLeadTests(Base):
    """Possible fake (a permanent bounce on the suppression list), Correct the email, Resend follow-up."""

    def setUp(self):
        super().setUp()
        self.site = SiteSettings.load()
        self.site.auto_email_from_name, self.site.auto_email_from_address = "Barry Lobenstein", "barry@spa99.test"
        self.site.save()  # the automatic switch stays OFF: the resend must work anyway
        self.now = timezone.now()

    def suppress(self, email, reason="hard_bounce"):
        from notifications.models import EmailSuppression

        EmailSuppression.objects.create(email=email, reason=reason, first_seen=self.now, last_seen=self.now)

    def test_the_tag_shows_for_a_permanent_bounce_only_and_costs_no_extra_queries_per_row(self):
        a, b, c = lead("typo@example.com"), lead("spam@example.com"), lead("fine@example.com")
        self.suppress("typo@example.com")
        self.suppress("spam@example.com", "complaint")
        rows = {r["email"]: r["bounced"] for r in lead_lists.page({**lead_lists.filters_from(self._request()), "range": "all"}, 1)[0]}
        self.assertEqual(rows, {"spam@example.com": False, "fine@example.com": False})  # a bounced lead is only in the Possible fakes tab
        fakes = {r["email"]: r["bounced"] for r in lead_lists.page({**lead_lists.filters_from(self._request()), "view": "fakes"}, 1)[0]}
        self.assertEqual(fakes, {"typo@example.com": True})
        self.assertEqual(call(self.reader, "get", "/leads/").content.decode().count("data-possible-fake"), 0)
        page = call(self.reader, "get", f"/leads/{a.pk}/")
        self.assertIn("This email bounced, so it may not be real.", page.content.decode())
        self.assertNotIn("data-bounce-notice", call(self.reader, "get", f"/leads/{b.pk}/").content.decode())  # a complaint is not a bounce
        self.assertNotIn("data-bounce-notice", call(self.reader, "get", f"/leads/{c.pk}/").content.decode())

    def _request(self):
        from django.test import RequestFactory

        request = RequestFactory().get("/leads/")
        request.user = self.reader
        return request

    def test_correcting_the_email_moves_his_journeys_and_notes_is_audited_and_clears_the_tag(self):
        session = lead("typo@example.com")
        self.suppress("typo@example.com")
        services.add_note("typo@example.com", self.approver, "Called, no answer")
        self.assertEqual(call(self.reader, "post", f"/leads/{session.pk}/email/", {"email": "fixed@example.com"}).status_code, 403)  # view only
        answer = call(self.approver, "post", f"/leads/{session.pk}/email/", {"email": " Fixed@Example.com "})
        self.assertEqual(answer.status_code, 302)
        session.refresh_from_db()
        self.assertEqual(session.lead_email, "fixed@example.com")
        self.assertEqual(StickyNote.objects.get().email, "fixed@example.com")
        edit = PersonEdit.objects.get()
        self.assertEqual((edit.what, edit.before, edit.after, edit.email), ("email", "typo@example.com", "fixed@example.com", "fixed@example.com"))
        page = call(self.reader, "get", f"/leads/{session.pk}/")
        self.assertNotIn("data-bounce-notice", page.content.decode())
        self.assertIn(f"Email changed by {self.approver.email}", [e["label"] for e in page.context["person"]["timeline"]])
        from notifications.models import EmailSuppression

        self.assertTrue(EmailSuppression.objects.filter(email="typo@example.com").exists())  # the old address stays on the list

    def test_the_lead_page_has_one_email_send_dialog_and_a_separate_correct_email_one(self):
        session = lead("fine@example.com")
        html = call(self.approver, "get", f"/leads/{session.pk}/").content.decode()
        self.assertIn("data-consent-text", html)  # the wording he ticked reaches the page
        self.assertEqual(html.count('data-dialog="email"'), 1)
        self.assertEqual(html.count('data-dialog="correct-email"'), 1)
        send = html.split('data-dialog="email"')[1].split("</dialog>")[0]
        self.assertIn('name="message"', send)  # the send form, not the correct-email one
        self.assertNotIn('type="email"', send)

    def test_a_taken_address_is_refused_and_says_whose(self):
        first, other = lead("typo@example.com"), lead("other@example.com")
        JourneySession.objects.filter(pk=other.pk).update(lead_first_name="Olly")
        answer = call(self.approver, "post", f"/leads/{first.pk}/email/", {"email": "other@example.com"}, follow=True)
        self.assertIn("another lead (Olly)", " ".join(str(m) for m in answer.context["messages"]))
        user = user_services.register_interest(cleaned(email="member@example.com", first_name="Mia", last_name="Member")).user
        result, owner = services.correct_lead_email("typo@example.com", "member@example.com", self.approver)
        self.assertEqual((result, owner["kind"], owner["name"]), (services.TAKEN, "account", "Mia Member"))
        self.assertEqual(services.correct_lead_email("typo@example.com", "not an email", self.approver)[0], services.INVALID)
        first.refresh_from_db()
        self.assertEqual(first.lead_email, "typo@example.com")
        self.assertFalse(PersonEdit.objects.exists())
        del user

    def test_resend_sends_once_with_the_switch_off_and_not_while_bounced_or_without_a_sender(self):
        session = lead("typo@example.com")
        self.suppress("typo@example.com")
        call(self.approver, "post", f"/leads/{session.pk}/email/", {"email": "fixed@example.com"})
        page = call(self.approver, "get", f"/leads/{session.pk}/").content.decode()
        self.assertIn("data-bounce-resend", page)
        self.assertNotIn("data-bounce-resend", call(self.reader, "get", f"/leads/{session.pk}/").content.decode())  # view only: no button
        self.assertNotIn("data-bounce-resend", call(self.approver, "get", f"/leads/{lead('x@example.com').pk}/").content.decode())
        self.assertEqual(call(self.reader, "post", f"/leads/{session.pk}/resend/").status_code, 403)
        self.suppress("fixed@example.com")  # still bouncing
        self.assertEqual(services.resend_follow_up("fixed@example.com", self.approver)[0], services.BOUNCED)
        from notifications.models import EmailSuppression

        EmailSuppression.objects.filter(email="fixed@example.com").delete()
        SiteSettings.objects.update(auto_email_from_address="")  # no sender address at all: it still goes, from hello@
        self.assertFalse(SiteSettings.load().lead_next_morning_on)
        mail.outbox.clear()
        self.assertEqual(services.resend_follow_up("fixed@example.com", self.approver)[0], services.SENT)
        self.assertEqual((len(mail.outbox), mail.outbox[0].to), (1, ["fixed@example.com"]))
        self.assertEqual(services.resend_follow_up("fixed@example.com", self.approver)[0], services.ALREADY)  # once
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Next-morning email sent", str(call(self.reader, "get", f"/leads/{session.pk}/").context["timeline_days"]))


class StaffEmailExportTests(Base):
    def test_staff_email_text_is_in_both_exports_and_an_unverified_account_gets_none(self):
        from outreach.models import PersonMessage

        PersonMessage.objects.create(email="acc@example.com", text="Hello Acc", author_label="Barry", subject="Hi")
        session = lead("acc@example.com")
        lead_export = call(self.admin, "get", f"/leads/{session.pk}/export/")
        self.assertEqual([m["text"] for m in json.loads(lead_export.content)["staff_emails"]], ["Hello Acc"])
        user = user_services.register_interest(cleaned(email="acc@example.com")).user
        self.assertEqual(user_services.export_user_data(user)["staff_emails"], [])  # not proven his yet
        type(user).objects.filter(pk=user.pk).update(email_verified_at=timezone.now())
        user.refresh_from_db()
        mine = user_services.export_user_data(user)["staff_emails"]
        self.assertEqual((mine[0]["text"], mine[0]["written_by"]), ("Hello Acc", "Barry"))


class SendMessageGuardTests(Base):
    def test_resending_after_a_failure_sends_but_a_repeat_of_a_good_one_does_not(self):
        with mock.patch("outreach.services.enqueue", side_effect=RuntimeError("queue down")):
            result, first = services.send_message(self.approver, "a@example.com", "Hello there")
        self.assertEqual((result, first.status), (services.DONE, "failed"))
        with mock.patch("outreach.services.enqueue"):
            self.assertEqual(services.send_message(self.approver, "a@example.com", "Hello there")[0], services.DONE)  # not "already sent"
            self.assertEqual(services.send_message(self.approver, "a@example.com", "Hello there")[0], services.DUPLICATE)
