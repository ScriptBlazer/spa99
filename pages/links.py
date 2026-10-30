"""The WhatsApp short link (docs/features/system.md, 'WhatsApp short link'). Every place that shows the discount WhatsApp link uses
`short_url(source)`: the address is /whatsapp/ on our own domain, which counts the click (pages.clicks) and forwards to
the wa.me link built from SiteSettings.whatsapp_number and whatsapp_message. No import of models here, so any app can use it."""
from urllib.parse import quote, urlencode

PATH = "/whatsapp/"
KEY = "whatsapp"
SOURCES = ("register", "membership", "memberships", "journey", "visit", "plans", "chat", "email", "gold", "gold_card", "home", "spa", "tour", "book", "footer", "home_sale", "other")  # the allowlist for ?from= (anything else is counted as "other")


# ?msg= keys that pre-fill the WhatsApp message (an allowlist: an unknown key is ignored, free text is never accepted)
MESSAGES = {
    "gold_business": "Hi, I've just applied for the Spa 99 Gold Card and I'm happy to do business with BML.",
}


RATES = "rates"  # the msg key whose text is the editable "better prices" message (SiteSettings.whatsapp_rate_message)


def short_path(source="other", msg=None):
    params = {"from": source if source in SOURCES else "other"}
    if msg in MESSAGES or msg == RATES:
        params["msg"] = msg
    return f"{PATH}?{urlencode(params)}"


def target_url(site, msg=None):
    """https://wa.me/<number>?text=<message>, built from System > Settings (number and message). A known `msg` key replaces the saved
    message. "" while no number is set."""
    if not site.whatsapp_number:
        return ""
    if msg == RATES:
        text = site.whatsapp_rate_message or site.whatsapp_message
    else:
        text = MESSAGES.get(msg) or site.whatsapp_message
    url = f"https://wa.me/{site.whatsapp_number}"
    return f"{url}?text={quote(text, safe='')}" if text else url


def short_url(source="other", site=None, msg=None):
    """The short path for `source`, or "" while no WhatsApp number is set in System > Settings (the lines that show it are then hidden)."""
    from plans.models import SiteSettings

    site = site or SiteSettings.load()
    return short_path(source, msg) if site.whatsapp_number else ""
