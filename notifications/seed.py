"""Starting subject lines for the emails. Edited in Control afterwards; only creates what is missing.
DEFAULT_SUBJECTS is also the fallback if a row is deleted, so a send never fails for lack of a subject."""
from .models import NotificationTemplate

# key: (subject, when it is sent)
DEFAULT_SUBJECTS = {
    "verify": ("Confirm your email for Spa 99", "Sign-up: confirm the email address."),
    "password_reset": ("Reset your Spa 99 password", "Forgot password."),
    "password_changed": ("Your Spa 99 password was changed", "After any password change (signed in or reset), team accounts too."),
    "team_invite": ("You've been added to the Spa 99 team", "To a new team member: the link to choose their own password."),
    "welcome": ("Welcome to Spa 99", "After the email address is confirmed."),
    "gold_approver": ("Gold Card application: {name} ({potential} potential)", "To the approver for each Gold application."),
    "gold_approver_repeat": (
        "Gold Card application: {name} ({potential} potential) - repeat application",
        "To the approver when the same person applies again.",
    ),
    "gold_final": ("Final approval: {name} ({potential} potential)", "To every final approver when an approver approves an application that needs final approval."),
    "gold_sent_back": (
        "{name} was approved, but the potential is {potential}. Are you sure?",
        "To every approver when a final approver sends an application back.",
    ),
    "gold_invite": ("Your Spa 99 Gold Card is approved", "To the applicant when Barry approves: the link to set up the account."),
    "gold_active": ("Your Spa 99 Gold Card is active", "To an existing member when Barry approves their Gold application."),
    "gold_ack": ("Your Spa 99 Gold Card application", "To the applicant after they apply."),
    "gold_respond": ("A message about your Spa 99 Gold Card application", "To the applicant when an approver clicks Respond on a Gold application."),
    "gold_declined": ("Your Spa 99 Gold Card application", "To the applicant when an approver declines AND ticks Email the applicant (off by default)."),
    "payment_window_open": ("Your Spa 99 membership can now be set up", "To every registered member when payments open (System > Payments)."),
    "payment_window_reminder": ("A gentle reminder about your Spa 99 membership", "Once, a few days before the payment window closes, to members who have not set up."),
    "payment_staff_alert": ("{count} member(s) are about to lose their launch price", "To the alert addresses in System > Defaults, once a day near the end of the window, while launch-price holders have not set up."),
    "invite": ("You are invited to register for Spa 99", "To a person on an invite list (System > Emails > Invites): the personal register link."),
}

# Old row names kept working until `backfill_site_data` renames them.
LEGACY_KEYS = {"gold_approver": "gold_barry", "gold_approver_repeat": "gold_barry_repeat"}


def run(ensure):
    for key, (subject, note) in DEFAULT_SUBJECTS.items():
        ensure(NotificationTemplate, {"key": key}, {"subject": subject, "note": note})
