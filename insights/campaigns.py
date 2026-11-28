"""Campaign tags and channels (docs/features/analytics.md A5): cleaning utm values, the channel of a visit, and the
link maker's tagged address. Pure functions: no database, no request."""
import re
from urllib.parse import parse_qsl, urlencode, urlparse

_JUNK = re.compile(r"[^a-z0-9_-]")
# Each part is cut so the whole key and a step ("source|medium|campaign|content:registered") fit the 100 character dimension column.
LIMITS = {"source": 20, "medium": 15, "campaign": 30, "content": 20}
CHANNELS = ("campaign", "search", "social", "email", "referral", "direct")

# The link maker (docs/features/analytics-design.md 3.5): placement -> (label, utm_source, utm_medium, utm_content).
PLACEMENTS = {
    "instagram-post": ("Instagram post", "instagram", "social", "post"),
    "instagram-story": ("Instagram story", "instagram", "social", "story"),
    "instagram-bio": ("Instagram bio", "instagram", "social", "bio"),
    "whatsapp": ("WhatsApp", "whatsapp", "message", ""),
    "email": ("Email", "email", "email", ""),
    "flyer-qr": ("Flyer QR", "flyer", "print", "qr"),
    "other": ("Other", "other", "link", ""),
}


def clean_utm(value, limit=60):
    """Lower-cased; spaces become '-'; only letters, digits, '-' and '_'; cut to `limit`."""
    text = re.sub(r"\s+", "-", str(value or "").strip().lower())
    return _JUNK.sub("", text)[:limit]


def utm_from_query(query):
    """{'source','medium','campaign','content'} cleaned, from a request's GET (a QueryDict or dict). Nothing else is read."""
    return {part: clean_utm(query.get(f"utm_{part}", ""), LIMITS[part]) for part in LIMITS}


def campaign_key(utm):
    """'source|medium|campaign|content' when any tag is present, else ''."""
    if not any(utm.values()):
        return ""
    return "|".join(utm[part] for part in LIMITS)


def split_key(key):
    """The four parts of a campaign key (empty strings when it is 'other' or odd)."""
    parts = key.split("|")
    return dict(zip(LIMITS, parts)) if len(parts) == 4 else dict.fromkeys(LIMITS, "")


def placement_label(key):
    """The link maker's name for a campaign key made by it ('Instagram story'), else None."""
    parts = split_key(key)
    for label, source, medium, content in PLACEMENTS.values():
        if (parts["source"], parts["medium"], parts["content"]) == (source, medium, content):
            return label
    return None


_SEARCH = re.compile(r"(^|\.)(google\.[a-z.]{2,6}|bing\.com|duckduckgo\.com|yahoo\.[a-z.]{2,6}|ecosia\.org)$")
_SOCIAL = re.compile(r"(^|\.)(instagram\.com|facebook\.com|fb\.com|fb\.me|tiktok\.com|x\.com|twitter\.com|t\.co|linkedin\.com|lnkd\.in|"
                     r"whatsapp\.com|wa\.me|pinterest\.[a-z.]{2,6}|youtube\.com|youtu\.be)$")
_MAIL = re.compile(r"^(mail\.google\.com|outlook\.(live|office|office365)\.com|mail\.yahoo\.com|mail\.proton\.me|mail\.aol\.com|webmail\..*)$|(^|\.)mail\.[a-z.]+$")
IN_APP = {"instagram": "instagram", "facebook": "facebook"}  # in-app browsers often send no referrer


def channel_for(utm, referrer_host, browser=""):
    """(channel, source) of a visit. referrer_host: 'direct' (none) or a site name; never our own site (the caller drops it)."""
    if any(utm.values()):
        channel = "email" if utm["medium"] == "email" else "campaign"
        return channel, utm["source"] or utm["medium"] or "campaign"
    host = (referrer_host or "direct").lower()
    if host == "direct":
        if browser in IN_APP:
            return "social", IN_APP[browser]
        return "direct", "direct"
    if _MAIL.search(host):
        return "email", host
    if _SEARCH.search(host):
        return "search", host
    if _SOCIAL.search(host):
        return "social", host
    return "referral", host


def build_link(path, placement, name, base=""):
    """The tagged address for the link maker: `path` (a path on our own site, e.g. '/plans/'), a PLACEMENTS key and a short name.
    Returns the path with ?utm_source=...&utm_medium=...&utm_campaign=...[&utm_content=...] (prefixed with `base`, e.g. the site URL,
    when given). Raises ValueError for an unknown placement, an empty name or a path that is not on our own site."""
    if placement not in PLACEMENTS:
        raise ValueError("Unknown placement.")
    campaign = clean_utm(name, LIMITS["campaign"])
    if not campaign:
        raise ValueError("Give the link a short name.")
    parsed = urlparse(str(path or "/"))
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/") or parsed.path.startswith("//"):
        raise ValueError("The page must be a path on this site.")
    _, source, medium, content = PLACEMENTS[placement]
    tags = [("utm_source", source), ("utm_medium", medium), ("utm_campaign", campaign)] + ([("utm_content", content)] if content else [])
    kept = [(k, v) for k, v in parse_qsl(parsed.query) if not k.startswith("utm_")]
    return f"{base.rstrip('/')}{parsed.path}?{urlencode(kept + tags)}"
