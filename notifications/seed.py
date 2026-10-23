"""Starting subject lines for the emails. Edited in Control afterwards; only creates what is missing.
DEFAULT_SUBJECTS is also the fallback if a row is deleted, so a send never fails for lack of a subject."""
from .models import NotificationTemplate

# key: (subject, when it is sent)
DEFAULT_SUBJECTS = {
    "verify": ("Confirm your email for Spa 99", "Sign-up: confirm the email address."),
    "password_reset": ("Reset your Spa 99 password", "Forgot password."),
    "welcome": ("Welcome to Spa 99", "After the email address is confirmed."),
    "gold_barry": ("Gold Card application: {name} ({potential} potential)", "To Barry for each Gold application."),
    "gold_barry_repeat": (
        "Gold Card application: {name} ({potential} potential) - repeat application",
        "To Barry when the same person applies again.",
    ),
    "gold_invite": ("Your Spa 99 Gold Card is approved", "To the applicant when Barry approves: the link to set up the account."),
    "gold_active": ("Your Spa 99 Gold Card is active", "To an existing member when Barry approves their Gold application."),
    "gold_ack": ("Your Spa 99 Gold Card application", "To the applicant after they apply."),
}


def run(ensure):
    for key, (subject, note) in DEFAULT_SUBJECTS.items():
        ensure(NotificationTemplate, {"key": key}, {"subject": subject, "note": note})
