"""Optional media for the immersive pages. Both tags return nothing when the files do not exist yet,
so templates skip the video and the steam layer cleanly until the assets are added."""
import json

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()

VIDEO_DIR = "content/video/"


def _exists(path):
    return bool(finders.find(path))


@register.simple_tag
def asset_url(path):
    """Static URL of a file, or '' when it is not in the static folders (used for optional assets)."""
    return static(path) if _exists(path) else ""


@register.simple_tag
def hero_video():
    """{% hero_video as hv %}: {'sources': json, 'poster': url} when hero video files exist, else None.
    Files (docs/design/HERO-VIDEO.md): hero-landscape.webm/.mp4, hero-portrait.webm/.mp4, hero-poster-landscape.webp."""
    wide, tall = "(min-width: 48em)", "(max-width: 47.99em)"
    candidates = [
        ("hero-landscape.webm", 'video/webm; codecs="av01.0.05M.08"', wide),
        ("hero-landscape.mp4", "video/mp4", wide),
        ("hero-portrait.webm", 'video/webm; codecs="av01.0.05M.08"', tall),
        ("hero-portrait.mp4", "video/mp4", tall),
    ]
    sources = [{"src": static(VIDEO_DIR + name), "type": kind, "media": media}
               for name, kind, media in candidates if _exists(VIDEO_DIR + name)]
    if not sources:
        return None
    poster = VIDEO_DIR + "hero-poster-landscape.webp"
    return {"sources": json.dumps(sources), "poster": static(poster) if _exists(poster) else ""}


@register.simple_tag
def has_photo(name):
    from content import images

    return images.has_image(name)
