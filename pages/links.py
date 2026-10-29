"""The WhatsApp short link (docs/features/system.md, 'WhatsApp short link'). Every place that shows the discount WhatsApp link uses
`short_url(source)`: the address is /whatsapp/ on our own domain, which counts the click (pages.clicks) and forwards to
SiteSettings.discount_contact_url. No import of models here, so any app can use it."""
from urllib.parse import urlencode

PATH = "/whatsapp/"
KEY = "whatsapp"
SOURCES = ("register", "membership", "plans", "chat", "email", "other")  # the allowlist for ?from= (anything else is counted as "other")


def short_path(source="other"):
    return f"{PATH}?{urlencode({'from': source if source in SOURCES else 'other'})}"


def short_url(source="other", site=None):
    """The short path for `source`, or "" while no WhatsApp link is set in System > Settings (the lines that show it are then hidden)."""
    from plans.models import SiteSettings

    site = site or SiteSettings.load()
    return short_path(source) if site.discount_contact_url else ""
