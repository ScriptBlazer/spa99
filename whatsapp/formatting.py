"""WhatsApp text formatting, rendered safely on the server (design brief section 4). ONE function, so bubbles, previews and template
previews cannot disagree. The text is escaped first and only then marked up, so message text can never put HTML on the page.

*bold*  _italic_  ~strike~  `code`  ```block```  "- " or "* " lists  "1. " numbered lists  "> " quotes  and http(s):// or www. links.
Markers count only at word edges with no space inside them; nothing formats inside code; the marks are removed, as in the app."""
import html
import re

from django.utils.safestring import mark_safe

OPEN, CLOSE = "\ue000", "\ue001"  # private-use characters hold finished HTML while the marks are processed
BLOCK = re.compile(r"```(.+?)```", re.S)
INLINE_CODE = re.compile(r"(?<![\w`])`(?=[^\s`])([^`\n]+?)(?<=[^\s`])`(?![\w`])")
URL = re.compile(r"(?:https?://|www\.)[^\s<]+", re.I)
BULLET = re.compile(r"^[-*] (.*)$")
NUMBER = re.compile(r"^\d+\. (.*)$")
MARKS = (("*", "strong"), ("_", "em"), ("~", "s"))
TRAILING = ".,;:!?)\"'*_~"


def _mark_pattern(marker):
    m = re.escape(marker)
    return re.compile(rf"(?<![\w{m}])({m})(?=[^\s{m}])(.+?)(?<=[^\s{m}])\1(?![\w{m}])")


PATTERNS = [(_mark_pattern(marker), tag) for marker, tag in MARKS]


def _hold(store, markup):
    store.append(markup)
    return f"{OPEN}{len(store) - 1}{CLOSE}"


def _link(match, store):
    raw = match.group(0)
    end = len(raw)
    while end and raw[end - 1] in TRAILING and not (raw[end - 1] == ")" and "(" in raw[:end]):
        end -= 1
    url, tail = raw[:end], raw[end:]
    if not url or url.lower() in ("www.", "http://", "https://"):
        return raw
    target = url if url.lower().startswith("http") else f"https://{url}"
    return _hold(store, f'<a href="{target}" target="_blank" rel="noopener noreferrer nofollow">{url}</a>') + tail


def _inline(line):
    """One line of raw text to safe HTML."""
    store = []
    text = html.escape(line.replace(OPEN, "").replace(CLOSE, ""), quote=True)
    text = INLINE_CODE.sub(lambda m: _hold(store, f"<code>{m.group(1)}</code>"), text)
    text = URL.sub(lambda m: _link(m, store), text)
    for pattern, tag in PATTERNS:
        text = pattern.sub(lambda m, tag=tag: f"<{tag}>{m.group(2)}</{tag}>", text)
    for _ in range(3):  # a held piece can sit inside another (a link in bold)
        text = re.sub(f"{OPEN}(\\d+){CLOSE}", lambda m: store[int(m.group(1))], text)
    return text


def _blocks(text):
    """Lines to block HTML: paragraphs, lists and quotes."""
    out, lines, i = [], text.split("\n"), 0
    while i < len(lines):
        line = lines[i]
        bullet, number = BULLET.match(line), NUMBER.match(line)
        if bullet or number:
            pattern, tag = (BULLET, "ul") if bullet else (NUMBER, "ol")
            items = []
            while i < len(lines) and pattern.match(lines[i]):
                items.append(f"<li>{_inline(pattern.match(lines[i]).group(1))}</li>")
                i += 1
            out.append(f"<{tag}>{''.join(items)}</{tag}>")
        elif line.startswith("> "):
            quoted = []
            while i < len(lines) and lines[i].startswith("> "):
                quoted.append(_inline(lines[i][2:]))
                i += 1
            out.append(f"<blockquote>{'<br>'.join(quoted)}</blockquote>")
        else:
            text_lines = []
            while i < len(lines) and not (BULLET.match(lines[i]) or NUMBER.match(lines[i]) or lines[i].startswith("> ")):
                text_lines.append(_inline(lines[i]))
                i += 1
            out.append("<br>".join(text_lines))
    return "".join(out)


def render(text):
    """Safe HTML for a message. Empty text gives an empty string."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    out, last = [], 0
    for match in (m for m in BLOCK.finditer(text) if m.group(1).strip()):
        if match.start() > last:
            out.append(_blocks(text[last:match.start()].strip("\n")))
        out.append(f"<pre>{html.escape(match.group(1).strip(chr(10)), quote=True)}</pre>")
        last = match.end()
    if last < len(text):
        out.append(_blocks(text[last:].strip("\n")))
    return mark_safe("".join(part for part in out if part))


def plain(text):
    """The text without its marks and on one line: for list previews and notifications."""
    text = BLOCK.sub(lambda m: m.group(1), (text or "").replace("\r", ""))
    first = next((line for line in text.split("\n") if line.strip()), "")
    first = re.sub(r"^(?:[-*] |\d+\. |> )", "", first.strip())
    first = INLINE_CODE.sub(lambda m: m.group(1), first)
    for pattern, _ in PATTERNS:
        first = pattern.sub(lambda m: m.group(2), first)
    return first
