"""Office 2, the pages: the Home cards, the five phone tabs, Approvals and Revenue markup, the lists that load themselves (shift and the end of a list), the add-your-number page. Mocked: sync queue."""
from django.test import Client

from office import approvals
from office.templatetags.office_tags import ring_of, ring_of_pounds, share_arcs
from office.tests.test_leads import lead
from office.tests.test_office2 import Base, call


class CardsAndTabsTests(Base):
    def test_ring_helpers_say_x_of_y_and_a_zero_total_is_a_closed_track_with_no_arc(self):
        self.assertEqual(ring_of(12, "applied"), "of 12 applied")
        self.assertEqual(ring_of(0, "applied"), "none yet")
        self.assertEqual(ring_of_pounds(22_400_000), "of £224k possible")
        self.assertEqual(share_arcs(3, 12)["first"], "75")
        self.assertEqual((share_arcs(0, 12)["on"], share_arcs(0, 0)["none"]), (0, True))
        self.assertEqual(share_arcs(1, 1000)["first"], "98")  # a share above zero never draws thinner than a sliver

    def test_home_has_three_cards_with_two_tappable_rings_each_and_only_for_an_editor(self):
        user = self.member("a@example.com")
        approvals.decide(user.pk, "approved", self.approver)
        page = call(self.approver, "get", "/")
        for card in ("waiting", "approved", "revenue"):
            self.assertContains(page, f'data-card="{card}"')
        self.assertContains(page, 'href="/approvals/?status=waiting"')
        self.assertContains(page, 'href="/people/?table=membership"')
        self.assertContains(page, "of 1 registered")
        self.assertNotContains(call(self.reader, "get", "/"), "data-approval-cards")
        self.assertNotContains(page, "data-range-form data-range-page")  # no range bar on the page itself: the phone has none

    def test_five_phone_tabs_no_more_sheet_and_gold_is_a_tab_only_for_people_without_the_rest(self):
        page = call(self.approver, "get", "/leads/").content.decode()
        self.assertNotIn("data-nav-sheet", page)
        for slot in "12345":
            self.assertIn(f'data-nav-slot="{slot}"', page)
        self.assertIn("<li data-nav-wide><a href=\"/gold/\"", page)  # Gold is a rail item for people who see everything
        self.assertIn('data-menu-gold', page)  # and sits in the person menu on a phone


class ListsTests(Base):
    def test_approvals_are_rows_with_decision_forms_and_the_next_page_follows_what_left(self):
        for i in range(30):
            self.member(f"p{i:02d}@example.com")
        page = call(self.approver, "get", "/approvals/").content.decode()
        self.assertIn('data-decision="approve"', page)
        self.assertEqual(page.count("<tr class=\"o-row o-approval\""), 30)
        plain, _ = approvals.page("waiting", 2, 25)
        shifted, _ = approvals.page("waiting", 2, 25, shift=3)
        self.assertEqual((len(plain), len(shifted)), (5, 8))  # three of the first page were decided: the next page starts three earlier
        fragment = call(self.approver, "get", "/approvals/?status=waiting&page=2", HTTP_HX_REQUEST="true").content.decode()
        self.assertIn("That is everyone.", fragment)  # the end of a list that was loaded in more than one go

    def test_a_short_list_says_nothing_at_its_end_and_assistant_answers_rows_to_the_auto_load(self):
        self.member("one@example.com")
        self.assertNotContains(call(self.approver, "get", "/approvals/"), "That is everyone.")
        rows = call(self.reader, "get", "/chats/", HTTP_HX_REQUEST="true")
        self.assertNotContains(rows, "<html")

    def test_the_add_your_number_page_is_the_compact_entrance(self):
        from mailings.addnumber import make_token

        lead("x@example.com")
        page = Client().get(f"/add-number/{make_token('x@example.com')}/")
        self.assertContains(page, "signin-fields")
        self.assertContains(page, "Add your number.")
