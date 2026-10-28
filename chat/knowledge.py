"""What the assistant knows: plain text built from the live app data (plans, hours, rooms, Gold Card, address, contact, FAQ).

The server, not the model, decides whether prices are in it: `build(prices=False)` contains no price, fee or sale figure at all.
The text is byte-stable while the data is unchanged (no dates, no counters), so Anthropic's prompt cache keeps hitting; it is
rebuilt at most once a minute per variant and shared by the workers through the Django cache."""
import hashlib
import logging

from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from pages import services as page_services
from plans import sales
from plans import services as plan_services
from plans.models import Closure, Plan, SiteSettings

from .models import FaqItem

logger = logging.getLogger("spa99.chat")
CACHE_SECONDS = 60


def _line(label, value):
    return f"{label}: {value}" if value else ""


def _lines(*items):
    return [item for item in items if item]


def _about(site):
    contact = site.contact_address
    return ["ABOUT SPA 99", *_lines(
        "Spa 99 is a private spa for men aged 18 and over, part of BML Group.",
        _line("Address", site.address_one_line),
        _line("Opening", site.opening_label),
        "Booking is open." if site.booking_open else "Booking is not open yet. Visitors can register now and we write before the doors open.",
        _line("Contact email", contact),
        _line("WhatsApp link", site.discount_contact_url),
    )]


def _hours():
    out = ["HOURS"]
    out += [f"- {label}: {text}" for label, text in page_services.opening_hours()]
    now = timezone.now()
    for closure in Closure.objects.filter(active=True, ends_at__gt=now).order_by("starts_at")[:10]:
        when = f"{timezone.localtime(closure.starts_at):%A %-d %B %Y %H:%M} to {timezone.localtime(closure.ends_at):%A %-d %B %Y %H:%M}"
        out.append(f"- Closure, {closure.name}: {when}. {closure.public_note}".strip())
    return out


def _plan(plan, site, ranges, prices):
    card = plan_services.plan_display(plan, site.vat_rate, ranges)
    lines = [f"- {plan.name} ({page_services.character(plan)}): {card['short_description'].replace('*', '')}".rstrip(": ")]
    lines.append("  " + "; ".join(card["facts"] + card["pills"][:1]) + ".")
    perks = [p.get("phrase") or f"{p.get('label', '')}: {p.get('value', '')}" for p in page_services.public_perks(plan)]
    if plan.kind == Plan.FREE_BY_APPLICATION:
        perks = [p.get("phrase") or p.get("label", "") for p in page_services.public_perks(plan)]  # Gold: what it holds, never decisions
    if perks:
        lines.append("  Also: " + "; ".join(p for p in perks if p) + ".")
    if prices:
        if plan.kind == Plan.FREE_BY_APPLICATION:
            lines.append(f"  Price: free to hold, with an annual admin fee: {card['annual_fee_text']} ex VAT ({card['annual_fee_inc_text']} inc VAT).")
        else:
            lines.append(f"  Price: {card['price_line']}.")
    elif plan.kind == Plan.FREE_BY_APPLICATION:
        lines.append("  There is an annual admin fee; its amount is shared with the prices.")
    return lines


def _plans(site, prices):
    ranges = plan_services.hours_ranges()
    out = ["MEMBERSHIPS AND SINGLE VISIT", "Off-peak is the daytime period; peak is the evening. Booking is not available in the chat."]
    if not prices:
        out.append("PRICES ARE NOT AVAILABLE TO THIS VISITOR YET. Do not state or hint at any price, fee or discount.")
    for plan in plan_services.visible_plans():
        out += _plan(plan, site, ranges, prices)
    if prices:
        offer = sales.register_offer(site.vat_rate)
        if offer:
            out.append(f"Sale on now: {offer['text']}")
    return out


def _rooms():
    out = ["THE SPA (rooms and temperatures)"]
    for card in page_services.facility_cards():
        facts = ", ".join(card["facts"])
        out.append(f"- {card['name']}: {card['line']} {card['description']} {('(' + facts + ')') if facts else ''}".strip())
    out.append("Every visit includes every room and all areas, as long as you like. Free drinks. Towels, robe, slippers, toiletries and trunks are supplied.")
    return out


def _gold():
    facts = page_services.gold_facts()
    out = ["THE GOLD CARD",
           "By application, for people in property (others may apply too). Each application is read by a person, and only the team decides. "
           "Never say whether someone will be accepted. Apply at /gold-card/apply/."]
    if facts:
        out.append("- " + "; ".join(f"{f['value']} {f['label']}" for f in facts["figures"]) + ".")
        out.append("- " + "; ".join(facts["pills"]) + ".")
        if facts["perks"]:
            out.append("- Perks: " + "; ".join(p["name"] for p in facts["perks"]) + ".")
    return out


def _faq():
    items = list(FaqItem.objects.filter(visible=True))
    if not items:
        return []
    out = ["FAQ (written by the team; these answers win over anything else)"]
    for item in items:
        out += [f"Q: {item.question}", f"A: {item.answer}"]
    return out


def _pages(prices):
    links = [("Tailor your membership (a short guide, under two minutes)", reverse("journey")), ("Register", "/register/"),
             ("The spa", reverse("spa")), ("The Gold Card", reverse("gold_card")), ("Apply for the Gold Card", reverse("gold_apply")),
             ("Visit us", reverse("visit"))]
    if prices:
        links.insert(1, ("Memberships", reverse("memberships")))
    return ["PAGES YOU MAY LINK TO (markdown links, site paths only)"] + [f"- {label}: {path}" for label, path in links]


def _build(prices):
    site = SiteSettings.load()
    blocks = [_about(site), _hours(), _plans(site, prices), _rooms(), _gold(), _faq(), _pages(prices)]
    return "\n\n".join("\n".join(block) for block in blocks if block)


def build(prices=False):
    """(text, digest) for the visitor's price access. Cached for a minute; the digest names the content (useful in logs and tests)."""
    key = f"chat:knowledge:{'p' if prices else 'n'}"
    try:
        hit = cache.get(key)
    except Exception:  # noqa: BLE001 - a broken cache must not break the chat
        logger.exception("Chat knowledge cache unavailable")
        hit = None
    if hit:
        return hit
    text = _build(prices)
    result = (text, hashlib.sha256(text.encode()).hexdigest()[:12])
    try:
        cache.set(key, result, CACHE_SECONDS)
    except Exception:  # noqa: BLE001
        logger.exception("Chat knowledge cache unavailable")
    return result
