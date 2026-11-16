"""Team levels against every guarded action (docs/features/user-rules.md U2/U3): Viewer, Office, Admin, Developer, Superuser, plus the
Gold approver and Membership approver permissions. One table, one loop: a denied action is a 403, an allowed one is anything but 403/404."""
import uuid

from django.test import Client

from chat.models import Conversation
from common import levels
from gold import services as gold_services
from gold.tests.test_gold import application_data
from office.tests.test_leads import lead
from outreach.models import OutreachEntry
from office.tests.test_office import OFFICE, OfficeTestCase
from plans.tests.helpers import make_team_member
from users import services as user_services
from users.tests.test_register import cleaned

EDIT = "edit"  # Office and up
ADMIN = "admin"  # Admin and up
APPROVALS = "approvals"  # Admin and up, or Office with Membership approver
GOLD = "gold"  # the Gold approver permission on Office or higher (superuser always)
DEVELOPER = "developer"

# (name, method, path with {lead} {person} {gold} {victim}, rule)
ACTIONS = [
    ("sticky note", "post", "/leads/{lead}/notes/add/", EDIT),
    ("approach list page", "get", "/outreach/", EDIT),
    ("add to approach list", "post", "/leads/{lead}/outreach/", EDIT),
    ("email / Message", "post", "/leads/{lead}/message/", EDIT),
    ("archive lead", "post", "/leads/{lead}/archive/", EDIT),
    ("unarchive lead", "post", "/leads/{lead}/unarchive/", EDIT),
    ("mark genuine", "post", "/leads/{lead}/genuine/", EDIT),
    ("fix lead email", "post", "/leads/{lead}/email/", EDIT),
    ("resend follow-up", "post", "/leads/{lead}/resend/", EDIT),
    ("WhatsApp redirect", "get", "/gold/{gold}/respond/", EDIT),
    ("revenue", "get", "/revenue/", ADMIN),
    ("assistant chats", "get", "/chats/", ADMIN),
    ("export", "get", "/people/export.csv", ADMIN),
    ("payment setup", "post", "/people/{person}/setup/", ADMIN),
    ("delete person", "post", "/people/{victim}/delete/", ADMIN),  # each level has its own person to delete
    ("approvals page", "get", "/approvals/", APPROVALS),
    ("approve membership", "post", "/approvals/{person}/approve/", APPROVALS),
    ("approve Gold", "post", "/gold/{gold}/approve/", GOLD),
    ("activity", "get", "/activity/", DEVELOPER),
    ("assistant chat", "get", "/chats/{chat}/", ADMIN),
    ("Gold decline", "post", "/gold/{gold}/decline/", GOLD),
    ("Gold resend", "post", "/gold/{gold}/resend/", GOLD),
    ("person export", "get", "/people/{person}/export/", ADMIN),
    ("lead export", "get", "/leads/{lead}/export/", ADMIN),
    ("approach row: done", "post", "/outreach/{entry}/done/", EDIT),  # each call gets a fresh entry
    ("approach row: remove", "post", "/outreach/{entry}/remove/", EDIT),
    ("approach row: back to leads", "post", "/outreach/{entry}/to-leads/", EDIT),
    ("approach row: archive", "post", "/outreach/{entry}/archive/", EDIT),
]
READS = ["/", "/leads/", "/people/", "/gold/", "/analytics/", "/insights/summary/"]  # every level, Viewer included

# who -> (level, Gold approver, Membership approver)
WHO = {"viewer": (levels.VIEWER, False, False), "office": (levels.OFFICE, False, False), "office+membership": (levels.OFFICE, False, True),
       "office+gold": (levels.OFFICE, True, False), "admin": (levels.ADMIN, False, False), "admin+gold": (levels.ADMIN, True, False),
       "developer": (levels.DEVELOPER, False, False), "superuser": (levels.SUPERUSER, False, False)}


def allowed(who, rule):
    level, gold, membership = WHO[who]
    rank = levels.rank(level)
    if rule == EDIT:
        return rank >= levels.rank(levels.OFFICE)
    if rule == ADMIN:
        return rank >= levels.rank(levels.ADMIN)
    if rule == APPROVALS:
        return rank >= levels.rank(levels.ADMIN) or membership
    if rule == GOLD:
        return level == levels.SUPERUSER or gold
    return rank >= levels.rank(levels.DEVELOPER)


class LevelMatrixTests(OfficeTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.people = {name: make_team_member(f"{name.replace('+', '-')}@example.test", level, approver=gold, membership=membership) for name, (level, gold, membership) in WHO.items()}
        cls.ids = {"lead": lead("hugo@example.com").pk, "person": user_services.register_interest(cleaned(email="reg@example.com")).user.pk,
                   "gold": gold_services.submit_application(application_data())[0].pk, "chat": Conversation.objects.create().pk}
        cls.victims = {name: user_services.register_interest(cleaned(email=f"victim{i}@example.com", mobile=f"0791112{i:04d}")).user.pk for i, name in enumerate(WHO)}

    def call(self, who, method, path):
        client = Client(HTTP_HOST=OFFICE)
        client.force_login(self.people[who])
        entry = OutreachEntry.objects.create(lead_email=f"row{uuid.uuid4().hex[:8]}@example.com").pk if "{entry}" in path else ""
        return getattr(client, method)(path.format(victim=self.victims[who], entry=entry, **self.ids))

    def test_every_level_against_every_guarded_action(self):
        for who in WHO:
            for name, method, path, rule in ACTIONS:
                code = self.call(who, method, path).status_code
                if allowed(who, rule):
                    self.assertNotIn(code, (403, 404), f"{who} should be allowed: {name}")
                else:
                    self.assertEqual(code, 403, f"{who} should be refused: {name}")

    def test_every_level_reads_leads_people_and_gold(self):
        for who in WHO:
            for path in READS:
                self.assertEqual(self.call(who, "get", path).status_code, 200, f"{who} {path}")

    def test_the_navigation_and_buttons_follow_the_level(self):
        for who, links in (("viewer", ()), ("office", ("/outreach/",)), ("office+membership", ("/outreach/", "/approvals/")), ("admin", ("/outreach/", "/approvals/", "/revenue/", "/chats/"))):
            page = self.call(who, "get", "/").content.decode()
            for link in ("/outreach/", "/approvals/", "/revenue/", "/chats/"):
                self.assertEqual(f'href="{link}"' in page, link in links, f"{who} {link}")
        gold_page = self.call("viewer", "get", "/gold/{gold}/").content.decode()
        self.assertNotIn("data-channels", gold_page)  # no WhatsApp or Email buttons for a Viewer
        self.assertNotIn("wa.me", gold_page)
        self.assertIn("data-channels", self.call("office", "get", "/gold/{gold}/").content.decode())

    def test_the_helpers_agree_with_the_table(self):
        for who, (level, gold, membership) in WHO.items():
            user = self.people[who]
            self.assertEqual(levels.can_approve_memberships(user), allowed(who, APPROVALS), who)
            self.assertEqual(levels.is_approver(user), allowed(who, GOLD), who)
