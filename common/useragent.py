"""Rough device class from a User-Agent string. Good enough for statistics; never used for security."""
import re

_BOT = re.compile(r"bot|crawl|spider|slurp|headless|python-requests|curl|wget|monitor|preview|facebookexternalhit", re.I)
_TABLET = re.compile(r"ipad|tablet|kindle|silk", re.I)
_MOBILE = re.compile(r"mobi|iphone|ipod|android", re.I)


def device_type(user_agent):
    """'bot', 'tablet', 'mobile', 'desktop' or 'unknown'."""
    ua = (user_agent or "").strip()
    if not ua:
        return "unknown"
    if _BOT.search(ua):
        return "bot"
    if _TABLET.search(ua) or ("android" in ua.lower() and "mobi" not in ua.lower()):
        return "tablet"
    if _MOBILE.search(ua):
        return "mobile"
    return "desktop"
