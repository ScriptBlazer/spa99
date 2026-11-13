"""Office > Activity: who may open it, every source worded right, the filters, paging that joins up, the dashboard figures (range, change on the period before, counts,
day buckets), the list's day headings and sentences, and the edge cases (an account that is gone, a person erased)."""
import re
import uuid
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

from io import StringIO
from urllib.parse import urlencode
from unittest import mock

from django.core.management import call_command
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from common import levels
from gold import audit as gold_audit
from gold import services as gold_services
from gold.models import ApplicationEvent, GoldApplication
from gold.tests.test_gold import application_data
from office import activity, activity_store, approvals
from office.templatetags import office_tags
from office import signals, snapshots
from office.models import ActivityDay, ActivityDirtyDay, ActivityTimeOfDay, MembershipReviewEvent
from office.tests.test_office import OFFICE, OfficeTestCase
from outreach import services as outreach
from outreach.models import LeadArchiveEvent, OutreachEntry, PersonEdit, PersonMessage, StickyNote
from plans.tests.helpers import make_team_member
from system import audit as system_audit
from system.models import SiteDefaults, SystemEvent
from users import services as user_services
from users.tests.test_register import cleaned

SECRET_NOTE, SECRET_MESSAGE = "the-private-note-text", "the-private-message-body"


def page(user, query="", **extra):
    activity_store.apply()  # the stored totals the page reads (in real life the hourly job and the refresh write them)
    client = Client(HTTP_HOST=OFFICE)
    client.force_login(user)
    return client.get(f"/activity/{query}", **extra)


def london(*args):
    return timezone.make_aware(datetime(*args))


def filters(**over):
    return {"staff": "", "group": "", "from": None, "to": None, "range": "all", "error": "", **over}


filters_ = filters


def dashboard(f, now=None):
    activity_store.apply()
    return activity.dashboard(f, now)


def staff_choices():
    activity_store.apply()
    return activity.staff_choices()


class Base(OfficeTestCase):
    def setUp(self):
        self.dev = make_team_member("dev@example.test", levels.DEVELOPER)
        self.barry = make_team_member("barry@example.test", levels.ADMIN, approver=True)
        self.lead_email = "lead@example.com"

    def rows(self, **filters):
        activity_store.apply()
        return activity.page(filters_(**filters), size=500)[0]

    def by_what(self, what):
        return [r for r in self.rows() if r["what"] == what]


class AccessTests(Base):
    def test_developer_and_superuser_see_it_and_everyone_else_is_refused_with_no_nav_item(self):
        for level in (levels.DEVELOPER, levels.SUPERUSER):
            response = page(make_team_member(f"{level}@example.test", level))
            self.assertEqual(response.status_code, 200, level)
            self.assertContains(response, "data-office-nav-item=\"activity\"")
        for name, user in (("admin", make_team_member("a@example.test", levels.ADMIN)), ("office", make_team_member("o@example.test", levels.OFFICE)),
                           ("approver", make_team_member("ap@example.test", levels.OFFICE, approver=True))):
            self.assertEqual(page(user).status_code, 403, name)
            home = Client(HTTP_HOST=OFFICE)
            home.force_login(user)
            self.assertNotContains(home.get("/"), "/activity/")
            self.assertEqual(page(user, "?all=1&page=2").status_code, 403, name)  # the opened list and its pages are refused the same way


class SourceTests(Base):
    def test_notes_edits_archive_messages_and_the_approach_list_read_in_plain_english(self):
        _, note = outreach.add_note(self.lead_email, self.barry, SECRET_NOTE)
        outreach.edit_note(note, self.barry, SECRET_NOTE + " edited")
        outreach.delete_note(note, self.barry)
        outreach.restore_note(note, self.barry)
        PersonEdit.objects.create(email=self.lead_email, what=PersonEdit.MOBILE, after="07911123456", by_label="Barry (barry@example.test)")
        outreach.archive_lead(self.lead_email, self.barry, "Test lead")
        outreach.unarchive_lead(self.lead_email, self.barry)
        for kind in (LeadArchiveEvent.GENUINE, LeadArchiveEvent.UNGENUINE):
            LeadArchiveEvent.objects.create(email=self.lead_email, kind=kind, by_label="Barry (barry@example.test)")
        outreach.add_to_list(self.barry, lead_email=self.lead_email)
        PersonMessage.objects.create(email=self.lead_email, text=SECRET_MESSAGE, author=self.barry, author_label="Barry (barry@example.test)")
        whats = {r["what"] for r in self.rows()}
        self.assertTrue({"Note added", "Note edited", "Note deleted", "Note restored", "Mobile added", "Archived", "Moved back to Leads", "Marked as genuine",
                         "Genuine mark undone", "Email sent", "Added to the approach list"} <= whats, whats)
        archived = self.by_what("Archived")[0]
        self.assertEqual((archived["who"], archived["detail"], archived["email"]), ("Barry", "Test lead", self.lead_email))
        self.assertEqual(self.by_what("Note added")[0]["who"], "Barry")  # his first name, from his account
        self.assertEqual(self.by_what("Mobile added")[0]["detail"], "07911123456")
        self.assertEqual(self.by_what("Marked done on the approach list"), [])
        outreach.mark_done(OutreachEntry.objects.get(lead_email=self.lead_email), self.barry)
        self.assertEqual(len(self.by_what("Marked done on the approach list")), 1)

    def test_an_email_change_shows_old_and_new_and_a_failed_email_says_so(self):
        PersonEdit.objects.create(email="new@example.com", what=PersonEdit.EMAIL, before="old@example.com", after="new@example.com", by_label="Barry")
        PersonMessage.objects.create(email="x@example.com", text="t", author_label="Barry", status=PersonMessage.FAILED)
        self.assertEqual((self.by_what("Email changed")[0]["detail"]), "old@example.com to new@example.com")
        self.assertEqual(self.by_what("Email failed")[0]["detail"], "Did not send")

    def test_membership_decisions_and_gold_staff_actions_and_manual_setup(self):
        user = user_services.register_interest(cleaned(email="hugo@example.com", plan="tier-2", mobile="07911100001")).user
        approvals.decide(user.pk, "approved", self.barry)
        approvals.decide(user.pk, "declined", self.barry)
        approvals.decide(user.pk, "waiting", self.barry)
        self.assertEqual([r["what"] for r in self.rows() if r["group"] == "approvals"], ["Undid a decision", "Declined", "Approved"])
        self.assertEqual(self.rows()[0]["name"], user.get_full_name())
        self.assertTrue(self.rows()[0]["href"].endswith(f"/people/{user.pk}/"))
        gold_services.submit_application(application_data())
        application = GoldApplication.objects.get()
        gold_audit.record(application, ApplicationEvent.APPROVED, actor=self.barry, channel=gold_audit.OFFICE, message="a secret reason")
        gold_audit.record(application, ApplicationEvent.NOTE_ADDED, actor=self.barry, channel=gold_audit.OFFICE, message="note")  # a note is read from the sticky notes
        gold_audit.record(application, ApplicationEvent.EMAIL_SENT)  # automatic
        gold = [r for r in self.rows() if r["group"] == "gold"]
        self.assertEqual([r["what"] for r in gold], ["Approved a Gold application"])
        self.assertEqual(gold[0]["name"], application.full_name)
        system_audit.log_event(SystemEvent.SETUP_MANUAL, user=self.barry, detail={"plan": "tier-2", "member": user.public_id}, sentence="x")
        system_audit.log_event(SystemEvent.SALE_RESTORED, user=self.barry, detail={"member": user.public_id}, sentence="x")
        system_audit.log_event(SystemEvent.PAYMENTS_OPENED, user=self.barry, sentence="x")  # a System action, not an Office one
        memberships = [r for r in self.rows() if r["group"] == "memberships"]
        self.assertEqual({r["what"] for r in memberships}, {"Set up membership manually", "Restored a sale price"})
        self.assertEqual(memberships[0]["name"], user.get_full_name())

    def test_automatic_actions_are_not_listed(self):
        LeadArchiveEvent.objects.create(email="a@example.com", kind=LeadArchiveEvent.ARCHIVED, by_label=outreach.GROUP_EMAIL_LABEL)
        PersonEdit.objects.create(email="a@example.com", what=PersonEdit.MOBILE, after="07911", by_label=outreach.SELF_LABEL)
        self.assertEqual(self.rows(), [])

    def test_note_and_message_text_never_reach_the_page(self):
        outreach.add_note(self.lead_email, self.barry, SECRET_NOTE)
        PersonMessage.objects.create(email=self.lead_email, text=SECRET_MESSAGE, author_label="Barry")
        body = page(self.dev).content.decode()
        self.assertIn("added a note on", body)
        self.assertIn("emailed", body)
        self.assertNotIn(SECRET_NOTE, body)
        self.assertNotIn(SECRET_MESSAGE, body)


class FilterTests(Base):
    def make(self):
        now = timezone.now()
        StickyNote.objects.create(email="a@example.com", text="x", author_label="Barry", created_at=now - timedelta(days=10))
        PersonEdit.objects.create(email="a@example.com", what=PersonEdit.MOBILE, after="07911", by_label="Dana", at=now - timedelta(days=2))
        PersonMessage.objects.create(email="a@example.com", text="t", author_label="Dana", sent_at=now)

    def test_staff_type_and_dates(self):
        self.make()
        self.assertEqual([r["who"] for r in self.rows()], ["Dana", "Dana", "Barry"])  # newest first
        self.assertEqual({r["who"] for r in self.rows(staff="Barry")}, {"Barry"})
        self.assertEqual([r["what"] for r in self.rows(group="emails")], ["Email sent"])
        self.assertEqual([r["what"] for r in self.rows(group="notes")], ["Note added"])
        day = (timezone.now() - timedelta(days=2)).date()
        self.assertEqual([r["what"] for r in self.rows(**{"from": day, "to": day})], ["Mobile added"])
        self.assertEqual(len(self.rows(**{"from": day})), 2)
        self.assertEqual(staff_choices(), [("barry", "Barry"), ("dana", "Dana")])

    def test_the_page_reads_the_query_string_and_refuses_a_backwards_range(self):
        self.make()
        body = page(self.dev, "?range=all&staff=barry&group=notes").content.decode()
        self.assertIn("added a note on", body)
        self.assertNotIn("emailed", body)
        backwards = page(self.dev, "?range=all&from=2026-05-02&to=2026-05-01")
        self.assertContains(backwards, "end date can")
        self.assertContains(backwards, "emailed")  # both ends ignored


class PagingTests(Base):
    def test_pages_join_up_by_offset_and_the_merge_key_is_stable(self):
        now = timezone.now()
        for i in range(60):
            StickyNote.objects.create(email=f"p{i}@example.com", text="x", author_label="Barry", created_at=now - timedelta(minutes=i))
        PersonMessage.objects.create(email="m@example.com", text="t", author_label="Dana", sent_at=now - timedelta(minutes=25, seconds=30))
        first, more = activity.page({"staff": "", "group": "", "from": None, "to": None})
        second, more_after = activity.page({"staff": "", "group": "", "from": None, "to": None}, offset=50)
        self.assertEqual((len(first), more, len(second), more_after), (50, True, 11, False))
        ats = [r["at"] for r in first + second]
        self.assertEqual(ats, sorted(ats, reverse=True))
        self.assertEqual(len({(r["at"], r["email"]) for r in first + second}), 61)


class EdgeTests(Base):
    def test_a_deleted_staff_account_keeps_his_stored_label(self):
        gone = make_team_member("gone@example.test", levels.ADMIN)
        outreach.add_note(self.lead_email, gone, "x")
        PersonMessage.objects.create(email=self.lead_email, text="t", author=gone, author_label="Gone Person (gone@example.test)")
        gone.delete()
        self.assertEqual({r["who"] for r in self.rows()}, {"Gone"})  # a bare email and "Name (email)" are one person, shown by his first name
        self.assertEqual({r["staff"] for r in self.rows()}, {"Gone Person (gone@example.test)"})
        self.assertEqual(page(self.dev).status_code, 200)
        self.assertEqual(staff_choices(), [("gone@example.test", "Gone Person (gone@example.test)")])

    def test_an_erased_person_does_not_break_it(self):
        user = user_services.register_interest(cleaned(email="erase@example.com", plan="tier-2", mobile="07911100002")).user
        approvals.decide(user.pk, "approved", self.barry)
        outreach.add_note("erase@example.com", self.barry, "x")
        outreach.erase_email("erase@example.com")
        user.delete()  # his review events go with him
        PersonEdit.objects.create(email="erased@example.com", what=PersonEdit.MOBILE, after="07911", by_label="Barry")  # a row whose person is gone: the address stays plain
        self.assertEqual(MembershipReviewEvent.objects.count(), 0)
        response = page(self.dev)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "erased@example.com")
        system_audit.log_event(SystemEvent.SETUP_CANCELLED, user=self.barry, detail={"member": "GONE0000"}, sentence="x")  # the member is gone
        self.assertContains(page(self.dev), "a removed person")


class ReviewFindingTests(Base):
    def test_sixty_edits_at_the_same_moment_page_as_fifty_then_ten_with_no_overlap(self):
        moment = timezone.now()
        for i in range(60):
            PersonEdit.objects.create(email=f"p{i}@example.com", what=PersonEdit.MOBILE, after="07911", by_label="Barry", at=moment)
        first, more = activity.page(filters())
        second, more_after = activity.page(filters(), 50)
        self.assertEqual((len(first), more, len(second), more_after), (50, True, 10, False))
        self.assertEqual(len({r["pk"] for r in first + second}), 60)
        self.assertEqual([r["pk"] for r in first + second], sorted((r["pk"] for r in first + second), reverse=True))  # the database order, so the pages join up

    def test_equal_times_across_sources_also_keep_one_fixed_order_through_the_pages(self):
        moment = timezone.now()
        for i in range(30):
            PersonEdit.objects.create(email=f"p{i}@example.com", what=PersonEdit.MOBILE, after="07911", by_label="Barry", at=moment)
            PersonMessage.objects.create(email=f"m{i}@example.com", text="t", author_label="Barry", sent_at=moment)
        one = activity.page(filters())[0]
        seen = [(r["source"], r["pk"]) for r in one + activity.page(filters(), 50)[0]]
        self.assertEqual((len(seen), len(set(seen))), (60, 60))

    def test_an_older_gold_note_is_counted_once(self):
        gold_services.submit_application(application_data())
        application = GoldApplication.objects.get()
        event = gold_audit.record(application, ApplicationEvent.NOTE_ADDED, actor=self.barry, channel=gold_audit.OFFICE, message="secret")
        StickyNote.objects.create(email=application.email, text="secret", author_label="Barry (barry@example.test)", source_event=uuid.uuid4())  # the copy of that event
        notes = self.by_what("Note added")
        self.assertEqual(len(notes), 1)
        self.assertEqual(dashboard(filters())["series"]["notes"]["total"], 1)
        self.assertEqual([r for r in self.rows() if r["group"] == "gold"], [])

    def test_the_same_person_is_one_entry_however_his_label_was_stored(self):
        user = make_team_member("sam@example.test", levels.ADMIN)
        user.first_name, user.last_name = "Sam", "Hill"
        user.save()
        StickyNote.objects.create(email="a@example.com", text="x", author_label="Sam Hill (sam@example.test)")
        system_audit.log_event(SystemEvent.SALE_RESTORED, user=user, detail={"member": "X"}, sentence="x")  # the audit stores a bare email
        PersonMessage.objects.create(email="a@example.com", text="t", author_label="sam@example.test")
        activity_store.apply()
        with self.assertNumQueries(3):  # the distinct stored labels, the accounts, the team
            choices = activity.staff_choices()
        self.assertEqual(choices, [("sam@example.test", "Sam Hill (sam@example.test)")])
        self.assertEqual(len(self.rows(staff="sam@example.test")), 3)  # the filter matches both forms
        self.assertEqual({r["who"] for r in self.rows()}, {"Sam"})
        self.assertNotIn("staff", dashboard(filters()))  # the Who did what card is gone; the dropdown above reads the stored labels

    def test_an_action_with_no_staff_label_is_left_out_not_shown_as_unknown(self):
        PersonEdit.objects.create(email="a@example.com", what=PersonEdit.MOBILE, after="07911", by_label="")
        StickyNote.objects.create(email="a@example.com", text="x", author_label="")
        PersonMessage.objects.create(email="a@example.com", text="t", author_label="")
        self.assertEqual(self.rows(), [])
        self.assertEqual(dashboard(filters())["total"], 0)
        self.assertNotContains(page(self.dev), "Unknown")

    def test_every_page_is_the_whole_page_with_the_staff_list(self):
        for i in range(60):
            PersonEdit.objects.create(email=f"p{i}@example.com", what=PersonEdit.MOBILE, after="07911", by_label="Barry")
        for query in ("", "?all=1", "?all=1&page=2"):
            whole = page(self.dev, query)
            self.assertIn("staff", whole.context)
            self.assertContains(whole, 'id="f-staff"')
            self.assertContains(whole, 'data-office-charts')


class RangeTests(Base):
    now = london(2026, 11, 11, 15, 0)   # a Wednesday

    def test_the_range_options_and_the_default_come_from_system(self):
        body = page(self.dev).content.decode()
        for value in ("week", "month", "30d", "all"):
            self.assertIn(f'name="range" value="{value}"', body)
        self.assertLess(body.index('value="week"'), body.index('value="month"'))
        self.assertIn('value="week" checked', body)  # the code default
        self.assertEqual(SiteDefaults.code_default("activity_range"), "week")
        SiteDefaults.objects.update_or_create(singleton_key="site", defaults={"activity_range": "month"})
        self.assertIn('value="month" checked', page(self.dev).content.decode())
        self.assertIn('value="30d" checked', page(self.dev, "?range=30d").content.decode())  # asked, and remembered for the next visit

    def test_this_week_starts_monday_midnight_london_and_is_compared_with_last_week_up_to_the_same_weekday(self):
        p = activity.period(filters(range="week"), self.now)
        self.assertEqual((p.start, p.prev_from, p.prev_to), (london(2026, 11, 9), date(2026, 11, 2), date(2026, 11, 4)))  # whole days: Monday to Wednesday against Monday to Wednesday
        sunday = activity.period(filters(range="week"), london(2026, 11, 8, 23, 59))
        self.assertEqual(sunday.start, london(2026, 11, 2))
        monday = activity.period(filters(range="week"), london(2026, 11, 9, 0, 0, 1))
        self.assertEqual(monday.start, london(2026, 11, 9))
        summer = activity.period(filters(range="week"), london(2026, 7, 1, 0, 30))  # British Summer Time: Monday 00:00 London is 23:00 UTC on the Sunday
        self.assertEqual(summer.start, london(2026, 6, 29))
        self.assertEqual(summer.start.astimezone(dt_timezone.utc).hour, 23)

    def test_month_30_days_dates_and_all_time_periods(self):
        month = activity.period(filters(range="month"), london(2026, 3, 31, 12, 0))
        self.assertEqual((month.start, month.prev_from, month.prev_to), (london(2026, 3, 1), date(2026, 2, 1), date(2026, 2, 28)))  # February is shorter: it stops at its end
        month = activity.period(filters(range="month"), self.now)
        self.assertEqual((month.start, month.prev_from, month.prev_to), (london(2026, 11, 1), date(2026, 10, 1), date(2026, 10, 11)))
        thirty = activity.period(filters(range="30d"), self.now)
        self.assertEqual((thirty.start, thirty.prev_from, thirty.prev_to), (london(2026, 10, 13), date(2026, 9, 13), date(2026, 10, 12)))
        custom = activity.period(filters(**{"from": date(2026, 11, 3), "to": date(2026, 11, 5)}), self.now)
        self.assertEqual((custom.name, custom.start, custom.end, custom.prev_from, custom.prev_to), ("custom", london(2026, 11, 3), london(2026, 11, 6), date(2026, 10, 31), date(2026, 11, 2)))
        everything = activity.period(filters(), self.now)
        self.assertEqual((everything.start, everything.has_previous, everything.granularity), (None, False, "week"))

    def test_the_change_compares_like_with_like(self):
        dana = "Dana (dana@example.test)"
        for at in (london(2026, 11, 9, 10), london(2026, 11, 11, 14), london(2026, 11, 11, 16)):  # the last is later today: today counts as a whole day
            PersonEdit.objects.create(email="a@example.com", what=PersonEdit.MOBILE, after="07911", by_label=dana, at=at)
        for at in (london(2026, 11, 3, 10), london(2026, 11, 4, 14, 59),    # last week, up to Wednesday (whole days): counted
                   london(2026, 11, 4, 15, 30), london(2026, 11, 5, 9), london(2026, 11, 1, 9)):  # later on that Wednesday: counted, too; Thursday and the week before: not
            PersonEdit.objects.create(email="a@example.com", what=PersonEdit.MOBILE, after="07911", by_label=dana, at=at)
        data = dashboard(filters(range="week"), self.now)
        self.assertEqual((data["series"]["all"]["total"], data["series"]["all"]["previous_total"]), (3, 3))
        self.assertEqual(data["series"]["leads"]["previous_total"], 3)
        self.assertEqual(office_tags.change_ana(2, 2, "week"), "Same as last week")
        self.assertEqual(office_tags.change_ana(5, 2, "week"), "+3 on last week")
        self.assertEqual(office_tags.change_ana(1, 7, "week"), "6 fewer than last week")
        self.assertEqual(office_tags.change_ana(4, 0, "week"), "+4 on last week")
        self.assertEqual(office_tags.change_ana(4, 1, "custom"), "+3 on the days before")
        self.assertEqual(office_tags.change_ana(4, 1, "all"), "")
        self.assertIsNone(dashboard(filters(), self.now)["series"]["all"]["previous_total"])

    def test_counts_by_staff_and_by_type_match_the_list(self):
        ana, ben = "Ana (ana@example.test)", "ben@example.test"
        for i in range(3):
            StickyNote.objects.create(email=f"n{i}@example.com", text="x", author_label=ana)
        for i in range(2):
            PersonEdit.objects.create(email=f"e{i}@example.com", what=PersonEdit.MOBILE, after="07911", by_label=ana)
            PersonMessage.objects.create(email=f"m{i}@example.com", text="t", author_label=ben)
        data = dashboard(filters())
        rows = activity.page(filters(), size=100)[0]
        self.assertEqual((data["total"], len(rows)), (7, 7))
        by_type = {t["key"]: t["value"] for t in data["types"]}
        self.assertEqual(by_type, {"approvals": 0, "leads": 2, "notes": 3, "emails": 2, "gold": 0, "memberships": 0})
        for key, n in by_type.items():
            self.assertEqual(len([r for r in rows if r["group"] == key]), n)
        for gone in ("staff", "more_staff"):
            self.assertNotIn(gone, data)  # Who did what was replaced by By time
        self.assertNotIn("staff", data["summaries"])
        self.assertEqual([k["key"] for k in data["kpis"]], ["all", "notes", "leads", "emails"])  # the three busiest, ties in table order
        self.assertEqual(dashboard(filters(staff="ben@example.test"))["total"], 2)
        self.assertEqual(dashboard(filters(group="notes"))["total"], 3)

    def test_the_busiest_three_are_filled_in_table_order_when_few_types_have_actions(self):
        PersonMessage.objects.create(email="a@example.com", text="t", author_label="Ben")
        data = dashboard(filters())
        self.assertEqual([k["key"] for k in data["kpis"]], ["all", "emails", "approvals", "leads"])
        self.assertEqual(data["series"]["approvals"]["total"], 0)

    def test_the_day_buckets(self):
        for at in (london(2026, 11, 9, 10), london(2026, 11, 9, 11), london(2026, 11, 11, 14)):
            PersonEdit.objects.create(email="a@example.com", what=PersonEdit.MOBILE, after="07911", by_label="Dana", at=at)
        data = dashboard(filters(range="week"), self.now)
        self.assertEqual(data["labels"], [f"2026-11-{d}" for d in ("09", "10", "11", "12", "13", "14", "15")])  # Monday to Sunday
        self.assertEqual(data["series"]["all"]["values"], [2, 0, 1, 0, 0, 0, 0])
        self.assertEqual(data["granularity"], "day")
        self.assertEqual(data["summaries"]["days"], "3 actions this week. Busiest day: Monday, with 2.")
        self.assertEqual(data["day_counts"], {"2026-11-09": 2, "2026-11-11": 1})
        month = dashboard(filters(range="month"), self.now)
        self.assertEqual((len(month["labels"]), month["labels"][0], month["labels"][-1]), (11, "2026-11-01", "2026-11-11"))

    def test_a_late_evening_in_summer_belongs_to_the_next_london_day(self):
        PersonEdit.objects.create(email="a@example.com", what=PersonEdit.MOBILE, after="07911", by_label="Dana", at=datetime(2026, 7, 1, 23, 30, tzinfo=dt_timezone.utc))  # 00:30 on 2 July in London
        data = dashboard(filters(**{"from": date(2026, 7, 1), "to": date(2026, 7, 3)}), london(2026, 7, 10, 12))
        self.assertEqual(dict(zip(data["labels"], data["series"]["all"]["values"])), {"2026-07-01": 0, "2026-07-02": 1, "2026-07-03": 0})

    def test_all_time_and_long_ranges_group_by_week(self):
        for at in (london(2026, 10, 1, 10), london(2026, 10, 14, 10), london(2026, 11, 11, 10)):
            PersonEdit.objects.create(email="a@example.com", what=PersonEdit.MOBILE, after="07911", by_label="Dana", at=at)
        data = dashboard(filters(), self.now)
        self.assertEqual((data["granularity"], data["labels"][0], data["labels"][-1]), ("week", "2026-09-28", "2026-11-09"))
        self.assertEqual(sum(data["series"]["all"]["values"]), 3)
        self.assertIn("Busiest week: w/c ", data["summaries"]["days"])
        long = dashboard(filters(**{"from": date(2026, 9, 1), "to": date(2026, 11, 11)}), self.now)
        self.assertEqual(long["granularity"], "week")
        short = dashboard(filters(**{"from": date(2026, 10, 12), "to": date(2026, 11, 11)}), self.now)
        self.assertEqual(short["granularity"], "day")  # 31 days

    def test_an_empty_range_says_so_and_the_tiles_show_zero(self):
        body = page(self.dev, "?range=month").content.decode()
        self.assertIn("No staff actions in this range.", body)
        self.assertIn("Nothing happened in this range.", body)
        self.assertIn("See all time", body)
        self.assertIn("No staff activity yet.", page(self.dev, "?range=all").content.decode())
        self.assertIn("Nothing matches that. Try fewer filters.", page(self.dev, "?staff=nobody").content.decode())


class ListTests(Base):
    def test_day_headings_and_the_year(self):
        today = date(2026, 11, 11)
        self.assertEqual([activity.day_heading(d, today) for d in (today, date(2026, 11, 10), date(2026, 11, 9), date(2025, 12, 31))], ["Today", "Yesterday", "Mon 9 Nov", "Wed 31 Dec 2025"])

    def test_rows_are_grouped_by_day_with_the_true_count_and_a_continued_day_has_no_second_heading(self):
        now = timezone.now()
        for at in (now, now - timedelta(seconds=5), now - timedelta(days=1)):
            StickyNote.objects.create(email="a@example.com", text="x", author_label="Dana", created_at=at)
        data = dashboard(filters())
        rows = activity.page(filters(), day_counts=data["day_counts"])[0]
        heads = [(r["heading"]["label"], r["heading"]["count"]) if r["heading"] else None for r in rows]
        today_first = timezone.localtime(now).date() == timezone.localtime(now - timedelta(seconds=5)).date()
        if today_first:
            self.assertEqual(heads, [("Today", 2), None, ("Yesterday", 1)])
        later = activity.page(filters(), after_day=rows[0]["day"])[0]
        self.assertIsNone(later[0]["heading"])  # the next page carries on the same day
        self.assertEqual(rows[0]["time"], timezone.localtime(rows[0]["at"]).strftime("%H:%M"))

    def test_the_sentences(self):
        _, note = outreach.add_note(self.lead_email, self.barry, SECRET_NOTE)
        outreach.edit_note(note, self.barry, "x")
        outreach.archive_lead(self.lead_email, self.barry, "Test lead")
        PersonEdit.objects.create(email=self.lead_email, what=PersonEdit.MOBILE, before="07911111111", after="07922222222", by_label="Barry Hill (barry@example.test)")
        PersonEdit.objects.create(email=self.lead_email, what=PersonEdit.EMAIL, after="new@example.com", by_label="Barry Hill (barry@example.test)")
        PersonMessage.objects.create(email=self.lead_email, text=SECRET_MESSAGE, author_label="Barry Hill (barry@example.test)", status=PersonMessage.FAILED)
        outreach.add_to_list(self.barry, lead_email=self.lead_email)
        rows = {r["what"]: r for r in self.rows()}
        self.assertEqual((rows["Note added"]["before"], rows["Note added"]["after"]), ("added a note on ", ""))
        self.assertEqual(rows["Mobile changed"]["before"] + "P" + rows["Mobile changed"]["after"], "changed the mobile of P")
        self.assertEqual(rows["Email added"]["before"], "added an email for ")
        self.assertEqual(rows["Email failed"]["before"], "tried to email ")
        self.assertEqual(rows["Archived"]["before"], "archived ")
        self.assertEqual(rows["Added to the approach list"]["after"], " to the approach list")
        body = page(self.dev).content.decode()
        for words in ("added a note on", "edited a note on", "archived", "changed the mobile of", "tried to email", "to the approach list", "Did not send", "07911111111 to 07922222222"):
            self.assertIn(words, body)
        self.assertNotIn("Unknown", body)
        self.assertNotIn(SECRET_NOTE, body)
        self.assertNotIn(SECRET_MESSAGE, body)

    def test_membership_gold_and_system_sentences_and_an_unknown_one(self):
        user = user_services.register_interest(cleaned(email="hugo@example.com", plan="tier-2", mobile="07911100001")).user
        approvals.decide(user.pk, "approved", self.barry)
        approvals.decide(user.pk, "waiting", self.barry)
        gold_services.submit_application(application_data())
        application = GoldApplication.objects.get()
        for action in (ApplicationEvent.SENT_FOR_FINAL, ApplicationEvent.INVITE_RESENT, ApplicationEvent.GUIDE_SENT):
            gold_audit.record(application, action, actor=self.barry, channel=gold_audit.OFFICE)
        gold_audit.record(application, ApplicationEvent.RESPONDED, actor=self.barry, channel=gold_audit.OFFICE, meta={"whatsapp": True})
        system_audit.log_event(SystemEvent.SALE_RESTORED, user=self.barry, detail={"member": user.public_id}, sentence="x")
        rows = {r["what"]: r for r in self.rows()}
        self.assertEqual((rows["Approved"]["before"], rows["Undid a decision"]["before"], rows["Undid a decision"]["detail"]), ("approved ", "undid the decision on ", "Was approved"))
        self.assertEqual((rows["Sent a Gold application for final approval"]["before"], rows["Sent a Gold application for final approval"]["after"]), ("sent ", " for final Gold approval"))
        self.assertEqual(rows["Sent a Gold invite again"]["after"], " the Gold invite again")
        self.assertEqual((rows["Sent the Gold guide"]["before"], rows["Sent the Gold guide"]["after"]), ("sent ", " the Gold guide"))
        self.assertEqual((rows["Marked Contacted"]["before"], rows["Marked Contacted"]["after"]), ("marked ", " as contacted"))
        self.assertEqual((rows["Restored a sale price"]["before"], rows["Restored a sale price"]["after"]), ("restored the sale price for ", ""))
        self.assertNotIn("Something new", activity.WORDING)  # an unknown action reads "{staff} · {what} · {person}"
        row = {"what": "Something new"}
        before, after = activity.WORDING.get(row["what"], ("", ""))
        self.assertEqual((before, after), ("", ""))

    def test_a_removed_person_and_a_person_with_a_page(self):
        user = user_services.register_interest(cleaned(email="hugo@example.com", plan="tier-2", mobile="07911100001")).user
        approvals.decide(user.pk, "approved", self.barry)
        body = page(self.dev).content.decode()
        self.assertIn('<a class="o-feed-row"', body)
        self.assertIn(f"/people/{user.pk}/", body)
        self.assertIn('class="o-feed-person"', body)
        system_audit.log_event(SystemEvent.SETUP_CANCELLED, user=self.barry, detail={"member": "GONE0000"}, sentence="x")
        body = page(self.dev).content.decode()
        self.assertIn('<span class="o-unrated">a removed person</span>', body)
        self.assertIn('<div class="o-feed-row"', body)


class ClosedListTests(Base):
    def make(self, n):
        moment = timezone.now()
        for i in range(n):
            PersonEdit.objects.create(email=f"p{i}@example.com", what=PersonEdit.MOBILE, after="07911", by_label="Barry", at=moment - timedelta(seconds=i))

    def parts(self, body):
        top = body.split('data-region="list-top"')[1].split('<div class="o-act-rest"')[0]
        rest = body.split('<div class="o-act-rest"')[1]
        return top, rest

    def test_the_list_card_sits_straight_under_the_tiles_above_the_charts(self):
        body = page(self.dev).content.decode()
        order = [body.index(marker) for marker in ('data-office-kpis', 'id="list"', 'id="days"', 'id="times"', 'id="types"')]
        self.assertEqual(order, sorted(order))

    def test_eight_rows_while_closed_and_see_all_opens_the_rest(self):
        self.make(20)
        response = page(self.dev)
        top, rest = self.parts(response.content.decode())
        self.assertEqual((top.count("data-activity-row"), rest.count("data-activity-row")), (8, 0))   # closed: only the 8 newest are in the page
        self.assertContains(response, 'href="?all=1#list" data-act-toggle data-page-target="#act-list" data-page-scroll="#list">See all</a>')
        self.assertNotContains(response, "pager-list")
        opened = page(self.dev, "?all=1")
        top, rest = self.parts(opened.content.decode())
        self.assertEqual((top.count("data-activity-row"), rest.count("data-activity-row")), (0, 10))   # opened: the page is rows 1 to 10 on its own
        self.assertContains(opened, ">Show less</a>")
        self.assertContains(opened, "pager-list")   # 20 rows: two pages of 10
        self.assertContains(opened, '<input type="hidden" name="all" value="1">', html=False)
        self.assertContains(response, '<span class="o-muted o-list-count" data-region="count-list" data-fade>20</span>')  # the true total

    def test_eight_or_fewer_have_no_see_all(self):
        self.make(8)
        response = page(self.dev)
        self.assertNotContains(response, "data-act-toggle")
        top, rest = self.parts(response.content.decode())
        self.assertEqual((top.count("data-activity-row"), rest.count("data-activity-row")), (8, 0))
        self.make(1)
        self.assertContains(page(self.dev), "data-act-toggle")


class ActivityPagesTests(Base):
    """Opened: the whole list ten rows a page (activity.OPEN_PAGE_SIZE, fixed), the shared pagination under it, the count of pages from the stored total."""
    def setUp(self):
        super().setUp()
        SiteDefaults.objects.update_or_create(singleton_key="site", defaults={"list_page_size": 25})   # the setting no longer decides this list

    def make(self, n):
        moment = timezone.now()
        for i in range(n):
            PersonEdit.objects.create(email=f"p{i}@example.com", what=PersonEdit.MOBILE, after="07911", by_label="Barry", at=moment - timedelta(seconds=i))

    def test_the_open_page_size_is_ten(self):
        self.assertEqual(activity.OPEN_PAGE_SIZE, 10)

    def test_page_one_is_rows_one_to_ten_with_the_pagination(self):
        self.make(70)   # seven pages of 10
        opened = page(self.dev, "?all=1")
        self.assertEqual((len(opened.context["top"]), len(opened.context["rest"])), (0, 10))
        self.assertEqual(opened.context["pager"]["num_pages"], 7)
        self.assertContains(opened, 'aria-label="Activity pages"')
        self.assertContains(opened, 'data-page-target="#act-list" data-page-scroll="#list"')
        self.assertContains(opened, 'aria-current="page"')
        self.assertContains(opened, 'aria-disabled="true">Previous</span>')
        self.assertContains(opened, 'href="?all=1&amp;page=2#list" rel="next">Next</a>')
        closed = page(self.dev)
        self.assertEqual((len(closed.context["top"]), len(closed.context["rest"])), (8, 0))   # closed: the 8 newest, a preview
        self.assertEqual([r["pk"] for r in opened.context["rest"]][:8], [r["pk"] for r in closed.context["top"]])

    def test_the_page_count_is_the_stored_total_over_ten(self):
        for total, pages in ((10, 1), (11, 2), (20, 2), (21, 3)):
            PersonEdit.objects.all().delete()
            self.make(total)
            self.assertEqual(page(self.dev, "?all=1").context["pager"]["num_pages"], pages, total)

    def test_page_two_has_its_own_rows_with_no_overlap_and_a_heading(self):
        self.make(25)
        one, two, three = (page(self.dev, f"?all=1&page={n}") for n in (1, 2, 3))
        self.assertEqual([len(p.context["rest"]) for p in (one, two, three)], [10, 10, 5])
        a, b, c = ([r["pk"] for r in p.context["rest"]] for p in (one, two, three))
        self.assertEqual(len(set(a + b + c)), 25)
        ats = [r["at"] for p in (one, two, three) for r in p.context["rest"]]
        self.assertEqual(ats, sorted(ats, reverse=True))   # one fixed order across the pages
        for p in (one, two, three):
            self.assertIsNotNone(p.context["rest"][0]["heading"])   # a page stands on its own: it starts with its day
        self.assertContains(two, 'aria-disabled="true">Next</span>', count=0)
        self.assertContains(three, 'aria-disabled="true">Next</span>')

    def test_the_links_keep_the_filters_and_all(self):
        self.make(30)
        again = page(self.dev, "?all=1&range=all&group=leads&page=2")
        self.assertContains(again, 'href="?all=1&amp;range=all&amp;group=leads&amp;page=3#list"')
        self.assertContains(again, 'href="?all=1&amp;range=all&amp;group=leads&amp;page=1#list"')
        self.assertNotContains(again, "page=2&amp;page=")
        self.assertEqual(again.context["pager"]["num_pages"], 3)
        other = page(self.dev, "?all=1&range=all&group=notes")   # a type with no rows: nothing to page
        self.assertNotContains(other, "pager-list")
        self.assertContains(other, "Nothing matches that")   # and the empty message still shows

    def test_a_page_past_the_end_is_the_last_page_and_garbage_is_the_first(self):
        self.make(25)
        last = page(self.dev, "?all=1&page=99")
        self.assertEqual((last.context["pager"]["number"], len(last.context["rest"])), (3, 5))
        self.assertEqual(page(self.dev, "?all=1&page=abc").context["pager"]["number"], 1)
        self.assertEqual(page(self.dev, "?all=1&page=0").context["pager"]["number"], 1)

    def test_the_count_comes_from_the_stored_total(self):
        self.make(40)
        activity_store.apply()
        client = Client(HTTP_HOST=OFFICE)
        client.force_login(self.dev)
        with CaptureQueriesContext(connection) as queries:
            opened = client.get("/activity/?all=1")
        self.assertEqual((len(opened.context["rest"]), opened.context["pager"]["num_pages"]), (10, 4))
        self.assertFalse([q["sql"] for q in queries if "COUNT(" in q["sql"].upper() and "outreach_personedit" in q["sql"]])   # no count over the sources

    def test_the_fragment_is_just_the_list_and_the_pager(self):
        self.make(30)
        response = page(self.dev, "?all=1&range=all&page=2&fragment=1")
        body = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "office/_activity_list.html")
        self.assertIn('id="act-list"', body)
        self.assertEqual(body.count("data-activity-row"), 10)
        self.assertIn('href="?all=1&amp;range=all&amp;page=3#list" rel="next">Next</a>', body)
        self.assertNotIn("fragment", "".join(re.findall(r'href="[^"]*"', body)))   # the links never carry it
        for absent in ("<html", "o-filters", 'id="days"', "office-series", "<h1"):
            self.assertNotIn(absent, body)

    def test_see_all_opens_in_place_the_fragments_for_open_page_one_and_closed(self):
        self.make(30)
        opened = page(self.dev, "?all=1&fragment=1").content.decode()
        self.assertEqual(opened.count("data-activity-row"), 10)   # page 1: ten rows, a few more than the closed 8
        self.assertIn("pager-list", opened)
        self.assertIn('data-page-open>Show less</a>', opened)
        self.assertIn('href="?#list" data-act-toggle data-page-target="#act-list"', opened)
        closed = page(self.dev, "?fragment=1").content.decode()
        self.assertEqual(closed.count("data-activity-row"), 8)
        self.assertNotIn("pager-list", closed)
        self.assertIn('href="?all=1#list" data-act-toggle data-page-target="#act-list" data-page-scroll="#list">See all</a>', closed)
        for body in (opened, closed):
            self.assertIn('id="act-list"', body)
            self.assertNotIn("<html", body)
        full = page(self.dev).content.decode()   # the plain link works without script
        self.assertIn('href="?all=1#list" data-act-toggle', full)

    def test_the_fragment_has_the_same_access_check(self):
        self.make(30)
        for level in (levels.ADMIN, levels.OFFICE):
            user = make_team_member(f"frag-{level}@example.test", level)
            refused = page(user, "?all=1&page=2&fragment=1")
            self.assertEqual(refused.status_code, 403, level)
            self.assertNotContains(refused, "act-list", status_code=403)
        anonymous = Client(HTTP_HOST=OFFICE).get("/activity/?all=1&fragment=1")
        self.assertNotEqual(anonymous.status_code, 200)
        self.assertNotIn(b"act-list", anonymous.content)

    def test_see_all_is_a_link_that_works_without_script_and_show_less_goes_back(self):
        self.make(20)
        self.assertContains(page(self.dev, "?all=1&page=1"), 'href="?#list" data-act-toggle data-page-target="#act-list" data-page-scroll="#list" data-page-open>Show less</a>')
        self.assertContains(page(self.dev, "?all=1&range=all&page=2"), 'href="?range=all#list" data-act-toggle data-page-target="#act-list" data-page-scroll="#list" data-page-open>Show less</a>')

    def test_no_pagination_for_one_page_and_none_when_closed(self):
        self.make(30)
        self.assertContains(page(self.dev, "?all=1"), "pager-list")   # 30 rows: three pages of 10
        PersonEdit.objects.all().delete()
        self.make(10)
        self.assertNotContains(page(self.dev, "?all=1"), "pager-list")   # 10 rows: one page
        self.assertNotContains(page(self.dev, "?page=2"), "pager-list")   # closed: the page number means nothing


class StoredTotalsTests(Base):
    now = london(2026, 11, 11, 15, 0)

    def make(self):
        """Actions of three people and four types over six weeks, with some at the London day edges."""
        for who, at in (("Barry (barry@example.test)", london(2026, 11, 11, 9)), ("Barry (barry@example.test)", london(2026, 11, 9, 0, 0, 1)), ("barry@example.test", london(2026, 11, 8, 23, 59)),
                        ("Dana", london(2026, 11, 4, 12)), ("Dana", london(2026, 10, 20, 12)), ("Eli (eli@example.test)", london(2026, 9, 30, 23, 59)), ("Eli (eli@example.test)", london(2026, 10, 1, 0, 0, 1))):
            PersonEdit.objects.create(email="a@example.com", what=PersonEdit.MOBILE, after="07911", by_label=who, at=at)
        for who, at in (("Dana", london(2026, 11, 10, 8)), ("Barry (barry@example.test)", london(2026, 11, 3, 8)), ("Eli (eli@example.test)", london(2026, 10, 25, 8))):
            StickyNote.objects.create(email="a@example.com", text="x", author_label=who, created_at=at)
        PersonMessage.objects.create(email="a@example.com", text="t", author_label="Dana", sent_at=london(2026, 11, 11, 10))
        PersonEdit.objects.create(email="a@example.com", what=PersonEdit.MOBILE, after="07911", by_label=outreach.SELF_LABEL, at=london(2026, 11, 11, 10))  # automatic: never stored

    def test_stored_totals_equal_the_live_counting_for_every_range_staff_and_type(self):
        self.make()
        activity_store.apply()
        for extra in ({"range": "week"}, {"range": "month"}, {"range": "30d"}, {"range": "all"}, {"from": date(2026, 10, 1), "to": date(2026, 11, 4)}, {"from": date(2026, 11, 9)},
                      {"range": "all", "staff": "barry@example.test"}, {"range": "all", "staff": "dana"}, {"range": "30d", "group": "leads"}, {"range": "all", "staff": "eli@example.test", "group": "leads"}):
            f = filters(**extra)
            p = activity.period(f, self.now)
            live = activity._by_day(f, p.start, activity._local(p.day_to, 1) if p.day_to else None)  # the old live counting, over the same whole days
            data = dashboard(f, self.now)
            by_type, by_day = {}, {}
            for group, _label, day, n in live:
                by_type[group] = by_type.get(group, 0) + n
                by_day[day.isoformat()] = by_day.get(day.isoformat(), 0) + n
            self.assertEqual(data["total"], sum(by_type.values()), extra)
            self.assertEqual({g: data["series"][g]["total"] for g, _ in activity.GROUPS if data["series"][g]["total"]}, by_type, extra)
            self.assertEqual(data["day_counts"], by_day, extra)
            if p.has_previous:
                before = activity._by_day(f, activity._local(p.prev_from), activity._local(p.prev_to, 1))
                self.assertEqual(data["series"]["all"]["previous_total"], sum(n for *_, n in before), extra)
        self.assertEqual(sorted(k for k, _ in activity.staff_choices()), ["barry@example.test", "dana", "eli@example.test"])  # a bare email and "Name (email)" are one person
        self.assertEqual(ActivityDay.objects.filter(staff_key="barry@example.test", group="leads").count(), 3)  # 8, 9 and 11 Nov: the bare email and "Name (email)" are one person

    def test_london_day_edges(self):
        for at in (london(2026, 6, 30, 23, 59), london(2026, 7, 1, 0, 0, 1), london(2026, 3, 29, 0, 30), london(2026, 3, 28, 23, 30)):  # summer time, and the night the clocks go forward
            PersonEdit.objects.create(email="a@example.com", what=PersonEdit.MOBILE, after="07911", by_label="Dana", at=at)
        activity_store.apply()
        self.assertEqual(sorted(ActivityDay.objects.values_list("day", flat=True)), [date(2026, 3, 28), date(2026, 3, 29), date(2026, 6, 30), date(2026, 7, 1)])
        self.assertEqual(activity_store.wanted(date(2026, 7, 1), date(2026, 7, 1)).keys(), {(date(2026, 7, 1), "leads", "dana")})

    def test_a_new_action_shows_after_a_refresh_and_not_before(self):
        self.assertEqual(dashboard(filters())["total"], 0)
        outreach.add_note(self.lead_email, self.barry, "x")
        self.assertEqual(activity.dashboard(filters())["total"], 0)  # stored: the page does not count the sources
        snapshots.build_everything()  # the hourly roll-up and the queued job both end here
        data = activity.dashboard(filters())
        self.assertEqual((data["total"], data["series"]["notes"]["total"]), (1, 1))
        self.assertEqual(activity.staff_choices(), [("barry@example.test", "barry@example.test")])  # his account has no name yet: the label is his email

    def test_only_today_and_yesterday_are_recounted_in_the_refresh_and_the_rebuild_does_the_rest(self):
        now = timezone.now()
        PersonEdit.objects.create(email="a@example.com", what=PersonEdit.MOBILE, after="07911", by_label="Dana", at=now - timedelta(days=10))
        PersonEdit.objects.create(email="a@example.com", what=PersonEdit.MOBILE, after="07911", by_label="Dana", at=now)
        activity_store.refresh_recent()
        self.assertEqual(ActivityDay.objects.count(), 1)
        call_command("rebuild_activity", stdout=StringIO())
        self.assertEqual(ActivityDay.objects.count(), 2)
        PersonEdit.objects.all().delete()  # every action erased: a plain rebuild refuses to wipe the totals (the safeguard), --allow-empty clears them
        call_command("rebuild_activity", stdout=StringIO())
        self.assertEqual(ActivityDay.objects.count(), 2)
        call_command("rebuild_activity", "--allow-empty", stdout=StringIO())
        self.assertEqual(ActivityDay.objects.count(), 0)

    def test_rebuild_dry_run_writes_nothing_and_shows_every_row_then_a_real_run_and_a_second_one(self):
        self.make()
        ActivityDay.objects.create(day=date(2020, 1, 1), group="notes", staff_key="old", staff_label="Old Person (old@example.com)", count=5)  # stale: to remove
        stale = ActivityDay.objects.create(day=date(2020, 1, 2), group="leads", staff_key="old2", staff_label="Old Two", count=1)
        before = list(ActivityDay.objects.order_by("pk").values_list("pk", "day", "group", "staff_key", "count"))
        out = StringIO()
        call_command("rebuild_activity", "--dry-run", stdout=out)
        text = out.getvalue()
        self.assertEqual(list(ActivityDay.objects.order_by("pk").values_list("pk", "day", "group", "staff_key", "count")), before)  # nothing written
        self.assertIn("DRY RUN: this only reads. Nothing will be changed.", text)
        self.assertRegex(text, r"Rows to add: [1-9]")
        self.assertIn("Rows to remove: 2", text)
        self.assertIn("1 Jan 2020 · Notes · Old Person: 5 → removed", text)  # day · type · staff: before → after, no email
        self.assertIn("2 Jan 2020 · Leads · Old Two: 1 → removed", text)
        self.assertRegex(text, r"\d{1,2} \w{3} \d{4} · \w+ · [^:]+: none → \d+")
        self.assertNotIn("@", text)
        self.assertIn("BY TYPE", text)
        self.assertIn("BY STAFF", text)
        self.assertIn("DAYS COVERED", text)
        self.assertIn("python manage.py rebuild_activity", text)
        short = StringIO()
        call_command("rebuild_activity", "--dry-run", "--summary", stdout=short)
        self.assertNotIn("EVERY ROW", short.getvalue())
        self.assertIn("Rows to remove: 2", short.getvalue())
        done = StringIO()
        call_command("rebuild_activity", stdout=done)
        self.assertIn("1 Jan 2020 · Notes · Old Person: 5 → removed", done.getvalue())
        self.assertIn("DONE", done.getvalue())
        self.assertFalse(ActivityDay.objects.filter(pk=stale.pk).exists())
        self.assertGreater(ActivityDay.objects.count(), 5)
        again = StringIO()
        call_command("rebuild_activity", stdout=again)
        self.assertIn("Nothing changed", again.getvalue())
        self.assertIn("Rows added: 0", again.getvalue())

    def test_the_page_makes_no_count_query_on_the_source_tables(self):
        self.make()
        activity_store.apply()
        client = Client(HTTP_HOST=OFFICE)
        client.force_login(self.dev)
        for query in ("", "?range=all", "?range=all&staff=dana&group=notes"):
            with CaptureQueriesContext(connection) as queries:
                self.assertEqual(client.get(f"/activity/{query}").status_code, 200)
            sql = [q["sql"] for q in queries]
            self.assertFalse([q for q in sql if "COUNT(" in q.upper() and "activitydays" not in q.lower() and "office_activityday" not in q.lower()], query)
            self.assertFalse([q for q in sql if " UNION " in q.upper()], query)  # the old staff list
            grouped = [q for q in sql if "GROUP BY" in q.upper()]
            self.assertTrue(all("office_activityday" in q or "office_activitytimeofday" in q for q in grouped), grouped)  # the only grouped sums are over the stored totals
            self.assertEqual(len([q for q in sql if "office_activitytimeofday" in q]), 1)  # By time adds one small read
            self.assertTrue(any("office_activityday" in q for q in sql))


class RefreshRequestTests(Base):
    def test_every_action_that_adds_a_row_to_a_source_asks_for_the_refresh(self):
        user = user_services.register_interest(cleaned(email="hugo@example.com", plan="tier-2", mobile="07911100001")).user
        gold_services.submit_application(application_data())
        application = GoldApplication.objects.get()
        _, note = outreach.add_note(self.lead_email, self.barry, "x")
        entry = outreach.add_to_list(self.barry, lead_email=self.lead_email)[1]
        actions = {
            "note": lambda: outreach.add_note(self.lead_email, self.barry, "y"),
            "note edit": lambda: outreach.edit_note(note, self.barry, "z"),
            "note delete": lambda: outreach.delete_note(note, self.barry),
            "lead edit": lambda: outreach._edit(self.lead_email, PersonEdit.FIRST_NAME, "", "Hugh", self.barry),
            "archive": lambda: outreach.archive_lead(self.lead_email, self.barry, "r"),
            "approach list done": lambda: outreach.mark_done(entry, self.barry),
            "email": lambda: PersonMessage.objects.create(email=self.lead_email, text="t", author=self.barry, author_label="Barry (barry@example.test)"),
            "approval": lambda: approvals.decide(user.pk, "approved", self.barry),
            "gold": lambda: gold_audit.record(application, ApplicationEvent.APPROVED, actor=self.barry, channel=gold_audit.OFFICE),
            "membership": lambda: system_audit.log_event(SystemEvent.SETUP_MANUAL, user=self.barry, detail={"plan": "tier-2", "member": user.public_id}, sentence="x"),
        }
        for name, act in actions.items():
            with mock.patch.object(snapshots, "_queue") as queue, self.captureOnCommitCallbacks(execute=True):
                act()
            self.assertTrue(queue.called, name)

    def test_automatic_rows_and_other_system_events_do_not_ask(self):
        with mock.patch.object(snapshots, "_queue") as queue, self.captureOnCommitCallbacks(execute=True):
            PersonEdit.objects.create(email="a@example.com", what=PersonEdit.MOBILE, after="07911", by_label=outreach.SELF_LABEL)
            system_audit.log_event(SystemEvent.PAYMENTS_OPENED, user=self.barry, sentence="x")
        self.assertFalse(queue.called)


class OffsetPagingTests(Base):
    def make(self, n=120):
        now = timezone.now()
        for i in range(n):
            StickyNote.objects.create(email=f"p{i}@example.com", text="x", author_label="Barry", created_at=now - timedelta(minutes=i + 1))
        return now

    def test_the_pages_walk_every_row_once_in_one_order(self):
        self.make(230)
        seen = []
        for number in range(5):
            rows, more = activity.page(filters(), offset=number * 50)
            seen += [(r["source"], r["pk"]) for r in rows]
            self.assertEqual(more, number < 4)
        self.assertEqual((len(seen), len(set(seen))), (230, 230))

    def test_a_deep_page_reads_only_the_rows_it_needs(self):
        self.make(120)
        with CaptureQueriesContext(connection) as queries:
            rows, more = activity.page(filters(), offset=100, size=10)
        self.assertEqual((len(rows), more), (10, True))
        self.assertTrue(all("LIMIT 111" in q["sql"] for q in queries if "stickynote" in q["sql"].lower() and "SELECT" in q["sql"][:8]))   # offset + size + 1 from each source

    def test_a_page_past_the_end_is_empty_in_the_helper(self):
        self.make(5)
        self.assertEqual(activity.page(filters(), offset=100), ([], False))


class StaleDayTests(Base):
    def quiet(self):
        """A test's own transaction never commits, so callbacks from its set-up would stay queued and hide the one under test: drop them."""
        connection.run_on_commit.clear()
        signals._local.days = set()

    def total(self, moment):
        return sum(ActivityDay.objects.filter(day=timezone.localtime(moment).date()).values_list("count", flat=True))

    def run_refresh(self, act):
        self.quiet()
        with self.captureOnCommitCallbacks(execute=True):
            act()
        activity_store.refresh_recent()

    def test_deleting_an_old_row_lowers_that_days_stored_count_after_a_refresh(self):
        old = timezone.now() - timedelta(days=9)
        for i in range(3):
            OutreachEntry.objects.create(lead_email=f"l{i}@example.com", added_by_label="Barry (barry@example.test)", added_at=old)
        activity_store.apply()
        day = timezone.localtime(old).date()
        self.assertEqual(ActivityDay.objects.get(day=day).count, 3)
        self.run_refresh(lambda: OutreachEntry.objects.filter(lead_email="l0@example.com").delete())  # removed from the approach list: its "Added" row goes
        self.assertEqual(ActivityDay.objects.get(day=day).count, 2)
        self.assertFalse(ActivityDirtyDay.objects.exists())  # cleared once recounted

    def test_a_backdated_save_and_a_moved_time_recount_their_days(self):
        old, older = timezone.now() - timedelta(days=9), timezone.now() - timedelta(days=20)
        self.run_refresh(lambda: StickyNote.objects.create(email="a@example.com", text="x", author_label="Dana", created_at=old))
        self.assertEqual(self.total(old), 1)
        edit = PersonEdit.objects.create(email="a@example.com", what=PersonEdit.MOBILE, after="07911", by_label="Dana", at=old)
        activity_store.apply()
        self.assertEqual(self.total(old), 2)

        def move():
            edit.at = older
            edit.save()
        self.run_refresh(move)
        self.assertEqual(self.total(old), 1)  # the note only: the edit left
        self.assertEqual(self.total(older), 1)

    def test_a_burst_of_deletes_marks_each_day_once_and_recounts_nothing_in_the_request(self):
        old = timezone.now() - timedelta(days=9)
        for i in range(20):
            StickyNote.objects.create(email=f"p{i}@example.com", text="x", author_label="Dana", created_at=old)
        activity_store.apply()
        self.quiet()
        with mock.patch.object(activity_store, "apply") as recount, mock.patch.object(snapshots, "_queue"), self.captureOnCommitCallbacks(execute=True):
            StickyNote.objects.all().delete()
        self.assertFalse(recount.called)
        self.assertEqual(list(ActivityDirtyDay.objects.values_list("day", flat=True)), [timezone.localtime(old).date()])

    def test_todays_rows_are_not_marked(self):
        self.quiet()
        with self.captureOnCommitCallbacks(execute=True):
            StickyNote.objects.create(email="a@example.com", text="x", author_label="Dana")
        self.assertFalse(ActivityDirtyDay.objects.exists())


class RecountSafeguardTests(TestCase):
    """A long recount that finds nothing while totals are stored deletes nothing (Moishe: never delete unless there is a new one)."""

    def test_an_empty_full_recount_keeps_the_stored_totals(self):
        from datetime import date
        from unittest import mock

        from office import activity_store
        from office.models import ActivityDay

        ActivityDay.objects.create(day=date(2026, 11, 1), group="notes", staff_key="barry@example.com", staff_label="Barry", count=3)
        with mock.patch.object(activity_store, "wanted", return_value={}), self.assertLogs("spa99.activity", "WARNING"):
            self.assertEqual(activity_store.apply(), (0, 0, 0))
        self.assertEqual(ActivityDay.objects.count(), 1)

    def test_a_single_day_that_really_emptied_is_cleared(self):
        from datetime import date
        from unittest import mock

        from office import activity_store
        from office.models import ActivityDay

        day = date(2026, 11, 1)
        ActivityDay.objects.create(day=day, group="notes", staff_key="barry@example.com", staff_label="Barry", count=1)
        with mock.patch.object(activity_store, "wanted", return_value={}):
            self.assertEqual(activity_store.apply(day, day), (0, 0, 1))
        self.assertEqual(ActivityDay.objects.count(), 0)


class SignalSafetyTests(TestCase):
    """The Activity bookkeeping can never turn a staff action's save into an error."""

    def test_a_failing_mark_still_saves_the_note(self):
        from unittest import mock

        from outreach.models import StickyNote

        with mock.patch("office.models.ActivityDirtyDay.objects") as broken, self.assertLogs("spa99.activity", "ERROR"), self.captureOnCommitCallbacks(execute=True):
            broken.filter.side_effect = RuntimeError("database down")
            note = StickyNote.objects.create(email="safe@example.com", text="x", author_label="Barry", created_at=timezone.now() - timedelta(days=10))
        self.assertTrue(StickyNote.objects.filter(pk=note.pk).exists())



class ByTimeTests(Base):
    """The By time ring: the four parts of the London day, from the stored ActivityTimeOfDay rows."""

    def edit(self, at, who="Dana"):
        PersonEdit.objects.create(email="a@example.com", what=PersonEdit.MOBILE, after="07911", by_label=who, at=at)

    def parts(self):
        out = {}
        for d, p, n in ActivityTimeOfDay.objects.values_list("day", "part", "count"):
            out[(d, p)] = out.get((d, p), 0) + n
        return out

    def test_the_part_edges_in_london_time_on_a_summer_and_a_winter_date(self):
        for day in (date(2026, 7, 14), date(2026, 1, 14)):  # BST and GMT: the wall clock decides, not UTC
            for hour, minute in ((5, 59), (6, 0), (11, 59), (12, 0), (16, 59), (17, 0), (21, 59), (22, 0)):
                self.edit(london(day.year, day.month, day.day, hour, minute))
        activity_store.apply()
        for day in (date(2026, 7, 14), date(2026, 1, 14)):
            self.assertEqual({p: self.parts()[(day, p)] for p in ("morning", "afternoon", "evening", "night")}, {"night": 2, "morning": 2, "afternoon": 2, "evening": 2}, day)
        self.assertEqual({activity.part_of_hour(h) for h in (0, 5, 22, 23)}, {"night"})
        self.assertEqual([activity.part_of_hour(h) for h in (6, 11, 12, 16, 17, 21)], ["morning", "morning", "afternoon", "afternoon", "evening", "evening"])

    def test_a_late_summer_action_is_the_london_hour_not_the_utc_hour(self):
        self.edit(london(2026, 7, 14, 22, 30))  # 21:30 UTC, but 22:30 in London: night, on the 14th
        self.edit(london(2026, 7, 14, 0, 30))   # 23:30 UTC on the 13th, but London's 14th: night of the 14th
        activity_store.apply()
        self.assertEqual(self.parts(), {(date(2026, 7, 14), "night"): 2})

    def test_clock_change_days_keep_the_london_day_and_hour(self):
        self.edit(datetime(2026, 3, 29, 1, 30, tzinfo=dt_timezone.utc))   # spring forward: 02:30 BST on the 29th, night
        self.edit(datetime(2026, 10, 25, 0, 30, tzinfo=dt_timezone.utc))  # fall back: 01:30 BST on the 25th, night
        self.edit(datetime(2026, 10, 25, 1, 30, tzinfo=dt_timezone.utc))  # 01:30 GMT on the 25th, night again
        self.edit(datetime(2026, 10, 25, 6, 0, tzinfo=dt_timezone.utc))   # 06:00 GMT: morning
        activity_store.apply()
        self.assertEqual(self.parts(), {(date(2026, 3, 29), "night"): 1, (date(2026, 10, 25), "night"): 2, (date(2026, 10, 25), "morning"): 1})

    def test_the_ring_centre_is_the_busiest_part_a_tie_goes_earlier_and_empty_has_none(self):
        self.assertEqual(dashboard(filters())["busiest_part"], "")  # empty: the centre says 0 actions
        self.edit(london(2026, 11, 5, 9))
        self.edit(london(2026, 11, 5, 19))
        activity_store.apply()
        self.assertEqual(dashboard(filters())["busiest_part"], "Morning")  # one each: the earlier part wins
        self.edit(london(2026, 11, 5, 20))
        activity_store.apply()
        self.assertEqual(dashboard(filters())["busiest_part"], "Evening")

    def test_the_store_writes_and_recounts_the_time_table_and_leaves_matching_rows_alone(self):
        self.edit(london(2026, 11, 5, 13), "Barry (barry@example.test)")
        StickyNote.objects.create(email="a@example.com", text="x", author_label="barry@example.test", created_at=london(2026, 11, 5, 14))
        self.assertEqual(activity_store.apply_both(), ((2, 0, 0), (2, 0, 0)))  # by type: leads and notes; by time: the same two rows
        self.assertEqual(self.parts(), {(date(2026, 11, 5), "afternoon"): 2})
        self.assertEqual(ActivityTimeOfDay.objects.count(), 2)
        pk = ActivityTimeOfDay.objects.first().pk
        self.assertEqual(activity_store.apply_both(), ((0, 0, 0), (0, 0, 0)))
        self.assertEqual(ActivityTimeOfDay.objects.first().pk, pk)  # untouched
        self.edit(london(2026, 11, 5, 23), "Barry (barry@example.test)")
        activity_store.apply_both()
        self.assertEqual(self.parts(), {(date(2026, 11, 5), "afternoon"): 2, (date(2026, 11, 5), "night"): 1})
        PersonEdit.objects.filter(at=london(2026, 11, 5, 23)).delete()
        activity_store.refresh_recent(date(2026, 11, 6))  # a recount of today and yesterday takes the stale night row away
        self.assertEqual(self.parts(), {(date(2026, 11, 5), "afternoon"): 2})

    def test_the_ring_obeys_the_staff_type_and_date_filters_and_says_where_most_happens(self):
        for hour in (13, 14, 15):
            self.edit(london(2026, 11, 5, hour), "Barry (barry@example.test)")
        self.edit(london(2026, 11, 5, 8), "Barry (barry@example.test)")
        StickyNote.objects.create(email="a@example.com", text="x", author_label="Dana", created_at=london(2026, 11, 5, 9))
        StickyNote.objects.create(email="a@example.com", text="x", author_label="Dana", created_at=london(2026, 10, 1, 23))
        data = dashboard(filters())
        self.assertEqual([(t["key"], t["value"]) for t in data["times"]], [("morning", 2), ("afternoon", 3), ("evening", 0), ("night", 1)])
        self.assertEqual((data["times_total"], data["total"]), (6, 6))
        self.assertEqual(data["summaries"]["times"], "Most of it happens in the afternoon: 3 of 6.")
        self.assertEqual(data["busiest_part"], "Afternoon")  # the ring centre (Moishe 2026-11-13: not the By type total)
        self.assertEqual([t["value"] for t in dashboard(filters(staff="barry@example.test"))["times"]], [1, 3, 0, 0])
        self.assertEqual([t["value"] for t in dashboard(filters(group="notes"))["times"]], [1, 0, 0, 1])
        self.assertEqual([t["value"] for t in dashboard(filters(**{"from": date(2026, 11, 1), "to": date(2026, 11, 30)}))["times"]], [2, 3, 0, 0])
        self.assertEqual(sum(t["share_bp"] for t in data["times"]), 10000)
        empty = dashboard(filters(staff="nobody"))
        self.assertEqual((empty["times_total"], empty["times_empty"], empty["summaries"]["times"]), (0, True, "No staff actions in this range."))

    def test_the_page_has_by_time_and_no_who_did_what(self):
        self.edit(london(2026, 11, 5, 13))
        body = page(self.dev).content.decode()
        self.assertIn('id="times"', body)
        self.assertIn("By time", body)
        self.assertNotIn("Who did what", body)
        self.assertNotIn('id="staff"', body)
        self.assertIn('"times"', body)  # in the chart data

    def test_dry_run_writes_nothing_shows_each_time_row_then_the_real_run_and_a_second_one_say_so(self):
        self.edit(london(2026, 11, 5, 13), "Barry Lobenstein (barry@example.test)")
        activity_store.apply()
        ActivityTimeOfDay.objects.filter(part="afternoon").update(count=20)  # wrong: to change
        ActivityTimeOfDay.objects.create(day=date(2020, 1, 1), part="night", group="notes", staff_key="barry@example.test", count=4)  # stale: to remove
        ActivityDay.objects.create(day=date(2020, 1, 1), group="notes", staff_key="barry@example.test", staff_label="Barry Lobenstein (barry@example.test)", count=4)  # so the days have a change too
        before = list(ActivityTimeOfDay.objects.order_by("pk").values_list("pk", "day", "part", "count"))
        out = StringIO()
        call_command("rebuild_activity", "--dry-run", stdout=out)
        text = out.getvalue()
        self.assertEqual(list(ActivityTimeOfDay.objects.order_by("pk").values_list("pk", "day", "part", "count")), before)  # nothing written
        self.assertIn("5 Nov 2026 · Afternoon · Leads · Barry Lobenstein: 20 → 1", text)
        self.assertIn("1 Jan 2020 · Night · Notes · Barry Lobenstein: 4 → removed", text)  # the name of a removed row comes from the stored day labels
        self.assertIn("BY TIME (actions stored, old total → new total)", text)
        self.assertIn("Afternoon: 20 → 1", text)
        self.assertIn("Night: 4 → 0", text)
        self.assertLess(text.index("BY STAFF"), text.index("EVERY ROW BY TIME"))  # its own section, after the existing ones
        self.assertNotIn("@", text)
        short = StringIO()
        call_command("rebuild_activity", "--dry-run", "--summary", stdout=short)
        self.assertIn("TOTALS BY TIME", short.getvalue())
        self.assertNotIn("EVERY ROW BY TIME", short.getvalue())
        done = StringIO()
        call_command("rebuild_activity", stdout=done)
        self.assertIn("1 Jan 2020 · Night · Notes · Barry Lobenstein: 4 → removed", done.getvalue())
        self.assertEqual(self.parts(), {(date(2026, 11, 5), "afternoon"): 1})
        again = StringIO()
        call_command("rebuild_activity", stdout=again)
        self.assertIn("Nothing changed", again.getvalue())

    def test_a_first_run_that_only_has_time_rows_to_add_is_not_called_nothing_changed(self):
        self.edit(london(2026, 11, 5, 13))
        activity_store.apply()
        ActivityTimeOfDay.objects.all().delete()  # the state just after deploying the new table
        out = StringIO()
        call_command("rebuild_activity", "--dry-run", stdout=out)
        self.assertNotIn("Nothing would change", out.getvalue())
        self.assertIn("5 Nov 2026 · Afternoon · Leads · Dana: none → 1", out.getvalue())

    def test_the_no_wipe_guard_covers_the_time_table_and_allow_empty_clears_it(self):
        self.edit(london(2026, 11, 5, 13))
        activity_store.apply()
        PersonEdit.objects.all().delete()
        with self.assertLogs("spa99.activity", "WARNING") as logs:
            self.assertEqual(activity_store.apply_both(), ((0, 0, 0), (0, 0, 0)))
        self.assertTrue(any("office_activitytimeofday" in line for line in logs.output))
        self.assertEqual(ActivityTimeOfDay.objects.count(), 1)
        text = StringIO()
        call_command("rebuild_activity", "--dry-run", stdout=text)
        self.assertIn("SAFEGUARD (by time)", text.getvalue())
        call_command("rebuild_activity", "--allow-empty", stdout=StringIO())
        self.assertEqual(ActivityTimeOfDay.objects.count(), 0)
        self.assertEqual(ActivityDay.objects.count(), 0)

    def test_an_error_while_counting_the_time_table_writes_nothing_in_either_table(self):
        self.edit(london(2026, 11, 5, 13))
        with mock.patch.object(activity_store, "wanted_time", side_effect=RuntimeError("boom")), self.assertRaises(RuntimeError):
            activity_store.apply_both()
        self.assertEqual((ActivityDay.objects.count(), ActivityTimeOfDay.objects.count()), (0, 0))
