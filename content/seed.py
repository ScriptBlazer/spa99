"""Placeholder copy for every page in docs/features/website.md. Short, calm, no exclamation marks.
Real copy is edited in Control. Only creates what is missing."""
from .models import Page, Section

# page key: (title, meta description, [(section key, heading, body, cta label, cta url)])
PAGES = {
    "home": ("Home", "Spa 99. A men's spa in North London. Beyond Luxury.", [
        ("hero", "Beyond Luxury", "A quiet place for men, in North London.", "Find your membership", "/journey/"),
        ("scene-heat", "Heat", "Steam and dry heat, slow and unhurried.", "", ""),
        ("scene-rest", "Rest", "Low light, warm wood and room to breathe.", "", ""),
        ("scene-reset", "Reset", "Cold water, a clear head and the rest of your day.", "", ""),
        ("memberships-teaser", "Memberships", "Three ways to come, by day or by evening.", "See memberships", "/memberships/"),
        ("gold-teaser", "The Gold Card", "Free, by application, for people in property.", "Learn more", "/gold/"),
        ("opening", "Opening January 2027", "Register your interest and we will write to you before we open.", "Register interest", "/register/"),
    ]),
    "spa": ("The spa", "Sauna, cold plunge, relaxing zone, gym and massage at 99 Vale Road.", [
        ("intro", "The spa", "Seven spaces, one calm building.", "", ""),
        ("how-it-works", "How a visit works", "Book a time, arrive, and stay as long as you like.", "", ""),
    ]),
    "memberships": ("Memberships", "Spa 99 memberships and single visits.", [
        ("intro", "Memberships", "Choose how often you come and when.", "", ""),
        ("price-note", "Prices", "Prices are shown without VAT, with the VAT-inclusive price beside them.", "", ""),
        ("not-sure", "Not sure?", "Answer a few quick questions and we will suggest the right one.", "Find yours", "/journey/"),
    ]),
    "gold": ("Gold Card", "The Spa 99 Gold Card, by application, for people in property.", [
        ("intro", "The Gold Card", "A free card for people in property, by application.", "Apply", "/gold/apply/"),
        ("who-for", "Who it is for", "Owners and investors, developers, managers, agents, property lawyers and the people who work with them.", "", ""),
        ("perks", "What it includes", "Unlimited visits, a longer booking window, guests, first call on the waitlist and BML members' events.", "", ""),
        ("apply-intro", "Apply", "A few questions. We will be in touch.", "", ""),
        ("thanks", "Thank you", "Thank you. We will be in touch.", "", ""),
    ]),
    "journey": ("Find your membership", "A few quick questions to find the right Spa 99 membership.", [
        ("intro", "Find your membership", "A few quick questions. It takes about two minutes.", "Begin", ""),
        ("result-title", "Your membership", "Here is what we would suggest, and why.", "", ""),
        ("gold-panel", "The Gold Card", "With your property background, you may be invited to hold the Gold Card.", "Apply for Gold", "/gold/"),
        ("gold-line", "", "Work in property? You may be eligible for the Gold Card.", "Find out more", "/gold/"),
        ("privacy-note", "", "Your answers are saved as you go so you can come back. See the privacy notice.", "Privacy notice", "/privacy/"),
    ]),
    "book": ("Book", "Booking at Spa 99 opens soon.", [
        ("placeholder", "Booking opens soon", "Register your interest and you will be the first to know.", "Register interest", "/register/"),
    ]),
    "register": ("Register interest", "Register your interest in Spa 99.", [
        ("intro", "Register your interest", "There is nothing to pay. We will write to you before we open.", "", ""),
        ("sent", "Check your email", "We have sent you a link to confirm your email address.", "", ""),
        ("verified", "Thank you", "Your email is confirmed.", "", ""),
    ]),
    "account": ("Your account", "Your Spa 99 account.", [
        ("opening-soon", "Opening January 2027", "Visits, bookings and membership will appear here when we open.", "", ""),
    ]),
    "visit": ("Visit us", "Spa 99, 99 Vale Road, London N4 1PR.", [
        ("address", "Visit us", "99 Vale Road, London N4 1PR.", "", ""),
        ("contact", "Contact", "Write to hello@spa99.uk.", "Email us", "mailto:hello@spa99.uk"),
        ("men-only", "A men's spa", "Spa 99 is for men only.", "", ""),
    ]),
    "privacy": ("Privacy notice", "How Spa 99 uses your information.", [
        ("body", "Privacy notice", "Legal text to be supplied.", "", ""),
    ]),
    "terms": ("Terms", "Spa 99 terms.", [
        ("body", "Terms", "Legal text to be supplied.", "", ""),
    ]),
    "error": ("Page not found", "", [
        ("not-found", "We cannot find that page", "It may have moved. Head back home and try again.", "Back to home", "/"),
    ]),
}


def run(ensure):
    for page_order, (key, (title, description, sections)) in enumerate(PAGES.items(), start=1):
        page, _ = ensure(Page, {"key": key}, {"title": title, "meta_description": description, "order": page_order})
        for order, (section_key, heading, body, cta_label, cta_url) in enumerate(sections, start=1):
            ensure(Section, {"page": page, "key": section_key}, {
                "heading": heading, "body": body, "cta_label": cta_label, "cta_url": cta_url, "order": order,
            })
