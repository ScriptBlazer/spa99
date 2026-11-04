"""Rich text from and to email: cleaning HTML to an allow-list (nh3, a Rust HTML sanitiser) and making a plain text copy.
Two profiles: `clean_outgoing` for what staff compose (small allow-list, no images), `clean_incoming` for what a person sent us (wider, for layout,
images allowed but never loaded unless staff choose). Neither lets a script, event handler, form, iframe, style sheet, `javascript:` or `data:` link through.
The result is stored and served; it is never trusted again without going through here (send_templated cleans once more before sending)."""
import re
import secrets
from html import unescape
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


FOLD_CLASS = "em-fold-from"  # our marker: "everything after this is earlier quoted mail" (Outlook quotes; see mark_outlook_fold)


def _filter(allowed_styles, fold=None):
    def attribute_filter(tag, attr, value):
        if attr == "style":
            return _style_ok(value, allowed_styles) or None
        if attr == "class":  # only our own markers for quoted history (a client's real class names are dropped)
            if fold and value.strip() == fold:  # the one-off token mark_outlook_fold put in: nobody who writes the mail can know it, so a sender cannot hide his own text with it
                return FOLD_CLASS
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


def _run(html, tags, raw_attrs, styles, schemes, fold=None, attribute_filter=None):
    return nh3.clean(html or "", tags=tags, attributes={k: set(v) for k, v in raw_attrs.items()}, url_schemes=schemes, link_rel="noopener noreferrer nofollow", set_tag_attribute_values={"a": {"target": "_blank"}},
                     attribute_filter=attribute_filter or _filter(styles, fold), strip_comments=True, clean_content_tags={"script", "style", "iframe", "object", "embed", "form", "svg", "math", "template", "noscript", "head", "title"})


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
    token = secrets.token_hex(8)
    return _run(mark_outlook_fold(html, token), IN_TAGS, RAW_ATTRS_IN, IN_STYLES, SCHEMES | {"cid"}, fold=token).strip()


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
    return _run(html, SIGNATURE_TAGS, SIGNATURE_ATTRS, set(), SIGNATURE_SCHEMES, attribute_filter=_signature_filter).strip()


def absolute_images(html, site_url):
    """Our own picture addresses (/static/common/img/email/...) made absolute from `site_url`: a mail app has no site to load a relative address from. Those files keep their plain names for good
    (no hash), so an email sent years ago still shows its pictures."""
    return (html or "").replace(f'src="{OWN_IMAGES}', f'src="{(site_url or "").rstrip("/")}{OWN_IMAGES}')


# ---------- Outlook's quoted history ----------
# Gmail and Apple Mail mark what they quote (a gmail_quote container, a blockquote), which clean_incoming keeps. Outlook marks nothing the cleaner can keep (its markers are ids and
# inline styles, and attributes are stripped), so the marker is put in BEFORE cleaning: an empty div with a one-off class, which the page script reads as "this and everything after it is
# earlier mail". Everything here is one pass (str.find from `<` to `>`, never a backwards scan over the whole input), and a marker is only ever put where there are words before it: if nothing
# is found, or nothing comes before it, nothing is hidden. English headers only (From, Sent or Date, To, Subject).

OUTLOOK_IDS = re.compile(r"divRplyFwdMsg|appendonsend|OLK_SRC_BODY_SECTION|mail-editor-reference-message-container", re.I)
ID_ATTR_END = re.compile(r"""\bid\s*=\s*["']?$""", re.I)
HEADER_LABEL = re.compile(r"^(from|sent|date|to|subject)\s*:", re.I)
LINE_BREAKS = {"br", "p", "div", "tr", "li", "hr", "table", "ul", "ol", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "pre"}
HIDDEN_ELEMENTS = {"script", "style", "head", "title"}
ABSORB = {"div", "p", "font", "span", "b", "strong", "i", "em", "u", "hr", "center"}  # open tags right before the header: the marker goes before them, so no empty bordered box is left behind
TAG_NAME = re.compile(r"<\s*(/?)\s*([a-zA-Z][\w:-]*)")
SEPARATOR = re.compile(r"^(?:|[_=*-]{3,}|-{2,}\s*(?:original|forwarded)\s+message\s*-{2,})$", re.I)
HEADER_WINDOW = 8


def _tokens(html):
    """('text' or 'tag', start, end) over the raw HTML, comments skipped. One pass of str.find; a `<` that does not begin a tag is text."""
    pos, size = 0, len(html)
    while pos < size:
        lt = html.find("<", pos)
        if lt < 0:
            yield "text", pos, size
            return
        if lt > pos:
            yield "text", pos, lt
        if html.startswith("<!--", lt):
            end = html.find("-->", lt + 4)
            if end < 0:
                return
            pos = end + 3
            continue
        if lt + 1 >= size or not (html[lt + 1].isalpha() or html[lt + 1] in "/!?"):
            yield "text", lt, lt + 1
            pos = lt + 1
            continue
        gt = html.find(">", lt)
        if gt < 0:
            yield "text", lt, size
            return
        yield "tag", lt, gt + 1
        pos = gt + 1


def _html_lines(html):
    """[(line of visible text, raw offset where it starts)]: block tags and <br> end a line, script and style text is left out."""
    lines, current, start, hidden = [], [], None, 0

    def flush():
        nonlocal current, start
        text = " ".join("".join(current).split())
        if text:
            lines.append((text, start))
        current, start = [], None

    for kind, a, b in _tokens(html):
        if kind == "text":
            if hidden:
                continue
            text = unescape(html[a:b]).replace("\xa0", " ")
            if text.strip():
                start = a if start is None else start
                current.append(text)
            elif current:
                current.append(" ")
            continue
        found = TAG_NAME.match(html, a)
        if not found:
            continue
        name, closing = found.group(2).lower(), bool(found.group(1))
        if name in HIDDEN_ELEMENTS:
            hidden = max(hidden + (-1 if closing else 1), 0)
        if name in LINE_BREAKS:
            flush()
    flush()
    return lines


def _header_block(labels):
    """Index of the first line that starts an Outlook-style header block: From:, then within the next few lines To: and Subject: and one of Sent: or Date:, in any order."""
    for i, label in enumerate(labels):
        if label == "from":
            window = labels[i + 1:i + 1 + HEADER_WINDOW]
            if "to" in window and "subject" in window and ("sent" in window or "date" in window):
                return i
    return None


def _label(text):
    found = HEADER_LABEL.match(text.strip())
    return found.group(1).lower() if found else ""


def _absorb(html, pos):
    """Move `pos` back over the open tags (div, p, span, b, hr ...) that sit right before it, so the marker lands before the box the header is in."""
    for _ in range(6):
        k = pos
        while k > 0 and html[k - 1].isspace():
            k -= 1
        if k == 0 or html[k - 1] != ">":
            break
        lt = html.rfind("<", 0, k)
        found = TAG_NAME.match(html, lt) if lt >= 0 else None
        if not found or found.group(1) or found.group(2).lower() not in ABSORB:
            break
        pos = lt
    return pos


def _id_marker(html):
    """Offset of the tag that carries one of Outlook's ids (Outlook web, Outlook for Mac), or None. At most a few hits are looked at."""
    for index, hit in enumerate(OUTLOOK_IDS.finditer(html)):
        if index >= 8:
            break
        lt = html.rfind("<", 0, hit.start())
        if lt < 0 or html.find(">", lt, hit.start()) != -1 or not TAG_NAME.match(html, lt) or not ID_ATTR_END.search(html[lt:hit.start()]):
            continue
        return lt
    return None


def _words_before(html, end):
    """True when there is a word or a picture before `end` (text in script, style and head does not count)."""
    hidden = 0
    for kind, a, b in _tokens(html[:end]):
        if kind == "text":
            if not hidden and unescape(html[a:b]).replace("\xa0", " ").strip():
                return True
            continue
        found = TAG_NAME.match(html, a)
        if not found:
            continue
        name, closing = found.group(2).lower(), bool(found.group(1))
        if name in HIDDEN_ELEMENTS:
            hidden = max(hidden + (-1 if closing else 1), 0)
        elif name == "img" and not hidden:
            return True
    return False


def outlook_fold_position(html):
    """Where Outlook's quoted mail begins in this HTML, or None: the earliest of an Outlook id (divRplyFwdMsg, appendonsend, OLK_SRC_BODY_SECTION, mail-editor-reference-message-container) and
    a From / Sent or Date / To / Subject header block. None when nothing before it is a word (a forward with no text of his own), and when it sits inside a table (the parser would move a
    marker out of a table, past words that belong before it)."""
    html = html or ""
    found = []
    by_id = _id_marker(html)
    if by_id is not None:
        found.append(_absorb(html, by_id))
    lines = _html_lines(html)
    block = _header_block([_label(text) for text, _ in lines])
    if block is not None:
        found.append(_absorb(html, lines[block][1]))
    if not found:
        return None
    pos = min(found)
    before = html[:pos].lower()
    if before.count("<table") > before.count("</table") or not _words_before(html, pos):
        return None
    return pos


def mark_outlook_fold(html, token):
    """`html` with an empty `<div class="token">` put in front of Outlook's quoted mail (clean_incoming turns the class into FOLD_CLASS). Unchanged when no quote is found."""
    pos = outlook_fold_position(html)
    return html if pos is None else f'{html[:pos]}<div class="{token}"></div>{html[pos:]}'


def split_outlook_text(text):
    """(his words, the quoted mail that starts with an Outlook header block). The block is From:, then To: and Subject: and one of Sent: or Date: within eight lines; the separator line
    before it (a rule of underscores, "-----Original Message-----") goes with the quote. (text, "") when there is none, or when nothing comes before it."""
    lines = (text or "").split("\n")
    block = _header_block([_label(line) for line in lines])
    if block is None:
        return text, ""
    start = block
    while start > 0 and SEPARATOR.match(lines[start - 1].strip()):
        start -= 1
    head = "\n".join(lines[:start]).rstrip()
    if not head.strip():
        return text, ""
    return head, "\n".join(lines[start:]).strip()
