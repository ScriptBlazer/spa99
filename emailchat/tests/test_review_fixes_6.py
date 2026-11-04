"""Review round: Auto-Submitted with parameters, and staff erasure names the unlinked direct threads on the address. Mocked: nothing real is sent."""
from django.contrib.messages import get_messages
from django.utils import timezone

from common import levels
from emailchat import direct
from emailchat.models import Thread
from emailchat.tests.test_direct_mail import header
from emailchat.tests.test_emailchat import Base, office
from plans.tests.helpers import make_team_member
from users import services as user_services
from users.models import User
from users.tests.test_register import cleaned


class RobotHeaderTests(Base):
    def reason(self, value):
        return direct.automatic_reason({"Headers": [header("Auto-Submitted", value)]}, "dan@client.example")

    def test_auto_forwarded_with_parameters_is_a_forward_and_real_robots_still_drop(self):
        for value in ("auto-forwarded", "Auto-Forwarded; param=1", "  AUTO-FORWARDED ;x", "no; foo", "no"):
            self.assertEqual(self.reason(value), "", value)
        for value in ("auto-replied", "auto-generated; x=1", "auto-replied;auto-forwarded"):
            self.assertEqual(self.reason(value), "auto-submitted", value)


class ErasureNamesUnlinkedThreadsTests(Base):
    def test_the_person_page_and_the_delete_message_name_the_unlinked_direct_threads_and_leave_them(self):
        member = user_services.register_interest(cleaned(email="victim@client.example")).user
        User.objects.filter(pk=member.pk).update(email_verified_at=timezone.now())
        member.refresh_from_db()
        spoof = Thread.objects.create(email="victim@client.example", direct_to="barry@staff.example.test", subject="Spoofed hello")
        Thread.objects.create(email="someone@else.example", direct_to="barry@staff.example.test", subject="Not his")
        admin = make_team_member("admin@example.test", levels.ADMIN)
        page = office(admin, "get", f"/people/{member.pk}/").content.decode()
        self.assertIn("data-unlinked-threads", page)
        self.assertIn("Spoofed hello", page)
        self.assertIn(f"/email/{spoof.pk}/", page)
        self.assertNotIn("Not his", page)
        self.assertEqual(user_services.export_user_data(member, include_chats=True)["email_threads_not_included"], [{"email": "victim@client.example", "subject": "Spoofed hello"}])
        self.assertEqual(user_services.export_user_data(member, include_chats=True)["email_threads"], [])  # named, never exported
        response = office(admin, "post", f"/people/{member.pk}/delete/")
        self.assertEqual(response.status_code, 302)
        text = " ".join(str(m) for m in get_messages(response.wsgi_request))
        self.assertIn("1 direct email thread from victim@client.example", text)
        self.assertTrue(Thread.objects.filter(pk=spoof.pk).exists())
