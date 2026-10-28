"""Starting FAQ for the Ask us chat, drafted only from the site's own copy (content/seed.py, docs/features/website.md). Only creates
what is missing; never overwrites what Moishe edited in System > FAQ. Hours, rooms, plans and prices are not repeated here: the
assistant reads them live from the app."""
from .models import FaqItem

# (question, answer, suggested)
FAQ = [
    ("When do you open?", "Booking is not open yet. Register and we will write before the doors open. Our opening hours, including the cleaning hours and "
     "the closing for Shabbos and Yom Tov, are in the hours information.", True),
    ("What is included in a membership?", "Every visit: every room and all areas, as long as you like. Free drinks and free ice lollies. Come with nothing: "
     "towels, robe, slippers, toiletries and trunks are supplied. Memberships differ in visits a month, when you can come, how far ahead you can book "
     "and guests.", True),
    ("What is the Gold Card?", "The Gold Card is for people who own, build and manage property: owners and investors, developers, block, estate and portfolio "
     "managers, people at property and management firms, agents and brokers, and property lawyers. Not in property? You are still welcome to apply. It holds "
     "the fullest membership, and a little more. It is by application: each application is read personally, and if it is a fit, we invite you.", True),
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
