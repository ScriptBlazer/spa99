"""Starting copy for every page in docs/features/website.md and docs/design/BRIEF.md. Short, calm, no
exclamation marks. Real copy is edited in Control. Only creates what is missing, so edits are never overwritten.

"{opening}" in any text is replaced by the opening time in Site settings (opening date, or its text while empty),
so the date lives in one place.

Section keys use underscores so templates can reach them: {{ home.journey_entry.heading }}.
Multi-line text (steps, role lists) is one line per row in `body`."""
from .models import Page, Section

STEP_2_PILLS = "Your own locker\nPhones stay in the locker"  # the kit row (arrive_kit) now says towel, robe and slippers

# page key: (title, meta description, [(section key, heading, body, cta label, cta url)])
PAGES = {
    "home": ("Home", "Spa 99. A private spa for men in North London. Beyond Luxury. Opening {opening}.", [
        ("hero", "Beyond Luxury.", "A private spa for men in North London. Opening {opening}.", "Tailor your membership", "/journey/"),
        ("hero_link", "", "", "See the spa", "/the-spa/"),
        ("hero_caption", "Reception.", "A large fish tank to wait beside, before the rest of the spa.", "", ""),
        ("statement", "Heat, cold, quiet, and time that is yours.",
         "Two saunas, a cold plunge, a gym and a room to do nothing in. Come early, come late, stay as long as you like.", "", ""),
        ("scene_heat", "", "Heat, slowly.", "", ""),
        ("scene_cold", "", "Then cold.", "", ""),
        ("scene_rest", "", "Then nothing at all.", "", ""),
        ("scenes_link", "", "", "See the spa", "/the-spa/"),
        ("inside", "What's inside.", "", "", ""),
        ("facts_hours_label", "", "Open every day", "", ""),
        ("facts_hours_count_label", "", "hours a day", "", ""),
        ("facts_capacity_label", "", "", "", ""),  # fill in Control (for example "guests at most, at any time") to show the capacity fact
        ("lounge_caption", "The lounge.", "", "", ""),
        ("journey_entry", "Which membership suits you?", "A few taps. Under two minutes.", "Tailor your membership", "/journey/"),
        ("memberships_teaser", "Three memberships. One single visit.", "", "Compare memberships", "/memberships/"),
        ("gold_teaser", "The Gold Card.", "For people in property. Free, by application.", "About the Gold Card", "/gold-card/"),
        ("opening", "{opening}.", "99 Vale Road, London N4.", "Register interest", "/register/"),
    ]),
    "spa": ("The spa", "Sauna, cold plunge, relaxing zone, gym and massage at 99 Vale Road.", [
        ("intro", "The spa.", "{rooms} spaces, one quiet visit.", "", ""),
        ("opener_1", "Open {hours}.", "Every day. Closed for {closure}.", "", ""),
        ("opener_2", "For men only.", "18 and over.", "", ""),
        ("opener_3", "Heat, steam, cold and rest.", "{Rooms} rooms, all part of the same visit.", "", ""),
        ("opener_4", "Stay as long as you like.", "Your robe and slippers are waiting.", "", ""),
        ("opener_image", "", "robe", "", ""),  # name of the opener picture; "door-wide" switches to the door
        ("facts_rooms", "", "rooms, one visit", "", ""),
        ("facts_hours", "", "every day", "", ""),
        ("facts_men", "Men only", "18 and over", "", ""),
        ("moment_towel", "Before the heat.", "A swan towel, folded on the bench.", "", ""),
        ("tiles_intro", "Steam, cold, water.", "Between rounds of heat.", "", ""),
        ("moment_shower", "In every shower.", "Toiletries in the swan bottles. A fresh towel on the rail.", "", ""),
        ("moment_slippers", "Soft underfoot.", "Swan slippers, from the lockers to the loungers.", "", ""),
        ("moment_tote", "On the way out.", "", "", ""),
        ("arrive_kit", "Every visit includes",
         "Towels | towel-bench | 45% 50%\nRobe | robe | 66% 38%\nSlippers | slippers | 62% 60%\nToiletries | toiletries | 50% 55%", "", ""),
        ("how_it_works", "How a visit works", "", "", ""),
        ("step_1", "Book.", "Choose a time that suits you.", "", ""),
        ("step_1_pills", "", "", "", ""),
        ("booking_pending", "", "Booking opens with membership", "", ""),
        ("step_2", "Arrive.", "A towel, robe and slippers are waiting.", "", ""),
        ("step_2_pills", "", STEP_2_PILLS, "", ""),
        ("step_3", "Stay.", "As long as you like, until closing.", "", ""),
        ("step_3_pills", "", "Every room is part of the visit", "", ""),
        ("next", "Find the right way to visit.", "", "Tailor your membership", "/journey/"),
        ("next_from", "", "Memberships from {price} a month, {price_inc} inc VAT.", "", ""),
        ("next_link", "", "", "See memberships", "/memberships/"),
    ]),
    "memberships": ("Memberships", "Spa 99 memberships and single visits, with prices ex VAT and inc VAT.", [
        ("intro", "Memberships.", "Choose when you come and how often.", "", ""),
        ("not_sure", "Not sure?", "", "Tailor your membership", "/journey/"),
        ("compare", "Compare everything", "", "", ""),
        ("every_visit", "", "Every visit: {kit}, and every room.", "See the spa", "/the-spa/"),
        ("gold_line", "", "There is also the Gold Card, for people in property.", "About the Gold Card", "/gold-card/"),
        ("price_note", "", "Prices including VAT are shown under each price.", "", ""),
        ("register_label", "", "", "Register interest", "/register/"),
        ("continue", "", "Register your interest. Nothing to pay now.", "Continue", ""),
        ("recommended_label", "Recommended", "", "", ""),
        ("single_note", "", "Single visits open with booking.", "", ""),
    ]),
    "gold": ("Gold Card", "The Spa 99 Gold Card: free, by application, for people in property.", [
        ("hero", "The Gold Card.", "For people who own, build and manage property. Free, by application.", "Apply", "/gold-card/apply/"),
        ("who", "Who it is for.",
         "Owners and investors\nDevelopers\nBlock, estate and portfolio managers\nPeople at property and management firms\nAgents and brokers\nProperty lawyers", "", ""),
        ("who_note", "", "Not in property? You're still welcome to apply.", "", ""),
        ("holds", "What it holds.", "", "", ""),
        ("holds_lead", "", "The fullest membership, and a little more.", "", ""),
        ("how", "How it works.", "", "", ""),
        ("step_1", "Apply.", "A few minutes, mostly taps.", "", ""),
        ("step_2", "We read it.", "Each application is read personally.", "", ""),
        ("step_3", "We'll be in touch.", "If it's a fit, we'll invite you.", "", ""),
        ("apply", "Apply for the Gold Card", "A few taps, and we will be in touch.", "Apply for the Gold Card", "/gold-card/apply/"),
        ("apply_note", "", "Free. No account needed.", "", ""),
    ]),
    "signin": ("Sign in", "Sign in to your Spa 99 account.", [
        ("intro", "Welcome back.", "Sign in to your Spa 99 account.", "", ""),  # an uploaded image overrides the lockers picture
        ("caption", "", "Your own locker, every visit.", "", ""),
    ]),
    "gold-apply": ("Apply for the Gold Card", "Apply for the Spa 99 Gold Card.", [
        ("screen_1", "Your property.", "A few taps about your work in property.", "", ""),
        ("screen_2", "Your visits.", "What you would use, so we know you.", "", ""),
        ("screen_3", "You.", "So we can reply.", "", ""),
        ("sent", "Thank you.", "Your application is with us. We'll be in touch personally.", "Back to home", "/"),
        ("closed", "Applications are not open yet.", "Please check back soon.", "Back to home", "/"),
    ]),
    "journey": ("Tailor your membership", "A few taps to find the right Spa 99 membership.", [
        ("screen_1", "Your time.", "When you'd come, and how often.", "", ""),
        ("screen_2", "What draws you.", "The parts of the spa you'd use.", "", ""),
        ("screen_3", "Company.", "Some come alone. Some bring a friend.", "", ""),
        ("screen_4", "About you.", "Optional, and only to suggest the right fit.", "", ""),
        ("result_label", "", "Your membership", "", ""),
        ("why", "Why it suits you", "", "", ""),
        ("result_cta", "", "", "Register interest in {plan}", "/register/"),
        ("change_answers", "", "", "Change my answers", ""),
        ("gold_panel", "The Gold Card.",
         "With your property background, you may be invited to hold the Gold Card. It's free, by application, and your answers come with you.",
         "Apply for the Gold Card", "/gold-card/apply/"),
        ("gold_line", "", "In property? You may be eligible for the Gold Card.", "Apply", "/gold-card/apply/"),
        ("others", "Or choose another", "", "Choose {plan}", ""),
        ("continue", "", "", "Continue", ""),
        ("skip", "", "", "Skip this part", ""),
        ("last", "", "", "See my membership", ""),
        ("back", "", "", "Back", ""),
        ("prefer_not", "", "", "Prefer not to say", ""),
        ("start_again", "", "", "Start again", ""),
        ("save_error", "", "We couldn't save that just now. Your answers are safe on this page.", "", ""),
        ("result_empty", "Thank you.", "Have a look at the memberships and choose the one that suits you.", "See memberships", "/memberships/"),
        ("result_loading", "", "One moment", "", ""),
        ("result_error", "We could not load your result just now. Please try again.", "Please try again.", "See the memberships", "/memberships/"),
        ("unavailable", "", "The guided journey is not available just now.", "See the memberships", "/memberships/"),
        ("not_a_fit", "", "Daytime only", "", ""),
        ("optional", "", "(optional)", "", ""),
    ]),
    "book": ("Book", "Booking at Spa 99 opens soon.", [
        ("placeholder", "Booking opens soon.", "When the doors open, you'll choose your time here.", "Register interest", "/register/"),
        ("opening_month", "{opening}", "", "", ""),
        ("how", "How booking will work", "", "", ""),
    ]),
    "register": ("Register interest", "Register your interest in Spa 99.", [
        ("intro", "Register interest", "No payment now. We'll write before the doors open.", "", ""),
        ("journey_note", "", "Your answers come with you.", "", ""),
        ("sent", "Check your email.", "It works for 24 hours.", "", ""),
        ("verified", "Thank you.", "Your email is confirmed.", "", ""),
    ]),
    "account": ("Your account", "Your Spa 99 account.", [
        ("opening_soon", "Opens {opening}", "", "", ""),
        ("id_note", "", "Share it with a member who wants to bring you as a guest.", "", ""),
    ]),
    "visit": ("Visit us", "Spa 99, 99 Vale Road, London N4 1PR.", [
        ("address", "Visit us.", "99 Vale Road\nLondon N4 1PR", "", ""),
        ("men_only", "", "Men only. 18 and over.", "", ""),
        ("getting_here", "", "", "", ""),
    ]),
    "privacy": ("Privacy notice", "How Spa 99 uses your information.", [
        ("body", "Privacy notice.", "", "", ""),
        ("draft_note", "Draft.", "The full text is to be supplied before launch.", "", ""),
        ("part_1", "What we collect", "To be supplied.", "", ""),
        ("part_2", "How we use it", "To be supplied.", "", ""),
        ("part_3", "Your rights", "To be supplied.", "", ""),
        ("contact", "Contact", "Write to us at", "", ""),
    ]),
    "terms": ("Terms", "Spa 99 terms.", [
        ("body", "Terms.", "", "", ""),
        ("draft_note", "Draft.", "The full text is to be supplied before launch.", "", ""),
        ("part_1", "Membership", "To be supplied.", "", ""),
        ("part_2", "Using the spa", "To be supplied.", "", ""),
        ("contact", "Contact", "Write to us at", "", ""),
    ]),
}


def run(ensure):
    for page_order, (key, (title, description, sections)) in enumerate(PAGES.items(), start=1):
        page, _ = ensure(Page, {"key": key}, {"title": title, "meta_description": description, "order": page_order})
        for order, (section_key, heading, body, cta_label, cta_url) in enumerate(sections, start=1):
            ensure(Section, {"page": page, "key": section_key}, {
                "heading": heading, "body": body, "cta_label": cta_label, "cta_url": cta_url, "order": order,
            })
