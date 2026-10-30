"""Office additions (2026-10-30): heard_via in Leads and Analytics, the chats card, 'Gave email in chat', Invited, not registered."""
from datetime import timedelta
from uuid import uuid4

from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from chat.models import Conversation, Message
from insights import rollup
from journey import services as journey
from journey.models import JourneySession
from mailings.models import ContactList, ContactListMember, Invite
from office import leads as lead_lists
from office.tests.test_leads import lead, verify
from office.tests.test_office import OFFICE, OfficeTestCase, get, staff
from users import services
from users.models import User
from users.tests.test_register import cleaned


def row_emails(query=""):
    request = type("R", (), {"GET": dict(x.split("=") for x in query.split("&") if x)})()
    return sorted(r["email"] for r in lead_lists.page(lead_lists.filters_from(request), 1)[0])


def chat(email="", user=None, question="Do you have a sauna?", **extra):
    conversation = Conversation.objects.create(lead_email=email, user=user, message_count=1, **extra)
    Message.objects.create(conversation=conversation, role=Message.USER, text=question)
    return conversation


class HeardViaTests(OfficeTestCase):
    def setUp(self):
        self.office, self.admin = staff("Office", "o@example.com"), staff("Admin", "a@example.com")

    def with_heard(self, email, value):
        session = lead(email)
        journey.save_answer(session, "heard_via", options=[value])
        return session

    def test_filter_column_and_csv(self):
        self.with_heard("a@x.com", "friend")
        self.with_heard("b@x.com", "social_media")
        lead("c@x.com")
        self.assertEqual(row_emails("heard=friend"), ["a@x.com"])
        self.assertEqual(row_emails(), ["a@x.com", "b@x.com", "c@x.com"])
        page = get(self.office, "/leads/?heard=social_media")
        self.assertContains(page, "b@x.com")
        self.assertNotContains(page, "a@x.com")
        self.assertContains(page, "Social media")
        body = get(self.admin, "/leads/export.csv?heard=friend").content.decode()
        self.assertIn("heard_via", body.splitlines()[0])
        self.assertIn("A friend", body)
        self.assertNotIn("b@x.com", body)

    def test_analytics_counts_follow_the_range(self):
        for i, value in enumerate(["friend", "friend", "social_media"]):
            session = journey.create_session("Mozilla/5.0 (Macintosh) Safari/605.1")
            for key, values in {"time": ["evening"], "frequency": ["two_three"], "facilities": ["gym"], "company": ["alone"], "industry": ["finance"], "heard_via": [value]}.items():
                journey.save_answer(session, key, options=values)
            journey.set_step(session, step=2)
            from journey import engine
            engine.complete(session)
        rollup.run()
        data = get(self.office, "/analytics/data/?range=all").json()["journey_answers"]["heard_via"]
        self.assertEqual({a["label"]: a["count"] for a in data}["A friend"], 2)
        self.assertEqual({a["label"]: a["count"] for a in data}["Social media"], 1)
        self.assertContains(get(self.office, "/analytics/?range=all"), "How people heard about us")

    def test_person_and_lead_pages_show_it_near_the_top(self):
        session = self.with_heard("a@x.com", "friend")
        self.assertContains(get(self.office, f"/leads/{session.pk}/"), "data-person-heard")


class ChatsCardTests(OfficeTestCase):
    def setUp(self):
        self.office = staff("Office", "o@example.com")

    def test_lead_page_lists_only_his_chats_newest_five_and_filters_chats(self):
        session = lead("hugo@example.com")
        mine = [chat("Hugo@Example.com", question=f"Hugo question {i}.") for i in range(6)]  # spaces: a random CSRF token can never match
        chat("other@example.com", question="Not his")
        chat("hugo@example.com", question="Staff test", staff_test=True)
        page = get(self.office, f"/leads/{session.pk}/")
        self.assertContains(page, "Chats with the assistant")
        self.assertNotContains(page, "Not his")
        self.assertNotContains(page, "Staff test")
        self.assertContains(page, "data-chats-all")
        self.assertContains(page, "Hugo question 5.")
        self.assertNotContains(page, "Hugo question 0.")  # the sixth, oldest one is behind the link
        self.assertContains(page, f"/chats/{mine[5].pk}/")
        full = get(self.office, f"/chats/?lead={session.pk}")
        self.assertContains(full, "Hugo question 0.")
        self.assertNotContains(full, "Not his")
        self.assertEqual(get(self.office, "/chats/?lead=not-a-uuid").status_code, 404)
        self.assertEqual(get(self.office, f"/chats/?lead={uuid4()}").status_code, 404)

    def test_person_page_uses_the_account_link_and_pruned_chats_are_gone(self):
        user = services.register_interest(cleaned(email="sam@example.com")).user
        mine = chat(user=user, question="Mine")
        chat("zed@example.com", question="Zed's")
        page = get(self.office, f"/people/{user.pk}/")
        self.assertContains(page, "Mine")
        self.assertNotContains(page, "Zed's")
        Conversation.objects.filter(pk=mine.pk).update(last_at=timezone.now() - timedelta(days=91))
        from chat import services as chat_services
        chat_services.prune()
        self.assertContains(get(self.office, f"/people/{user.pk}/"), "No chats kept")
        self.assertContains(get(self.office, f"/chats/?user={user.pk}"), "Chats with sam@example.com")


class ChatsCardMoreTests(OfficeTestCase):
    def test_chat_tied_to_the_journey_session_shows_without_a_typed_email(self):
        session = lead("hugo@example.com")
        Conversation.objects.create(session=session, message_count=1)
        other = lead("zed@example.com")
        Conversation.objects.create(session=other, message_count=1)
        page = get(staff("Office", "o@example.com"), f"/leads/{session.pk}/")
        self.assertContains(page, "1 message")
        self.assertNotContains(page, "2 messages")

    def test_pages_do_not_query_more_with_more_chats(self):
        office = staff("Office", "o@example.com")
        session = lead("hugo@example.com")
        user = services.register_interest(cleaned(email="sam@example.com")).user
        client = Client(HTTP_HOST=OFFICE)
        client.force_login(office)

        def count(path):
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(client.get(path).status_code, 200)
            return len(ctx)
        paths = [f"/leads/{session.pk}/", f"/people/{user.pk}/"]
        chat("hugo@example.com")
        chat(user=user)
        one = [count(p) for p in paths]
        for _ in range(5):
            chat("hugo@example.com")
            chat(user=user)
        self.assertEqual([count(p) for p in paths], one)


class HeardAlignTests(OfficeTestCase):
    def test_newest_answering_journey_wins_in_list_and_filter(self):
        first = lead("a@x.com")
        journey.save_answer(first, "heard_via", options=["friend"])
        second = lead("a@x.com")
        journey.save_answer(second, "heard_via", options=["social_media"])
        lead("a@x.com", finish=False)  # newest journey answered nothing: it does not hide the answer
        self.assertEqual(row_emails("heard=social_media"), ["a@x.com"])
        self.assertEqual(row_emails("heard=friend"), [])
        rows = lead_lists.page(lead_lists.filters_from(type("R", (), {"GET": {}})()), 1)[0]
        self.assertEqual(rows[0]["heard_via"], "Social media")


class ViaChatTests(OfficeTestCase):
    def test_filter_and_tag(self):
        lead("a@x.com")
        lead("b@x.com")
        chat("A@x.com")
        chat("b@x.com", staff_test=True)
        self.assertEqual(row_emails("chat=1"), ["a@x.com"])
        page = get(staff("Office", "o@example.com"), "/leads/")
        self.assertContains(page, "data-via-chat", count=1)


class InvitedTests(OfficeTestCase):
    def setUp(self):
        self.office, self.admin = staff("Office", "o@example.com"), staff("Admin", "a@example.com")
        self.batch = uuid4()

    def invite(self, email, status=Invite.SENT, name="", **extra):
        return Invite.objects.create(email=email, name=name, status=status, batch_id=self.batch, sent_at=timezone.now(), **extra)

    def emails(self, query=""):
        body = get(self.admin, f"/invited/?{query}").content.decode()
        return [e for e in ("a@x.com", "b@x.com", "c@x.com", "d@x.com", "e@x.com") if e in body]

    def test_excludes_accounts_groups_by_email_and_filters(self):
        self.invite("a@x.com", name="Old")
        self.invite("a@x.com", name="Latest")  # same address twice: one row, the latest name
        self.invite("b@x.com", Invite.OPENED, opened_at=timezone.now())
        self.invite("c@x.com", expires_at=timezone.now() - timedelta(days=1))
        self.invite("d@x.com")
        User.objects.create_user("D@x.com", "x")  # has an account (any case, verified or not)
        self.invite("e@x.com", Invite.QUEUED)  # never sent
        self.assertEqual(self.emails("state=all"), ["a@x.com", "b@x.com", "c@x.com"])
        self.assertEqual(self.emails(), ["a@x.com"])  # default: not clicked, still valid
        self.assertEqual(self.emails("state=clicked"), ["b@x.com"])
        self.assertEqual(self.emails("state=expired"), ["c@x.com"])
        self.assertEqual(self.emails("state=all&q=LATEST"), ["a@x.com"])
        body = get(self.admin, "/invited/?state=all").content.decode()
        self.assertEqual(body.count("data-invited-row"), 3)
        self.assertIn("Latest", body)
        self.assertNotIn(">Old<", body)
        self.assertIn("Invite again from System", body)

    def test_opened_but_not_clicked_state_column_and_csv(self):
        now = timezone.now()
        self.invite("a@x.com", email_opened_at=now)  # opened the email only
        self.invite("b@x.com", Invite.OPENED, opened_at=now, email_opened_at=now)  # opened and clicked
        self.invite("c@x.com")  # nothing
        self.invite("d@x.com", email_opened_at=now, expires_at=now - timedelta(days=1))  # opened, but expired
        self.assertEqual(self.emails("state=opened"), ["a@x.com"])
        self.assertEqual(self.emails("state=all"), ["a@x.com", "b@x.com", "c@x.com", "d@x.com"])
        self.assertIn("Opened email", get(self.admin, "/invited/").content.decode())
        with CaptureQueriesContext(connection) as small:
            get(self.admin, "/invited/?state=all")
        self.invite("e@x.com", email_opened_at=now)
        with CaptureQueriesContext(connection) as big:
            get(self.admin, "/invited/?state=all")
        self.assertEqual(len(small), len(big))
        csv_text = get(self.admin, "/invited/export.csv?state=opened").content.decode()
        self.assertIn("opened_email", csv_text.splitlines()[0])
        self.assertIn("a@x.com", csv_text)
        self.assertNotIn("c@x.com", csv_text)

    def test_lists_and_link_to_the_lead_page(self):
        self.invite("a@x.com")
        group = ContactList.objects.create(name="Gym members")
        ContactListMember.objects.create(list=group, email="A@x.com")
        session = lead("a@x.com")
        body = get(self.admin, "/invited/").content.decode()
        self.assertIn("Gym members", body)
        self.assertIn(f"/leads/{session.pk}/", body)

    def test_permissions_and_csv(self):
        self.invite("a@x.com", name="Hugo")
        self.assertEqual(get(None, "/invited/").status_code, 302)
        self.assertEqual(get(User.objects.create_user("m@example.com", "x"), "/invited/").status_code, 404)
        self.assertEqual(get(self.office, "/invited/").status_code, 403)  # Admin and above only (Moishe, 2026-10-30)
        self.assertEqual(get(self.admin, "/invited/").status_code, 200)
        self.assertNotContains(get(self.office, "/leads/"), 'data-office-nav-item="invited"')
        self.assertContains(get(self.admin, "/leads/"), 'data-office-nav-item="invited"')
        self.assertEqual(get(self.office, "/invited/export.csv").status_code, 403)
        response = get(self.admin, "/invited/export.csv")
        self.assertEqual(response.status_code, 200)
        text = response.content.decode()
        self.assertIn("clicked_the_link", text)
        self.assertIn("a@x.com", text)

    def test_page_query_count_does_not_grow(self):
        client = Client(HTTP_HOST=OFFICE)
        client.force_login(self.admin)

        def count():
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(client.get("/invited/?state=all").status_code, 200)
            return len(ctx)
        self.invite("a@x.com")
        one = count()
        for i in range(6):
            self.invite(f"n{i}@x.com")
            ContactListMember.objects.create(list=ContactList.objects.get_or_create(name=f"L{i}")[0], email=f"n{i}@x.com")
            lead(f"n{i}@x.com", finish=False)
        self.assertEqual(count(), one)


class ChatCostTests(OfficeTestCase):
    def test_cost_is_for_developer_level_only(self):
        conversation = chat("a@x.com", total_cost_pence="12.3456")
        Message.objects.create(conversation=conversation, role=Message.ASSISTANT, text="Yes", stop_reason="end_turn", cost_pence="7.5000")
        for role, sees in (("Office", False), ("Admin", False), ("Developer", True)):
            user = staff(role, f"{role.lower()}@example.com")
            for path in ("/chats/", f"/chats/{conversation.pk}/"):
                body = get(user, path).content.decode()
                self.assertEqual("Cost" in body or "12.35p" in body or "7.50p" in body, sees, (role, path))
        self.assertContains(get(staff("Developer", "d2@example.com"), "/chats/"), "12.35p")
        self.assertContains(get(staff("Developer", "d3@example.com"), f"/chats/{conversation.pk}/"), "7.50p")
