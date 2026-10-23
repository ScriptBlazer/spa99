"""Turns a legal body (format in content/legal.py) into safe HTML: paragraphs, lists, small headings, links and the
{contact} / {ico} / {hosting} / {version} tokens. Everything typed in Control is escaped first; only the markup made
here is trusted."""
import re

from django.utils.html import escape
from django.utils.safestring import mark_safe

LINK = re.compile(r"\[([^\]]+)\]\(((?:/|https://|mailto:)[^)\s]*)\)")
PLACEHOLDERS = {
    "ico": "[ICO registration number — to add before launch]",
    "hosting": "[Hosting provider name — to add before launch]",
}


def _resolve(line, values, show_placeholders):
    """Apply the fill-later tokens to one escaped line. Returns None when the line should be dropped."""
    for token, placeholder in PLACEHOLDERS.items():
        mark = "{" + token + "}"
        if mark not in line:
            continue
        value = values.get(token, "").strip()
        if value:
            line = line.replace(mark, escape(value))
        elif show_placeholders:
            line = line.replace(mark, f'<mark class="legal-todo" data-legal-todo="{token}">{escape(placeholder)}</mark>')
        elif f"({mark})" in line:
            line = re.sub(r"\s*\(" + re.escape(mark) + r"\)", "", line)
        else:
            return None
    return line


def render(text, contact="", version="", values=None, show_placeholders=False):
    """Safe HTML for one legal body. `values` holds the fill-later rows ({"ico": "...", "hosting": "..."})."""
    values = values or {}
    contact_html = f'<a href="mailto:{escape(contact)}">{escape(contact)}</a>' if contact else "us"
    out, items = [], []

    def close_list():
        if items:
            out.append("<ul>" + "".join(f"<li>{item}</li>" for item in items) + "</ul>")
            items.clear()

    for raw in (text or "").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        kind = "li" if raw.startswith("- ") else "h3" if raw.startswith("### ") else "p"
        body = raw[2:] if kind == "li" else raw[4:] if kind == "h3" else raw
        line = escape(body)
        line = LINK.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', line)
        line = line.replace("{contact}", contact_html).replace("{version}", escape(version))
        line = _resolve(line, values, show_placeholders)
        if line is None:
            continue
        if kind == "li":
            items.append(line)
            continue
        close_list()
        out.append(f"<{kind}>{line}</{kind}>")
    close_list()
    return mark_safe("\n".join(out))
