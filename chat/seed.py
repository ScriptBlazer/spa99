"""Starting FAQ for the Ask us chat, drafted only from the site's own copy (content/seed.py, docs/features/website.md). Only creates
what is missing; never overwrites what Moishe edited in System > FAQ. Hours, rooms, plans and prices are not repeated here: the
assistant reads them live from the app."""
from .models import FaqItem, KnowledgeNote

# (question, answer, suggested)
FAQ = [
    ("When do you open?", "Booking is not open yet. Register and we will write before the doors open. Our opening hours, including the cleaning hours and "
     "the closing for Shabbos and Yom Tov, are in the hours information.", True),
    ("What is included in a membership?", "Every visit: every room and all areas, as long as you like. Free drinks and free ice lollies. Come with nothing: "
     "towels, robe, slippers, toiletries and trunks are supplied. Memberships differ in visits a month, when you can come, how far ahead you can book "
     "and guests.", True),
    ("What is the Gold Card?", "The Gold Card is a free membership for BML clients, past, present and future, by approval. Every application is reviewed personally, so being a BML client does not make it automatic. Not a BML client yet? You are still welcome to apply. It holds the fullest membership, and a little more. If it is a fit, we invite you.", True),
    ("Where are you?", "BML House, 99c Vale Road, London N4 1PR.", True),
    ("Who is Spa 99 for?", "Spa 99 is for men only, 18 and over.", False),
    ("What should I bring?", "Come with nothing. Towels, robe, slippers, toiletries and trunks are all supplied. Phones do not go in the spa: they stay in "
     "your own locker.", False),
    ("Can I book a visit?", "Booking opens with membership. When the doors open, you will choose your time. For now you can register, with nothing to pay.", False),
    ("How do I find the right membership?", "Tailor your membership: a few taps, under two minutes, and we suggest the right fit.", False),
    ("How long can I stay?", "As long as you like. Take your time. Nothing here is rushed.", False),
    ("Is there a virtual tour?", "Yes. Take the tour on the website to look around the lounge, the saunas, the relaxing zone and the gym. Images are for "
     "illustration only.", False),
]


def run(ensure):
    for order, (question, answer, suggested) in enumerate(FAQ, start=1):
        ensure(FaqItem, {"question": question}, {"answer": answer, "order": order, "suggested": suggested, "visible": True})
    run_notes(ensure)


# (topic, title, text): short facts from the site's own copy and the agreed rules (docs/SPA99_RULES.md). No prices.
NOTES = [
    ("lockers", "Lockers", "Lockers are included in every membership and are assigned when you book."),
    ("lockers", "Phones", "No phones in the spa: they stay in your locker."),
    ("visiting", "What to bring", "Come with nothing. Towels, robe, slippers, toiletries and trunks are all supplied."),
    ("facilities", "Included in every visit", "Every visit includes every room and all areas, with free drinks and free ice lollies."),
    ("booking", "Length of a visit", "A booked visit is a two-hour slot, and you may stay as long as you like."),
    ("booking", "When booking opens", "Booking opens with membership. Register and we will write before the doors open."),
    ("policies", "Who it is for", "Spa 99 is for men only, aged 18 and over."),
    ("gold", "How the Gold Card works", "The Gold Card is by application. Each application is read personally, and if it is a fit, we invite you."),
]


def run_notes(ensure):
    for order, (topic, title, text) in enumerate(NOTES, start=1):
        ensure(KnowledgeNote, {"title": title}, {"topic": topic, "text": text, "order": order, "active": True})
