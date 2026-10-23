"""Responsive pictures for the site. Optimised renders live in content/static/content/img/ (see
scripts/build_images.py); a photo uploaded in Control (Section.image or Facility.image) always wins.
A name with no files yet (the new renders) shows a calm placeholder, never a broken image."""
import json
from functools import lru_cache
from pathlib import Path

from django.templatetags.static import static
from django.utils.html import format_html
from django.utils.safestring import mark_safe

MANIFEST_PATH = Path(__file__).resolve().parent / "image_manifest.json"
JPEG_MAX = 1600  # the build script keeps JPEG fallbacks up to this width


@lru_cache(maxsize=1)
def manifest():
    try:
        return json.loads(MANIFEST_PATH.read_text())
    except (OSError, ValueError):
        return {}


def has_image(name):
    return name in manifest()


def _path(name, width, ext):
    return static(f"content/img/{name}-{width}.{ext}")


def srcset(name, ext="webp"):
    info = manifest()[name]
    widths = [w for w in info["widths"] if ext == "webp" or w <= JPEG_MAX]
    return ", ".join(f"{_path(name, w, ext)} {w}w" for w in widths)


def src(name, width=None, ext="webp"):
    """One URL for a given name (the largest size that is at most `width`, or the smallest if none)."""
    info = manifest()[name]
    widths = [w for w in info["widths"] if ext == "webp" or w <= JPEG_MAX]
    pick = max([w for w in widths if width is None or w <= width] or [min(widths)])
    return _path(name, pick, ext)


def placeholder(alt="", css_class=""):
    """A finished-looking block for a render that does not exist yet: espresso with the swan mark."""
    from django.template.loader import render_to_string

    mark = render_to_string("common/_mark.html")
    # Decorative: there is no picture to describe yet, and the heading beside it names the room.
    return format_html('<div class="photo photo-placeholder {}" aria-hidden="true">{}</div>', css_class, mark_safe(mark))


def picture(name, alt="", sizes="100vw", eager=False, override=None, css_class=""):
    """<picture> with WebP and JPEG sources, or the uploaded file, or the placeholder."""
    if override:
        try:
            url = override.url
        except (ValueError, AttributeError):
            url = ""
        if url:
            return format_html(
                '<img class="photo {}" src="{}" alt="{}" loading="{}" decoding="async">',
                css_class, url, alt, "eager" if eager else "lazy",
            )
    if not has_image(name):
        return placeholder(alt, css_class)
    info = manifest()[name]
    priority = mark_safe(' fetchpriority="high"') if eager else ""
    return format_html(
        '<picture><source type="image/webp" srcset="{}" sizes="{}"><img class="photo {}" src="{}" srcset="{}" sizes="{}" '
        'width="{}" height="{}" alt="{}" loading="{}" decoding="async"{}></picture>',
        srcset(name), sizes, css_class, src(name, JPEG_MAX, "jpg"), srcset(name, "jpg"), sizes,
        info["width"], info["height"], alt, "eager" if eager else "lazy", priority,
    )
