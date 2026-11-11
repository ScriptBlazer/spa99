"""Leads > Possible fakes (docs/features/office-2.md): a permanent bounce puts a lead in the tab, Mark as genuine takes him out for good."""
from unittest import mock

from notifications import suppression
from notifications.models import EmailSuppression
from office import counts
from office.tests.test_leads import lead
from office.tests.test_office2 import Base, call
from outreach import services as outreach
from outreach.models import ArchivedLead, GenuineLead, LeadArchiveEvent


class PossibleFakesTests(Base):
    def rows(self, view=""):
        return sorted(r["email"] for r in call(self.reader, "get", f"/leads/?view={view}" if view else "/leads/").context["rows"])

    def bounce(self, email):
        suppression.add(email, EmailSuppression.HARD_BOUNCE)

    def test_a_bounced_lead_is_only_in_the_fakes_tab_a_complaint_does_not_count_and_archived_wins(self):
        lead("a@example.com"), lead("b@example.com"), lead("c@example.com")
        self.bounce("a@example.com")
        suppression.add("b@example.com", EmailSuppression.COMPLAINT)
        self.assertEqual((self.rows(), self.rows("fakes")), (["b@example.com", "c@example.com"], ["a@example.com"]))
        outreach.archive_lead("a@example.com", self.admin)
        self.assertEqual((self.rows("fakes"), self.rows("archived")), ([], ["a@example.com"]))  # archived wins

    def test_correcting_the_email_takes_him_out_of_the_tab_because_the_new_address_has_not_bounced(self):
        lead("typo@example.com")
        self.bounce("typo@example.com")
        self.assertEqual(self.rows("fakes"), ["typo@example.com"])
        self.assertEqual(outreach.correct_lead_email("typo@example.com", "Real@Example.com", self.admin)[0], outreach.DONE)
        self.assertEqual((self.rows("fakes"), self.rows()), ([], ["real@example.com"]))
        self.assertTrue(EmailSuppression.objects.filter(email="typo@example.com").exists())

    def test_a_corrected_address_takes_the_genuine_mark_away_and_an_archived_lead_cannot_be_marked(self):
        lead("typo2@example.com")
        self.bounce("typo2@example.com")
        self.assertEqual(outreach.mark_genuine("typo2@example.com", self.admin), outreach.DONE)
        outreach.correct_lead_email("typo2@example.com", "real2@example.com", self.admin)
        self.assertFalse(GenuineLead.objects.filter(email="typo2@example.com").exists())
        lead("kept@example.com")
        self.bounce("kept@example.com")
        ArchivedLead.objects.create(email="kept@example.com")
        self.assertEqual(outreach.mark_genuine("kept@example.com", self.admin), outreach.ARCHIVED_LEAD)
        self.assertFalse(GenuineLead.objects.filter(email="kept@example.com").exists())

    def test_mark_as_genuine_moves_him_back_for_good_survives_a_second_bounce_and_keeps_the_address_blocked(self):
        session = lead("a@example.com")
        self.bounce("a@example.com")
        self.assertContains(call(self.admin, "get", f"/leads/{session.pk}/"), "data-possible-fake")
        self.assertEqual(outreach.mark_genuine("a@example.com", self.admin), outreach.DONE)
        self.assertEqual(outreach.mark_genuine("a@example.com", self.admin), outreach.ALREADY)
        self.assertEqual((self.rows(), self.rows("fakes")), (["a@example.com"], []))
        EmailSuppression.objects.filter(email="a@example.com").delete()
        suppression.add("a@example.com", EmailSuppression.HARD_BOUNCE, feedback_id="second")  # bounces again
        self.assertEqual((self.rows(), self.rows("fakes")), (["a@example.com"], []))
        self.assertTrue(suppression.is_suppressed("a@example.com"))  # still blocked from email (1A)
        self.assertNotEqual(outreach.email_block("a@example.com"), "")
        row = call(self.reader, "get", "/leads/").context["rows"][0]
        self.assertEqual((row["bounced"], row["genuine"]), (False, True))  # no Possible fake tag
        page = call(self.admin, "get", f"/leads/{session.pk}/")
        self.assertNotContains(page, "data-possible-fake")
        self.assertContains(page, "data-bounce-notice")  # the notice that the address does not work stays

    def test_only_a_bounced_address_can_be_marked_and_undo_puts_him_back_in_the_tab(self):
        lead("a@example.com")
        self.assertEqual(outreach.mark_genuine("a@example.com", self.admin), outreach.NOT_FAKE)
        self.bounce("a@example.com")
        outreach.mark_genuine("a@example.com", self.admin)
        self.assertEqual(outreach.unmark_genuine("a@example.com", self.admin), outreach.DONE)
        self.assertEqual(outreach.unmark_genuine("a@example.com", self.admin), outreach.ALREADY)
        self.assertEqual(self.rows("fakes"), ["a@example.com"])

    def test_the_total_leaves_out_fakes_agrees_with_the_list_and_a_bounce_or_mark_asks_for_a_refresh(self):
        lead("a@example.com"), lead("b@example.com")
        with mock.patch("office.snapshots.request_refresh") as refresh:
            self.bounce("a@example.com")
            self.assertEqual(refresh.call_count, 1)
            outreach.mark_genuine("a@example.com", self.admin)
            self.assertGreaterEqual(refresh.call_count, 2)
            asked = refresh.call_count
            outreach.unmark_genuine("a@example.com", self.admin)
            self.assertGreater(refresh.call_count, asked)  # the Activity signal asks too (one job in real life: the refresh is debounced)
        stored = self.figures()
        self.assertEqual((stored["leads_total"], stored["fakes_total"]), (len(self.rows()), len(self.rows("fakes"))))
        self.assertEqual((stored["leads_total"], stored["fakes_total"]), (1, 1))
        page = call(self.reader, "get", "/leads/").context
        self.assertEqual((page["tiles"]["leads_total"], page["fakes_count"]), (1, 1))
        outreach.mark_genuine("a@example.com", self.admin)
        self.assertEqual(counts.compute_leads(), {"leads_total": 2, "fakes_total": 0})

    def test_permissions_timeline_and_audit(self):
        session = lead("a@example.com")
        self.bounce("a@example.com")
        genuine, undo = f"/leads/{session.pk}/genuine/", f"/leads/{session.pk}/not-genuine/"
        self.assertEqual(call(self.reader, "post", genuine).status_code, 403)
        self.assertFalse(GenuineLead.objects.exists())
        self.assertEqual(call(self.approver, "post", genuine).status_code, 302)
        self.assertEqual(GenuineLead.objects.get().marked_by_label, outreach.label(self.approver))
        self.assertEqual(call(self.reader, "post", undo).status_code, 403)
        call(self.admin, "post", undo)
        self.assertEqual(list(LeadArchiveEvent.objects.order_by("at").values_list("kind", flat=True)), ["genuine", "ungenuine"])
        labels = [e[2] for e in outreach.timeline_entries(["a@example.com"])]
        self.assertEqual(sorted(labels), sorted([f"Marked as genuine by {outreach.label(self.approver)}", f"Genuine mark undone by {outreach.label(self.admin)}"]))

    def test_the_tab_has_search_sort_and_csv_and_a_lead_page_offers_the_button_only_while_he_is_a_fake(self):
        lead("a@example.com"), lead("b@example.com")
        self.bounce("a@example.com"), self.bounce("b@example.com")
        self.assertEqual(call(self.reader, "get", "/leads/?view=fakes&q=b@").context["rows"][0]["email"], "b@example.com")
        self.assertEqual(sorted(self.rows("fakes")), ["a@example.com", "b@example.com"])
        self.assertContains(call(self.admin, "get", "/leads/?view=fakes"), "Mark as genuine")
        self.assertNotContains(call(self.reader, "get", "/leads/?view=fakes"), "Mark as genuine")  # same permission as Archive
        self.assertEqual(call(self.reader, "get", "/leads/?view=fakes&sort=email&dir=asc").context["rows"][0]["email"], "a@example.com")
        from office import leads as lead_lists

        body = lead_lists.csv_response({**lead_lists.filters_from(mock.Mock(GET={"view": "fakes"})), "q": ""}).content.decode()
        self.assertIn("a@example.com", body)
        self.assertIn("b@example.com", body)
        ArchivedLead.objects.create(email="a@example.com")
        self.assertFalse(self.bounce_context("a@example.com")["can_mark"])  # archived wins: no button for him
        self.assertTrue(self.bounce_context("b@example.com")["can_mark"])

    def bounce_context(self, email):
        from journey.models import JourneySession

        return call(self.admin, "get", f"/leads/{JourneySession.objects.get(lead_email=email).pk}/").context["bounce"]
