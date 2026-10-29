"""One command that fills System with the real starting values (docs/features/system.md, "Live setup").

  manage.py setup_live --dry-run    # show what it would do; change nothing, send nothing
  manage.py setup_live              # do it

Order: seed_phase1 (seed_all) first, setup_roles (the groups), then the values below. It only fills what is empty: an edited value is never overwritten,
an existing account only gains a missing level or role (nothing is ever removed), and running it twice changes nothing.
New accounts get NO password: each is invited by email to choose their own (sent after the commit, never on a dry run).
Never prints a password, a link or a secret.

Not a migration, on purpose (data and seeds never go in migrations).
"""
from io import StringIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction

from common import levels
from plans.management.commands.seed_phase1 import INITIAL_STAFF_ALERT_EMAIL, seed_all
from plans.models import SiteSettings
from system import audit
from system.models import SiteDefaults, SystemEvent
from system.services import ChangeRefused, record_direct, save_logged
from users.management.commands.create_team_member import make_member

# Backends that never deliver: a real run refuses them, so the team invites can't silently go nowhere.
NO_EMAIL_BACKENDS = {"django.core.mail.backends.console.EmailBackend", "django.core.mail.backends.dummy.EmailBackend"}

# ======================================================================================================================
# THE LIVE VALUES. Edit them here and nowhere else (never in app code). Everything below this block is logic only.
# ======================================================================================================================
TEAM = [
    {"email": "moishe@spa99.uk", "first_name": "Moishe", "last_name": "Berkowitz", "level": levels.DEVELOPER, "approver": False, "final_approver": True},
    {"email": "barry@spa99.uk", "first_name": "Barry", "last_name": "Lobenstein", "level": levels.ADMIN, "approver": True, "final_approver": False},
]
SITE_SETTINGS = {  # SiteSettings field -> value. Filled only while the field is empty.
    "contact_email": "hello@spa99.uk",
    "gold_approver_cc": "moishe@spa99.uk",
    "discount_contact_url": "https://wa.me/447441919990",  # the spa WhatsApp (07441 919990)
}
STAFF_ALERT_EMAILS = INITIAL_STAFF_ALERT_EMAIL  # System > Defaults > Payment alert emails. Filled by seed_phase1, once only (kept there:
#   the seed imports nothing from this command, so moving it here would be a circular import).
OLD_SUBJECTS = {"gold_final": "Final approval: {name} (Low potential)",
                "gold_sent_back": "{name} was approved, but the potential is Low. Are you sure?"}  # the old defaults, replaced only on an exact match
FINAL_APPROVAL_ON = False  # left at its default (off); System > Approval turns it on.
# ======================================================================================================================


class Command(BaseCommand):
    help = "Fill System with the real starting values (seed first, then the team, contact email, Gold CC, WhatsApp). Use --dry-run first."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show what would be done; change nothing and send nothing.")
        parser.add_argument("--no-email-check", action="store_true", help="Run even though email only prints or drops mail (the invites will not arrive).")

    def handle(self, *args, **options):
        self.dry = options["dry_run"]
        if not self.dry and not options["no_email_check"] and settings.EMAIL_BACKEND in NO_EMAIL_BACKENDS:
            raise CommandError("Email is not set up (EMAIL_BACKEND only prints or drops mail), so the team invites would never arrive. "
                               "Set up Postmark first (docs/GO-LIVE.md step 7), send yourself a test, then run this again. "
                               "--no-email-check runs it anyway (then use Forgot password once email works).")
        self.problems = self.changed = self.left = 0
        self.invites = []
        try:
            with transaction.atomic():
                self.run()
                if self.dry:
                    transaction.set_rollback(True)  # nothing is kept, and no invite is queued (see invite())
        except (ChangeRefused, ValidationError) as error:
            raise CommandError(str(error)) from error
        verb = "would be set" if self.dry else "set"
        self.stdout.write(f"{'Dry run (nothing saved, nothing sent)' if self.dry else 'Done'}: {self.changed} {verb}, {self.left} already set (left alone), "
                          f"{self.problems} problem{'s' if self.problems != 1 else ''}.")
        self.next_steps()

    # ---------- the steps ----------

    def run(self):
        before = SiteDefaults.load()
        alert_before = (before.staff_alert_emails, before.staff_alert_seeded)
        created = seed_all()
        self.say(f"seed_phase1: {'would create' if self.dry else 'created'} {sum(created.values())} starting rows" if created
                 else "seed_phase1: everything is already there")
        call_command("setup_roles", stdout=StringIO())  # the level and role groups (safe to repeat); quiet, it prints its own lines
        self.alert_email(alert_before)
        for person in TEAM:
            self.team_member(person)
        self.site_settings()
        self.email_subjects()
        self.say(f"final_approval_on: left at its default ({'on' if FINAL_APPROVAL_ON else 'off'}); turn it on in System > Approval")

    def next_steps(self):
        """The closing block. It only reads the launch switches (never changes them) so the soft-launch state is visible at a glance."""
        if self.dry:
            return self.say("\nNothing was saved. Run it again without --dry-run to do it.")
        site, defaults = SiteSettings.load(), SiteDefaults.load()

        def state(on):
            return "ON" if on else "off"

        self.say("\nLaunch state (changed in System > Settings > Launch, never by this script):\n"
                 f"  Memberships public: {state(site.memberships_public)} (off = hidden until you open it)\n"
                 f"  Journey asks for an email: {state(site.journey_email_gate)}\n"
                 f"  Final approval: {state(site.final_approval_on)}\n"
                 f"  Booking open: {state(site.booking_open)}\n"
                 f"  Payments: not opened by this script (window is {defaults.payment_window_days} days once you open them)\n"
                 "  This script never emails the public; the only mail it sends is a new team member's invite.")
        self.say("\nNext steps:\n"
                 "  1. Moishe and Barry: open the invite email (the link lasts 1 hour) and choose a password. Link expired? System > Team, resend.\n"
                 f"  2. Sign in at {settings.SYSTEM_URL}/dev-login/, then enter the unlock code (SYSTEM_UNLOCK_CODE in the live .env).\n"
                 "  3. Check Settings > Launch: Memberships public off, final approval as you want it. Do not open payments yet.\n"
                 "  4. Check Defaults (payment alert address, caps) and Emails (a test to yourself).\n"
                 "  5. Check /health/ answers OK and the worker is running (System dashboard: queue and last jobs).\n"
                 "  6. Take a database backup before opening anything to the public.")

    def say(self, text):
        self.stdout.write(text)

    def done(self, label, text, verbs=("set", "would set")):
        self.changed += 1
        self.say(f"{label}: {verbs[1] if self.dry else verbs[0]} {text}")

    def kept(self, label, text="already set (left alone)"):
        self.left += 1
        self.say(f"{label}: {text}")

    def problem(self, label, text):
        self.problems += 1
        self.say(f"{label}: PROBLEM, {text}. Skipped.")

    def alert_email(self, before):
        """seed_phase1 fills this once and only while empty; here we just report what it did."""
        row = SiteDefaults.load()
        label = "staff_alert_emails"
        if not before[0] and not before[1] and row.staff_alert_emails:
            self.done(label, f"to {row.staff_alert_emails} (by seed_phase1)")
        elif before[0]:
            self.kept(label)
        else:
            self.kept(label, "already seeded once and cleared on purpose (left alone)")

    def email_subjects(self):
        """Saved subjects that still equal the exact old default text (it said 'Low potential') get the new {potential} text.
        Any other text is a custom edit and is never touched."""
        from notifications.models import NotificationTemplate
        from notifications.seed import DEFAULT_SUBJECTS

        for key, old in OLD_SUBJECTS.items():
            row = NotificationTemplate.objects.filter(key=key).first()
            label = f"email subject {key}"
            if row is None or row.subject != old:
                self.kept(label)
                continue
            row.subject = DEFAULT_SUBJECTS[key][0]
            row._history_user = None
            row.save(update_fields=["subject", "updated_at"])
            self.done(label, f"to the {{potential}} wording")

    def site_settings(self):
        site = SiteSettings.load()
        fields = []
        for name, value in SITE_SETTINGS.items():
            try:
                SiteSettings._meta.get_field(name).run_validators(value)  # the same rules the System forms use
            except ValidationError as error:  # a bad value is reported, the rest carry on
                self.problem(name, f"the value is invalid ({'; '.join(error.messages)})")
                continue
            if getattr(site, name):
                self.kept(name)
            else:
                setattr(site, name, value)
                fields.append(name)
                self.done(name, f"to {value}")
        if fields:
            save_logged(site, None, fields=fields)  # recorded in the change log as a script (no person)

    def team_member(self, person):
        email, label = person["email"].strip().lower(), f"team {person['email']}"
        try:
            validate_email(email)
        except ValidationError:
            return self.problem(label, "not a valid email address")
        User = get_user_model()
        user = User.objects.filter(email__iexact=email).first()
        want_level, want_approver, want_final = person["level"], person["approver"], person["final_approver"]
        if user is not None and not user.is_active:
            return self.problem(label, "the account is deactivated (reactivate it in System > Team)")
        if user is not None:
            return self.existing(user, label, want_level, want_approver, want_final)
        try:
            user, _ = make_member(email, want_level, want_approver, want_final, person["first_name"], person["last_name"], password=None, via="setup_live")
        except ChangeRefused as error:
            return self.problem(label, str(error))
        self.done(label, f"{self.describe(want_level, want_approver, want_final)}, invite to choose a password "
                         f"{'would be sent' if self.dry else 'will be sent after saving'}", verbs=("created as", "would create as"))
        self.invite(user)

    def existing(self, user, label, want_level, want_approver, want_final):
        """Only ever adds: a higher level is kept, roles already held are kept."""
        held_level = levels.held_level(user)
        approver, final = levels.held_roles(user)
        level = want_level if levels.rank(want_level) > levels.rank(held_level) else held_level
        new_approver, new_final = approver or want_approver, final or want_final
        if (level, new_approver, new_final) == (held_level, approver, final) and user.is_staff:
            return self.kept(label, f"exists as {self.describe(held_level, approver, final)} (left alone)")
        if user.is_superuser:  # apply_level would clear the superuser flag: add the role groups only
            groups = ([levels.APPROVER_GROUP] if new_approver and not approver else []) + ([levels.FINAL_APPROVER_GROUP] if new_final and not final else [])
            user.groups.add(*[Group.objects.get_or_create(name=name)[0] for name in groups])
        else:
            from system.team import apply_level

            try:
                apply_level(user, level, new_approver, actor=None, final=new_final)
            except ChangeRefused as error:
                return self.problem(label, str(error))
        text = self.describe(level, new_approver, new_final)
        sentence = f"Set {user.email} to {text} (setup_live)"
        record_direct(None, "team", "users.user", user, "level", self.describe(held_level, approver, final), text, sentence=sentence)
        audit.log_event(SystemEvent.ROLE_CHANGED, detail={"person": user.email, "new": text, "via": "setup_live"}, email="command line", sentence=sentence)
        self.done(label, f"existing account now {text} (nothing removed, password and name untouched)")

    @staticmethod
    def describe(level, approver, final):
        return levels.LABELS[level] + (" + Approver" if approver else "") + (" + Final approver" if final else "")

    def invite(self, user):
        """Sent only after the commit, never on a dry run (so a rollback can never email)."""
        if self.dry:
            return
        from users.tasks import send_team_invite_email

        def send(pk=str(user.pk), email=user.email):
            try:
                ok = send_team_invite_email(pk) == "sent"
            except Exception:  # noqa: BLE001 - reported below, never a crash after the data is saved
                ok = False
            if not ok:
                self.problems += 1
            self.say(f"invite {email}: " + ("invite sent (the link lasts 1 hour)" if ok else "invite FAILED: resend in System > Team"))

        transaction.on_commit(send)
