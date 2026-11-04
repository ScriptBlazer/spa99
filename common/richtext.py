"""A staff member's signature: cleaned HTML to an allow-list (nh3, a Rust HTML sanitiser), before it is stored, shown or sent. It is the only rich text left in the site (staff write plain text).
No script, event handler, form, iframe, style sheet, `javascript:` or `data:` link gets through."""
import re

import nh3

PIXELS = re.compile(r"^\d{1,4}%?$")
EXPAND = re.compile(r"[\\]|url\(|expression|@import|javascript|behaviou?r|/\*", re.I)


def _run(html, tags, raw_attrs, schemes, attribute_filter):
    return nh3.clean(html or "", tags=tags, attributes={k: set(v) for k, v in raw_attrs.items()}, url_schemes=schemes, link_rel="noopener noreferrer nofollow", set_tag_attribute_values={"a": {"target": "_blank"}},
                     attribute_filter=attribute_filter, strip_comments=True, clean_content_tags={"script", "style", "iframe", "object", "embed", "form", "svg", "math", "template", "noscript", "head", "title"})


MAX_DEPTH = 400  # real mail nests a few dozen levels (tables in tables)
MAX_TAGS = 50_000  # `<` characters in the whole HTML. nh3's time is not bounded by depth alone: it is quadratic in some shapes (`<div/>`, `<div <>`, `<x-a></x-b>`, and mis-nested
# `<span><div></span></div>`), whatever the depth counter says. Measured at this cap the worst shape takes well under a second; real newsletters hold a few thousand `<`.
MAX_HTML = 300_000  # characters of HTML. The tag budget cannot see inside one tag: nh3's time is quadratic in the number of different attributes on a tag (203,000 of them in 1 MB took
# 33 s; 0.7 s at 240,000 characters), and a quoted `>` hides how many tags there are, so no count of `<` or `>` bounds it. Total size does: at this cap the worst shape measured about a
# second. A real newsletter is 20 to 100 KB (an 18,000 `<` one about 150 KB), so a mail over this is refused (its text is kept) rather than risk a worker for half a minute.
NAME = re.compile(r"(/?)([a-zA-Z][^\s/>]*)")  # the start of what sits between a `<` and the next `>`
NO_NESTING = {"br", "img", "hr", "wbr", "input", "meta", "link", "area", "base", "col", "source", "track", "embed", "p", "li", "td", "th", "tr", "option", "dd", "dt"}  # void or closed by the next one


def too_complex(html):
    """True when the markup is refused as hostile or absurd: longer than MAX_HTML, more than MAX_TAGS `<` characters, or nested deeper than MAX_DEPTH. Linear in the size of the input: `<` is counted
    first (no tag can hide from that), then one pass jumps from `<` to the next `>` with str.find, so no input can make it back up. An end tag only counts when a start tag of
    that name is open. A `/>` ending does not close anything (HTML ignores it on these tags). This is a guard, not a parser: the depth it reports can differ from nh3's
    either way (mis-nested or sloppy mail), which is why the tag count, not the depth, is what bounds the cleaner's time."""
    html = html or ""
    if len(html) > MAX_HTML or html.count("<") > MAX_TAGS:
        return True
    depth, open_by_name, pos = 0, {}, 0
    while True:
        start = html.find("<", pos)
        if start < 0:
            return False
        end = html.find(">", start)
        if end < 0:
            return False
        pos = end + 1
        match = NAME.match(html, start + 1, end)
        if not match:
            continue
        closing, name = match.group(1), match.group(2).lower()
        if name in NO_NESTING:
            continue
        if closing:
            if open_by_name.get(name):
                open_by_name[name] -= 1
                depth -= 1
        else:
            open_by_name[name] = open_by_name.get(name, 0) + 1
            depth += 1
            if depth > MAX_DEPTH:
                return True


# ---------- a staff member's signature (docs/design/spa99-signature-*.html) ----------
# Wider than anything staff type in an email: the CodeTwo signature is a layout of tables, inline styles, links and two pictures. Still no script, no form, no frame, no style sheet, no
# `javascript:` link, no `url()` or negative offset in a style, no position, and a picture only from http, https or our own /static/common/img/email/ folder.

SIGNATURE_TAGS = {"table", "thead", "tbody", "tfoot", "tr", "td", "th", "p", "span", "strong", "b", "em", "i", "u", "br", "a", "img", "div", "hr", "small", "sup", "sub"}
_STYLED = {"style"}
SIGNATURE_ATTRS = {"a": {"href", "title", "style"}, "img": {"src", "alt", "width", "height", "style", "title"}, "table": {"width", "cellpadding", "cellspacing", "border", "align", "role", "style"},
                   "td": {"style", "colspan", "rowspan", "width", "height", "align", "valign"}, "th": {"style", "colspan", "rowspan", "width", "height", "align", "valign"},
                   **{tag: _STYLED for tag in ("tr", "tbody", "thead", "tfoot", "p", "span", "strong", "b", "em", "i", "u", "div", "hr", "small", "sup", "sub")}}
SIGNATURE_SCHEMES = {"http", "https", "mailto", "tel"}
SIGNATURE_PROPS = {"color", "background-color", "background", "font", "font-family", "font-size", "font-weight", "font-style", "line-height", "letter-spacing", "text-transform", "text-decoration",
                   "text-align", "vertical-align", "padding", "padding-top", "padding-right", "padding-bottom", "padding-left", "margin", "margin-top", "margin-right", "margin-bottom",
                   "margin-left", "border", "border-top", "border-right", "border-bottom", "border-left", "border-collapse", "border-radius", "width", "height", "max-width", "display",
                   "white-space"}
SIGNATURE_VALUE = re.compile(r"[\w\s#%.,'\"()/+-]{1,150}")
NEGATIVE = re.compile(r"(?:^|[\s,(])-\d")
DISPLAYS = {"block", "inline", "inline-block", "table", "table-cell"}
OWN_IMAGES = "/static/common/img/email/"
MAX_SIGNATURE = 50_000  # characters; the CodeTwo ones are about 3,500


def _signature_style(value):
    kept = []
    for part in (value or "").split(";"):
        name, sep, val = part.partition(":")
        name, val = name.strip().lower(), val.strip()
        if not sep or name not in SIGNATURE_PROPS or not SIGNATURE_VALUE.fullmatch(val) or EXPAND.search(val) or NEGATIVE.search(val):
            continue
        if "gradient" in val.lower() or (name == "display" and val.lower() not in DISPLAYS):
            continue
        kept.append(f"{name}: {val}")
    return "; ".join(kept)


def _signature_filter(tag, attr, value):
    if attr == "style":
        return _signature_style(value) or None
    if attr in ("width", "height", "colspan", "rowspan", "cellpadding", "cellspacing", "border"):
        return value if PIXELS.match(value.strip()) else None
    if attr in ("align", "valign"):
        return value if value.lower() in ("left", "right", "center", "top", "middle", "bottom") else None
    if attr == "role":
        return "presentation" if value.strip().lower() == "presentation" else None
    if attr in ("title", "alt"):
        return value[:300]
    if attr == "src":
        value = value.strip()
        return value if len(value) <= 2000 and (re.match(r"^https?://", value, re.I) or value.startswith(OWN_IMAGES)) else None
    return value


def clean_signature(html):
    """A signature, cleaned to the wide allow-list above ('' for nothing, or for markup over MAX_SIGNATURE characters or too complicated). Safe to store and to show in the Office page."""
    html = html or ""
    if len(html) > MAX_SIGNATURE or too_complex(html):
        return ""
    return _run(html, SIGNATURE_TAGS, SIGNATURE_ATTRS, SIGNATURE_SCHEMES, _signature_filter).strip()


def absolute_images(html, site_url):
    """Our own picture addresses (/static/common/img/email/...) made absolute from `site_url`: a mail app has no site to load a relative address from. Those files keep their plain names for good
    (no hash), so an email sent years ago still shows its pictures."""
    return (html or "").replace(f'src="{OWN_IMAGES}', f'src="{(site_url or "").rstrip("/")}{OWN_IMAGES}')
