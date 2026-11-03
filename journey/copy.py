"""Words for the email step that sits before the result (docs/features/journey.md "Email gate"). Kept here, next to the
logic that needs them; the other journey words are content rows."""

# Changes whenever the consent wording changes; stored on the session like the privacy version (JourneySession.lead_consent_version).
CONSENT_VERSION = "2026-11-03"

GATE = {
    "heading": "One last thing.",
    "body": "We will show you your tailored membership, with its price.",
    "first_name_label": "First name",
    "email_label": "Email",
    "mobile_label": "Mobile",
    "country_label": "Country",
    "mobile_country_label": "Country code",
    "consent": "Yes, Spa 99 may email and WhatsApp me about opening. I can stop at any time.",
    "privacy_label": "How we use your details",
    "cta": "See my tailored membership",
    "saving": "One moment",
    "error": "We couldn't save that just now. Please try again.",
    "errors": {
        "first_name": "Please add your first name.",
        "email": "That email does not look right.",
        "mobile": "That mobile does not look right. Check the country and the number.",
        "consent": "Please tick the box to carry on.",
    },
}

# The Ask us chat asks for an email only, so it keeps the email-only wording (it must not claim a WhatsApp consent it never collects).
CHAT_CONSENT = "Yes, Spa 99 may email me about opening. I can unsubscribe at any time."
