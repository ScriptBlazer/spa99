"""The WhatsApp short link (docs/features/system.md, 'WhatsApp short link'). Every place that shows the discount WhatsApp link uses
`short_url(source)`: the address is /whatsapp/ on our own domain, which counts the click (pages.clicks) and forwards to
SiteSettings.discount_contact_url. No import of models here, so any app can use it."""
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

PATH = "/whatsapp/"
KEY = "whatsapp"
SOURCES = ("register", "membership", "memberships", "journey", "visit", "plans", "chat", "email", "gold", "other")  # the allowlist for ?from= (anything else is counted as "other")


# ?msg= keys that pre-fill the WhatsApp message (an allowlist: an unknown key is ignored, free text is never accepted)
MESSAGES = {
    "gold_business": "Hi, I've just applied for the Spa 99 Gold Card and I'm happy to do business with BML.",
}


def short_path(source="other", msg=None):
    params = {"from": source if source in SOURCES else "other"}
    if msg in MESSAGES:
        params["msg"] = msg
    return f"{PATH}?{urlencode(params)}"


def with_message(target, msg):
    """`target` (the WhatsApp link) with the allowlisted message pre-filled as text=. Unchanged for an unknown key, or when the link
    already carries a text= of its own."""
    text = MESSAGES.get(msg)
    if not text:
        return target
    parts = urlsplit(target)
    if "text" in dict(parse_qsl(parts.query)):
        return target
    query = "&".join(filter(None, [parts.query, urlencode({"text": text}, quote_via=quote)]))
    return urlunsplit(parts._replace(query=query))


def short_url(source="other", site=None, msg=None):
    """The short path for `source`, or "" while no WhatsApp link is set in System > Settings (the lines that show it are then hidden)."""
    from plans.models import SiteSettings

    site = site or SiteSettings.load()
    return short_path(source, msg) if site.discount_contact_url else ""
