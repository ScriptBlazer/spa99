"""The two reach out buttons on the lead, person and Gold pages (docs/features/whatsapp.md, Reach out buttons): keyed on `state`, never on `configured`; WhatsApp is the one
primary when he can be sent to on it, else Email; the grey line when there is no mobile; Gold keeps both secondary and shows them to a reader too. Mocked: no real Twilio call."""
from gold import services as gold_services
from gold.tests.test_gold import application_data
from office.tests.test_leads import lead
from outreach import services as outreach
from whatsapp.tests.test_whatsapp import Base, office
from django.test import override_settings


class ReachButtonTests(Base):
    def lead_page(self, user, email="hugo@example.com", mobile="07400 123456"):
        session = lead(email)
        if mobile:
            outreach.set_lead_contact(email, self.approver, first_name="Hugo", mobile=mobile)
        return office(user, "get", f"/leads/{session.pk}/")

    def test_a_mobile_and_no_chat_shows_both_buttons_with_whatsapp_the_one_primary(self):
        page = self.lead_page(self.approver)
        self.assertContains(page, "Start WhatsApp chat")
        self.assertContains(page, "data-email-open")
        html = page.content.decode()
        self.assertRegex(html, r'<form method="post" action="/leads/[^"]*/whatsapp/" data-whatsapp-start><input type="hidden" name="csrfmiddlewaretoken"[^>]*><button type="submit" class="btn btn-primary btn-block o-wa-btn" data-whatsapp-open>')
        self.assertNotRegex(html, r'<a [^>]*data-whatsapp-open')  # Start writes, so it is a POST form, never a link
        self.assertRegex(html, r'class="btn btn-secondary btn-block o-email-btn" data-dialog-open="email"[^>]*data-email-open')

    def test_no_mobile_shows_the_email_button_alone_with_a_clickable_grey_line_that_opens_the_dialog(self):
        page = self.lead_page(self.approver, "eddie@example.com", mobile="")
        self.assertNotContains(page, "data-whatsapp-open")
        self.assertContains(page, "Add a number to enable WhatsApp")
        self.assertRegex(page.content.decode(), r'<button type="button" class="o-quiet o-channel-add" data-dialog-open="mobile"[^>]*data-add-mobile>')
        self.assertRegex(page.content.decode(), r'class="btn btn-primary btn-block o-email-btn" data-dialog-open="email"[^>]*data-email-open')  # no WhatsApp: Email is the one primary

    @override_settings(TWILIO_ACCOUNT_SID="")
    def test_twilio_not_set_up_keeps_the_button_and_says_so(self):
        page = self.lead_page(self.approver)
        self.assertContains(page, "Start WhatsApp chat")
        self.assertContains(page, "WhatsApp is not set up yet.")
        self.assertRegex(page.content.decode(), r'class="btn btn-secondary btn-block o-wa-btn o-btn-off" aria-disabled="true"[^>]*data-wa-off')

    def test_a_reader_still_sees_the_card_and_is_told_it_is_view_only_once(self):
        page = self.lead_page(self.reader)
        html = page.content.decode()
        self.assertContains(page, "No WhatsApp chat yet")
        self.assertContains(page, "data-email-off")
        self.assertEqual(html.count("View only."), 1)

    def test_gold_shows_both_channels_secondary_so_approve_stays_the_one_primary_and_a_reader_still_sees_them(self):
        application, _ = gold_services.submit_application(application_data(email="gold-btn@example.com", mobile="+447400123999"))
        html = office(self.approver, "get", f"/gold/{application.pk}/").content.decode()
        self.assertIn("o-channels", html)
        self.assertRegex(html, r'<button type="submit" class="btn btn-secondary btn-block o-wa-btn" data-whatsapp-open>')
        self.assertRegex(html, r'class="btn btn-secondary btn-block o-email-btn" data-dialog-open="email"[^>]*data-email-open')
        self.assertNotRegex(html, r'btn-primary btn-block o-(wa|email)-btn')
        reader = office(self.reader, "get", f"/gold/{application.pk}/").content.decode()  # outside the can_edit block: a reader sees the card, off, with the reason once
        self.assertIn("o-channels", reader)
        self.assertIn("No WhatsApp chat yet", reader)
        self.assertEqual(reader.count("View only."), 1)

    def test_gold_with_no_number_gets_the_add_a_mobile_dialog_and_staff_can_save_one_audited(self):
        from outreach.models import PersonEdit

        application, _ = gold_services.submit_application(application_data(email="gold-none@example.com", mobile=""))
        page = office(self.approver, "get", f"/gold/{application.pk}/")
        self.assertEqual(page.context["whatsapp"]["edit_url"], f"/gold/{application.pk}/mobile/")
        self.assertTrue(page.context["whatsapp"]["can_add_number"])
        self.assertContains(page, 'data-dialog="mobile"')
        self.assertContains(page, "data-add-mobile")
        self.assertEqual(office(self.reader, "post", f"/gold/{application.pk}/mobile/", {"mobile_country": "GB", "mobile": "07400 123456"}).status_code, 403)
        saved = office(self.approver, "post", f"/gold/{application.pk}/mobile/", {"mobile_country": "GB", "mobile": "07400 123456"}, HTTP_ACCEPT="application/json").json()
        self.assertTrue(saved["ok"])
        application.refresh_from_db()
        self.assertEqual(application.mobile, "+447400123456")
        self.assertTrue(PersonEdit.objects.filter(email="gold-none@example.com", what=PersonEdit.MOBILE, after="+447400123456").exists())
        self.assertEqual(office(self.approver, "get", f"/gold/{application.pk}/").context["whatsapp"]["state"], "ready")
        bad = office(self.approver, "post", f"/gold/{application.pk}/mobile/", {"mobile_country": "GB", "mobile": "12"}, HTTP_ACCEPT="application/json").json()
        self.assertFalse(bad["ok"])

    def test_the_consent_text_follows_the_version_the_lead_ticked(self):
        from journey.copy import consent_text

        self.assertEqual(consent_text(""), "Agreed that we may email about Spa 99 opening")
        self.assertEqual(consent_text("2026-11-03"), "Agreed that we may email and WhatsApp about Spa 99 opening")
        self.assertEqual(consent_text("2026-11-04-2"), "Agreed that we may email and WhatsApp about Spa 99 opening and offers")
        self.assertIn("if a number was added", consent_text("2026-11-04"))  # an older wording keeps its own text
