"""The approach list keeps its history: removing someone marks the row removed (never deletes it), every list ignores removed rows, Activity still shows Added, Marked done and
Removed, and only erasing a person deletes."""
from django.test import Client

from mailings import segments
from office import activity_store
from office.models import ActivityDay
from office.tests.test_activity import Base
from office.tests.test_office import OFFICE
from office.tests.test_leads import lead, verify
from outreach import listing, services
from outreach.models import ArchivedLead, OutreachEntry
from users import services as user_services
from users.tests.test_register import cleaned

EMAIL = "hugo@example.com"


class ApproachHistoryTests(Base):
    def add(self, email=EMAIL):
        result, entry = services.add_to_list(self.barry, lead_email=email, reason="Met at the fair")
        self.assertEqual(result, services.DONE)
        return entry

    def test_remove_keeps_the_row_and_every_list_ignores_it(self):
        entry = self.add()
        services.mark_done(entry, self.barry)
        self.add()  # a done entry no longer blocks a new open one
        open_entry = OutreachEntry.objects.get(done_at__isnull=True)
        services.remove_entry(open_entry, self.barry)
        open_entry.refresh_from_db()
        self.assertIsNotNone(open_entry.removed_at)
        self.assertEqual((open_entry.removed_by, open_entry.removed_by_label), (self.barry, services.label(self.barry)))
        self.assertEqual(OutreachEntry.objects.count(), 2)
        self.assertEqual(listing.counts(), {"open": 0, "done": 1})
        self.assertEqual(list(listing.queryset(listing.OPEN)), [])
        self.assertFalse(services.open_entries({EMAIL}, None, None).exists())
        self.assertEqual(services.approach_entries(EMAIL).count(), 1)  # only the done row still keeps him out of Leads
        whats = [r["what"] for r in self.rows()]
        self.assertEqual(whats.count("Added to the approach list"), 2)
        self.assertEqual(whats.count("Marked done on the approach list"), 1)
        removed = self.by_what("Removed from the approach list")
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0]["after"], " from the approach list")

    def test_re_adding_a_removed_person_works_and_keeps_the_old_row(self):
        old = self.add()
        services.remove_entry(old, self.barry)
        new = self.add()
        self.assertNotEqual(old.pk, new.pk)
        self.assertEqual(OutreachEntry.objects.count(), 2)
        self.assertEqual(services.add_to_list(self.barry, lead_email=EMAIL)[0], services.ALREADY)
        self.assertEqual(listing.counts()["open"], 1)

    def test_archive_takes_him_off_the_list_and_unarchive_does_not_bring_the_row_back(self):
        self.add()
        entry = OutreachEntry.objects.get()
        services.entry_archive(entry, self.barry, "Not real")
        entry.refresh_from_db()
        self.assertIsNotNone(entry.removed_at)
        self.assertEqual(listing.counts(), {"open": 0, "done": 0})
        self.assertTrue(ArchivedLead.objects.filter(email=EMAIL).exists())
        services.unarchive_lead(EMAIL, self.barry)
        entry.refresh_from_db()
        self.assertIsNotNone(entry.removed_at)  # back in Leads, not back on the list
        self.assertFalse(services.approach_entries(EMAIL).exists())

    def test_back_to_leads_marks_every_row_for_him_removed(self):
        entry = self.add()
        services.mark_done(entry, self.barry)
        self.add()
        services.entry_to_leads(OutreachEntry.objects.get(done_at__isnull=True), self.barry)
        self.assertFalse(OutreachEntry.objects.filter(removed_at__isnull=True).exists())
        self.assertEqual(OutreachEntry.objects.count(), 2)

    def test_erasing_a_person_still_deletes_every_row_removed_ones_too(self):
        removed = self.add()
        services.remove_entry(removed, self.barry)
        self.add()
        services.erase_email(EMAIL)
        self.assertEqual(OutreachEntry.objects.count(), 0)

    def test_registering_leaves_the_row_and_activity_still_shows_added(self):
        lead(EMAIL)
        self.add()
        user = user_services.register_interest(cleaned(email=EMAIL)).user
        verify(user)
        self.assertEqual(OutreachEntry.objects.count(), 1)  # nothing deleted or rewritten
        self.assertEqual(listing.counts(), {"open": 0, "done": 0})  # he has left the list
        self.assertEqual(len(self.by_what("Added to the approach list")), 1)


class OneLinePerClickTests(Base):
    """Each click is one Activity line, live and in the stored daily totals, even when the lead also has an older Done row."""

    def leads_total(self):
        activity_store.apply()
        return sum(ActivityDay.objects.filter(staff_key="barry@example.test", group="leads").values_list("count", flat=True))

    def lead_with_done_and_open_rows(self):
        entry = services.add_to_list(self.barry, lead_email=EMAIL)[1]
        services.mark_done(entry, self.barry)
        return services.add_to_list(self.barry, lead_email=EMAIL)[1]

    def test_remove_is_one_line_and_only_the_clicked_row_is_labelled(self):
        open_entry = self.lead_with_done_and_open_rows()
        before = self.leads_total()
        services.remove_entry(open_entry, self.barry)
        self.assertEqual(self.leads_total() - before, 1)
        self.assertEqual(len(self.by_what("Removed from the approach list")), 1)

    def test_back_to_leads_is_one_line_and_the_older_done_row_goes_quietly(self):
        open_entry = self.lead_with_done_and_open_rows()
        before = self.leads_total()
        services.entry_to_leads(open_entry, self.barry)
        self.assertEqual(self.leads_total() - before, 1)
        self.assertEqual(OutreachEntry.objects.filter(removed_at__isnull=False).count(), 2)
        self.assertEqual(OutreachEntry.objects.filter(removed_by_label="").count(), 1)  # the quiet one: removed_at only
        self.assertEqual(len(self.by_what("Removed from the approach list")), 1)

    def test_archive_from_the_list_is_only_the_archived_line(self):
        open_entry = self.lead_with_done_and_open_rows()
        before = self.leads_total()
        services.entry_archive(open_entry, self.barry, "Not real")
        self.assertEqual(self.leads_total() - before, 1)
        self.assertEqual(self.by_what("Removed from the approach list"), [])
        self.assertEqual(len(self.by_what("Archived")), 1)
        self.assertEqual(OutreachEntry.objects.filter(removed_at__isnull=False, removed_by_label="").count(), 2)

    def test_a_second_remove_cannot_overwrite_who_removed_it(self):
        entry = self.add_entry()
        services.remove_entry(entry, self.barry)
        services.remove_entry(entry, self.dev)
        entry.refresh_from_db()
        self.assertEqual(entry.removed_by, self.barry)

    def add_entry(self):
        return services.add_to_list(self.barry, lead_email=EMAIL)[1]

    def test_the_buttons_404_on_a_removed_row_and_the_lead_is_back_in_group_email_segments(self):
        lead(EMAIL)
        entry = self.add_entry()
        self.assertNotIn(EMAIL, [s.lead_email for s in segments._leads({})])  # on the list: not in the segment
        services.remove_entry(entry, self.barry)
        self.assertIn(EMAIL, [s.lead_email for s in segments._leads({})])
        client = Client(HTTP_HOST=OFFICE)
        client.force_login(self.barry)
        for action in ("done", "remove", "to-leads", "archive"):
            self.assertEqual(client.post(f"/outreach/{entry.pk}/{action}/").status_code, 404, action)
