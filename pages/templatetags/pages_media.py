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
    """{% hero_video as hv %}: {'sources': json, 'poster': url, 'poster_portrait': url} for the Home hero.
    The posters are the hero's only still (never another photo); 'sources' is '[]' when no video files exist.
    None only when there is neither a video nor a poster.
    Files (docs/design/HERO-VIDEO.md): hero-landscape.webm/.mp4, hero-portrait.webm/.mp4, hero-poster-landscape.webp, hero-poster-portrait.webp."""
    wide, tall = "(min-width: 48em)", "(max-width: 47.99em)"
    candidates = [
        ("hero-landscape.webm", 'video/webm; codecs="av01.0.08M.08"', wide),
        ("hero-landscape.mp4", "video/mp4", wide),
        ("hero-portrait.webm", 'video/webm; codecs="av01.0.04M.08"', tall),
        ("hero-portrait.mp4", "video/mp4", tall),
    ]
    sources = [{"src": static(VIDEO_DIR + name), "type": kind, "media": media}
               for name, kind, media in candidates if _exists(VIDEO_DIR + name)]
    landscape = VIDEO_DIR + "hero-poster-landscape.webp"
    portrait = VIDEO_DIR + "hero-poster-portrait.webp"
    poster = static(landscape) if _exists(landscape) else ""
    poster_portrait = static(portrait) if _exists(portrait) else poster
    if not sources and not poster:
        return None
    return {"sources": json.dumps(sources), "poster": poster, "poster_portrait": poster_portrait}


@register.simple_tag
def has_photo(name):
    from content import images

    return images.has_image(name)
