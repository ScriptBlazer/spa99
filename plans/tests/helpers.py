"""Test helper: the email recipients live in SiteSettings now (System > Emails), so tests that send mail set them."""
from plans.models import SiteSettings


def set_recipients(approvers="approver@example.test", cc="cc@example.test", contact="hello@example.test"):
    site = SiteSettings.load()
    site.gold_approver_emails, site.gold_approver_cc, site.contact_email = approvers, cc, contact
    site.save()
    return site
