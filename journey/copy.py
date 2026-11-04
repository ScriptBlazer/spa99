"""Words for the email step that sits before the result (docs/features/journey.md "Email gate"). Kept here, next to the
logic that needs them; the other journey words are content rows."""

# Changes whenever the consent wording changes; stored on the session like the privacy version (JourneySession.lead_consent_version).
CONSENT_VERSION = "2026-11-04"

# What each stored consent version said, for the Office (staff see the wording the person actually ticked, never today's). "" = a lead from before the versions (and the Ask us
# chat, which asks for an email only). A version not listed here reads as the generic line.
CONSENT_TEXTS = {
    "": "Agreed that we may email about Spa 99 opening",
    "2026-11-03": "Agreed that we may email and WhatsApp about Spa 99 opening",
    "2026-11-04": "Agreed that we may email, and WhatsApp if a number was added, about Spa 99 opening and offers",
}


def consent_text(version):
    return CONSENT_TEXTS.get(version or "", f"Agreed to the consent wording of version {version}")


GATE = {
    "heading": "One last thing.",
    "body": "We will show you your tailored membership, with its price.",
    "first_name_label": "First name",
    "email_label": "Email",
    "mobile_label": "Mobile (optional)",
    "mobile_optional": True,  # the number is optional: blank is fine, a typed one is checked (Moishe, 2026-11-04)
    "mobile_hint": "Add it and the team can reach out with good offers.",
    "country_label": "Country",
    "mobile_country_label": "Country code",
    "consent": "Yes, Spa 99 may email me, and WhatsApp me if I add a number, about opening and offers. I can stop at any time.",
    "privacy_label": "How we use your details",
    "cta": "See my tailored membership",
    "saving": "One moment",
    "error": "We couldn't save that just now. Please try again.",
    "errors": {
        "first_name": "Please add your first name.",
        "email": "That email does not look right.",
        "mobile": "That mobile does not look right. Check it, or leave it blank.",
        "consent": "Please tick the box to carry on.",
    },
}

# The Ask us chat asks for an email only, so it keeps the email-only wording (it must not claim a WhatsApp consent it never collects).
CHAT_CONSENT = "Yes, Spa 99 may email me about opening. I can unsubscribe at any time."
