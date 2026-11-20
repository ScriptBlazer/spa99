from django.test import SimpleTestCase

from office.templatetags.office_tags import short_by
from outreach import services


class ShortByTests(SimpleTestCase):
    def test_staff_get_a_first_name_and_automatic_lines_are_said_in_words(self):
        self.assertEqual(short_by("Email sent by Nochum Green (nochum@spa99.co.uk)"), "Email sent by Nochum")
        self.assertEqual(short_by(f"Mobile added by {services.SELF_LABEL}"), "Mobile added by him, through his email link")  # was "by His"
        self.assertEqual(short_by(f"Archived by {services.GROUP_EMAIL_LABEL}"), "Archived automatically, by the group email")
        self.assertEqual(short_by("Moved back by Bounce"), "Moved back automatically, after an email bounced")
        self.assertEqual(short_by("Started the journey"), "Started the journey")
