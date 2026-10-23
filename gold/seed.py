"""Default Gold rating weights and thresholds (docs/features/gold-application.md). Edited in Control afterwards.
Only creates what is missing.

Defaults: owner/investor, developer and manager are worth 5 points, firm/agent/lawyer 3. High needs 6, Medium 3.
So a bare owner is Medium and an owner with a portfolio of 10+ is High ("property link with scale")."""
from .models import GoldChoice, GoldRule, GoldSignalSource

P, S, W, B, R, T = (
    GoldRule.PROPERTY_LINK, GoldRule.SIZE, GoldRule.WHERE, GoldRule.BML, GoldRule.REFERRED, GoldRule.THRESHOLD,
)

# group, match value, label, points, counts as property
RULES = [
    (P, "owner_investor", "Owner or investor", 5, True),
    (P, "developer", "Developer", 5, True),
    (P, "manager", "Manager of a block, estate or portfolio", 5, True),
    (P, "firm", "Works at a property or management firm", 3, True),
    (P, "agent", "Agent or broker", 3, True),
    (P, "property_lawyer", "Property lawyer", 3, True),
    (P, "none", "No property link", 0, False),
    (S, "1_9", "1 to 9 properties", 0, False),
    (S, "10_49", "10 to 49 properties", 1, False),
    (S, "50_199", "50 to 199 properties", 2, False),
    (S, "200_plus", "200 or more properties", 3, False),
    (W, "north_london", "Based in North London", 1, False),
    (B, "yes", "Works with BML", 3, False),
    (R, "yes", "Referred by someone", 1, False),
    (T, "high", "Points needed for High", 6, False),
    (T, "medium", "Points needed for Medium", 3, False),
]


# group, value, label (the wording on the application form)
CHOICES = [
    (P, "owner_investor", "Owner / investor"),
    (P, "developer", "Developer"),
    (P, "manager", "Manager (block, estate, portfolio)"),
    (P, "firm", "Work at a property or management firm"),
    (P, "agent", "Agent / broker"),
    (P, "property_lawyer", "Property lawyer"),
    (P, "none", "None of these"),
    (S, "1_9", "1 to 9"),
    (S, "10_49", "10 to 49"),
    (S, "50_199", "50 to 199"),
    (S, "200_plus", "200 or more"),
    (W, "north_london", "North London"),
    (W, "rest_of_london", "Rest of London"),
    (W, "rest_of_uk", "Rest of the UK"),
    (W, "abroad", "Abroad"),
    (B, "yes", "Yes"),
    (B, "not_yet", "Not yet"),
]

# signal, journey question key, answer value ("" = pass the option through), value it gives ("" = the option's own)
SIGNAL_SOURCES = [
    (P, "property_link", "", ""),
    (P, "property_law", "yes", "property_lawyer"),  # asked only of people in law
    (S, "property_size", "", ""),
]


def run(ensure):
    position = {}
    for group, value, label in CHOICES:
        position[group] = position.get(group, 0) + 1
        ensure(GoldChoice, {"group": group, "value": value}, {"label": label, "order": position[group]})
    for order, (signal, question, answer, gives) in enumerate(SIGNAL_SOURCES, start=1):
        ensure(GoldSignalSource, {"signal": signal, "question_key": question, "answer_value": answer},
               {"sets_value": gives, "order": order})
    for group, value, label, points, is_property in RULES:
        ensure(GoldRule, {"group": group, "match_value": value}, {"label": label, "points": points, "is_property": is_property})
