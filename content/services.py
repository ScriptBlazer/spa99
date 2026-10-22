"""Read site copy. Templates use the `content_tags` library: {% load content_tags %} {% page_content "home" as home %}."""
from .models import Page, Section


class SectionView:
    """A section as templates see it; missing sections are empty rather than errors."""

    def __init__(self, section=None):
        self.heading = section.heading if section else ""
        self.body = section.body if section else ""
        self.image = section.image if section and section.image else None
        self.image_alt = section.image_alt if section else ""
        self.cta_label = section.cta_label if section else ""
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
    return PageContent({section.key: SectionView(section) for section in sections})


def page_meta(page_key):
    page = Page.objects.filter(key=page_key).first()
    return {"title": page.title if page else "", "meta_description": page.meta_description if page else ""}
