"""The draft journey from docs/features/journey.md: questions, options, plan points and suggestion rules.
Only creates what is missing; points and wording are then edited in Control."""
from decimal import Decimal

from .models import Option, Question, SuggestionRule

T1, T2, T3 = "tier-1", "tier-2", "tier-3"
PROPERTY_LINK_VALUES = ["owner_investor", "developer", "manager", "firm", "agent", "property_lawyer"]

# (value, label, plan points, weight, reason)
TIME = [
    ("early_morning", "Early morning (5 to 9am)", {T1: 2, T2: 1}, None, "Early mornings suit you"),
    ("daytime", "Off-peak (9am to 6pm)", {T1: 3, T2: 1}, None, "Off-peak visits fit"),
    ("evening", "Peak (6 to 10pm)", {T2: 3, T3: 2}, None, "Peak times suit you"),
    ("late_night", "Late night (10pm to 3am)", {T2: 3, T3: 2}, None, "Late nights suit you"),
]
FREQUENCY = [
    ("now_and_then", "Now and then", {T1: 3, T2: 1}, Decimal("0.25"), "A visit now and then"),
    ("weekly", "Weekly", {T1: 3, T2: 2}, Decimal("1"), "About one visit a week"),
    ("two_three", "2-3 a week", {T2: 4, T3: 2}, Decimal("2.5"), "Two to three visits a week"),
    ("most_days", "Most days", {T3: 6, T2: 1}, Decimal("5"), "Most days of the week"),
]
FACILITIES = [
    ("dry_sauna", "Dry sauna"), ("wet_sauna", "Wet sauna"), ("cold_plunge", "Cold plunge"), ("ice_bucket", "Ice bucket"),
    ("relaxing_zone", "Relaxing zone"), ("gym", "Gym"), ("massage_room", "Massage room"), ("kitchenette", "Kitchenette"),
]
COMPANY = [
    ("alone", "Alone (Time to myself.)", {T2: 1}, ""),
    # Guest visits are Tier 3 and Gold only (GST-01), so "sometimes" leans to Tier 3. "Often" was retired (2026-10-23).
    ("sometimes", "Sometimes with a friend (Now and then.)", {T3: 3}, "Sometimes with a friend"),
]
INDUSTRY = [
    ("property", "Property"), ("finance", "Finance"), ("business_owner", "Business owner"), ("law", "Law"),
    ("medical", "Medical"), ("tech", "Tech"), ("creative", "Creative"), ("other", "Other"),
]
# Gold points per occupation (Moishe 2026-10-23): these reach the "Gold might suit you" level, like a property owner.
INDUSTRY_GOLD_POINTS = {"finance": 3, "business_owner": 3, "law": 3}
PROPERTY_LINK = [
    ("owner_investor", "Owner or investor"), ("developer", "Developer"), ("manager", "Manager (block, estate, portfolio)"),
    ("firm", "At a property or management firm"), ("agent", "Agent or broker"), ("property_lawyer", "Property lawyer"),
]
PROPERTY_SIZE = [("1_9", "1 to 9"), ("10_49", "10 to 49"), ("50_199", "50 to 199"), ("200_plus", "200 or more")]
YES_NO = [("yes", "Yes"), ("no", "No")]
HEARD_VIA = [
    ("friend", "A friend"), ("bml", "BML member"), ("social_media", "Social media"), ("other", "Other"),
]

GUEST_COMPANY = ["sometimes", "often"]  # "often" was retired (2026-10-23); old sessions keep their points
GUEST_RULES = {  # 2026-10-23: "Sometimes with a friend" never yields Tier 1 and wins ties for Tier 3
    "Sometimes with a friend: not Tier 1": {
        "kind": SuggestionRule.EXCLUDE, "order": 1, "plan_slugs": [T1],
        "conditions": [{"question": "company", "any_of": GUEST_COMPANY}],
    },
    "Sometimes with a friend: tie goes to Tier 3": {
        "kind": SuggestionRule.TIE_BREAK, "order": 3, "plan_slugs": [T3, T2, T1],
        "conditions": [{"question": "company", "any_of": GUEST_COMPANY}],
    },
}
MIN_CHOICES = {"time": 1, "facilities": 1, "industry": 1}  # 2026-10-23: "Choose at least one." (industry too, 2026-10-26: it is multi-select)

# key, text, help, type, screen, order, condition, options
QUESTIONS = [
    ("time", "When would you come?", "Choose at least one.", Question.MULTI, 1, 1, {}, TIME),
    ("frequency", "How often?", "", Question.SCALE, 1, 2, {}, FREQUENCY),
    ("facilities", "What would you use?", "Choose at least one.", Question.MULTI, 2, 1, {}, FACILITIES),
    ("company", "Do you usually come alone?", "", Question.SINGLE, 3, 1, {}, COMPANY),
    ("industry", "What do you do?", "Choose at least one.", Question.MULTI, 4, 1, {}, INDUSTRY),
    ("property_link", "Your link to property", "", Question.SINGLE, 4, 2,
     {"question": "industry", "any_of": ["property"]}, PROPERTY_LINK),
    ("property_size", "How many properties or units?", "An approximate range is fine.", Question.SINGLE, 4, 3,
     {"question": "property_link", "any_of": PROPERTY_LINK_VALUES}, PROPERTY_SIZE),
    ("property_law", "Is it property law?", "", Question.SINGLE, 4, 4,
     {"question": "industry", "any_of": ["law"]}, YES_NO),
    ("heard_via", "How did you hear about us?", "", Question.SINGLE, 4, 5, {}, HEARD_VIA),
    # Typed follow-ups (optional): shown under their parent when "Other" is chosen.
    ("industry_other", "In a few words", "", Question.TEXT, 4, 6, {"question": "industry", "any_of": ["other"]}, []),
    ("heard_via_other", "Where?", "", Question.TEXT, 4, 7, {"question": "heard_via", "any_of": ["other"]}, []),
]


def _normalise(option):
    """Options are 2-tuples (value, label) or 4/5-tuples with points; return a dict of Option fields."""
    value, label, *rest = option
    fields = {"label": label}
    if rest:
        points, *more = rest
        fields["plan_points"] = points
        if len(more) == 2:  # time and frequency: (weight, reason)
            fields["weight"], fields["reason"] = more
        elif len(more) == 1:  # company: reason
            fields["reason"] = more[0]
    return value, fields


def run(ensure):
    for key, text, help_text, kind, screen, order, condition, options in QUESTIONS:
        question, _ = ensure(Question, {"key": key}, {
            "text": text, "help_text": help_text, "type": kind, "screen": screen, "order": order, "condition": condition,
            "min_choices": MIN_CHOICES.get(key, 0),
        })
        for position, option in enumerate(options, start=1):
            value, fields = _normalise(option)
            if key == "industry" and value in INDUSTRY_GOLD_POINTS:
                fields["gold_points"] = INDUSTRY_GOLD_POINTS[value]
            ensure(Option, {"question": question, "value": value}, {**fields, "order": position})

    ensure(SuggestionRule, {"name": "Evening or late night: not for daytime-only plans"}, {
        "kind": SuggestionRule.EXCLUDE, "order": 1,
        "conditions": [{"question": "time", "any_of": ["evening", "late_night"]}],
        "target_daytime_only": True,
    })
    ensure(SuggestionRule, {"name": "Evenings with guests: towards Tier 3"}, {
        "kind": SuggestionRule.ADD_POINTS, "order": 2, "points": 3, "plan_slugs": [T3],
        "conditions": [
            {"question": "time", "any_of": ["evening", "late_night"]},
            {"question": "company", "any_of": GUEST_COMPANY},
        ],
        "reason": "Room to bring a guest",
    })
    for name, fields in GUEST_RULES.items():  # guest visits are Tier 3 and Gold only (GST-01)
        ensure(SuggestionRule, {"name": name}, fields)
    ensure(SuggestionRule, {"name": "Tie-break: prefer Tier 2"}, {
        "kind": SuggestionRule.TIE_BREAK, "order": 4, "plan_slugs": [T2, T3, T1],
    })
