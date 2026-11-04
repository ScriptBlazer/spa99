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


def clean_incoming(html):
    """What a person sent us. Images are allowed in the markup (src http, https or cid:) and the display endpoint decides whether they load. Markup that is `too_complex`
    (over MAX_HTML or MAX_TAGS, or deeper than MAX_DEPTH) is not cleaned at all (the cleaner's time grows with the square of the size in bad shapes): '' comes back, and the caller keeps the plain text."""
    if too_complex(html):
        return ""
    return _run(html, IN_TAGS, RAW_ATTRS_IN, IN_STYLES, SCHEMES | {"cid"}).strip()


def remote_image_count(clean_html):
    return len(re.findall(r'<img\b[^>]*\ssrc="https?://', clean_html or "", re.I))


def cid_names(clean_html):
    return set(re.findall(r'<img\b[^>]*\ssrc="cid:([^"]+)"', clean_html or "", re.I))


QUOTE_MARKS = 8  # how many "> " a line shows: a deeper quote is still one quote to read, and a hostile mail cannot make every line thousands of characters long


class _Text(HTMLParser):
    """Collects lines as [quote depth, text]. Everything is one pass over the input: nothing here looks back or forward over the lines collected so far."""
    BLOCKS = {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "table", "pre", "hr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines, self.cur, self.href, self.link, self.skip, self.quote, self.lists = [], [], None, [], 0, 0, []
        self.level = 0

    def nl(self):
        self.lines.append((self.level, "".join(self.cur)))
        self.cur, self.level = [], self.quote  # every line of a quote starts "> "

    def add(self, text):
        self.cur.append(text)
        if self.href is not None:
            self.link.append(text)

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head", "title"):
            self.skip += 1
        elif tag == "br":
            self.nl()
        elif tag in ("ul", "ol"):
            if not self.lists:
                self.nl()
            self.lists.append([tag, 0])
        elif tag == "li":
            self.nl()
            if self.lists and self.lists[-1][0] == "ol":
                self.lists[-1][1] += 1
                self.add(f"{self.lists[-1][1]}. ")
            else:
                self.add("- ")
        elif tag == "blockquote":
            self.quote += 1
            self.nl()
        elif tag in self.BLOCKS:
            self.nl()
        elif tag == "a":
            self.href, self.link = dict(attrs).get("href"), []

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head", "title"):
            self.skip = max(self.skip - 1, 0)
        elif tag == "blockquote":
            self.quote = max(self.quote - 1, 0)
            self.nl()
        elif tag in ("ul", "ol"):
            if self.lists:
                self.lists.pop()
            if not self.lists:
                self.nl()
        elif tag == "li":
            pass  # the next item, or the end of the list, starts the new line
        elif tag in self.BLOCKS:
            self.nl()
        elif tag == "a" and self.href:
            href = self.href.strip()
            shown = "".join(self.link)
            if href.lower().startswith("mailto:"):
                target = href[7:].split("?")[0].strip()
            else:
                target = href if href.startswith(("http://", "https://")) else ""
            if target and target not in shown:
                self.add(f" ({target})")
            self.href = None

    def handle_data(self, data):
        if self.skip:
            return
        first, *rest = data.replace("\xa0", " ").split("\n")
        self.add(first)
        for part in rest:  # a newline in the source is a line break (and the next line keeps its quote marks)
            self.nl()
            self.add(part)


def html_to_text(html):
    """A readable plain text copy: blocks become lines, list items start "- " (numbered lists keep their numbers), every quoted line "> " (at most QUOTE_MARKS deep), links and
    mailto: addresses are kept in brackets. Linear in the size of the input. A line that holds only a typed ">" is kept; a line with nothing on it is a gap."""
    parser = _Text()
    parser.feed(html or "")
    parser.close()
    parser.nl()
    lines = [(level, text.rstrip()) for level, text in parser.lines]
    after, next_level = [0] * len(lines), 0  # the quote depth of the next line with words on it, found by one pass from the end
    for i in range(len(lines) - 1, -1, -1):
        after[i] = next_level
        if lines[i][1].strip():
            next_level = lines[i][0]
    out, before, blank = [], 0, False
    for i, (level, text) in enumerate(lines):
        if text.strip():
            out.append("> " * min(level, QUOTE_MARKS) + text)
            before, blank = level, False
        elif not blank:
            out.append(">" if level and before and after[i] else "")  # a gap inside a quote keeps its ">"
            blank = True
    return "\n".join(out).strip()
