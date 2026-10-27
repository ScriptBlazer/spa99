"""Leads: linking an email's journeys to the account on verify, the Leads list and its filters, the lead page by opaque id,
the CSV permission, the merged timeline and the stored lead figures. Mocked: sync queue, locmem email."""
import json
from datetime import timedelta

from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from gold import services as gold_services
from gold.models import GoldApplication
from gold.tests.test_gold import application_data
from insights import rollup
from insights.tests.test_metrics import finished_journey
from journey import services as journey
from journey.models import JourneySession
from office import leads as lead_lists
from office.tests.test_office import OFFICE, OfficeTestCase, get, staff
from users import services, tokens
from users.models import User
from users.tests.test_register import cleaned


def lead(email, finish=True, time="evening"):
    """A visitor who leaves `email` at the gate (and finishes the journey when `finish`)."""
    session = finished_journey(time=time) if finish else journey.create_session("Mozilla/5.0 (Macintosh) Safari/605.1")
    journey.save_lead(session, email, True)
    session.refresh_from_db()
    return session


def verify(user):
    return services.verify_email(tokens.make_verify_token(user))


class LinkingTests(OfficeTestCase):
    def test_verify_links_every_session_with_the_email_once_and_never_steals(self):
        a, b = lead("hugo@example.com"), lead("other@example.com")
        JourneySession.objects.filter(pk=b.pk).update(lead_email="HUGO@Example.com")  # another browser, another case
        mine = lead("hugo@example.com", finish=False)
        owner = User.objects.create_user("someone@example.com", "x")
        JourneySession.objects.filter(pk=mine.pk).update(user=owner)  # already someone else's
        application, _ = gold_services.submit_application(application_data(email="Hugo@example.com"))
        user = services.register_interest(cleaned(email="hugo@example.com")).user
        self.assertEqual(JourneySession.objects.filter(user=user).count(), 0)  # registering alone proves nothing
        verify(user)
        self.assertEqual({s.pk for s in JourneySession.objects.filter(user=user)}, {a.pk, b.pk})
        mine.refresh_from_db()
        self.assertEqual(mine.user_id, owner.pk)
        application.refresh_from_db()
        self.assertEqual(application.user_id, user.pk)
        self.assertEqual(services.link_earlier_data(user), (0, 0))  # idempotent
        self.assertTrue(JourneySession.history.filter(id=a.pk, user=user).exists())  # history keeps the link

    def test_export_includes_linked_sessions_and_erase_clears_them(self):
        lead("hugo@example.com")
        user = services.register_interest(cleaned(email="hugo@example.com")).user
        verify(user)
        exported = services.export_user_data(user)["journey_sessions"]
        self.assertEqual(len(exported), 1)
        self.assertTrue(exported[0]["answers"])  # full detail now, not only the address
        services.delete_user_data(user)
        self.assertFalse(JourneySession.objects.filter(lead_email__iexact="hugo@example.com").exists())


class LeadUnsubscribedTests(OfficeTestCase):
    def test_lead_page_and_list_show_unsubscribed(self):
        from mailings import optout

        session = lead("hugo@example.com")
        office = staff("Office", "o@example.com")
        self.assertNotContains(get(office, f"/leads/{session.pk}/"), "data-unsubscribed")
        optout.unsubscribe("Hugo@example.com")
        self.assertContains(get(office, f"/leads/{session.pk}/"), "data-unsubscribed")
        self.assertContains(get(office, "/leads/"), "data-unsubscribed")

    def test_list_labels_an_account_that_turned_news_off(self):
        lead("sam@example.com")
        user = User.objects.create_user("sam@example.com", "x", email_verified_at=timezone.now(), marketing_consent=False)
        office = staff("Office", "o@example.com")
        self.assertContains(get(office, "/leads/?show=registered"), "data-unsubscribed")
        User.objects.filter(pk=user.pk).update(marketing_consent=True)
        self.assertNotContains(get(office, "/leads/?show=registered"), "data-unsubscribed")


class LeadsListTests(OfficeTestCase):
    def setUp(self):
        self.office = staff("Office", "o@example.com")
        self.admin = staff("Admin", "a@example.com")

    def emails(self, query="", user=None):
        rows = lead_lists.page(lead_lists.filters_from(type("R", (), {"GET": dict(x.split("=") for x in query.split("&") if x)})()), 1)[0]
        return [r["email"] for r in rows]

    def test_one_row_per_email_excluding_registered_and_staff_with_filters(self):
        lead("one@example.com", time="evening")
        lead("one@example.com", time="daytime")  # a second journey: same row
        hot = lead("two@example.com")
        JourneySession.objects.update(gold_potential="low", gold_score=1)
        JourneySession.objects.filter(pk=hot.pk).update(gold_potential="high", gold_score=9)
        lead("three@example.com", finish=False)
        lead("reg@example.com")
        User.objects.create_user("reg@example.com", "x", email_verified_at=timezone.now())  # has a verified account (any case)
        lead("unverified@example.com", finish=False)
        User.objects.create_user("unverified@example.com", "x")  # an unverified account does not take the lead over
        lead("boss@example.com")
        staff("Office", "BOSS@example.com")
        self.assertEqual(sorted(self.emails()), ["one@example.com", "three@example.com", "two@example.com", "unverified@example.com"])
        self.assertEqual(self.emails("show=registered"), ["reg@example.com"])
        self.assertEqual(self.emails("potential=high"), ["two@example.com"])
        self.assertEqual(self.emails("q=THREE"), ["three@example.com"])
        self.assertEqual(self.emails("industry=finance").count("three@example.com"), 0)
        gold_services.submit_application(application_data(email="one@example.com"))
        self.assertEqual(self.emails("gold=yes"), ["one@example.com"])
        self.assertEqual(self.emails("sort=potential")[0], "two@example.com")
        self.assertEqual(self.emails("sort=visits")[0], "one@example.com")
        rows = lead_lists.page(lead_lists.filters_from(type("R", (), {"GET": {}})()), 1)[0]
        self.assertEqual({r["email"]: r["journeys"] for r in rows}["one@example.com"], 2)
        self.assertEqual([r["email"] for r in lead_lists.hot_leads()], ["two@example.com"])

    def test_views_permissions_and_csv(self):
        lead("one@example.com")
        self.assertEqual(get(None, "/leads/").status_code, 302)  # sign in first
        self.assertEqual(get(User.objects.create_user("m@example.com", "x"), "/leads/").status_code, 404)  # not team
        self.assertEqual(get(self.office, "/leads/").status_code, 200)
        self.assertContains(get(self.office, "/leads/"), "one@example.com")
        self.assertEqual(get(self.office, "/leads/export.csv").status_code, 403)
        response = get(self.admin, "/leads/export.csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn("one@example.com", response.content.decode())

    def test_list_query_count_does_not_grow(self):
        client = Client(HTTP_HOST=OFFICE)
        client.force_login(self.office)

        def count():
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(client.get("/leads/").status_code, 200)
            return len(ctx)
        lead("first@example.com")  # an empty page skips the row queries: compare from one row
        empty = count()
        for i in range(4):
            lead(f"p{i}@example.com")
        self.assertEqual(count(), empty)


class LeadPageTests(OfficeTestCase):
    def test_opaque_id_bad_id_redirect_and_timeline_order(self):
        office = staff("Office", "o@example.com")
        session = lead("one@example.com")
        page = get(office, f"/leads/{session.pk}/")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn("one@example.com", page.request["PATH_INFO"])
        timeline = page.context["person"]["timeline"]
        self.assertEqual([e["at"] for e in timeline], sorted((e["at"] for e in timeline), reverse=True))  # newest first
        self.assertEqual({"journey_started", "lead_given", "journey_finished"}, {e["kind"] for e in timeline})
        partial = get(office, f"/leads/{session.pk}/?tl=1", headers={"HX-Request": "true"})
        self.assertContains(partial, "data-timeline-chunk")
        self.assertNotContains(partial, "<html")
        self.assertEqual(get(office, "/leads/00000000-0000-0000-0000-000000000000/").status_code, 404)
        self.assertEqual(get(office, "/leads/not-a-token/").status_code, 404)
        anonymous = journey.create_session("Mozilla/5.0 Safari/605.1")  # no email: not a lead
        self.assertEqual(get(office, f"/leads/{anonymous.pk}/").status_code, 404)
        user = services.register_interest(cleaned(email="one@example.com")).user
        self.assertEqual(get(office, f"/leads/{session.pk}/").status_code, 200)  # unverified: still a lead (the address may not be his)
        verify(user)
        self.assertRedirects(get(office, f"/leads/{session.pk}/"), f"/people/{user.pk}/", fetch_redirect_response=False)
        person = get(office, f"/people/{user.pk}/")
        self.assertEqual(person.status_code, 200)
        data = person.context["person"]
        self.assertEqual(len(data["journeys"]), 1)
        self.assertEqual(data["tier"]["match"], data["tier"]["suggested_slug"] == data["tier"]["picked_slug"])
        kinds = [e["kind"] for e in data["timeline"]]
        self.assertLess(kinds.index("verified"), kinds.index("journey_started"))  # newest first
        self.assertTrue(data["consent"]["lead"])

    def test_lead_export_and_erase_are_admin_only(self):
        session = lead("one@example.com")
        office, admin = staff("Office", "o@example.com"), staff("Admin", "a@example.com")
        self.assertEqual(get(office, f"/leads/{session.pk}/export/").status_code, 403)
        body = json.loads(get(admin, f"/leads/{session.pk}/export/").content)
        self.assertEqual(body["email"], "one@example.com")
        client = Client(HTTP_HOST=OFFICE)
        client.force_login(office)
        self.assertEqual(client.post(f"/leads/{session.pk}/delete/").status_code, 403)
        client.force_login(admin)
        client.post(f"/leads/{session.pk}/delete/")
        session.refresh_from_db()
        self.assertEqual(session.lead_email, "")


class LeadFigureTests(OfficeTestCase):
    def test_snapshot_has_new_leads_conversion_hot_leads_and_activity(self):
        lead("one@example.com")
        hot = lead("two@example.com")
        converted = lead("three@example.com")
        old = lead("old@example.com")
        JourneySession.objects.filter(pk=old.pk).update(lead_at=timezone.now() - timedelta(days=20))
        user = services.register_interest(cleaned(email="three@example.com")).user
        verify(user)
        self.assertEqual(converted.__class__.objects.get(pk=converted.pk).user_id, user.pk)
        JourneySession.objects.update(gold_potential="low")
        JourneySession.objects.filter(pk=hot.pk).update(gold_potential="high")
        rollup.run()
        data = get(staff("Office", "o@example.com"), "/dashboard.json?range=7d").json()
        self.assertEqual((data["leads_new"], data["leads_new_previous"], data["leads_registered"], data["hot_leads"]), (3, 0, 1, 1))
        self.assertEqual(get(staff("Office", "p@example.com"), "/dashboard.json?range=30d").json()["leads_new"], 4)
        self.assertTrue(data["insights_leads"])
        self.assertEqual(data["insights_leads"][0]["options"][0]["of_total"], 3)  # one vote per lead not registered
        self.assertEqual([h["email"] for h in data["hot_lead_rows"]], ["two@example.com"])
        self.assertLessEqual(len(data["activity"]), 10)
        self.assertEqual({"lead", "registered", "verified", "journey_finished"} - {a["kind"] for a in data["activity"]}, set())


class ReviewFixTests(OfficeTestCase):
    def test_registering_with_someone_elses_email_exposes_and_erases_nothing_of_theirs(self):
        lead("victim@example.com")
        application, _ = gold_services.submit_application(application_data(email="victim@example.com"))
        attacker = services.register_interest(cleaned(email="victim@example.com")).user  # never verified
        application.refresh_from_db()
        self.assertIsNone(application.user)
        data = services.export_user_data(attacker)
        self.assertEqual(data["gold_applications"], [])
        self.assertEqual(data["journey_sessions"], [])
        from notifications.models import EmailLog

        EmailLog.objects.create(to="victim@example.com", subject="About you", template="welcome", status="sent", subject_email="victim@example.com")
        self.assertEqual(services.export_user_data(attacker)["emails"], [])
        services.delete_user_data(attacker)
        self.assertTrue(EmailLog.objects.filter(to="victim@example.com").exists())
        self.assertTrue(JourneySession.objects.filter(lead_email="victim@example.com").exists())
        self.assertTrue(GoldApplication.objects.filter(pk=application.pk).exists())
        office = staff("Office", "o@example.com")
        self.assertEqual(get(office, "/leads/").context["rows"][0]["email"], "victim@example.com")

    def test_unverified_account_page_shows_no_other_journeys_under_its_email(self):
        lead("victim@example.com")
        user = services.register_interest(cleaned(email="victim@example.com")).user
        data = get(staff("Office", "o@example.com"), f"/people/{user.pk}/").context["person"]
        self.assertEqual(data["unlinked_journeys"], [])

    def test_merge_moves_a_verified_removed_accounts_leads_to_keep(self):
        from system import team

        from users.tests.test_register import cleaned as _c  # noqa: F401

        keep = User.objects.create_user("keep@example.com", "x", email_verified_at=timezone.now())
        gone = User.objects.create_user("gone@example.com", "x", email_verified_at=timezone.now())
        session = lead("gone@example.com")
        dev = staff("Developer", "dev@example.com")
        team.merge_accounts(dev, "keep@example.com", "gone@example.com")
        session.refresh_from_db()
        self.assertEqual((session.user_id, session.lead_email), (keep.pk, "keep@example.com"))
        services.delete_user_data(keep)
        session.refresh_from_db()
        self.assertEqual(session.lead_email, "")

    def test_leads_total_follows_the_range_and_hot_filter_matches_the_count(self):
        old = lead("old@example.com")
        recent = lead("recent@example.com")
        JourneySession.objects.update(gold_potential="high")
        JourneySession.objects.filter(pk=old.pk).update(last_seen_at=timezone.now() - timedelta(days=60))
        rollup.run()
        office = staff("Office", "o@example.com")
        self.assertEqual(get(office, "/leads/").context["summary"]["leads_total"], 1)  # 30 days
        rows = get(office, "/leads/?hot=1&range=all").context["rows"]
        self.assertEqual(len(rows), 2)
        gold_services.submit_application(application_data(email="recent@example.com"))
        self.assertEqual([r["email"] for r in get(office, "/leads/?hot=1&range=all").context["rows"]], ["old@example.com"])

    def test_removing_a_lead_also_clears_emails_cookie_text_and_referrer(self):
        from notifications.models import EmailLog

        session = lead("one@example.com")
        JourneySession.objects.filter(pk=session.pk).update(referrer="https://x.example/p")
        EmailLog.objects.create(to="one@example.com", subject="Hi", template="welcome", status="sent")
        old_key = session.key
        self.assertEqual(journey.erase_lead_data("one@example.com"), 1)
        session.refresh_from_db()
        self.assertEqual((session.lead_email, session.referrer, session.person_key), ("", "", ""))
        self.assertNotEqual(session.key, old_key)
        self.assertFalse(EmailLog.objects.filter(to="one@example.com").exists())

    def test_activity_leaves_out_staff_addresses(self):
        lead("boss@example.com")
        staff("Office", "boss@example.com")
        self.assertEqual([a for a in lead_lists.activity() if a["kind"] == "lead"], [])
