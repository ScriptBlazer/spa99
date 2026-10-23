"""Team levels (common.levels): who is what, who may manage whom, and Approver."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from common import levels

User = get_user_model()


def person(email, level=None, approver=False, **flags):
    user = User.objects.create_user(email, "x", is_staff=level is not None or flags.get("is_superuser", False), **flags)
    if level in levels.GROUP_FOR:
        user.groups.add(Group.objects.get_or_create(name=levels.GROUP_FOR[level])[0])
    if approver:
        user.groups.add(Group.objects.get_or_create(name="Approver")[0])
    return user


class LevelTests(TestCase):
    def test_level_of_takes_the_highest_and_needs_staff_and_active(self):
        both = person("both@example.com", "office")
        both.groups.add(Group.objects.get_or_create(name="Developer")[0])
        self.assertEqual(levels.level_of(both), "developer")
        self.assertEqual(levels.level_of(person("root@example.com", is_superuser=True)), "superuser")
        member = User.objects.create_user("member@example.com", "x")
        member.groups.add(Group.objects.get(name="Developer"))
        self.assertEqual(levels.level_of(member), "none")  # a group alone, without is_staff, is nothing
        gone = person("gone@example.com", "admin")
        gone.is_active = False
        self.assertEqual(levels.level_of(gone), "none")
        self.assertEqual(levels.level_of(None), "none")

    def test_approver_needs_a_level_and_a_superuser_always_is(self):
        self.assertTrue(levels.is_approver(person("a@example.com", "office", approver=True)))
        self.assertFalse(levels.is_approver(person("b@example.com", "admin")))
        stray = User.objects.create_user("stray@example.com", "x", is_staff=True)
        stray.groups.add(Group.objects.get_or_create(name="Approver")[0])
        self.assertFalse(levels.is_approver(stray))  # Approver without a level counts for nothing
        self.assertTrue(levels.is_approver(person("root@example.com", is_superuser=True)))

    def test_can_manage_matrix(self):
        users = {name: person(f"{name}@example.com", name) for name in ("office", "admin", "developer")}
        users["superuser"] = person("root@example.com", is_superuser=True)
        users["superuser2"] = person("root2@example.com", is_superuser=True)
        users["nobody"] = User.objects.create_user("nobody@example.com", "x")
        manage = {(a, t): levels.can_manage(users[a], users[t]) for a in users for t in users}
        for actor in ("office", "admin", "nobody"):  # only developers and superusers manage the team
            self.assertFalse(any(manage[(actor, t)] for t in users), actor)
        self.assertTrue(manage[("developer", "office")] and manage[("developer", "admin")] and manage[("developer", "nobody")])
        self.assertFalse(manage[("developer", "developer")])  # same level below superuser: refused
        self.assertFalse(manage[("developer", "superuser")])
        self.assertTrue(all(manage[("superuser", t)] for t in ("office", "admin", "developer", "superuser2", "nobody")))
        self.assertFalse(manage[("superuser", "superuser")])  # never yourself
        self.assertFalse(manage[("developer", "developer")] or manage[("admin", "admin")])

    def test_can_assign_only_below_your_own_level_unless_superuser(self):
        developer, root = person("d@example.com", "developer"), person("root@example.com", is_superuser=True)
        self.assertTrue(levels.can_assign(developer, "admin") and not levels.can_assign(developer, "developer"))
        self.assertTrue(levels.can_assign(root, "superuser"))
