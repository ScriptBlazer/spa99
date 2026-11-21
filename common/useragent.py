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


# ---------- browser and system (analytics: docs/features/analytics.md, A1) ----------
# Order matters: in-app browsers and Edge/Samsung also say "Chrome" or "Safari" in their user agent.
_BROWSERS = (
    ("instagram", re.compile(r"instagram", re.I)),
    ("facebook", re.compile(r"FBAN|FBAV|FB_IAB|FBIOS", re.I)),
    ("samsung", re.compile(r"SamsungBrowser", re.I)),
    ("edge", re.compile(r"Edg/|EdgA/|EdgiOS/|Edge/", re.I)),
    ("firefox", re.compile(r"Firefox/|FxiOS/", re.I)),
    ("other", re.compile(r"OPR/|Opera|OPiOS|Vivaldi|DuckDuckGo|YaBrowser|UCBrowser", re.I)),  # Chrome look-alikes we do not list
    ("chrome", re.compile(r"Chrome/|CriOS/", re.I)),
    ("safari", re.compile(r"Version/[\d.]+.*Safari/|iPhone|iPad|iPod", re.I)),
)
_SYSTEMS = (
    ("ios", re.compile(r"iPhone|iPad|iPod", re.I)),
    ("android", re.compile(r"Android", re.I)),
    ("windows", re.compile(r"Windows", re.I)),
    ("macos", re.compile(r"Macintosh|Mac OS X", re.I)),
    ("linux", re.compile(r"Linux|X11", re.I)),
)


def browser_family(user_agent):
    """'chrome', 'safari', 'edge', 'firefox', 'samsung', 'instagram' (in-app), 'facebook' (in-app) or 'other'."""
    ua = user_agent or ""
    for name, pattern in _BROWSERS:
        if pattern.search(ua):
            return name
    return "other"


def os_family(user_agent):
    """'ios', 'android', 'windows', 'macos', 'linux' or 'other'."""
    ua = user_agent or ""
    for name, pattern in _SYSTEMS:
        if pattern.search(ua):
            return name
    return "other"
