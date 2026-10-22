"""Read site copy. Templates use the `content_tags` library: {% load content_tags %} {% page_content "home" as home %}."""
from plans.models import SiteSettings

from .models import Page, Section

OPENING_PLACEHOLDER = "{opening}"


def fill(text, opening):
    """Put the opening time (Site settings) where copy says {opening}. Other braces, like {plan}, are left alone."""
    return text.replace(OPENING_PLACEHOLDER, opening) if text and OPENING_PLACEHOLDER in text else text


class SectionView:
    """A section as templates see it; missing sections are empty rather than errors.
    {opening} in the heading, text or button label becomes the opening time from Site settings."""

    def __init__(self, section=None, opening=""):
        self.heading = fill(section.heading, opening) if section else ""
        self.body = fill(section.body, opening) if section else ""
        self.image = section.image if section and section.image else None
        self.image_alt = section.image_alt if section else ""
        self.cta_label = fill(section.cta_label, opening) if section else ""
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
    return PageContent({section.key: SectionView(section, opening) for section in sections})


def page_meta(page_key):
    page = Page.objects.filter(key=page_key).first()
    description = fill(page.meta_description, SiteSettings.load().opening_label) if page else ""
    return {"title": page.title if page else "", "meta_description": description}
