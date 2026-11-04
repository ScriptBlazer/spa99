"""Rich text from and to email: cleaning HTML to an allow-list (nh3, a Rust HTML sanitiser) and making a plain text copy.
Two profiles: `clean_outgoing` for what staff compose (small allow-list, no images), `clean_incoming` for what a person sent us (wider, for layout,
images allowed but never loaded unless staff choose). Neither lets a script, event handler, form, iframe, style sheet, `javascript:` or `data:` link through.
The result is stored and served; it is never trusted again without going through here (send_templated cleans once more before sending)."""
import re
from html.parser import HTMLParser

import nh3

OUT_TAGS = {"p", "br", "strong", "b", "em", "i", "u", "s", "mark", "span", "ul", "ol", "li", "a", "blockquote", "h2", "h3"}
IN_TAGS = OUT_TAGS | {"img", "div", "table", "thead", "tbody", "tfoot", "tr", "td", "th", "pre", "code", "hr", "h1", "h4", "h5", "h6", "sup", "sub", "small", "center",
                      "font", "cite", "strike", "caption", "del", "ins"}
OUT_STYLES = {"color", "background-color"}
IN_STYLES = OUT_STYLES | {"font-weight", "font-style", "text-decoration", "text-align", "font-size", "font-family"}
SCHEMES = {"http", "https", "mailto"}
COLOUR = r"(?:#[0-9a-f]{3,8}|rgba?\([\d\s,.%/]+\)|[a-z]{3,20})"
VALUES = {"color": COLOUR, "background-color": COLOUR, "font-weight": r"(?:normal|bold|bolder|lighter|[1-9]00)", "font-style": r"(?:normal|italic|oblique)",
          "text-decoration": r"(?:none|underline|line-through)", "text-align": r"(?:left|right|center|justify)",
          "font-size": r"(?:\d{1,3}(?:\.\d+)?(?:px|pt|em|rem|%))", "font-family": r"[\w\s,'\"-]{1,80}"}
PIXELS = re.compile(r"^\d{1,4}%?$")
RAW_ATTRS_OUT = {"a": {"href"}, "span": {"style"}, "p": {"style"}, "li": {"style"}}
RAW_ATTRS_IN = {"a": {"href", "title"}, "img": {"src", "alt", "width", "height", "title"}, "span": {"style"}, "p": {"style"}, "li": {"style"}, "div": {"style", "class"},
                "blockquote": {"style", "class"}, "td": {"style", "colspan", "rowspan", "width", "height", "align", "valign"}, "th": {"style", "colspan", "rowspan", "width", "align"},
                "table": {"style", "width", "align", "cellpadding", "cellspacing", "border"}, "tr": {"style"}, "font": {"color", "size", "face"}, "center": set(), "pre": set(),
                "h1": {"style"}, "h2": {"style"}, "h3": {"style"}, "h4": {"style"}}
EXPAND = re.compile(r"[\\]|url\(|expression|@import|javascript|behaviou?r|/\*", re.I)


def _style_ok(value, allowed):
    """Only whitelisted properties with plain values survive (no url(), no escapes, no comments). '' when nothing is left."""
    kept = []
    for part in (value or "").split(";"):
        name, sep, val = part.partition(":")
        name, val = name.strip().lower(), val.strip().lower()
        if sep and name in allowed and not EXPAND.search(val) and re.fullmatch(VALUES[name], val) and len(val) <= 80:
            kept.append(f"{name}: {val}")
    return "; ".join(kept)


def _filter(allowed_styles):
    def attribute_filter(tag, attr, value):
        if attr == "style":
            return _style_ok(value, allowed_styles) or None
        if attr == "class":  # only our own marker for quoted history (a client's real class names are dropped)
            return "quoted" if any(k in value for k in ("gmail_quote", "yahoo_quoted", "quote")) else None
        if attr in ("width", "height", "colspan", "rowspan", "cellpadding", "cellspacing", "border", "size"):
            return value if PIXELS.match(value.strip()) else None
        if attr in ("align", "valign"):
            return value if value.lower() in ("left", "right", "center", "top", "middle", "bottom") else None
        if attr == "color":
            return value if re.fullmatch(COLOUR, value.strip().lower()) else None
        if attr == "face":
            return value if re.fullmatch(VALUES["font-family"], value) else None
        if attr == "title" or attr == "alt":
            return value[:300]
        if attr == "src":  # an image: https, http (blocked later unless staff choose) or a cid: picture inside the same email; never data: or javascript:
            return value if re.match(r"^(?:https?://|cid:)", value.strip(), re.I) and len(value) <= 2000 else None
        return value
    return attribute_filter


def _run(html, tags, raw_attrs, styles, schemes):
    return nh3.clean(html or "", tags=tags, attributes={k: set(v) for k, v in raw_attrs.items()}, url_schemes=schemes, link_rel="noopener noreferrer nofollow", set_tag_attribute_values={"a": {"target": "_blank"}},
                     attribute_filter=_filter(styles), strip_comments=True, clean_content_tags={"script", "style", "iframe", "object", "embed", "form", "svg", "math", "template", "noscript", "head", "title"})


def clean_outgoing(html):
    """What staff composed: p, br, strong, b, em, i, u, s, mark, span (colour and background colour only), lists, links (http, https, mailto, with rel), quotes, h2, h3."""
    return _run(html, OUT_TAGS, RAW_ATTRS_OUT, OUT_STYLES, SCHEMES).strip()


def clean_incoming(html):
    """What a person sent us. Images are allowed in the markup (src http, https or cid:) and the display endpoint decides whether they load."""
    return _run(html, IN_TAGS, RAW_ATTRS_IN, IN_STYLES, SCHEMES | {"cid"}).strip()


def remote_image_count(clean_html):
    return len(re.findall(r'<img\b[^>]*\ssrc="https?://', clean_html or "", re.I))


def cid_names(clean_html):
    return set(re.findall(r'<img\b[^>]*\ssrc="cid:([^"]+)"', clean_html or "", re.I))


class _Text(HTMLParser):
    BLOCKS = {"p", "div", "li", "tr", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "table", "pre", "hr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.href, self.skip = [], None, 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head", "title"):
            self.skip += 1
        elif tag == "br":
            self.out.append("\n")
        elif tag in self.BLOCKS:
            self.out.append("\n" + ("- " if tag == "li" else "") + ("> " if tag == "blockquote" else ""))
        elif tag == "a":
            self.href = dict(attrs).get("href")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head", "title"):
            self.skip = max(self.skip - 1, 0)
        elif tag in self.BLOCKS:
            self.out.append("\n")
        elif tag == "a" and self.href:
            if self.href.startswith(("http://", "https://")) and (not self.out or self.href not in "".join(self.out[-3:])):
                self.out.append(f" ({self.href})")
            self.href = None

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_to_text(html):
    """A readable plain text copy: blocks become lines, list items start "- ", quotes "> ", links keep their address in brackets."""
    parser = _Text()
    parser.feed(html or "")
    parser.close()
    text = "".join(parser.out).replace("\xa0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
