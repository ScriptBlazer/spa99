from django import template

from content import images, services

register = template.Library()


@register.simple_tag
def page_content(page_key):
    """{% page_content "home" as home %} then {{ home.hero.heading }}."""
    return services.page_content(page_key)


@register.simple_tag
def photo(name, alt="", sizes="100vw", eager=False, override=None, css_class=""):
    """{% photo "dry-sauna" alt="..." sizes="(min-width: 64em) 60vw, 100vw" override=section.image %}"""
    return images.picture(name, alt=alt, sizes=sizes, eager=eager, override=override, css_class=css_class)


@register.filter
def lines(text):
    """Split a text block into its non-empty lines."""
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


@register.simple_tag
def photo_srcset(name):
    """The WebP srcset of an optimised render, for <link rel="preload" imagesrcset>."""
    return images.srcset(name) if images.has_image(name) else ""


@register.filter
def parts(sections, prefix="part_"):
    """The sections of a page whose key starts with `prefix`, in order (the numbered parts of a legal page)."""
    return [section for key, section in sections.items() if key.startswith(prefix)]
