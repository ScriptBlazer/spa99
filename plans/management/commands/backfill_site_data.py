"""One-off update for an EXISTING install after the "data, not code" review fixes (2026-10-22). New installs get all
of this from `seed_phase1`. This command fills the gaps in rows that already exist and changes nothing that was
written by hand:

- site copy that still says "January 2027" gets the {opening} placeholder (the date then lives in Site settings)
- facilities with no picture description get the starting one
- Gold perks with no short phrase get the starting one
- the Shabbos / Yom Tov hours line is written onto the opening rule
- (memberships page, 2026-10-22) plans with no tagline / render get the starting ones, perks with no `pill` get the
  starting one, and the "Not sure?" row gets the new wording only if it still has the exact old wording
- (The spa page, 2026-10-22) facilities get display, image name, focus and soft facts into empty slots only (the
  display is set only on a row that has no facts and no image name yet, so a later edit is never undone); missing
  `spa` copy rows are created; the exact old wording "Eight spaces, one quiet visit.", "Explore your membership" (spa
  closing button) and the massage line "by appointment" (OPS-06) are replaced

- (2026-10-23) facts are filled only on a never-touched row (cleared facts stay cleared); the three picture
  descriptions that no longer match the new photos (cold plunge, showers, massage room) are replaced only while they
  still have the exact old wording; the kitchenette goes from companion to tile only while it still has its seeded
  image and facts; the kitchenette moves after the showers only while all eight orders are still the old seeded ones

- (2026-10-23, round 3) missing rows for the opener lines, amenity moments and kit (`spa`), Gold page notes (`gold`), the
  Memberships "every visit" row and the whole `signin` page are created (never overwritten, never re-created for pages
  you did not ask about); step 2 pills lose "Towel, robe and slippers" only while exactly the old wording; Gold perks
  without a `note` get the starting one; the gym gets its bottle picture name only while it has no small picture at all.
  The last two run only on the first round 3 run (while the `signin` page does not exist), so clearing the gym's picture
  name or removing a note by hand stays cleared

- (Gold approval, 2026-10-23) the `gold_invite` and `gold_active` email rows are created when missing

- ("Register interest" becomes "Register", 2026-10-23) the button / heading / title rows, only while exactly the old wording

- (virtual tour, 2026-10-23) the `tour` page and its rows, and the `spa` `tour_link` row, are created when missing

Not a migration, on purpose. `--dry-run` shows what would change and saves nothing. Safe to run twice."""
from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

from content import seed as content_seed
from content.models import Page, Section
from journey import seed as journey_seed
from journey.models import Option, Question, SuggestionRule
from plans import seed as plans_seed
from plans.models import Facility, OpeningRule, Plan

OLD_OPENING = "January 2027"
# Seeded picture descriptions that no longer match the realistic photos (2026-10-23): replaced only while exactly this.
OLD_FACILITY_ALTS = {
    "cold-plunge": ("Cold plunge pool set into a travertine floor",),
    "showers": ("Rain showers behind walnut slatted screens",),
    "massage-room": ("Massage room with a walnut table", "Massage room with a made-up table and the swan on a timber slatted wall"),
}


def _swap(text):
    return text.replace(OLD_OPENING, "{opening}") if text and OLD_OPENING in text else text


def backfill():
    """Apply the updates. Returns Counter of 'what' -> rows changed."""
    changed = Counter()
    for section in Section.objects.all():
        new = {f: _swap(getattr(section, f)) for f in ("heading", "body", "cta_label")}
        if any(new[f] != getattr(section, f) for f in new):
            for field, value in new.items():
                setattr(section, field, value)
            section.save()
            changed["content.Section (opening placeholder)"] += 1
    for page in Page.objects.all():
        if _swap(page.meta_description) != page.meta_description:
            page.meta_description = _swap(page.meta_description)
            page.save()
            changed["content.Page (opening placeholder)"] += 1

    alts = {row[0]: row[4] for row in plans_seed.FACILITIES}
    for facility in Facility.objects.all():
        if facility.slug not in alts:
            continue
        if facility.image_alt == "" or facility.image_alt in OLD_FACILITY_ALTS.get(facility.slug, ()):  # exact old wording only
            facility.image_alt = alts[facility.slug]
            facility.save()
            changed["plans.Facility (picture description)"] += 1

    gold = Plan.objects.filter(slug="gold").first()
    phrases = {p["key"]: p["phrase"] for data in plans_seed.PLANS if data["slug"] == "gold" for p in data["perks"] if p.get("phrase")}
    if gold is not None:
        perks, touched = [dict(p) for p in gold.perks or []], False
        for perk in perks:
            if not perk.get("phrase") and perk.get("key") in phrases:
                perk["phrase"], touched = phrases[perk["key"]], True
        if touched:
            gold.perks = perks
            gold.save()
            changed["plans.Plan (Gold perk phrases)"] += 1

    for rule in OpeningRule.objects.filter(kind=OpeningRule.CLOSE_BEFORE_CANDLES, public_note=""):
        rule.public_title = rule.public_title or plans_seed.SHABBOS_TITLE
        rule.public_note = plans_seed.SHABBOS_NOTE
        rule.save()
        changed["plans.OpeningRule (Shabbos line)"] += 1

    for data in plans_seed.PLANS:  # memberships page: tagline, render, perk chips (only into empty slots)
        plan = Plan.objects.filter(slug=data["slug"]).first()
        if plan is None:
            continue
        touched = False
        for field in ("tagline", "render"):
            if data.get(field) and not getattr(plan, field):
                setattr(plan, field, data[field])
                touched = True
        pills = {p["key"]: p["pill"] for p in data["perks"] if p.get("pill")}
        perks = [dict(p) for p in plan.perks or []]
        for perk in perks:
            if not perk.get("pill") and perk.get("key") in pills:
                perk["pill"], touched = pills[perk["key"]], True
        if touched:
            plan.perks = perks
            plan.save()
            changed["plans.Plan (memberships page: tagline, render, pills)"] += 1

    not_sure = Section.objects.filter(page__key="memberships", key="not_sure", heading="Not sure? Find yours.").first()
    if not_sure is not None:
        not_sure.heading = "Not sure?"
        if not_sure.cta_label == "Explore your membership":
            not_sure.cta_label = "Tailor your membership"
        not_sure.save()
        changed["content.Section (memberships: Not sure?)"] += 1

    changed.update(_spa_page())
    changed.update(_home_opening_label())
    changed.update(_round_3())
    changed.update(_journey_and_gold_2026_10_23())
    changed.update(_virtual_tour())
    changed.update(_gold_invite_emails())
    return changed


def _gold_invite_emails():
    """2026-10-23 (Gold approval): the two email rows are created when missing, never overwritten."""
    from notifications.models import NotificationTemplate
    from notifications.seed import DEFAULT_SUBJECTS

    changed = Counter()
    for key in ("gold_invite", "gold_active"):
        subject, note = DEFAULT_SUBJECTS[key]
        _, created = NotificationTemplate.objects.get_or_create(key=key, defaults={"subject": subject, "note": note})
        if created:
            changed["notifications.NotificationTemplate (Gold approval emails)"] += 1
    return changed


def _virtual_tour():
    """2026-10-23: the `tour` page and its rows are created when missing (the spa `tour_link` row is created by
    `_spa_page`, which creates every missing spa row). Existing rows are never touched."""
    changed = Counter()
    title, description, sections = content_seed.PAGES["tour"]
    page, made = Page.objects.get_or_create(key="tour", defaults={
        "title": title, "meta_description": description, "order": list(content_seed.PAGES).index("tour") + 1})
    if made:
        changed["content.Page (virtual tour)"] += 1
    for order, (key, heading, body, cta_label, cta_url) in enumerate(sections, start=1):
        _, made = Section.objects.get_or_create(page=page, key=key, defaults={
            "heading": heading, "body": body, "cta_label": cta_label, "cta_url": cta_url, "order": order})
        changed["content.Section (virtual tour rows)"] += made
    return +changed


# (2026-10-23) exact old wording only; anything an admin has edited is left alone.
OLD_JOURNEY_HELP = {"time": "Choose any that fit.", "facilities": "Choose as many as you like."}
_KIT_TAIL = "\nSlippers | slippers | 62% 60%\nToiletries | toiletries | 50% 55%"
OLD_KIT_BODIES = [  # every earlier seeded kit body (exact matches only)
    "Towels | towel-bench | 45% 50%\nRobe | robe | 100% 38%" + _KIT_TAIL,
    "Towels | towel-bench | 45% 50%\nRobe | robe | 66% 38%" + _KIT_TAIL,
    "Towels | towel-bench-portrait | 50% 45%\nRobe | robe | 66% 38%" + _KIT_TAIL,
]
OLD_SECTION_TEXT = [  # page key, section key, field, old value, new value
    ("journey", "change_answers", "cta_label", "Change my answers", "Start again"),
    ("gold-apply", "screen_1", "heading", "Your property.", "About you."),
    ("gold-apply", "screen_1", "body", "A few taps about your work in property.", "A few taps, so we know you."),
    # Round 4 (2026-10-23): no promises of amenities, and the opening date reads "Launching ..."
    ("home", "opening", "heading", "Launching {opening}.", "{opening}."),  # 2026-10-23 (later): "Launching" is a label row now
    ("spa", "opener_4", "body", "Your robe and slippers are waiting.", "Take your time. Nothing here is rushed."),
    ("spa", "moment_shower", "heading", "In every shower.", "Between rounds."),
    ("spa", "moment_shower", "body", "Toiletries in the swan bottles. A fresh towel on the rail.",
     "Warm water, cool stone and a moment to yourself."),
    ("spa", "moment_slippers", "heading", "Soft underfoot.", "Unhurried."),
    ("spa", "moment_slippers", "body", "Swan slippers, from the lockers to the loungers.",
     "From the lockers to the loungers, at your own pace."),
    ("spa", "moment_tote", "heading", "On the way out.", "Until next time."),
    ("spa", "arrive_kit", "heading", "Every visit includes", "The details."),
    *[("spa", "arrive_kit", "body", old, content_seed.KIT_BODY) for old in OLD_KIT_BODIES],
    ("memberships", "every_visit", "body", "Every visit: {kit}, and every room.", "Every visit: every room, as long as you like."),
    ("spa", "step_2", "body", "A towel, robe and slippers are waiting.", "Leave the day at the door."),
    # "Register interest" becomes "Register" everywhere (2026-10-23, owner decision)
    ("home", "opening", "cta_label", "Register interest", "Register"),
    ("memberships", "register_label", "cta_label", "Register interest", "Register"),
    ("memberships", "continue", "body", "Register your interest. Nothing to pay now.", "Register. Nothing to pay now."),
    ("journey", "result_cta", "cta_label", "Register interest in {plan}", "Register for {plan}"),
    ("book", "placeholder", "cta_label", "Register interest", "Register"),
    ("register", "intro", "heading", "Register interest", "Register"),
]
# (page key, field, old value, new value) for the Page row itself
OLD_PAGE_TEXT = [
    ("register", "title", "Register interest", "Register"),
    ("register", "meta_description", "Register your interest in Spa 99.", "Register at Spa 99. Nothing to pay now."),
]
# Retired, never deleted: hidden from new journeys, old answers keep their label. (question, value, old label)
OLD_RETIRED_OPTIONS = [("company", "often", "Often with someone (Most visits.)"), ("heard_via", "instagram", "Instagram"),
                       ("heard_via", "walking_past", "Walking past")]
OLD_SOMETIMES_POINTS = {"tier-2": 1, "tier-3": 1}


def _journey_options_2026_10_23():
    """Company has two answers, 'Sometimes' leans to Tier 3 (GST-01); 'How did you hear' loses two answers."""
    changed = Counter()
    for key, value, label in OLD_RETIRED_OPTIONS:
        changed["journey.Option (retired)"] += Option.objects.filter(
            question__key=key, value=value, label=label, active=True).update(active=False)
    for option in Option.objects.filter(question__key="company", value="sometimes", plan_points=OLD_SOMETIMES_POINTS):
        option.plan_points = {"tier-3": 3}
        option.save()
        changed["journey.Option (Sometimes leans to Tier 3)"] += 1
    for option in Option.objects.filter(question__key="heard_via", value="bml", label="BML"):
        option.label = "BML member"
        option.save()
        changed["journey.Option (BML member)"] += 1
    social = Question.objects.filter(key="heard_via").first()
    if social is not None and Option.objects.filter(question=social, value="bml", label="BML member").exists():
        _, made = Option.objects.get_or_create(question=social, value="social_media", defaults={"label": "Social media", "order": 4})
        changed["journey.Option (Social media)"] += made
    for rule in SuggestionRule.objects.filter(name="Evenings with guests: towards Tier 3"):
        olds = ([{"question": "company", "any_of": ["often"]}], [{"question": "company", "any_of": ["sometimes"]}])
        if rule.conditions[1:] in olds:  # exact old conditions only
            rule.conditions = rule.conditions[:1] + [{"question": "company", "any_of": journey_seed.GUEST_COMPANY}]
            rule.save()
            changed["journey.SuggestionRule (guests rule)"] += 1
    for name, fields in journey_seed.GUEST_RULES.items():  # created when missing, never overwritten
        _, made = SuggestionRule.objects.get_or_create(name=name, defaults=fields)
        changed["journey.SuggestionRule (Sometimes: not Tier 1, ties to Tier 3)"] += made
    return +changed  # drop zero counts


def _journey_and_gold_2026_10_23():
    """'Choose at least one.' on Your time / What draws you (and the rule behind it), Start again, Gold 'About you.'"""
    changed = Counter()
    for question in Question.objects.filter(key__in=OLD_JOURNEY_HELP):
        if question.help_text == OLD_JOURNEY_HELP[question.key]:
            question.help_text = "Choose at least one."
            question.min_choices = max(question.min_choices, 1)
            question.save()
            changed["journey.Question (choose at least one)"] += 1
    for page_key, key, field, old, new in OLD_SECTION_TEXT:
        section = Section.objects.filter(page__key=page_key, key=key, **{field: old}).first()
        if section is not None:
            setattr(section, field, new)
            section.save()
            changed["content.Section (journey / Gold apply / spa / home wording)"] += 1
    for page_key, field, old, new in OLD_PAGE_TEXT:
        page = Page.objects.filter(key=page_key, **{field: old}).first()
        if page is not None:
            setattr(page, field, new)
            page.save()
            changed["content.Page (Register wording)"] += 1
    changed.update(_journey_options_2026_10_23())
    return changed


OLD_STEP_2_PILLS = "Towel, robe and slippers\nYour own locker\nPhones stay in the locker"
# page key -> the rows added in round 3 (None = every row of the page, creating the page too)
ROUND_3_ROWS = {
    "spa": ["opener_1", "opener_2", "opener_3", "opener_4", "opener_image", "moment_shower",
            "moment_slippers", "moment_tote", "arrive_kit"],
    "gold": ["holds_lead", "apply_note"],
    "memberships": ["every_visit"],
    "signin": None,
    "journey": ["last_suggestion", "need_one"],  # 2026-10-23: the "See my last suggestion" link on reopening
}


def _home_opening_label():
    """2026-10-23: the home `opening_label` row ("Launching"), created when missing; never overwritten."""
    page = Page.objects.filter(key="home").first()
    if page is None:
        return {}
    top = Section.objects.filter(page=page).order_by("-order").values_list("order", flat=True).first() or 0
    _, made = Section.objects.get_or_create(page=page, key="opening_label", defaults={"body": "Launching", "order": top + 1})
    return {"content.Section (home opening label)": 1} if made else {}


def _round_3():
    """Round 3 data (2026-10-23): fills missing rows only; the one wording change needs the exact old text."""
    changed = Counter()
    pages = list(content_seed.PAGES)
    # The record that round 3 has run is the `signin` page (new in round 3). Perk notes and the gym picture name can be
    # emptied by hand, and empty looks the same as "never set", so they are only set while that page does not exist yet.
    first_run = not Page.objects.filter(key="signin").exists()
    for page_key, wanted in ROUND_3_ROWS.items():
        title, description, sections = content_seed.PAGES[page_key]
        page = Page.objects.filter(key=page_key).first()
        if page is None and wanted is None:
            page = Page.objects.create(key=page_key, title=title, meta_description=description, order=pages.index(page_key) + 1)
            changed["content.Page (round 3)"] += 1
        if page is None:
            continue
        for order, (key, heading, body, cta_label, cta_url) in enumerate(sections, start=1):
            if wanted is not None and key not in wanted:
                continue
            _, made = Section.objects.get_or_create(page=page, key=key, defaults={
                "heading": heading, "body": body, "cta_label": cta_label, "cta_url": cta_url, "order": order})
            if made:
                changed["content.Section (round 3 rows)"] += 1
    pills = Section.objects.filter(page__key="spa", key="step_2_pills", body=OLD_STEP_2_PILLS).first()
    if pills is not None:
        pills.body = content_seed.STEP_2_PILLS
        pills.save()
        changed["content.Section (spa step 2 pills)"] += 1

    gold = Plan.objects.filter(slug="gold").first()
    if gold is not None and first_run:
        perks, touched = [dict(p) for p in gold.perks or []], False
        for perk in perks:
            note = plans_seed.GOLD_PERK_NOTES.get(perk.get("key"))
            if note and "note" not in perk:
                perk["note"], touched = note, True
        if touched:
            gold.perks = perks
            gold.save()
            changed["plans.Plan (Gold perk notes)"] += 1

    gym = Facility.objects.filter(slug="gym").first()
    if gym is not None and first_run and not gym.detail_image and not gym.detail_image_name:
        gym.detail_image_name = plans_seed.GYM_DETAIL["detail_image_name"]
        gym.detail_alt = gym.detail_alt or plans_seed.GYM_DETAIL["detail_alt"]
        gym.save()
        changed["plans.Facility (gym small picture)"] += 1
    return changed


OLD_MASSAGE_LINE = "A quiet room for a massage, by appointment."
OLD_SHOWERS_LINE = "Rain showers, good towels, everything you need."
# 2026-10-23 (later): exact old fact lists only, slug -> (old, new)
OLD_FACILITY_FACTS = {
    "dry-sauna": (["80–90°C", "Dry heat", "10–15 minutes", "Sit on a towel"], ["80–90°C", "Dry heat", "10–15 minutes"]),
    "cold-plunge": (["8–10°C", "1–3 minutes", "After the heat"], ["12°C", "1–3 minutes", "After the heat"]),
    "showers": (["Rain showers", "Between rounds"], ["Rain showers", "Warm rain, cool stone"]),
}
OLD_SPA_INTRO = "Eight spaces, one quiet visit."
# Stand-in images replaced by the realistic fal set (2026-10-22): swapped only while the old name is still set.
OLD_FACILITY_IMAGES = {"cold-plunge": "cold-tub", "kitchenette": "lounge"}


# The seeded order before 2026-10-23 (kitchenette last). Reordered only while the rows still have exactly these.
OLD_FACILITY_ORDER = {"dry-sauna": 1, "wet-sauna": 2, "cold-plunge": 3, "showers": 4, "relaxing-zone": 5,
                      "massage-room": 6, "gym": 7, "kitchenette": 8}


def _reorder_facilities():
    """Kitchenette goes right after the showers so the four tiles share one row. Never touches a rearranged set."""
    facilities = list(Facility.objects.all())
    if {f.slug: f.order for f in facilities} != OLD_FACILITY_ORDER:
        return 0
    new = {row[0]: order for order, row in enumerate(plans_seed.FACILITIES, start=1)}
    for facility in facilities:
        if facility.order != new[facility.slug]:
            facility.order = new[facility.slug]
            facility.save()
    return 1


def _spa_page():
    """The spa page data: facility fields, missing copy rows and three exact-wording fixes. Fills empty only."""
    changed = Counter()
    if _reorder_facilities():
        changed["plans.Facility (order: kitchenette after showers)"] += 1
    for facility in Facility.objects.all():
        seed = plans_seed.FACILITY_SPA_PAGE.get(facility.slug)
        touched = False
        if seed is not None:
            untouched = not facility.facts and not facility.image_name  # never backfilled or edited
            if untouched and facility.display != seed["display"]:
                facility.display, touched = seed["display"], True
            elif (facility.slug == "kitchenette" and facility.display == Facility.COMPANION and seed["display"] == Facility.TILE
                  and facility.image_name == seed["image_name"] and facility.facts == seed["facts"]):
                facility.display, touched = Facility.TILE, True  # 2026-10-23: kitchenette is a normal tile now
            if seed["image_name"] and not facility.image_name:
                facility.image_name, touched = seed["image_name"], True
            elif OLD_FACILITY_IMAGES.get(facility.slug) == facility.image_name:
                facility.image_name, touched = seed["image_name"], True
            if seed["image_focus"] != "50% 50%" and facility.image_focus in ("", "50% 50%"):
                facility.image_focus, touched = seed["image_focus"], True
            if untouched:  # empty facts can mean "show none" after an admin cleared them
                facility.facts, touched = list(seed["facts"]), True
        old_facts, new_facts = OLD_FACILITY_FACTS.get(facility.slug, (None, None))
        if old_facts is not None and list(facility.facts or []) == old_facts:
            facility.facts, touched = list(new_facts), True
        if facility.short_line == OLD_MASSAGE_LINE:
            facility.short_line, touched = "A quiet room for massage, part of your visit.", True
        elif facility.slug == "showers" and facility.short_line == OLD_SHOWERS_LINE:
            facility.short_line, touched = "Warm rain on cool stone, between rounds of heat.", True
        if touched:
            facility.save()
            changed["plans.Facility (the spa page fields)"] += 1

    page = Page.objects.filter(key="spa").first()
    if page is not None:
        _, _, sections = content_seed.PAGES["spa"]
        for order, (key, heading, body, cta_label, cta_url) in enumerate(sections, start=1):
            _, made = Section.objects.get_or_create(page=page, key=key, defaults={
                "heading": heading, "body": body, "cta_label": cta_label, "cta_url": cta_url, "order": order})
            if made:
                changed["content.Section (spa page rows)"] += 1
        fixed = 0
        for section in Section.objects.filter(page=page):  # saved one by one so the change is in the history
            if section.key == "intro" and section.body == OLD_SPA_INTRO:
                section.body = "{rooms} spaces, one quiet visit."
            elif section.key == "next" and section.cta_label == "Explore your membership":
                section.cta_label = "Tailor your membership"
            else:
                continue
            section.save()
            fixed += 1
        if fixed:
            changed["content.Section (spa page wording)"] += fixed
    return changed


class Command(BaseCommand):
    help = "Fill gaps in existing rows after the data-not-code fixes. Use --dry-run to preview."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show what would change; save nothing.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        with transaction.atomic():
            changed = backfill()
            if dry_run:
                transaction.set_rollback(True)
        prefix = "Would change" if dry_run else "Changed"
        if not changed:
            self.stdout.write("Nothing to change.")
        for name, count in sorted(changed.items()):
            self.stdout.write(f"{prefix} {count} x {name}")
        if dry_run:
            self.stdout.write("Dry run: nothing was saved.")
