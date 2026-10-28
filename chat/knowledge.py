"""What the assistant knows: plain text built from the live app data (plans, hours, rooms, Gold Card, address, contact, FAQ).

The server, not the model, decides whether prices are in it: `build(prices=False)` contains no price, fee or sale figure at all.
The text is byte-stable while the data is unchanged (no dates, no counters), so Anthropic's prompt cache keeps hitting; it is
rebuilt at most once a minute per variant and shared by the workers through the Django cache."""
import hashlib
import logging

from django.core.cache import cache
from django.urls import get_urlconf, reverse, set_urlconf
from django.utils import timezone

from pages import services as page_services
from plans import sales
from plans import services as plan_services
from plans.models import Closure, Plan, SiteSettings

from .models import FaqItem, KnowledgeNote

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
    lines.append("  " + "; ".join(dict.fromkeys(card["facts"] + card["pills"])) + ".")
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
    out = ["MEMBERSHIPS AND SINGLE VISIT", "Off-peak is the daytime period; peak is the evening. Booking itself is not available in the chat."]
    if not prices:
        out.append("PRICES ARE NOT AVAILABLE TO THIS VISITOR YET. Do not state or hint at any price, fee or discount.")
    for plan in plan_services.visible_plans():
        out += _plan(plan, site, ranges, prices)
    if prices:
        offer = sales.register_offer(site.vat_rate)
        if offer:
            out.append(f"Sale on now: {offer['text']}")
    return out


def _span(minutes):
    hours, rest = divmod(minutes, 60)
    return f"{hours} hour{'s' if hours != 1 else ''}" if not rest else f"{minutes} minutes"


def _booking(site):
    """The agreed booking rules (docs/SPA99_RULES.md sections 03 and 05), with the numbers read live. Booking is not open yet."""
    ranges = plan_services.hours_ranges()
    off_peak = [p.name for p in plan_services.visible_plans() if p.is_daytime_only]
    out = ["BOOKING RULES (agreed; booking is not open yet, so full booking details come when booking opens)",
           f"- A visit is a {_span(site.slot_length_minutes)} slot. Slots start every {site.slot_step_minutes} minutes inside opening hours.",
           f"- Book at least {site.booking_notice_minutes} minutes before the start. First entry is from 10 minutes before the start. Arrive any time during the slot, and stay as long as you like.",
           "- One booking per person per spa day (a spa day runs 5am to 3am the next morning), counting guest visits.",
           "- A slot must start and end inside opening hours: it cannot run into the cleaning hours or the Shabbos and Yom Tov closing. Bookings are allowed up to 1 hour before closing for Shabbos and Yom Tov.",
           "- How far ahead you can book, how many bookings you can hold at once, the cancellation time and guests depend on the membership (see each one above). Cancelling in time frees the place straight away.",
           "- A guest joins the member's booking, in the same slot, with their own account. Guest visits do not roll over."]
    if off_peak and ranges["daytime"]:
        out.append(f"- Off-peak memberships ({', '.join(off_peak)}) must finish within off-peak hours, {ranges['daytime']}.")
    return out


def _notes(prices):
    order = [key for key, _ in KnowledgeNote.TOPICS]
    notes = sorted(KnowledgeNote.objects.filter(active=True), key=lambda n: (order.index(n.topic) if n.topic in order else len(order), n.order, n.title))
    if not prices:
        notes = [n for n in notes if "£" not in n.title and "£" not in n.text]
    if not notes:
        return []
    labels = dict(KnowledgeNote.TOPICS)
    return ["KNOWLEDGE NOTES (written by the team, by topic)"] + [f"- {labels.get(n.topic, 'Other')}: {n.title}. {n.text}" for n in notes]


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


def _faq(prices):
    items = list(FaqItem.objects.filter(visible=True))
    if not prices:  # an entry that mentions a price waits for the email like any other price
        items = [i for i in items if "£" not in i.question and "£" not in i.answer]
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
    """Always with the public site's URLs: the System test console builds this on the System host, whose URLs have no tour or journey pages."""
    previous = get_urlconf()
    set_urlconf("config.urls")
    try:
        return _build_text(prices)
    finally:
        set_urlconf(previous)


def _build_text(prices):
    site = SiteSettings.load()
    blocks = [_about(site), _hours(), _plans(site, prices), _booking(site), _rooms(), _gold(), _notes(prices), _faq(prices), _pages(prices)]
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
