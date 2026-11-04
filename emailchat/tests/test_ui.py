"""The Email tab's screens (docs/features/email-chat-design.md): what the server renders for the list, the thread and New email, and the navigation words. Mocked as the
rest of the email chat tests."""
from django.test import override_settings

from emailchat import services
from emailchat.tests.test_emailchat import CONFIG, inbound_post, office, payload_for
from office.tests.test_office import OfficeTestCase
from plans.tests.helpers import make_team_member
from common import levels


@override_settings(**CONFIG)
class EmailScreenTests(OfficeTestCase):
    def setUp(self):
        self.approver = make_team_member("approver@example.test", levels.OFFICE, approver=True)
        self.reader = make_team_member("reader@example.test", levels.OFFICE)
        _, self.thread = services.create_thread("dan@example.com", "Parking and access", self.approver)
        inbound_post(payload_for(self.thread, "Where can I park?", "pm-ui-1"))

    def test_the_list_shows_three_lines_of_words_and_a_button_to_start_one(self):
        page = office(self.approver, "get", "/email/")
        self.assertContains(page, "o-em-row")
        self.assertContains(page, "Parking and access")
        self.assertContains(page, "Where can I park?")
        self.assertContains(page, "New email")
        self.assertContains(page, "Search name, address or subject")
        self.assertContains(page, "Sent with no reply")
        self.assertNotContains(office(self.reader, "get", "/email/"), "data-em-new")  # a reader may not start one

    def test_the_empty_states_say_what_is_missing(self):
        self.assertContains(office(self.approver, "get", "/email/?filter=noreply"), "Everyone has replied.")
        self.assertContains(office(self.approver, "get", "/email/?q=zzzz"), "No email matches that.")
        self.assertContains(office(self.approver, "get", "/email/?filter=unread", HTTP_HX_REQUEST="true"), "o-em-row")

    def test_the_thread_embeds_its_data_and_gives_a_reader_a_view_only_line(self):
        page = office(self.approver, "get", f"/email/{self.thread.pk}/")
        self.assertContains(page, 'id="em-data"')
        self.assertContains(page, "data-reply-open")
        self.assertContains(page, "data-em-thread")
        reader = office(self.reader, "get", f"/email/{self.thread.pk}/")
        self.assertContains(reader, "View only. Sending is for Approvers and Admins.")
        self.assertNotContains(reader, "data-reply-open")

    def test_new_email_has_the_recipient_field_and_the_editor(self):
        page = office(self.approver, "get", "/email/new/?to=dan@example.com")
        self.assertContains(page, 'role="combobox"')
        self.assertContains(page, "data-ed-editable")
        self.assertContains(page, 'id="em-new-data"')

    def test_the_navigation_says_assistant_and_has_an_email_item_and_leads_moves_to_more(self):
        html = office(self.approver, "get", "/").content.decode()
        self.assertIn('data-office-nav-item="email"', html)
        self.assertIn("<span>Assistant</span>", html)
        self.assertNotIn("<span>Chats</span>", html)
        self.assertRegex(html, r'<li data-nav-overflow><a href="/leads/"')
        self.assertIn('data-office-badge="email"', html)
