"""Read site copy. Templates use the `content_tags` library: {% load content_tags %} {% page_content "home" as home %}."""
from plans.models import SiteSettings
from plans.services import GOLD_STAR, gold_star

from .models import Page, Section

OPENING_PLACEHOLDER = "{opening}"


ROOMS_PLACEHOLDER = "{rooms}"
CONFIRM_PLACEHOLDER = "{confirm_for}"
NUMBER_WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"]


def rooms_word():
    """How many rooms are visible in Control, in words ('eight'), so copy never goes stale when a room is hidden."""
    from plans.models import Facility  # local: plans does not import content, keep it that way

    count = Facility.objects.filter(visible=True).count()
    return NUMBER_WORDS[count] if count < len(NUMBER_WORDS) else str(count)


def fill(text, opening, rooms=None):
    """Put the opening time (Site settings) where copy says {opening}, and the room count where it says {rooms}
    (capitalised at the start of the text). Other braces, like {plan}, are left alone."""
    if text and OPENING_PLACEHOLDER in text:
        text = text.replace(OPENING_PLACEHOLDER, opening)
    if text and rooms and ROOMS_PLACEHOLDER in text:
        text = text.replace(ROOMS_PLACEHOLDER, rooms)
        if text.startswith(rooms):
            text = text[0].upper() + text[1:]
    if text and CONFIRM_PLACEHOLDER in text:  # "{confirm_for}": how long the email confirmation link works (System > Defaults)
        from system import defaults

        hours = defaults.get().email_confirm_hours
        text = text.replace(CONFIRM_PLACEHOLDER, f"{hours} hour" + ("" if hours == 1 else "s"))
    if text and GOLD_STAR in text:  # "free{gold_star}": the asterisk only while the Gold plan has an annual fee
        text = text.replace(GOLD_STAR, gold_star())
    return text


class SectionView:
    """A section as templates see it; missing sections are empty rather than errors.
    {opening} in the heading, text or button label becomes the opening time from Site settings."""

    def __init__(self, section=None, opening="", rooms=None):
        self.heading = fill(section.heading, opening, rooms) if section else ""
        self.body = fill(section.body, opening, rooms) if section else ""
        self.image = section.image if section and section.image else None
        self.image_alt = section.image_alt if section else ""
        self.cta_label = fill(section.cta_label, opening, rooms) if section else ""
        self.cta_url = section.cta_url if section else ""
        self.exists = section is not None

    def __bool__(self):
        return self.exists


class PageContent(dict):
    """dict of section key -> SectionView; unknown keys give an empty SectionView (templates never crash)."""

    def __missing__(self, key):
        return SectionView(None)


def page_content(page_key):
    """All visible sections of a page, keyed by section key."""
    sections = Section.objects.filter(page__key=page_key, visible=True).order_by("order", "key")
    opening = SiteSettings.load().opening_label
    sections = list(sections)
    rooms = rooms_word() if any(ROOMS_PLACEHOLDER in f"{s.heading} {s.body} {s.cta_label}" for s in sections) else None
    return PageContent({section.key: SectionView(section, opening, rooms) for section in sections})


def page_meta(page_key):
    page = Page.objects.filter(key=page_key).first()
    description = fill(page.meta_description, SiteSettings.load().opening_label) if page else ""
    return {"title": page.title if page else "", "meta_description": description}
