"""The Visitors area of Analytics (docs/features/analytics.md A9, docs/features/analytics-design.md): one stored payload per range, built
by the snapshot job from the stored daily rows (never while a page loads). Everything is a count or a ratio of counts: no person in it."""
import json
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

from common import geoip
from insights import campaigns, metrics
from insights.metrics import K
from insights.models import DailyMetric
from insights.rollup import basis_points
from insights.visitors import LENGTH_BUCKETS, STEPS, WEEKDAYS

KEYS = (
    K.VISITORS, K.PAGE_VIEWS, K.VISITS, K.BOUNCES, K.VISIT_PAGES, K.VISIT_SECONDS, K.VISIT_LENGTH, K.DEVICES, K.BROWSERS, K.SYSTEMS, K.COUNTRIES,
    K.VIEWS_BY_DEVICE, K.VIEWS_BY_BROWSER, K.VIEWS_BY_SYSTEM, K.ENTRY_PAGES, K.EXIT_PAGES, K.ENGAGED_SECONDS, K.ENGAGED_VIEWS, K.SCROLL,
    K.VISITS_BY_CHANNEL, K.VISIT_SOURCES, K.CAMPAIGN_VISITS, K.CAMPAIGN_STEPS, K.CHANNEL_STEPS, K.CONTACT_TAPS, K.CONTACT_TAPS_PAGE, K.VISIT_HOUR,
)
DEVICE_NAMES = {"mobile": "Phone", "tablet": "Tablet", "desktop": "Computer"}
BROWSER_NAMES = {"chrome": "Chrome", "safari": "Safari", "edge": "Edge", "firefox": "Firefox", "samsung": "Samsung Internet",
                 "instagram": "Instagram app", "facebook": "Facebook app", "other": "Other"}
SYSTEM_NAMES = {"ios": "iPhone and iPad", "android": "Android", "windows": "Windows", "macos": "Mac", "linux": "Linux", "other": "Other"}
CHANNEL_NAMES = {"campaign": "Campaign links", "search": "Search", "social": "Social", "email": "Email", "referral": "Other sites", "direct": "Direct"}
CONTACT_KINDS = {"whatsapp": "WhatsApp", "phone": "Phone", "email": "Email", "instagram": "Instagram", "map": "Map"}
SCROLL_BUCKETS = (0, 25, 50, 75, 100)
DAY_NAMES = {"mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday", "fri": "Friday", "sat": "Saturday", "sun": "Sunday"}
MIN_FOR_PATTERN = 20  # visits before a busiest-hour sentence means anything
PAGES_CAP = 30
COUNTRIES_SHOWN = 10
SOURCES_SHOWN = 10

_country_names = {}


def country_name(code):
    if not _country_names:
        path = Path(__file__).resolve().parent.parent / "common" / "data" / "countries.json"
        _country_names.update({c["iso"].lower(): c["name"] for c in json.loads(path.read_text(encoding="utf-8"))})
    return {"unknown": "Unknown", "other": "Other"}.get(code) or _country_names.get(code, code.upper())


def _by_label(rows, labels):
    """{label: {(key, dimension): value}} for the given labels."""
    wanted, out = set(labels), defaultdict(lambda: defaultdict(int))
    for day, key, dimension, value in rows:
        if day in wanted:
            out[day][(key, dimension)] += value
    return out


def _sum(per_label, labels):
    total = defaultdict(int)
    for label in labels:
        for ident, value in per_label.get(label, {}).items():
            total[ident] += value
    return total


def figures(s):
    """The five overview figures from one set of sums (a day, a week or the whole range)."""
    visits, closed = s.get((K.VISITS, ""), 0), sum(v for (k, d), v in s.items() if k == K.VISIT_LENGTH)
    return {
        "visitors": s.get((K.VISITORS, ""), 0), "visits": visits,
        "pages_per_visit": round(s.get((K.VISIT_PAGES, ""), 0) / visits, 2) if visits else None,
        "avg_visit_seconds": round(s.get((K.VISIT_SECONDS, ""), 0) / closed) if closed else None,
        "bounce_rate_bp": basis_points(max(s.get((K.BOUNCES, ""), 0), 0), visits),
    }


def _change(now, before):
    if now is None or before is None or not before:
        return {"percent": None, "direction": "none"}
    pct = round((now - before) * 100 / before)
    return {"percent": abs(pct), "direction": "flat" if pct == 0 else ("up" if pct > 0 else "down")}


def _dims(s, key):
    return {d: v for (k, d), v in s.items() if k == key and d}


def _items(s, key, names, views_key=None, order=None):
    found = _dims(s, key)
    total = sum(found.values())
    keys = list(order or []) + sorted((d for d in found if d not in (order or [])), key=lambda d: (-found[d], d))
    items = [{"dimension": d, "label": names.get(d, d.title()), "value": found.get(d, 0), "share_bp": basis_points(found.get(d, 0), total) or 0,
              **({"views": s.get((views_key, d), 0)} if views_key else {})} for d in keys]
    return sorted(items, key=lambda i: (i["dimension"] in ("other", "unknown"), -i["value"], i["dimension"]))


def _ranked_with_other(s, key, limit, name):
    """Top `limit` named rows, then 'Other' (the rest plus the stored overflow), and 'Unknown' (where it applies) last."""
    found = _dims(s, key)
    total = sum(found.values())
    named = sorted(((d, v) for d, v in found.items() if d not in ("other", "unknown")), key=lambda i: (-i[1], i[0]))
    rest = sum(v for _, v in named[limit:]) + found.get("other", 0)
    rows = [(d, v, name(d)) for d, v in named[:limit]]
    if rest:
        rows.append(("other", rest, "Other"))
    if found.get("unknown"):
        rows.append(("unknown", found["unknown"], "Unknown"))
    return [{"dimension": d, "label": label, "value": v, "share_bp": basis_points(v, total) or 0} for d, v, label in rows]


def _page_label(group):
    return "Home" if group == "home" else group.replace("-", " ").replace("_", " ").capitalize()


def _pages(s):
    views, entry, exit_ = _dims(s, K.PAGE_VIEWS), _dims(s, K.ENTRY_PAGES), _dims(s, K.EXIT_PAGES)
    visits = s.get((K.VISITS, ""), 0)
    most = []
    for group, count in sorted(views.items(), key=lambda i: (-i[1], i[0]))[:PAGES_CAP]:
        engaged = s.get((K.ENGAGED_VIEWS, group), 0)
        scroll = {str(b): s.get((K.SCROLL, f"{group}:{b}"), 0) for b in SCROLL_BUCKETS}
        reported = sum(scroll.values())
        most.append({"page": group, "label": _page_label(group), "views": count, "reported_views": engaged,
                     "avg_seconds": round(s.get((K.ENGAGED_SECONDS, group), 0) / engaged) if engaged else None,
                     "scroll": scroll, "scrolled_half_bp": basis_points(scroll["50"] + scroll["75"] + scroll["100"], reported)})

    def ranked(found):
        return [{"page": g, "label": _page_label(g), "visits": v, "share_bp": basis_points(v, visits) or 0}
                for g, v in sorted(found.items(), key=lambda i: (-i[1], i[0]))[:PAGES_CAP]]
    return {"most_viewed": most, "first": ranked(entry), "last": ranked(exit_)}


def _steps(s, key, prefix_sep=":"):
    """{identity: {step: count}} from 'identity:step' dimensions."""
    out = defaultdict(lambda: dict.fromkeys(STEPS, 0))
    for dimension, value in _dims(s, key).items():
        identity, _, step = dimension.rpartition(prefix_sep)
        if step in STEPS:
            out[identity][step] += value
    return out


def _channels(s):
    visits = _dims(s, K.VISITS_BY_CHANNEL)
    total = sum(visits.values())
    steps = _steps(s, K.CHANNEL_STEPS)
    rows = [{"channel": c, "label": CHANNEL_NAMES[c], "visits": visits.get(c, 0), "share_bp": basis_points(visits.get(c, 0), total) or 0,
             "steps": steps.get(c, dict.fromkeys(STEPS, 0))} for c in CHANNEL_NAMES]
    return sorted(rows, key=lambda r: (-r["visits"], list(CHANNEL_NAMES).index(r["channel"])))


def _campaigns(s):
    steps = _steps(s, K.CAMPAIGN_STEPS)
    rows = []
    for key, visits in _dims(s, K.CAMPAIGN_VISITS).items():
        parts = campaigns.split_key(key)
        rows.append({"key": key, **parts, "campaign": parts["campaign"] or key, "placement": campaigns.placement_label(key), "visits": visits,
                     "steps": steps.get(key, dict.fromkeys(STEPS, 0))})
    return sorted(rows, key=lambda r: (-r["visits"], r["key"]))


def _contact(s):
    kinds = _dims(s, K.CONTACT_TAPS)
    order = [k for k in CONTACT_KINDS] + sorted(k for k in kinds if k not in CONTACT_KINDS)
    by_kind = [{"kind": k, "label": CONTACT_KINDS.get(k, k.title()), "value": kinds.get(k, 0)} for k in order if k in CONTACT_KINDS or kinds.get(k)]
    pages = defaultdict(dict)
    for dimension, value in _dims(s, K.CONTACT_TAPS_PAGE).items():
        kind, _, group = dimension.partition(":")
        pages[group][kind] = pages[group].get(kind, 0) + value
    by_page = [{"page": g, "label": _page_label(g), "taps": sum(k.values()),
                "kinds": [{"kind": kind, "label": CONTACT_KINDS.get(kind, kind.title()), "value": v}
                          for kind, v in sorted(k.items(), key=lambda i: (-i[1], i[0]))]} for g, k in pages.items()]
    return {"total": sum(kinds.values()), "by_kind": by_kind, "by_page": sorted(by_page, key=lambda r: (-r["taps"], r["page"]))[:PAGES_CAP]}


def _heatmap(s):
    grid = [[s.get((K.VISIT_HOUR, f"{day}:{hour:02d}"), 0) for hour in range(24)] for day in WEEKDAYS]
    return {"days": list(WEEKDAYS), "rows": grid, "max": max((max(r) for r in grid), default=0), "total": sum(sum(r) for r in grid)}


def _sentences(s, heat, channels, campaign_rows):
    out = {"busiest": "Not enough visits yet to show a pattern.", "channels": "", "campaign": ""}
    if heat["total"] >= MIN_FOR_PATTERN:
        by_hour = [sum(row[h] for row in heat["rows"]) for h in range(24)]
        hour = by_hour.index(max(by_hour))  # a tie takes the earlier hour
        by_day = [sum(row) for row in heat["rows"]]
        day = WEEKDAYS[by_day.index(max(by_day))]
        out["busiest"] = f"Most visits start between {hour:02d}:00 and {(hour + 1) % 24:02d}:00. {DAY_NAMES[day]} is the busiest day."
    top = [c for c in channels if c["visits"]][:2]
    if top:
        out["channels"] = f"Most visits came from {top[0]['label']}" + (f", then {top[1]['label']}." if len(top) > 1 else ".")
    if campaign_rows:
        best = campaign_rows[0]
        out["campaign"] = f"Top campaign: {best['campaign']} ({best['visits']:,} visit{'s' if best['visits'] != 1 else ''})."
    return out


def build(range_name="30d", today=None):
    """The stored JSON of Analytics > Visitors for one range."""
    from . import selectors

    range_name = range_name if range_name in selectors.ANALYTICS_RANGES else "30d"
    today = today or metrics.day()
    granularity, labels = selectors._points(range_name, today)
    rows = selectors._fetch(range_name, granularity, labels, KEYS)
    size = len(labels)
    previous = [] if range_name == "all" else [day - timedelta(days=size) for day in labels]
    per_label = _by_label(rows, labels + previous)
    here = _sum(per_label, labels)
    before = _sum(per_label, previous) if previous else None
    now_f, before_f = figures(here), (figures(before) if before is not None else None)

    overview = {key: {"value": value, "previous": before_f[key] if before_f else None,
                      **_change(value, before_f[key] if before_f else None)} for key, value in now_f.items()}
    day_f = [figures(per_label.get(day, {})) for day in labels]
    prev_f = [figures(per_label.get(day, {})) for day in previous]
    series = {key: {"values": [f[key] for f in day_f], "previous": [f[key] for f in prev_f]} for key in now_f}
    series["page_views"] = {"values": [per_label.get(d, {}).get((K.PAGE_VIEWS, ""), 0) for d in labels],
                            "previous": [per_label.get(d, {}).get((K.PAGE_VIEWS, ""), 0) for d in previous]}

    length = _dims(here, K.VISIT_LENGTH)
    length_total = sum(length.values())
    channels, campaign_rows, heat = _channels(here), _campaigns(here), _heatmap(here)
    since = DailyMetric.objects.filter(key=K.VISITS, dimension="").order_by("date").values_list("date", flat=True).first()
    return {
        "range": range_name, "ranges": list(selectors.ANALYTICS_RANGES), "granularity": granularity, "today": today.isoformat(),
        "labels": [d.isoformat() for d in labels], "previous_labels": [d.isoformat() for d in previous],
        "visitors_since": since.isoformat() if since else None,
        "overview": overview, "series": series,
        "devices": _items(here, K.DEVICES, DEVICE_NAMES, K.VIEWS_BY_DEVICE, order=["mobile", "desktop", "tablet"]),
        "browsers": _items(here, K.BROWSERS, BROWSER_NAMES, K.VIEWS_BY_BROWSER),
        "systems": _items(here, K.SYSTEMS, SYSTEM_NAMES, K.VIEWS_BY_SYSTEM),
        "countries": _ranked_with_other(here, K.COUNTRIES, COUNTRIES_SHOWN, country_name), "geoip_available": geoip.is_available(),
        "pages": _pages(here),
        "channels": channels,
        "sources": _ranked_with_other(here, K.VISIT_SOURCES, SOURCES_SHOWN, lambda d: d),
        "campaigns": campaign_rows,
        "contact_taps": _contact(here),
        "visit_length": [{"bucket": name, "visits": length.get(name, 0), "share_bp": basis_points(length.get(name, 0), length_total) or 0}
                         for name, _ in LENGTH_BUCKETS],
        "heatmap": heat,
        "sentences": _sentences(here, heat, channels, campaign_rows),
    }


def empty(range_name):
    """The payload before the first snapshot exists: zeros, never computed from data."""
    from . import selectors

    zero = {"value": 0, "previous": None, "percent": None, "direction": "none"}
    return {
        "range": range_name, "ranges": list(selectors.ANALYTICS_RANGES), "granularity": "day", "today": metrics.day().isoformat(), "labels": [],
        "previous_labels": [], "visitors_since": None,
        "overview": {key: dict(zero, value=None if key in ("pages_per_visit", "avg_visit_seconds", "bounce_rate_bp") else 0)
                     for key in ("visitors", "visits", "pages_per_visit", "avg_visit_seconds", "bounce_rate_bp")},
        "series": {key: {"values": [], "previous": []} for key in
                   ("visitors", "visits", "pages_per_visit", "avg_visit_seconds", "bounce_rate_bp", "page_views")},
        "devices": [], "browsers": [], "systems": [], "countries": [], "geoip_available": False,
        "pages": {"most_viewed": [], "first": [], "last": []}, "channels": _channels({}), "sources": [], "campaigns": [],
        "contact_taps": _contact({}), "visit_length": [{"bucket": n, "visits": 0, "share_bp": 0} for n, _ in LENGTH_BUCKETS],
        "heatmap": _heatmap({}), "sentences": {"busiest": "Not enough visits yet to show a pattern.", "channels": "", "campaign": ""},
    }
