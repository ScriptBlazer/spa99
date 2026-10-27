"""Editable wording of the automatic emails.

The layout stays in notifications/templates/notifications/emails/ (_base.html and _body.html/_body.txt). The words are plain
text: paragraphs separated by a blank line, {placeholders} filled in when sending, and `{button}` for the email's main link
(drawn as the Spa 99 button; in the plain-text version the address on its own line). Blank in the database = the built-in
default below, so "Reset to default" works and a send never fails for lack of a body.

Safety: the text is escaped, then paragraphs become <p>. Values are escaped too (a name like `<b>x</b>` shows as text).
Only placeholders ending in `_url` become links, and only the ones the code fills in. Stored text that no longer validates
(edited in the Django admin, say) is ignored at send time and the default is used."""
import re
from dataclasses import dataclass, field

from django.utils.html import conditional_escape, escape
from django.utils.safestring import mark_safe

TOKEN_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
BODY_MAX = 5000
SUBJECT_MAX = 300
BUTTON = "button"

FONT_BODY = "'Figtree','Segoe UI',-apple-system,BlinkMacSystemFont,'Helvetica Neue',Helvetica,Arial,sans-serif"
P_STYLE = "margin:0 0 16px;font-size:16px;line-height:26px;color:#492E21;"
LINK_STYLE = "color:#492E21;text-decoration:underline;word-break:break-word;"
GREETING_RE = re.compile(r"(hello|hi|dear)\b", re.I)
PREVIEW_MAX = 100


def preview_text(text):
    """The inbox preview line for an email body: the first paragraph that is not a short greeting, cut at 100 characters
    on a word boundary with an ellipsis. A paragraph with a link (the button, a {..._url} value) is never used. Plain text in, plain text out (the layout escapes it)."""
    for paragraph in re.split(r"\n\s*\n", (text or "").replace("\r\n", "\n")):
        paragraph = " ".join(paragraph.split())
        if not paragraph or "http://" in paragraph or "https://" in paragraph or (GREETING_RE.match(paragraph) and len(paragraph) < 40):
            continue
        if len(paragraph) <= PREVIEW_MAX:
            return paragraph
        cut = paragraph[:PREVIEW_MAX + 1]
        cut = cut[:cut.rfind(" ")] if " " in cut else cut[:PREVIEW_MAX]
        return cut.rstrip(" ,;:.-") + "\u2026"
    return ""


class Rich:
    """A value that carries both an HTML and a plain-text form (already safe: build it with escape())."""

    def __init__(self, html, text):
        self.html, self.text = mark_safe(html), text


@dataclass(frozen=True)
class EmailSpec:
    key: str
    title: str
    placeholders: dict  # name -> what it is (the frontend lists these)
    samples: dict  # name -> value used in the preview and the test email
    default_body: str = ""
    button_label: str = ""  # "" = this email has no {button}
    button_required: bool = False
    button_fallback: bool = True  # the small "if the button does not work" line after the button
    editable: bool = True  # False: only the subject is editable (the layout is a structured application summary)
    listed: bool = True  # False: not in the automatic list (a group mailing's body is its own text)
    subject_placeholders: dict = field(default_factory=dict)
    values: object = None  # callable(context) -> dict of computed placeholder values
    test_context: object = None  # the raw context a real send gets, for "send me a test" (default: the samples)


def _welcome_values(ctx):
    plan, opening, discount = ctx.get("plan_name", ""), ctx.get("opening_text", ""), ctx.get("discount_url", "")
    return {
        "registration_line": f"We have noted your registration for {plan}." if plan else "We have noted your registration.",
        "booking_line": f"We will write to you before booking opens{', ' + opening if opening else ''}.",
        "discount_line": (Rich(f'Looking for a better rate? Message us on WhatsApp: <a href="{escape(discount)}" style="{LINK_STYLE}">{escape(discount)}</a>',
                               f"Looking for a better rate? Message us on WhatsApp: {discount}") if discount else ""),
    }


def _plural(number, unit):
    return f"{number} {unit}" if number == 1 else f"{number} {unit}s"


def _row_days(ctx, fallback):
    """Days the link works: the row's own stamped length when the sender gave it (`valid_days`), else the Defaults value."""
    try:
        return max(1, int(ctx.get("valid_days")))
    except (TypeError, ValueError):
        return fallback


def _verify_values(ctx):
    from system import defaults

    return {"valid_for": _plural(defaults.get().email_confirm_hours, "hour")}


def _gold_invite_values(ctx):
    from system import defaults

    days = _row_days(ctx, defaults.get().gold_invite_days)
    return {"valid_for": _plural(days, "day"), "valid_days": days}


def _invite_values(ctx):
    from system import defaults

    return {"valid_for": _plural(_row_days(ctx, defaults.get().register_invite_days), "day")}


VALID_FOR = {"valid_for": "How long the link works, in words (e.g. '24 hours', '14 days'). Set in System > Defaults"}
_FIRST = {"first_name": "The person's first name"}
_SAMPLE_URL = "https://spa99.uk/example-link/"

SPECS = {spec.key: spec for spec in [
    EmailSpec(
        "verify", "Confirm your email", {**_FIRST, **VALID_FOR}, {"first_name": "James"},
        "Hello {first_name},\n\nPlease confirm your email address to finish setting up your Spa 99 account. The link works for {valid_for}."
        "\n\n{button}\n\nIf you did not ask for this, you can ignore this email.",
        button_label="Confirm my email", button_required=True, subject_placeholders=_FIRST, values=_verify_values),
    EmailSpec(
        "welcome", "Welcome", {**_FIRST, "account_id": "The account ID, e.g. AB12-CD34",
                               "registration_line": "'We have noted your registration for <plan>.'",
                               "booking_line": "'We will write to you before booking opens, and we plan to open in <month>.'",
                               "discount_line": "The WhatsApp discount line (empty when no link is set)"},
        {"first_name": "James", "account_id": "AB12-CD34", "registration_line": "We have noted your registration for Tier 2.",
         "booking_line": "We will write to you before booking opens, and we plan to open in December.",
         "discount_line": Rich(f'Looking for a better rate? Message us on WhatsApp: <a href="{_SAMPLE_URL}" style="{LINK_STYLE}">{_SAMPLE_URL}</a>',
                               f"Looking for a better rate? Message us on WhatsApp: {_SAMPLE_URL}")},
        "Hello {first_name},\n\nThank you for confirming your email. {registration_line}\n\n"
        "There is nothing to pay and nothing more to do right now. {booking_line}\n\n{discount_line}\n\nYour account ID is {account_id}.",
        subject_placeholders=_FIRST, values=_welcome_values,
        test_context={"first_name": "James", "plan_name": "Tier 2", "opening_text": "and we plan to open in December",
                      "discount_url": _SAMPLE_URL, "account_id": "AB12-CD34"}),
    EmailSpec(
        "password_reset", "Password reset", {**_FIRST}, {"first_name": "James"},
        "Hello {first_name},\n\nUse the link below to choose a new password. It works for one hour and only once.\n\n{button}\n\n"
        "If you did not ask for this, you can ignore this email. Your password has not changed.",
        button_label="Choose a new password", button_required=True, subject_placeholders=_FIRST),
    EmailSpec(
        "password_changed", "Password changed",
        {**_FIRST, "when": "When it was changed (London time)", "reset_url": "The forgot-password page, to reset it again"},
        {"first_name": "James", "when": "27 October 2026 at 14:05 (London time)", "reset_url": _SAMPLE_URL},
        "Hello {first_name},\n\nYour Spa 99 password was changed on {when}.\n\nIf this wasn't you, reset your password now: "
        "{reset_url}\n\nQuestions? Reply to this email and it will reach the team.",
        subject_placeholders=_FIRST),
    EmailSpec(
        "team_invite", "Added to the team",
        {**_FIRST, "level": "Their level: Office, Admin, Developer or Superuser", "office_url": "The address of the Office"},
        {"first_name": "James", "level": "Office", "office_url": "https://office.spa99.uk"},
        "Hello {first_name},\n\nYou've been added to the Spa 99 team ({level}). Use the link below to choose your own password. "
        "It works for one hour and only once.\n\n{button}\n\nThen sign in at {office_url}. If the link has run out, ask the person who "
        "added you to send a new one.",
        button_label="Choose my password", button_required=True, subject_placeholders=_FIRST),
    EmailSpec(
        "gold_ack", "Gold application received", {**_FIRST, "reference": "The application reference"},
        {"first_name": "James", "reference": "G-7K2M9Q"},
        "Hello {first_name},\n\nThank you. We have your Gold Card application and we will be in touch.\n\nYour reference is {reference}.",
        subject_placeholders=_FIRST),
    EmailSpec(
        "gold_invite", "Gold approved: set up the account", {**_FIRST, **VALID_FOR, "valid_days": "The number of days only (older wording; use valid_for)"},
        {"first_name": "James"},
        "Hello {first_name},\n\nGood news: your Spa 99 Gold Card application has been approved.\n\n"
        "Set up your account below. Your details are already filled in, you only choose a password. The link works for {valid_for} "
        "and can be used once.\n\n{button}\n\nIf the link has expired, reply to this email and we will send a new one.",
        button_label="Set up your account", button_required=True, subject_placeholders=_FIRST, values=_gold_invite_values),
    EmailSpec(
        "gold_active", "Gold active", {**_FIRST}, {"first_name": "James"},
        "Hello {first_name},\n\nYour Spa 99 Gold Card is active on your account, from today.\n\nYou can see it when you sign in.\n\n{button}",
        button_label="Go to my account", button_required=True, button_fallback=False, subject_placeholders=_FIRST),
    EmailSpec(
        "invite", "Invitation to register", {**_FIRST, **VALID_FOR}, {"first_name": "James"},
        "Hello {first_name},\n\nYou are invited to register for Spa 99, a men-only luxury spa at 99 Vale Road, London N4.\n\n"
        "Registering is free and there is nothing to pay. Use your personal link to start: your name and email are already filled in. The link works for {valid_for}."
        "\n\n{button}\n\nIf you were not expecting this, you can ignore this email.",
        button_label="Register for Spa 99", button_required=True, subject_placeholders=_FIRST, values=_invite_values),
    # Sent by an approver from the Office (docs/features/gold-actions.md). Respond: the typed {message} sits in this wording.
    # Declined: this wording only PREFILLS the decline form; the approver can edit it, and what is sent is exactly that text.
    EmailSpec(
        "gold_respond", "Gold application: a message from the team", {**_FIRST, "message": "What the approver wrote (line breaks kept)"},
        {"first_name": "James", "message": "Thank you for applying. Could you tell us a little more about the properties you own?"},
        "Hello {first_name},\n\n{message}\n\nYou can reply to this email and it will reach the team.",
        subject_placeholders=_FIRST),
    EmailSpec(
        "gold_declined", "Gold declined (only sent if the approver ticks Email the applicant)",
        {**_FIRST, "name": "The applicant's full name", "reference": "The application reference"},
        {"first_name": "James", "name": "James Smith", "reference": "GC-7K2M9Q"},
        "Hello {first_name},\n\nThank you for applying for the Spa 99 Gold Card. We have looked at your application carefully and we are "
        "not able to offer you a Gold Card at this time.\n\nThank you for your interest in Spa 99.",
        subject_placeholders={**_FIRST, "name": "The applicant's full name"}),
    # The structured emails to the approvers: layout and wording stay in the template files, only the subject is editable.
    EmailSpec("gold_approver", "Gold application (to approvers)", {}, {}, editable=False,
              subject_placeholders={"name": "The applicant's name", "potential": "High, Medium or Low"}),
    EmailSpec("gold_approver_repeat", "Gold application, repeat (to approvers)", {}, {}, editable=False,
              subject_placeholders={"name": "The applicant's name", "potential": "High, Medium or Low"}),
    EmailSpec("gold_final", "Final approval (to final approvers)", {}, {}, editable=False,
              subject_placeholders={"name": "The applicant's name"}),
    EmailSpec("gold_sent_back", "Sent back (to approvers)", {}, {}, editable=False,
              subject_placeholders={"name": "The applicant's name"}),
    # A group mailing's body is typed per mailing; this only supplies the placeholders, the layout and the preview samples.
    EmailSpec("mailing", "Group mailing", {**_FIRST}, {"first_name": "James"}, listed=False, subject_placeholders=_FIRST),
]}


def spec_for(key):
    return SPECS.get(key)


def listed_specs():
    return [s for s in SPECS.values() if s.listed]


def allowed_names(spec):
    return set(spec.placeholders) | ({BUTTON} if spec.button_label else set())


def placeholders_in(text):
    return TOKEN_RE.findall(text or "")


def _stray_braces(text):
    return "{" in TOKEN_RE.sub("", text or "") or "}" in TOKEN_RE.sub("", text or "")


def validate(spec, subject=None, body=None):
    """Field errors for a proposed subject and/or body: {"subject": [...], "body": [...]} (only fields with problems).
    A blank body is fine (it means the default)."""
    errors = {}

    def add(name, message):
        errors.setdefault(name, []).append(message)

    if subject is not None:
        subject = subject.strip()
        if not subject:
            add("subject", "The subject cannot be empty.")
        if len(subject) > SUBJECT_MAX:
            add("subject", f"The subject can be at most {SUBJECT_MAX} characters.")
        if "\n" in subject or "\r" in subject:
            add("subject", "The subject must be one line.")
        allowed = set(spec.subject_placeholders)
        for name in dict.fromkeys(placeholders_in(subject)):
            if name not in allowed:
                add("subject", _unknown(name, allowed))
        if _stray_braces(subject):
            add("subject", "A { or } is not part of a placeholder. Write placeholders like {first_name}.")
    if body is not None and body.strip():
        if not spec.editable:
            add("body", "The wording of this email cannot be changed here, only its subject.")
            return errors
        if len(body) > BODY_MAX:
            add("body", f"The text can be at most {BODY_MAX} characters.")
        allowed = allowed_names(spec)
        names = placeholders_in(body)
        for name in dict.fromkeys(names):
            if name not in allowed:
                add("body", _unknown(name, allowed))
        if _stray_braces(body):
            add("body", "A { or } is not part of a placeholder. Write placeholders like {first_name}.")
        if spec.button_required and BUTTON not in names:
            add("body", "Add {button} on a line of its own: it is the link the person needs.")
        if names.count(BUTTON) > 1:
            add("body", "Use {button} once.")
    return errors


def _unknown(name, allowed):
    listing = ", ".join("{" + n + "}" for n in sorted(allowed)) or "none"
    return f"Unknown placeholder {{{name}}}. You can use: {listing}."


def effective_body(spec, stored):
    """The body to send: the stored one when it is set and still valid, else the default."""
    if stored and stored.strip() and spec.editable and not validate(spec, body=stored):
        return stored
    return spec.default_body


def values_for(spec, context):
    """The placeholder values for a real send, from the context the sender gave."""
    context = context or {}
    values = {name: context.get(name, "") for name in spec.placeholders}
    if spec.values:
        values.update(spec.values(context))
    if "first_name" in values and not str(values["first_name"]).strip():
        values["first_name"] = "there"
    return values


def sample_values(spec):
    """The preview values: the samples, plus anything the spec computes from the live Defaults (e.g. how long a link works)."""
    values = dict(spec.samples)
    if spec.values and "valid_for" in spec.placeholders:
        values.update(spec.values({}))
    return values


def test_context_for(spec, url):
    """The context for a test send: raw values as a real sender gives them, plus the sample link."""
    return {**(spec.test_context if spec.test_context is not None else spec.samples), "url": url}  # computed values (valid_for) are filled at send


def _html_value(name, value):
    if isinstance(value, Rich):
        return value.html
    value = "" if value is None else str(value)
    if name.endswith("_url") and value.startswith(("http://", "https://")):
        return mark_safe(f'<a href="{escape(value)}" style="{LINK_STYLE}">{escape(value)}</a>')
    return conditional_escape(value)


def _text_value(value):
    return value.text if isinstance(value, Rich) else ("" if value is None else str(value))


def render(spec, body, values, button_url="", button_label=None):
    """(html, text) for the body. The html is the inside of the layout's content cell; the text is the plain-text body."""
    label = button_label or spec.button_label or "Open"
    html, text = [], []
    for paragraph in re.split(r"\n\s*\n", (body or "").replace("\r\n", "\n").replace("\r", "\n")):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        pieces_html, pieces_text, current_html, current_text = [], [], [], []

        def flush():
            line_html = "".join(current_html).strip()
            line_text = "".join(current_text).strip()
            if line_text:
                pieces_html.append(f'<p style="{P_STYLE}">{line_html.replace(chr(10), "<br>")}</p>')
                pieces_text.append(line_text)
            current_html.clear()
            current_text.clear()

        for index, part in enumerate(TOKEN_RE.split(paragraph)):
            if index % 2 == 0:  # literal text
                current_html.append(str(escape(part)))
                current_text.append(part)
            elif part == BUTTON and spec.button_label:
                flush()
                if button_url:
                    pieces_html.append(_button_html(button_url, label, spec.button_fallback))
                    pieces_text.append(f"{label}:\n{button_url}")
            else:
                value = values.get(part, "")
                current_html.append(str(_html_value(part, value)))
                current_text.append(_text_value(value))
        flush()
        html.extend(pieces_html)
        text.extend(pieces_text)
    return mark_safe("\n".join(html)), "\n\n".join(text)


def render_plain(text):
    """(html, text) for words typed by a person, shown exactly as typed: no placeholders, paragraphs on blank lines, line breaks kept."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", (text or "").replace("\r\n", "\n").replace("\r", "\n")) if p.strip()]
    html = "\n".join(f'<p style="{P_STYLE}">{str(escape(p)).replace(chr(10), "<br>")}</p>' for p in paragraphs)
    return mark_safe(html), "\n\n".join(paragraphs)


def _button_html(url, label, fallback):
    url_html, label_html = escape(url), escape(label)
    button = (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:8px 0 16px;"><tr>'
        '<td class="e-btn" bgcolor="#492E21" align="center" style="background:#492E21;background-image:linear-gradient(#492E21,#492E21);'
        'border-radius:6px;mso-padding-alt:15px 32px;">'
        f'<a href="{url_html}" target="_blank" style="display:inline-block;padding:15px 32px;font-family:{FONT_BODY};font-size:16px;'
        f'line-height:20px;font-weight:600;color:#F5F2D8;text-decoration:none;border-radius:6px;">{label_html}</a></td></tr></table>')
    if fallback:
        button += (f'<p class="e-muted" style="margin:0 0 16px;font-size:13px;line-height:20px;color:#7B675A;">'
                   f'If the button does not work, paste this link into your browser:<br>'
                   f'<a href="{url_html}" style="color:#7B675A;text-decoration:underline;word-break:break-all;">{url_html}</a></p>')
    return button
