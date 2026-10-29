"""A group mailing as parts ("blocks"): validation, rendering and the "Start from" templates. Spec: docs/features/email-builder.md.

Stored in `Mailing.blocks` as a list of {"type": ..., fields}. `clean()` returns the tidy list to store (only the known fields, image size
filled in) plus errors by part: {"_": ["whole-email problems"], "2": {"url": ["..."]}} (the key is the part's position, from 0).
`render()` turns stored parts into the inside of the shared layout's content cell, plus the plain-text version and the inbox preview line.
Rendering never touches the database (the image size is stored with the part), so a send does no extra queries per person."""
import json
import re
import uuid
from urllib.parse import urlsplit

from django.conf import settings
from django.utils.html import escape
from django.utils.safestring import mark_safe

from notifications import emailbody

from .models import IMAGE_EXTENSIONS

MAX_PARTS = 30
# Gmail clips an email over 102 KB and hides the footer (the unsubscribe link). The layout around the parts is about 12 KB, so the parts
# may use this much HTML.
HTML_MAX = 88_000
TOO_LONG = "This email is too long for some inboxes (they cut it off and hide the unsubscribe link). Shorten it."
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "0.0.0.0")
URL_MAX = 500
IMAGE_MAX_WIDTH = 504  # the layout's content width (600 less 2 x 48 padding); inside the spec's 552 cap
HEADING, PARAGRAPH, BUTTON, IMAGE, DIVIDER, SMALL_PRINT = "heading", "paragraph", "button", "image", "divider", "small_print"

# type -> field -> (max length, required). The UI reads this (it is in the editor context) so its counters match the checks.
TYPES = {
    HEADING: {"text": (120, True)},
    PARAGRAPH: {"text": (2000, True)},
    BUTTON: {"label": (40, True), "url": (URL_MAX, True)},
    IMAGE: {"image": (36, True), "alt": (200, True), "url": (URL_MAX, False)},
    DIVIDER: {},
    SMALL_PRINT: {"text": (500, True)},
}
TEXT_PARTS = (HEADING, PARAGRAPH, SMALL_PRINT)  # {first_name} works here
ONE_LINE = {(HEADING, "text"), (BUTTON, "label"), (IMAGE, "alt"), (BUTTON, "url"), (IMAGE, "url")}
FIELD_NAMES = {"text": "text", "label": "label", "url": "link", "alt": "alt text", "image": "image"}
REQUIRED_WORDS = {
    (HEADING, "text"): "Write the heading.", (PARAGRAPH, "text"): "Write the paragraph.", (SMALL_PRINT, "text"): "Write the small print.",
    (BUTTON, "label"): "Write the button label.", (BUTTON, "url"): "Add the button link.", (IMAGE, "image"): "Upload an image.",
    (IMAGE, "alt"): "Describe the image for people who cannot see it (alt text).",
}
URL_HELP = "Use a full link starting with http:// or https://, or a site path starting with a single / such as /account/book/."

SMALL_STYLE = "margin:0 0 16px;font-size:13px;line-height:20px;color:#7B675A;"
HEADING_STYLE = ("margin:28px 0 12px;font-family:'Signika','Trebuchet MS','Segoe UI',Helvetica,Arial,sans-serif;font-size:22px;line-height:28px;"
                 "font-weight:500;letter-spacing:-0.5px;color:#492E21;")
_BAD_URL_CHARS = re.compile(r"[\s\x00-\x1f\x7f\\<>\"']")


# ---------- the starting templates (words stored in code; the mailing is edited freely) ----------

STARTERS = {
    "booking_open": {
        "label": "Booking is open",
        "name": "Booking is open",
        "subject": "Booking is open at Spa 99",
        "kind": "service",
        "group": "everyone",
        "blocks": [
            {"type": HEADING, "text": "Booking is open"},
            {"type": PARAGRAPH, "text": "Hello {first_name},\n\nBooking is now open at Spa 99. You can choose a time that suits you and reserve your first visit "
                                        "from your account, whenever you are ready."},
            {"type": BUTTON, "label": "Book your first visit", "url": "/account/book/"},
            {"type": SMALL_PRINT, "text": "Spa 99, __ADDRESS__. If you have any questions, reply to this email and it will reach the team."},
        ],
    },
}


def starter_choices():
    """For the New mailing page's Start from choice: [(key, label)], Blank first (key '')."""
    return [("", "Blank")] + [(key, value["label"]) for key, value in STARTERS.items()]


# ---------- old mailings ----------

def from_body(body):
    """Paragraph parts from an old plain body (what the editor shows when a draft has a body and no parts)."""
    return [{"type": PARAGRAPH, "text": p.strip()} for p in re.split(r"\n\s*\n", (body or "").replace("\r\n", "\n").replace("\r", "\n")) if p.strip()]


# ---------- validation ----------

def clean_url(value):
    """(url, error). A full http(s) link, or a site path that starts with a single '/'. Nothing else (no javascript:, data:, mailto:)."""
    url = (value or "").strip() if isinstance(value, str) else ""
    if not url:
        return "", ""
    if len(url) > URL_MAX:
        return url, f"The link can be at most {URL_MAX} characters."
    if _BAD_URL_CHARS.search(url):
        return url, URL_HELP
    if url.startswith("/"):
        return (url, "") if not url.startswith("//") else (url, URL_HELP)
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        return url, URL_HELP
    if parts.scheme.lower() not in ("http", "https") or not host or "." not in host and host != "localhost":
        return url, URL_HELP
    if host in LOCAL_HOSTS and not settings.DEBUG:
        return url, "This link points to a computer, not the internet, so it would not work for the people who get the email."
    return url, ""


def absolute_url(url):
    """A stored link as the email needs it: a site path gets SITE_URL in front."""
    return f"{settings.SITE_URL}{url}" if url.startswith("/") else url


def _parse(raw):
    if isinstance(raw, (str, bytes)):
        raw = raw.strip()
        if not raw:
            return [], None
        try:
            raw = json.loads(raw)
        except ValueError:
            return None, "The email parts could not be read. Reload the page and try again."
    if raw is None:
        return [], None
    if not isinstance(raw, list):
        return None, "The email parts could not be read. Reload the page and try again."
    return raw, None


def _text_errors(kind, name, text):
    """Placeholder and length problems for a typed value."""
    limit, _ = TYPES[kind][name]
    if len(text) > limit:
        return [f"The {FIELD_NAMES[name]} can be at most {limit} characters."]
    if kind in TEXT_PARTS:
        return emailbody.validate(emailbody.SPECS["mailing"], body=text).get("body", [])
    return []


def _clean_part(part):
    """(cleaned part or None, {field: [messages]})."""
    errors = {}
    if not isinstance(part, dict) or part.get("type") not in TYPES:
        return None, {"type": ["Unknown part type."]}
    kind = part["type"]
    cleaned = {"type": kind}
    for name, (limit, required) in TYPES[kind].items():
        value = part.get(name)
        value = value.strip() if isinstance(value, str) else ""
        if kind == PARAGRAPH or kind == SMALL_PRINT:
            value = value.replace("\r\n", "\n").replace("\r", "\n")
        if (kind, name) in ONE_LINE and ("\n" in value or "\r" in value):
            errors.setdefault(name, []).append(f"The {FIELD_NAMES[name]} must be on one line.")
        if not value:
            if required:
                errors.setdefault(name, []).append(REQUIRED_WORDS[(kind, name)])
            cleaned[name] = ""
            continue
        if name == "url":
            value, problem = clean_url(value)
            if problem:
                errors.setdefault(name, []).append(problem)
        elif name == "image":
            pass  # checked together below
        else:
            for message in _text_errors(kind, name, value):
                errors.setdefault(name, []).append(message)
        cleaned[name] = value
    return cleaned, errors


def clean(raw):
    """(cleaned list, errors). `raw` is the posted JSON text or a list. Errors: {"_": [whole email], "<index>": {field: [messages]}}.
    Check `if errors` before storing: the cleaned list is only complete when there are none."""
    from .models import MailingImage

    parts, problem = _parse(raw)
    if problem:
        return [], {"_": [problem]}
    errors, cleaned = {}, []  # `cleaned` keeps a slot (None) for a part with an unknown type, so errors name the part where it sits
    if len(parts) > MAX_PARTS:
        errors["_"] = [f"An email can have at most {MAX_PARTS} parts."]
    for index, part in enumerate(parts):
        done, part_errors = _clean_part(part)
        if part_errors:
            errors[str(index)] = part_errors
        cleaned.append(done)
    ids = {}
    for index, part in enumerate(cleaned):
        if part is not None and part["type"] == IMAGE and part.get("image"):
            try:
                ids[index] = str(uuid.UUID(part["image"]))
            except ValueError:
                errors.setdefault(str(index), {}).setdefault("image", []).append("This image is not valid. Upload it again.")
    found = {str(i.pk): i for i in MailingImage.objects.filter(pk__in=set(ids.values()))} if ids else {}
    for index, image_id in ids.items():
        image = found.get(image_id)
        if image is None:
            errors.setdefault(str(index), {}).setdefault("image", []).append("This image no longer exists. Upload it again.")
        else:
            cleaned[index].update({"image": image_id, "width": image.width, "height": image.height, "ext": IMAGE_EXTENSIONS[image.content_type]})
    cleaned = [part for part in cleaned if part is not None]
    if not any(part["type"] != DIVIDER for part in cleaned) and len(parts) <= MAX_PARTS and "_" not in errors:
        errors["_"] = ["Add at least one part that is not a divider."]
    if not errors and len(render(cleaned, {"first_name": "Christopher"})[0].encode()) > HTML_MAX:
        errors["_"] = [TOO_LONG]
    return cleaned, errors


def flat_errors(errors):
    """Block errors as plain sentences for places that show a list: ["Part 3: Use a full link ..."]."""
    sentences = list(errors.get("_", []))
    for key in sorted((k for k in errors if k != "_"), key=int):
        for messages in errors[key].values():
            sentences.extend(f"Part {int(key) + 1}: {m}" for m in messages)
    return sentences


def check_stored(blocks):
    """Problems with the parts as stored (sending checks again: an image or wording may have changed since the draft was saved)."""
    return flat_errors(clean(blocks)[1])


# ---------- rendering ----------

def _text(kind, part, values):
    """(html, text) of a text part with {first_name} filled in (escaped)."""
    html, text = emailbody.render(emailbody.SPECS["mailing"], part.get("text", ""), values)
    if kind == HEADING:
        text = " ".join(text.split())
        return mark_safe(f'<h2 style="{HEADING_STYLE}">{escape(text)}</h2>') if text else "", text
    if kind == SMALL_PRINT:
        html = str(html).replace(f'style="{emailbody.P_STYLE}"', f'class="e-muted" style="{SMALL_STYLE}"')
    return html, text


def _image(part):
    width, height = part.get("width"), part.get("height")
    ext = f".{part['ext']}" if part.get("ext") else ""
    src = f"{settings.SITE_URL}/email-image/{part.get('image', '')}{ext}" if ext else f"{settings.SITE_URL}/email-image/{part.get('image', '')}/"
    size = f' width="{min(width, IMAGE_MAX_WIDTH)}"' if width else ""
    if width and height:
        size += f' height="{round(height * min(width, IMAGE_MAX_WIDTH) / width)}"'
    style = (f"display:block;width:{min(width, IMAGE_MAX_WIDTH)}px;max-width:100%;height:auto;border:0;outline:none;" if width
             else f"display:block;max-width:100%;height:auto;border:0;outline:none;")
    img = f'<img src="{escape(src)}"{size} alt="{escape(part.get("alt", ""))}" style="{style}">'
    if part.get("url"):
        img = f'<a href="{escape(absolute_url(part["url"]))}" target="_blank" style="text-decoration:none;">{img}</a>'
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:8px 0 20px;"><tr><td>{img}</td></tr></table>'


def render(blocks, values):
    """(body_html, body_text, preheader) for the layout. `values` are the placeholder values ({"first_name": ...}). Unknown parts are skipped."""
    html, text, paragraphs, others = [], [], [], []
    for part in blocks or []:
        kind = part.get("type") if isinstance(part, dict) else None
        if kind in TEXT_PARTS:
            part_html, part_text = _text(kind, part, values)
            if not part_text:
                continue
            html.append(str(part_html))
            text.append(part_text)
            (paragraphs if kind == PARAGRAPH else others).append(part_text)
        elif kind == BUTTON and part.get("label") and part.get("url"):
            url = absolute_url(part["url"])
            html.append(emailbody._button_html(url, part["label"], True))
            text.append(f"{part['label']}:\n{url}")
        elif kind == IMAGE and part.get("image"):
            html.append(_image(part))
            link = f"\n{absolute_url(part['url'])}" if part.get("url") else ""
            text.append(f"[Image: {part.get('alt', '')}]{link}")
        elif kind == DIVIDER:
            html.append('<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:16px 0;"><tr>'
                        '<td class="e-hair" height="1" style="border-top:1px solid #E2DDD0;font-size:0;line-height:0;">&nbsp;</td></tr></table>')
            text.append("----")
    preheader = emailbody.preview_text("\n\n".join(paragraphs)) or emailbody.preview_text("\n\n".join(others))
    return mark_safe("\n".join(html)), "\n\n".join(text), preheader
