"""System dashboard "Needs attention" box, and the bounce page: one row per address, Office links, one shared weekly count. Mocked: no real sending."""
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from journey.models import JourneySession
from mailings.models import Mailing
from notifications.models import EmailBounce, EmailSuppression, NotificationTemplate, StaffSender
from plans.models import SiteSettings
from system import attention, emails as emails_logic
from system.models import SiteDefaults
from system.tests.test_system import make_user, unlocked_client

User = get_user_model()
URLCONF = "config.urls_system"
DOMAIN = {"DEFAULT_FROM_EMAIL": "Spa 99 <hello@example.com>", "EMAIL_SENDING_DOMAIN": ""}


def texts():
    return [item["text"] for item in attention.attention_items()]


def staff(email, **kw):
    return User.objects.create_user(email, "pw-12345-xx", is_staff=True, **kw)


@override_settings(**DOMAIN)
class AttentionTests(TestCase):
    def setUp(self):
        SiteDefaults.objects.all().delete()
        row = SiteDefaults.load()
        row.staff_alert_emails, row.staff_alert_emails_on = "alerts@example.org", True
        row.save()
        self.admin = make_user("dev@example.com")  # on the sending domain: can send

    def test_nothing_wrong_means_no_box(self):
        self.assertEqual(attention.attention_items(), [])
        page = unlocked_client(self.admin).get("/")
        self.assertNotContains(page, "data-system-attention")

    def test_alert_emails_empty_or_off(self):
        row = SiteDefaults.load()
        row.staff_alert_emails = ""
        row.save()
        self.assertEqual(texts(), ["No payment alert email address is set."])
        row.staff_alert_emails, row.staff_alert_emails_on = "alerts@example.org", False
        row.save()
        self.assertEqual(texts(), ["Payment alert emails are switched off."])
        self.assertEqual(attention.attention_items()[0]["fix_url"], reverse("system_defaults", urlconf=URLCONF))

    def test_staff_member_who_cannot_send_links_to_his_email_page(self):
        barry = staff("barry@elsewhere.com", first_name="Barry")
        item = attention.attention_items()[0]
        self.assertIn("Barry has no address they can send from", item["text"])
        self.assertEqual(item["fix_url"], reverse("system_team_email", args=[barry.pk], urlconf=URLCONF))
        StaffSender.objects.create(user=barry, sending_address="barry@example.com")
        self.assertEqual(attention.attention_items(), [])
        self.assertEqual(unlocked_client(self.admin).get(reverse("system_team_email", args=[barry.pk], urlconf=URLCONF)).status_code, 200)

    def test_chosen_sender_who_can_no_longer_send(self):
        gone = staff("gone@elsewhere.com", first_name="Gone")
        template = NotificationTemplate.objects.create(key="lead_next_morning", subject="Hello", sender_user=gone)
        Mailing.objects.create(name="Old", subject="Old", status=Mailing.SENT, sender_user=gone)
        draft = Mailing.objects.create(name="News", subject="News", status=Mailing.DRAFT, sender_user=gone)
        found = [i for i in attention.attention_items() if "can no longer send" in i["text"]]
        self.assertEqual(sorted(i["fix_url"] for i in found), sorted([reverse("system_email_edit", args=[template.key], urlconf=URLCONF), reverse("system_mailing_edit", args=[draft.pk], urlconf=URLCONF)]))
        self.assertEqual(len(found), 2)  # the sent mailing is history: not listed

    def test_chosen_sender_who_can_still_send_is_fine(self):
        NotificationTemplate.objects.create(key="lead_next_morning", subject="Hello", sender_user=self.admin)
        self.assertEqual(attention.attention_items(), [])

    def test_stored_address_off_the_sending_domain(self):
        barry = staff("barry@example.com", first_name="Barry")  # can send by login, so only the stored address is wrong
        StaffSender.objects.create(user=barry, sending_address="barry@elsewhere.com")
        SiteSettings.objects.update_or_create(defaults={"auto_email_from_address": "x@elsewhere.com"}, pk=SiteSettings.load().pk)
        found = texts()
        self.assertEqual(len(found), 2)
        self.assertTrue(any("barry@elsewhere.com" in t for t in found) and any("x@elsewhere.com" in t for t in found))
        legacy = [i for i in attention.attention_items() if "x@elsewhere.com" in i["text"]][0]
        self.assertEqual(legacy["fix_url"], "")

    def test_inactive_or_non_staff_sender_rows_are_ignored(self):
        gone = staff("gone@example.com", is_active=False)
        StaffSender.objects.create(user=gone, sending_address="gone@elsewhere.com")
        member = User.objects.create_user("member@example.com", "pw-12345-xx")
        StaffSender.objects.create(user=member, sending_address="member@elsewhere.com")
        self.assertEqual(attention.attention_items(), [])

    def test_someone_who_cannot_send_is_listed_once(self):
        barry = staff("barry@elsewhere.com", first_name="Barry")
        StaffSender.objects.create(user=barry, sending_address="barry@elsewhere.com")  # off the domain, so he cannot send
        found = texts()
        self.assertEqual(len(found), 1)
        self.assertIn("no address they can send from", found[0])

    def test_recipient_addresses_are_not_checked_against_the_sending_domain(self):
        SiteSettings.objects.update_or_create(defaults={"contact_email": "hello@elsewhere.com", "gold_approver_cc": "cc@elsewhere.com"}, pk=SiteSettings.load().pk)
        self.assertEqual(attention.attention_items(), [])

    def test_no_final_approver(self):
        with mock.patch("system.attention.gold_approval.final_approver_missing", return_value=True):
            item = attention.attention_items()[0]
            self.assertEqual(item["fix_url"], reverse("system_approval", urlconf=URLCONF))
            page = unlocked_client(self.admin).get("/")
            self.assertContains(page, "data-system-attention-item")
            self.assertContains(page, "Gold has no final approver.")


class BounceTests(TestCase):
    def bounce(self, email, kind="hard", days=0, **kw):
        return EmailBounce.objects.create(email=email, kind=kind, received_at=timezone.now() - timedelta(days=days), **kw)

    def test_default_groups_by_address_and_hides_soft(self):
        self.bounce("a@example.com", days=3, detail="old")
        self.bounce("a@example.com", days=1, detail="new", postmark_type="HardBounce")
        self.bounce("b@example.com", kind="complaint")
        self.bounce("soft@example.com", kind="soft")
        EmailSuppression.objects.create(email="a@example.com", reason=EmailSuppression.HARD_BOUNCE, first_seen=timezone.now(), last_seen=timezone.now())
        rows = {r["email"]: r for r in emails_logic.bounce_rows()}
        self.assertEqual(set(rows), {"a@example.com", "b@example.com"})
        self.assertEqual((rows["a@example.com"]["count"], rows["a@example.com"]["detail"], rows["a@example.com"]["suppressed"]), (2, "new", True))
        self.assertFalse(rows["b@example.com"]["suppressed"])
        self.assertEqual([r["email"] for r in emails_logic.bounce_rows("soft")], ["soft@example.com"])
        self.assertEqual(len(emails_logic.bounce_rows("all")), 3)

    def test_links_person_then_lead_and_query_count_does_not_grow(self):
        person = User.objects.create_user("Person@Example.com", "pw-12345-xx")
        lead = JourneySession.objects.create(lead_email="Lead@example.com", is_bot=False)
        JourneySession.objects.create(lead_email="bot@example.com", is_bot=True)
        for email in ("person@example.com", "lead@example.com", "bot@example.com", "nobody@example.com"):
            self.bounce(email)
        rows = {r["email"]: r["office_url"] for r in emails_logic.bounce_rows()}
        self.assertEqual(rows["person@example.com"], f"{settings.OFFICE_URL}/people/{person.pk}/")
        self.assertEqual(rows["lead@example.com"], f"{settings.OFFICE_URL}/leads/{lead.pk}/")
        self.assertEqual((rows["bot@example.com"], rows["nobody@example.com"]), ("", ""))
        with self.assertNumQueries(5):
            emails_logic.bounce_rows()
        for i in range(20):
            self.bounce(f"more{i}@example.com")
        with self.assertNumQueries(5):
            emails_logic.bounce_rows()

    def test_suppressions_page_links_too(self):
        person = User.objects.create_user("gone@example.com", "pw-12345-xx")
        EmailSuppression.objects.create(email="gone@example.com", reason=EmailSuppression.COMPLAINT, first_seen=timezone.now(), last_seen=timezone.now())
        page = unlocked_client(make_user("dev@example.com")).get("/emails/suppressions/")
        self.assertContains(page, f'href="{settings.OFFICE_URL}/people/{person.pk}/"')

    def test_one_weekly_count_for_tile_and_emails_page(self):
        self.bounce("a@example.com", days=1)
        self.bounce("a@example.com", kind="complaint", days=2)  # same address: counts once
        self.bounce("b@example.com", days=2)
        self.bounce("c@example.com", kind="complaint")  # complaints have their own tile
        self.bounce("soft@example.com", kind="soft")
        self.bounce("old@example.com", days=9)
        self.assertEqual(emails_logic.bounces_week(), 2)  # a and b
        self.assertEqual(emails_logic.overview()["stats"]["bounces_week"], 2)
        page = unlocked_client(make_user("dev@example.com")).get("/")
        self.assertEqual(page.context["bounces_week"], 2)

    def test_cap_of_500_addresses_and_unknown_kind_is_the_default(self):
        EmailBounce.objects.bulk_create([EmailBounce(email=f"p{i}@example.com", kind="hard", received_at=timezone.now()) for i in range(505)])
        self.assertEqual(len(emails_logic.bounce_rows()), 500)
        client = unlocked_client(make_user("dev@example.com"))
        self.assertEqual(client.get("/emails/bounces/?kind=nonsense").context["kind"], "")
