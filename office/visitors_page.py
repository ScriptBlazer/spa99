"""Analytics > Visitors, shaped for the page (docs/features/analytics-design.md). Pure functions: they take the stored snapshot
(`selectors.visitors`) and the live figures and return what the template prints, so every figure is worded and formatted once.
Nothing here reads the database; nothing here is a person."""
import math
from datetime import date

from django.urls import reverse

from insights import campaigns
from office import analytics_visitors as av
from office.templatetags.office_tags import ANALYTICS_PERIODS, bp_rate, change_ana, compact, num

MIN_FIGURE = 10        # a rate or an average built on fewer visits or views than this is "Not enough yet"
SHOWN = 10             # rows before "Show all"
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
DAY_LETTERS = ("M", "T", "W", "T", "F", "S", "S")
HOURS = [f"{h:02d}" for h in range(24)]
NOT_ENOUGH = "Not enough yet"
EMPTY = {"visits": "No visits in this range yet.", "campaigns": "No campaign visits yet.", "pages": "No page views in this range yet.",
         "taps": "No contact taps in this range yet.", "pattern": "Not enough visits yet to show a pattern."}
LENGTH_LABELS = {"0-10s": "Under 10s", "10-30s": "10 to 30s", "30s-1m": "30s to 1m", "1-3m": "1 to 3m", "3-10m": "3 to 10m", "10m+": "Over 10m"}
LIVE_HEADINGS = (("by_page", "Pages"), ("by_country", "Countries"), ("by_device", "Devices"), ("by_channel", "How they came"))
LINK_PAGES = (("home", "Home", "home"), ("spa", "The spa", "spa"), ("memberships", "Memberships", "memberships"), ("gold-card", "Gold Card", "gold_card"),
              ("visit", "Visit us", "visit"), ("book", "Book", "book"), ("journey", "Start the journey", "journey"))
TAP_ICONS = {"whatsapp": "whatsapp", "phone": "phone", "email": "envelope", "instagram": "instagram", "map": "map-pin"}


def link_page_path(key):
    """The public path of a link maker page ('' when unknown). From the site's own URL names, so the list follows the site."""
    for page_key, _, name in LINK_PAGES:
        if page_key == key:
            return reverse(name, urlconf="config.urls")
    return ""


# ---------- words and numbers (brief section 5) ----------

def seconds_text(value):
    """8s · 1m 20s · 3m · 1h 5m"""
    seconds = int(round(value))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        minutes, rest = divmod(seconds, 60)
        return f"{minutes}m {rest}s" if rest else f"{minutes}m"
    hours, minutes = divmod(seconds // 60, 60)
    return f"{hours}h {minutes}m" if minutes else f"{hours}h"


def pct(share_bp):
    return "0%" if not share_bp else bp_rate(share_bp)


def plural(n, word):
    return f"{n:,} {word}" if n == 1 else f"{n:,} {word}s"


def _ratio(value, top):
    return f"{(max(value, 0) / top if top else 0):.4f}"


def _since(data):
    value = data.get("visitors_since")
    return date.fromisoformat(value) if value else None


def _counting_since(data):
    """True when the previous period starts before the first day of these figures (a half-empty previous period would show false growth)."""
    since, before = _since(data), data.get("previous_labels") or []
    return bool(since and before and before[0] < since.isoformat())


def early_note(data):
    since = _since(data)
    if not since or (date.fromisoformat(data["today"]) - since).days >= 30:
        return ""
    return f"Visitor figures started on {since.day} {since:%B %Y}, so the first weeks will look thin."


# ---------- Overview ----------

def _spark(values):
    """Line and area paths in a 100 by 40 box. Missing points (None) are left out; fewer than two points means no line."""
    points = [(i, v) for i, v in enumerate(values) if v is not None]
    if len(points) < 2:
        return None
    last = len(values) - 1
    low, high = min(v for _, v in points), max(v for _, v in points)

    def y(v):
        return (36.0 if not high else 20.0) if high == low else 36 - (v - low) / (high - low) * 32
    path = [(i / last * 100, y(v)) for i, v in points]
    line = "M" + " L".join(f"{px:.2f} {py:.2f}" for px, py in path)
    return {"line": line, "area": f"{line} L{path[-1][0]:.2f} 40 L{path[0][0]:.2f} 40 Z"}


def _tiles(data):
    o, series, rng = data["overview"], data["series"], data["range"]
    ref = ANALYTICS_PERIODS.get(rng)
    since = _since(data)
    visits, before_visits = o["visits"]["value"] or 0, o["visits"]["previous"] or 0
    rate_ok = visits >= MIN_FIGURE
    both_ok = rate_ok and before_visits >= MIN_FIGURE

    def line(text):
        if not ref or not since:
            return ""
        return f"Counting since {since.day} {since:%b}" if _counting_since(data) else text

    def count_line(key):
        return change_ana(o[key]["value"], o[key]["previous"], rng) if o[key]["previous"] is not None else ""

    def decimal_line():
        now, was = o["pages_per_visit"]["value"], o["pages_per_visit"]["previous"]
        if not both_ok or now is None or was is None:
            return ""
        diff = round(now - was, 1)
        return f"Same as {ref}" if not diff else (f"+{diff:.1f} on {ref}" if diff > 0 else f"{-diff:.1f} fewer than {ref}")

    def seconds_line():
        now, was = o["avg_visit_seconds"]["value"], o["avg_visit_seconds"]["previous"]
        if not both_ok or now is None or was is None:
            return ""
        diff = round(now) - round(was)
        return f"Same as {ref}" if not diff else f"{seconds_text(abs(diff))} {'longer' if diff > 0 else 'shorter'} than {ref}"

    def points_line():
        now, was = o["bounce_rate_bp"]["value"], o["bounce_rate_bp"]["previous"]
        if not both_ok or now is None or was is None:
            return ""
        diff = round((now - was) / 100)
        return f"Same as {ref}" if not diff else f"{plural(abs(diff), 'point').replace(',', '')} {'higher' if diff > 0 else 'lower'} than {ref}"

    ppv, avg, bounce = o["pages_per_visit"]["value"], o["avg_visit_seconds"]["value"], o["bounce_rate_bp"]["value"]
    tiles = [
        ("visitors", "Visitors", compact(o["visitors"]["value"]), count_line("visitors")),
        ("visits", "Visits", compact(visits), count_line("visits")),
        ("pages_per_visit", "Pages per visit", f"{ppv:.1f}" if rate_ok and ppv is not None else "", decimal_line()),
        ("avg_visit_seconds", "Average visit", seconds_text(avg) if rate_ok and avg is not None else "", seconds_line()),
        ("bounce_rate_bp", "Bounce rate", bp_rate(bounce) if rate_ok and bounce is not None else "", points_line()),
    ]
    return [{"key": key, "label": label, "value": value or NOT_ENOUGH, "small": not value, "change": line(change),
             "spark": _spark(series[key]["values"])} for key, label, value, change in tiles]


# ---------- ranked lists ----------

def _rank(items, label="label", value="value", share="share_bp", taupe=(), icon=None):
    top = max((i[value] for i in items), default=0)
    return [{"label": i[label], "num": num(i[value]), "share": pct(i[share]) if share else "", "ratio": _ratio(i[value], top),
             "taupe": i.get("dimension") in taupe, "icon": icon.get(i.get("kind")) if icon else None} for i in items]


def _channels(data):
    rows = [{"label": c["label"], "value": c["visits"], "share_bp": c["share_bp"]} for c in data["channels"]]
    steps = [{"label": c["label"], "visits": num(c["visits"]), **{k: num(v) for k, v in c["steps"].items()}} for c in data["channels"]]
    return {"how": _rank(rows), "sources": _rank([{**s, "label": s["label"][:1].upper() + s["label"][1:]} for s in data["sources"]], taupe=("other", "unknown")),
            "steps": steps, "empty": not any(c["visits"] for c in data["channels"])}


def _campaigns(data):
    rows = []
    for c in data["campaigns"]:
        name = c["campaign"] if c["campaign"] != "other" or c["source"] else "Other campaigns"
        where = c["placement"] or " / ".join(part for part in (c["source"], c["medium"]) if part) or "Other"
        if not c["placement"] and c["content"]:
            where = f"{where} · {c['content']}"
        steps = c["steps"]
        pairs = [(label, steps[k]) for k, label in (("started", "Started"), ("finished", "Finished"), ("registered", "Registered"), ("gold", "Gold applied"), ("contact", "Taps")) if steps[k]]
        rows.append({"name": name, "where": where, "visits": num(c["visits"]), "visits_text": plural(c["visits"], "visit"),
                     "steps": {k: num(v) for k, v in steps.items()}, "pairs": [{"label": a, "value": num(b)} for a, b in pairs]})
    return rows


def _pages(data):
    p = data["pages"]
    top = max((r["views"] for r in p["most_viewed"]), default=0)
    most = []
    for r in p["most_viewed"]:
        enough = r["reported_views"] >= MIN_FIGURE and r["avg_seconds"] is not None
        avg, scroll = (seconds_text(r["avg_seconds"]), pct(r["scrolled_half_bp"])) if enough else (None, None)
        most.append({"label": r["label"], "views": num(r["views"]), "views_text": plural(r["views"], "view"), "ratio": _ratio(r["views"], top),
                     "avg": avg, "scroll": scroll,
                     "line": f"{avg} on the page, {scroll} scrolled halfway" if enough else "Time and scroll: not enough yet"})

    def entry(rows):
        top_visits = max((r["visits"] for r in rows), default=0)
        return [{"label": r["label"], "visits": num(r["visits"]), "visits_text": plural(r["visits"], "visit"), "share": pct(r["share_bp"]),
                 "ratio": _ratio(r["visits"], top_visits)} for r in rows]
    return {"most": most, "first": entry(p["first"]), "last": entry(p["last"]), "shown": SHOWN}


def _taps(data):
    t = data["contact_taps"]
    return {"total": t["total"], "headline": plural(t["total"], "tap"), "by_kind": _rank(t["by_kind"], icon=TAP_ICONS, share=None),
            "by_page": [{"label": r["label"], "taps": num(r["taps"]), "taps_text": plural(r["taps"], "tap"), "kinds": ", ".join(f"{k['label']} {k['value']:,}" for k in r["kinds"])}
                        for r in t["by_page"][:SHOWN]]}


def _people_use(data):
    devices = data["devices"]
    total = sum(d["value"] for d in devices)
    rows = [{"key": d["dimension"], "label": d["label"], "num": num(d["value"]), "share": pct(d["share_bp"]), "grow": d["value"]} for d in devices]
    spoken = ", ".join(f"{r['label']} {r['share']}" for r in sorted(rows, key=lambda r: -r["grow"]) if r["grow"])
    return {"devices": rows, "devices_spoken": spoken, "total": total,
            "browsers": _rank(data["browsers"], taupe=("other",)), "systems": _rank(data["systems"], taupe=("other",))}


def _length(data):
    rows = [{"bucket": b["bucket"], "label": LENGTH_LABELS.get(b["bucket"], b["bucket"]), "visits": b["visits"], "share_bp": b["share_bp"]} for b in data["visit_length"]]
    total = sum(r["visits"] for r in rows)
    top = max(rows, key=lambda r: r["visits"]) if total else None
    return {"rows": [{**r, "visits_text": num(r["visits"]), "share": pct(r["share_bp"])} for r in rows], "empty": not total,
            "summary": f"The most common visit length is {top['label']}." if top else EMPTY["visits"]}


def _heat(data):
    h = data["heatmap"]
    top = h["max"]
    cells = [{"d": d, "h": hour, "v": v, "level": min(4, math.ceil(v * 4 / top)) if v and top else 0}
             for d, row in enumerate(h["rows"]) for hour, v in enumerate(row)]
    table = [{"day": DAYS[d], "values": row, "total": sum(row)} for d, row in enumerate(h["rows"])]
    return {"show": h["total"] >= av.MIN_FOR_PATTERN, "cells": cells, "table": table, "days": [{"short": d, "letter": l} for d, l in zip(DAYS, DAY_LETTERS)],
            "hours": HOURS, "labelled": [x for x in range(0, 24, 3)]}


def _countries(data):
    rows = _rank(data["countries"], taupe=("other", "unknown"))
    if not data["countries"]:
        summary = "Countries are not available yet."
    else:
        summary = f"Most visitors come from {data['countries'][0]['label']}." if data["countries"][0]["dimension"] not in ("unknown", "other") else ""
    return {"rows": rows, "summary": summary}


def _sentence_pages(data):
    most = data["pages"]["most_viewed"]
    return f"Most viewed: {most[0]['label']} ({plural(most[0]['views'], 'view')})." if most else EMPTY["pages"]


def _sentence_taps(data):
    kinds = [k for k in data["contact_taps"]["by_kind"] if k["value"]]
    if not kinds:
        return EMPTY["taps"]
    best = max(kinds, key=lambda k: k["value"])
    return f"{plural(data['contact_taps']['total'], 'tap')}, most on {best['label']}."


def _sentence_devices(data):
    ranked = [d for d in data["devices"] if d["value"]]
    return f"Most visitors use a {ranked[0]['label']} ({pct(ranked[0]['share_bp'])})." if ranked else EMPTY["visits"]


# ---------- Live now ----------

def live_context(live):
    """The live card's first paint: the same figures live.json sends, worded the way the page script words them."""
    count = live["count"]
    lists = []
    for key, heading in LIVE_HEADINGS:
        rows = [{"label": live_label(key, r["label"]), "value": r["value"]} for r in live.get(key, [])[:3]]
        lists.append({"key": key, "heading": heading, "rows": rows})
    return {"count": count, "empty": not count, "lists": lists, "line": "in the last 5 minutes" if count else "No one on the site right now."}


def live_label(key, raw):
    if raw in ("", "unknown", None):
        return "Unknown"
    if key == "by_country":
        return av.country_name(raw)
    if key == "by_device":
        return av.DEVICE_NAMES.get(raw, raw.title())
    if key == "by_channel":
        return av.CHANNEL_NAMES.get(raw, raw.title())
    return av._page_label(raw)


def live_labels():
    """What the page script needs to word a poll the same way (countries and pages it does itself)."""
    return {"by_device": av.DEVICE_NAMES, "by_channel": av.CHANNEL_NAMES}


# ---------- the page ----------

def build(data, live):
    """Everything analytics_visitors.html prints, from one snapshot payload and one live reading."""
    sentences = data["sentences"]
    countries, length = _countries(data), _length(data)
    channels = _channels(data)
    link_pages = [{"key": k, "label": label} for k, label, _ in LINK_PAGES]
    return {
        "data": data, "early_note": early_note(data), "live": live_context(live), "live_labels": live_labels(),
        "tiles": _tiles(data), "channels": channels, "channels_summary": sentences["channels"] or EMPTY["visits"],
        "campaigns": _campaigns(data), "campaigns_summary": sentences["campaign"] or EMPTY["campaigns"],
        "pages": _pages(data), "pages_summary": _sentence_pages(data),
        "taps": _taps(data), "taps_summary": _sentence_taps(data),
        "use": _people_use(data), "use_summary": _sentence_devices(data),
        "countries": countries, "length": length, "heat": _heat(data), "busiest": sentences["busiest"],
        "placements": [{"key": key, "label": spec[0]} for key, spec in campaigns.PLACEMENTS.items()], "link_pages": link_pages,
        "empty": EMPTY, "chart_json": {"visit_length": length["rows"], "summaries": {"length": length["summary"]}},
    }
