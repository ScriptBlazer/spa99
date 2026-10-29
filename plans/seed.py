"""Starting data for plans, settings, hours and facilities (docs/PRICING.md, SPA99_RULES.md section 03/15).
Only creates what is missing; never overwrites what has been edited in Control."""
from datetime import time
from decimal import Decimal

from .models import Facility, OpeningRule, Plan, SiteSettings

# One calm line under a Gold perk on the Gold Card page (the perk's optional "note"). Merch has none, on purpose.
GOLD_PERK_NOTES = {"leil_shishi": "The Thursday evening meal, included.", "events": "Invitations through the year."}

# The gym is a compact section with one picture (Moishe, 2026-10-26): the seed no longer gives it the bottle picture. The constant stays
# because backfill_site_data (older installs) still reads it.
GYM_DETAIL = {"detail_image_name": "bottle-gym", "detail_alt": "A steel Spa 99 bottle on the gym bench"}

PLANS = [
    {
        "slug": "tier-1", "name": "Tier 1", "kind": Plan.MONTHLY, "price_ex_vat": Decimal("299.00"),
        "visits_per_month": 6, "hours": Plan.DAYTIME_ONLY, "booking_window_days": 1, "upcoming_limit": 1,
        "cancel_hours": 10, "guests_per_month": 0, "no_show_result": "Visit lost",
        "perks": [{"key": "merch", "label": "Merch", "value": "Buy"}],
        "short_description": "Off-peak visits, six a month.", "order": 1,
        "tagline": "For the off-peak regular.", "render": "relax-loungers",
    },
    {
        "slug": "tier-2", "name": "Tier 2", "kind": Plan.MONTHLY, "price_ex_vat": Decimal("399.00"),
        "visits_per_month": 8, "hours": Plan.ANY_TIME, "booking_window_days": 3, "upcoming_limit": 2,
        "cancel_hours": 10, "guests_per_month": 0, "no_show_result": "Visit lost",
        "perks": [
            {"key": "merch", "label": "Merch", "value": "Buy"},
            {"key": "leil_shishi", "label": "Leil Shishi", "value": "Option, £45 + VAT a place", "pill": "Leil Shishi option"},
        ],
        "short_description": "Off-peak or peak, eight visits a month.", "highlight": True, "order": 2,
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
        "annual_fee": Decimal("199.00"),  # ex VAT like every plan price; editable in System > Plans (2026-10-26)
        "visits_per_month": None, "hours": Plan.ANY_TIME, "booking_window_days": 7, "upcoming_limit": 3,
        "cancel_hours": 5, "guests_per_month": 2, "no_show_result": "Booking window drops to today + 3",
        "perks": [
            {"key": "merch", "label": "Merch", "value": "Free with each release", "phrase": "Each merch release"},
            {"key": "leil_shishi", "label": "Leil Shishi", "value": "Included", "phrase": "Leil Shishi when offered",
             "note": GOLD_PERK_NOTES["leil_shishi"]},
            {"key": "waitlist_priority", "label": "Waitlist", "value": "First call"},
            {"key": "events", "label": "BML members' events", "value": "Yes", "phrase": "BML members' events",
             "note": GOLD_PERK_NOTES["events"]},
        ],
        "short_description": "A free membership{gold_star} for BML clients, past, present and future, by approval.", "order": 4,
    },
    {
        "slug": "single-visit", "name": "Single visit", "kind": Plan.ONE_OFF, "price_ex_vat": Decimal("99.00"),
        "visits_per_month": 1, "hours": Plan.DAYTIME_ONLY, "booking_window_days": 1, "upcoming_limit": 1,
        "cancel_hours": 10, "guests_per_month": 0, "no_show_result": "Visit used, no refund, no credit",
        "perks": [{"key": "merch", "label": "Merch", "value": "Buy"}],
        "short_description": "One off-peak visit, no membership.", "order": 5,
        "render": "door-gold",
    },
]

SHABBOS_TITLE = "Shabbos and Yom Tov"
SHABBOS_NOTE = "Closed from Friday afternoon until Saturday night"

OPENING_RULES = [
    {"key": "daytime", "label": "Off-peak", "kind": OpeningRule.PERIOD, "start_time": time(5, 0), "end_time": time(18, 0), "order": 1},
    {"key": "evening", "label": "Peak", "kind": OpeningRule.PERIOD, "start_time": time(18, 0), "end_time": time(3, 0), "order": 2},
    {"key": "daily-closure", "label": "Cleaning hours", "kind": OpeningRule.DAILY_CLOSURE,
     "start_time": time(3, 0), "end_time": time(5, 0), "order": 3},
    {"key": "shabbos-close", "label": "Friday and before Yom Tov: close before candle lighting",
     "kind": OpeningRule.CLOSE_BEFORE_CANDLES, "offset_minutes": 120, "order": 4,
     "public_title": SHABBOS_TITLE, "public_note": SHABBOS_NOTE},
    {"key": "shabbos-open", "label": "Saturday night and after Yom Tov: open after it ends",
     "kind": OpeningRule.OPEN_AFTER_NIGHTFALL, "offset_minutes": 60, "order": 5},
]

# slug, name, short line, description, picture description (alt text)
FACILITIES = [
    ("dry-sauna", "Dry sauna", "Cedar benches and dry heat. Stay as long as feels right.", "A dry sauna in warm timber.",
     "Dry sauna with cedar benches and a glass door etched with the swan"),
    ("wet-sauna", "Wet sauna", "Soft steam and warm stone benches.", "A quiet steam room clad in travertine.",
     "Steam room clad in travertine"),
    ("cold-plunge", "Cold plunge", "Still, cold water. A minute is enough.", "A cold plunge to cool down after the heat.",
     "A round oak cold plunge tub with steps, in a marble room"),
    ("showers", "Showers", "Rain showers to rinse off, before and after the saunas.", "Open rain showers.",
     "Rain showers behind black-framed frosted glass screens, with a marble column and a mosaic wall"),
    ("ice-bucket", "Ice bucket", "A wooden bucket of ice water on a chain, by the showers.", "A wooden bucket of ice water, tipped by pulling a chain.",
     "A wooden ice bucket on a bronze bracket beside the rain showers"),
    ("kitchenette", "Kitchenette", "Tea, coffee and somewhere to sit after.", "A place to make a drink and stay a while.",
     "Kitchenette and lounge corner"),
    ("relaxing-zone", "Relaxing zone", "Loungers, low light and nothing to do.", "Low light and comfortable seating.",
     "Relaxing zone with loungers, travertine and the swan on the wall"),
    ("massage-room", "Massage room", "A quiet, private room for massage.", "A private room for massage, part of your visit.",
     "Massage room with two cream leather massage chairs along a timber-lit wall"),
    ("gym", "Gym", "A compact, well-equipped gym.", "A compact, well-equipped gym with free weights and machines.",
     "Gym with free weights and a swan panel on the wall"),
]

# The spa page (docs/design/SPA-PAGE.md 3.2): slug -> display, image_name, image_focus, detail_image_name, facts.
# Temperatures: Moishe + Barry 2026-10-26: dry sauna 110–120°C, wet sauna 60–80°C, cold plunge 9–11°C. Times are still typical values;
# replace them in Control once confirmed.
FACILITY_SPA_PAGE = {
    "dry-sauna": {"display": "feature", "image_name": "dry-sauna", "image_focus": "50% 55%",
                  "facts": ["110–120°C", "Dry heat", "10–15 minutes"]},
    "wet-sauna": {"display": "tile", "image_name": "wet-sauna", "image_focus": "50% 50%", "facts": ["60–80°C", "Soft steam", "10–15 minutes"]},
    "cold-plunge": {"display": "tile", "image_name": "cold-plunge", "image_focus": "100% 62%", "facts": ["9–11°C", "1–3 minutes", "After the heat"]},
    "showers": {"display": "tile", "image_name": "showers-mosaic", "image_focus": "35% 55%", "facts": ["Rain showers", "Warm water"]},
    "ice-bucket": {"display": "tile", "image_name": "ice-bucket", "image_focus": "50% 50%", "facts": ["Ice-cold water", "Pull the chain"]},
    "relaxing-zone": {"display": "feature", "image_name": "relaxing-zone", "image_focus": "55% 60%",
                      "facts": ["Loungers", "Low light", "Quiet"]},
    "massage-room": {"display": "feature", "image_name": "massage-room", "image_focus": "50% 50%", "facts": ["Part of your visit"]},
    "gym": {"display": "compact", "image_name": "gym", "image_focus": "40% 55%",
            "facts": ["Free weights", "Machines", "Part of your visit"]},
    "kitchenette": {"display": "companion", "image_name": "kitchenette", "image_focus": "55% 60%",
                    "facts": ["Tea and coffee", "Somewhere to sit"]},
}


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
            **FACILITY_SPA_PAGE.get(slug, {}),
        })
