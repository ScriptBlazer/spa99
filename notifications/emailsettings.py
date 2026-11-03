"""Per-email settings and the shared footer (docs/features/office-outreach.md, Email flexibility).

The footer is three lines under every email (brand, address, contact; placeholders {site_name}, {address}, {contact_email}; a blank line
is left out). The shared lines live on SiteSettings; an email can use them as they are, without the contact line, or its own three lines
(NotificationTemplate). The unsubscribe link and the "why you get this" notice are NOT part of this: they are drawn by the layout under
the footer from `unsubscribe_url` / `notice`, so no setting here can remove them.

An email's footer mode, sender, heading and button text are stored on its NotificationTemplate row; "" means that email's built-in
default (EmailSpec.default_footer / default_sender, the subject as heading, the spec's button text), so an untouched email renders exactly as
before. `options_for(key, posted)` reads the saved row, with any posted (not yet saved) values on top, for a preview or a test send."""
import logging
from dataclasses import dataclass

from django.utils.html import escape
from django.utils.safestring import mark_safe

from common import emaildefaults as d

from . import emailbody

logger = logging.getLogger("spa99.email")

LINK_STYLE = "color:#7B675A;text-decoration:underline;"
LINE_FIELDS = ("footer_brand_line", "footer_address_line", "footer_contact_line")
LINE_LABELS = {"footer_brand_line": "Brand line", "footer_address_line": "Address line", "footer_contact_line": "Contact line"}


@dataclass(frozen=True)
class Options:
    footer_mode: str
    footer_lines: tuple  # (brand, address, contact) templates, with the mode already applied ("" = left out)
    sender: str
    heading: str = ""
    button_text: str = ""


# ---------- checking what is typed ----------

def validate_line(text):
    """Problems with one footer line (a list of messages)."""
    problems = []
    text = text or ""
    if len(text) > d.FOOTER_LINE_MAX:
        problems.append(f"At most {d.FOOTER_LINE_MAX} characters.")
    if "\n" in text or "\r" in text:
        problems.append("One line only.")
    allowed = set(d.FOOTER_PLACEHOLDERS)
    for name in dict.fromkeys(emailbody.placeholders_in(text)):
        if name not in allowed:
            problems.append(emailbody._unknown(name, allowed))
    if emailbody._stray_braces(text):
        problems.append("A { or } is not part of a placeholder. Write placeholders like {contact_email}.")
    return problems


def validate_lines(data):
    """{field: [messages]} for the footer lines present in `data` (a dict or QueryDict)."""
    errors = {}
    for name in LINE_FIELDS:
        if name in data and (problems := validate_line(data.get(name))):
            errors[name] = problems
    return errors


def validate_options(spec, data):
    """Problems in the per-email settings in `data` (heading, button_text, footer_mode, sender, custom footer lines): {field: [messages]}."""
    errors = {}
    heading = (data.get("heading") or "").strip()
    if heading:
        if len(heading) > d.HEADING_MAX:
            errors["heading"] = [f"The heading can be at most {d.HEADING_MAX} characters."]
        elif "\n" in heading or "\r" in heading:
            errors["heading"] = ["The heading must be one line."]
        else:
            allowed = set(spec.subject_placeholders)
            problems = [emailbody._unknown(n, allowed) for n in dict.fromkeys(emailbody.placeholders_in(heading)) if n not in allowed]
            if emailbody._stray_braces(heading):
                problems.append("A { or } is not part of a placeholder. Write placeholders like {first_name}.")
            if problems:
                errors["heading"] = problems
    button = (data.get("button_text") or "").strip()
    if button:
        if not spec.button_label:
            errors["button_text"] = ["This email has no button."]
        elif len(button) > d.BUTTON_TEXT_MAX or "\n" in button or "\r" in button:
            errors["button_text"] = [f"The button text must be one line of at most {d.BUTTON_TEXT_MAX} characters."]
        elif "{" in button or "}" in button:
            errors["button_text"] = ["The button text is plain words, without { }."]
    if data.get("footer_mode", "") not in ("", *dict(d.FOOTER_MODES)):
        errors["footer_mode"] = ["Choose one of the footers."]
    if data.get("sender", "") not in ("", *dict(d.SENDERS)):
        errors["sender"] = ["Choose one of the senders."]
    if data.get("footer_mode") == d.FOOTER_CUSTOM:
        errors.update(validate_lines(data))
    return errors


# ---------- reading the settings ----------

def shared_lines():
    from plans.models import SiteSettings

    site = SiteSettings.load()
    return site.footer_brand_line, site.footer_address_line, site.footer_contact_line


def options_for(key, posted=None, shared=None):
    """The settings an email uses now. `posted` (a dict or QueryDict from an edit screen) replaces the saved values for a preview or test;
    `shared` (brand, address, contact) replaces the saved shared footer (the Footer tab's preview)."""
    from .models import NotificationTemplate

    spec = emailbody.spec_for(key)
    row = NotificationTemplate.objects.filter(key=key).first()

    def pick(name, fallback):
        return posted[name] if posted is not None and name in posted else fallback

    mode = pick("footer_mode", row.footer_mode if row else "") or (spec.default_footer if spec else d.FOOTER_SHARED)
    sender = pick("sender", row.sender if row else "") or (spec.default_sender if spec else d.SENDER_SITE)
    if mode not in dict(d.FOOTER_MODES):
        mode = d.FOOTER_SHARED
    if sender not in dict(d.SENDERS):
        sender = d.SENDER_SITE
    if mode == d.FOOTER_CUSTOM:
        lines = tuple(pick(name, getattr(row, name) if row else getattr(d, "FOOTER_" + name[7:-5].upper())) for name in LINE_FIELDS)
        if any(validate_line(line) for line in lines):  # stored text that no longer validates: use the shared footer
            lines = tuple(shared) if shared is not None else shared_lines()
    else:
        lines = tuple(shared) if shared is not None else shared_lines()
        if mode == d.FOOTER_NO_CONTACT:
            lines = (lines[0], lines[1], "")
    editable = spec is not None and spec.editable
    heading = (pick("heading", row.heading if row else "") or "").strip() if editable else ""
    button = (pick("button_text", row.button_text if row else "") or "").strip() if editable and spec.button_label else ""
    return Options(mode, lines, sender, heading, button)


# ---------- using them ----------

def _fill(template, ctx):
    """(html, text) of one footer line with the placeholders filled in; ("", "") when nothing is left. Unknown {names} stay as typed."""
    html, text = [], []
    for index, part in enumerate(emailbody.TOKEN_RE.split(template or "")):
        if index % 2 == 0:
            html.append(str(escape(part)))
            text.append(part)
        elif part in d.FOOTER_PLACEHOLDERS:
            value = str(ctx.get(part, "") or "")
            if part == "contact_email":
                html.append(f'<a class="e-link" href="mailto:{escape(value)}" style="{LINK_STYLE}">{escape(value)}</a>')
            else:
                html.append(str(escape(value)))
            text.append(value)
        else:
            html.append(str(escape("{" + part + "}")))
            text.append("{" + part + "}")
    html, text = "".join(html), "".join(text)
    return (mark_safe(html), text) if text.strip() else ("", "")


def footer_context(options, ctx):
    """What the layouts draw for the footer: {"brand", "address", "contact"} as safe html ("" = left out) and "text" (the plain-text lines,
    each ending in a newline, in the order the text layout has always used: address, contact, brand)."""
    brand, address, contact = (_fill(line, ctx) for line in options.footer_lines)
    text = "".join(f"{line[1]}\n" for line in (address, contact, brand) if line[1])
    return {"brand": brand[0], "address": address[0], "contact": contact[0], "text": text}


def sender_for(options, site):
    """(from_email or None, reply_to list or None) for the chosen sender. None = the site sender (DEFAULT_FROM_EMAIL, Reply-To the contact
    address). The person sender needs the address set in System > Emails; without it the site sender is used and a warning is logged."""
    if options.sender == d.SENDER_PERSON:
        sender = site.auto_sender
        if sender:
            return sender, [site.auto_email_from_address.strip()]
        logger.warning("Person sender chosen but no automatic emails sender address is set: sent from the site sender")
    return None, None
