"""Tiny condition language used by questions (show only if...) and suggestion rules.

A condition is {"question": "industry", "any_of": ["property"]}, or a list of those (all must match).
`values` maps a question key to the list of option values answered. Empty condition = always true.
"""


def matches(condition, values):
    if not condition:
        return True
    items = condition if isinstance(condition, list) else [condition]
    for item in items:
        if not item:
            continue
        wanted = set(item.get("any_of") or [])
        if wanted and not (set(values.get(item.get("question"), [])) & wanted):
            return False
    return True
