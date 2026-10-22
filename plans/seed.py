"""Starting data for plans, settings, hours and facilities (docs/PRICING.md, SPA99_RULES.md section 03/15).
Only creates what is missing; never overwrites what has been edited in Control."""
from datetime import time
from decimal import Decimal

from .models import Facility, OpeningRule, Plan, SiteSettings

PLANS = [
    {
        "slug": "tier-1", "name": "Tier 1", "kind": Plan.MONTHLY, "price_ex_vat": Decimal("299.00"),
        "visits_per_month": 6, "hours": Plan.DAYTIME_ONLY, "booking_window_days": 1, "upcoming_limit": 1,
        "cancel_hours": 10, "guests_per_month": 0, "no_show_result": "Visit lost",
        "perks": [{"key": "merch", "label": "Merch", "value": "Buy"}],
        "short_description": "Daytime visits, six a month.", "order": 1,
        "tagline": "For the daytime regular.", "render": "relax-loungers",
    },
    {
        "slug": "tier-2", "name": "Tier 2", "kind": Plan.MONTHLY, "price_ex_vat": Decimal("399.00"),
        "visits_per_month": 8, "hours": Plan.ANY_TIME, "booking_window_days": 3, "upcoming_limit": 2,
        "cancel_hours": 10, "guests_per_month": 0, "no_show_result": "Visit lost",
        "perks": [
            {"key": "merch", "label": "Merch", "value": "Buy"},
            {"key": "leil_shishi", "label": "Leil Shishi", "value": "Option, £45 + VAT a place", "pill": "Leil Shishi option"},
        ],
        "short_description": "Day or evening, eight visits a month.", "highlight": True, "order": 2,
        "tagline": "Your evenings, too.", "render": "dry-sauna",
    },
    {
        "slug": "tier-3", "name": "Tier 3", "kind": Plan.MONTHLY, "price_ex_vat": Decimal("499.00"),
        "visits_per_month": None, "hours": Plan.ANY_TIME, "booking_window_days": 7, "upcoming_limit": 3,
        "cancel_hours": 5, "guests_per_month": 1, "no_show_result": "Booking window drops to today + 1",
        "perks": [
            {"key": "merch", "label": "Merch", "value": "Buy"},
            {"key": "leil_shishi", "label": "Leil Shishi", "value": "Option, £45 + VAT a place", "pill": "Leil Shishi option"},
        ],
        "short_description": "Unlimited visits, a week ahead, one guest a month.", "order": 3,
        "tagline": "Whenever you like.", "render": "gym",
    },
    {
        "slug": "gold", "name": "Gold Card", "kind": Plan.FREE_BY_APPLICATION, "price_ex_vat": Decimal("0.00"),
        "visits_per_month": None, "hours": Plan.ANY_TIME, "booking_window_days": 7, "upcoming_limit": 3,
        "cancel_hours": 5, "guests_per_month": 2, "no_show_result": "Booking window drops to today + 3",
        "perks": [
            {"key": "merch", "label": "Merch", "value": "Free with each release", "phrase": "Each merch release"},
            {"key": "leil_shishi", "label": "Leil Shishi", "value": "Included", "phrase": "Leil Shishi when offered"},
            {"key": "waitlist_priority", "label": "Waitlist", "value": "First call"},
            {"key": "events", "label": "BML members' events", "value": "Yes", "phrase": "BML members' events"},
        ],
        "short_description": "Free, by application. For people in property.", "order": 4,
    },
    {
        "slug": "single-visit", "name": "Single visit", "kind": Plan.ONE_OFF, "price_ex_vat": Decimal("99.00"),
        "visits_per_month": 1, "hours": Plan.DAYTIME_ONLY, "booking_window_days": 1, "upcoming_limit": 1,
        "cancel_hours": 10, "guests_per_month": 0, "no_show_result": "Visit used, no refund, no credit",
        "perks": [{"key": "merch", "label": "Merch", "value": "Buy"}],
        "short_description": "One daytime visit, no membership.", "order": 5,
        "render": "door-gold",
    },
]

SHABBOS_TITLE = "Shabbos and Yom Tov"
SHABBOS_NOTE = "Closed from Friday afternoon until Saturday night"

OPENING_RULES = [
    {"key": "daytime", "label": "Daytime", "kind": OpeningRule.PERIOD, "start_time": time(5, 0), "end_time": time(18, 0), "order": 1},
    {"key": "evening", "label": "Evening", "kind": OpeningRule.PERIOD, "start_time": time(18, 0), "end_time": time(3, 0), "order": 2},
    {"key": "daily-closure", "label": "Closed every night", "kind": OpeningRule.DAILY_CLOSURE,
     "start_time": time(3, 0), "end_time": time(5, 0), "order": 3},
    {"key": "shabbos-close", "label": "Friday and before Yom Tov: close before candle lighting",
     "kind": OpeningRule.CLOSE_BEFORE_CANDLES, "offset_minutes": 120, "order": 4,
     "public_title": SHABBOS_TITLE, "public_note": SHABBOS_NOTE},
    {"key": "shabbos-open", "label": "Saturday night and after Yom Tov: open after it ends",
     "kind": OpeningRule.OPEN_AFTER_NIGHTFALL, "offset_minutes": 60, "order": 5},
]

# slug, name, short line, description, picture description (alt text)
FACILITIES = [
    ("dry-sauna", "Dry sauna", "Cedar and dry heat. Stay as long as it feels right.", "A dry sauna in warm timber.",
     "Dry sauna with cedar benches and a glass door etched with the swan"),
    ("wet-sauna", "Wet sauna", "Soft steam and warm stone benches.", "A quiet steam room clad in travertine.",
     "Steam room clad in travertine"),
    ("cold-plunge", "Cold plunge", "Still, cold water. A minute is enough.", "A cold plunge to finish a round of heat.",
     "Cold plunge pool set into a travertine floor"),
    ("showers", "Showers", "Rain showers, good towels, everything you need.", "Open rain showers.",
     "Rain showers behind walnut slatted screens"),
    ("relaxing-zone", "Relaxing zone", "Loungers, low light and nothing to do.", "Low light and comfortable seating.",
     "Relaxing zone with loungers, travertine and the swan on the wall"),
    ("massage-room", "Massage room", "A quiet room for a massage, by appointment.", "A private room for massage.",
     "Massage room with a walnut table"),
    ("gym", "Gym", "Free weights and machines, never crowded.", "A calm, well equipped gym.",
     "Gym with free weights and a swan panel on the wall"),
    ("kitchenette", "Kitchenette", "Tea, coffee and somewhere to sit after.", "A place to make a drink and stay a while.",
     "Kitchenette and lounge corner"),
]


def run(ensure):
    """`ensure(model, lookup, defaults)` creates a row if missing and counts it."""
    ensure(SiteSettings, {"singleton_key": "site"}, {})
    for data in PLANS:
        ensure(Plan, {"slug": data["slug"]}, {k: v for k, v in data.items() if k != "slug"})
    for data in OPENING_RULES:
        ensure(OpeningRule, {"key": data["key"]}, {k: v for k, v in data.items() if k != "key"})
    for order, (slug, name, line, description, alt) in enumerate(FACILITIES, start=1):
        ensure(Facility, {"slug": slug}, {
            "name": name, "short_line": line, "description": description, "image_alt": alt, "order": order,
        })
