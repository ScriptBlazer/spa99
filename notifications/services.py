"""Sending email. Every send is logged (EmailLog). A failure is logged, never raised, so a broken mail server
cannot break a sign-up or a Gold application."""
import logging
from dataclasses import replace

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.safestring import mark_safe

from plans.models import SiteSettings

from . import emailbody, emailsettings, suppression
from .models import EmailLog, NotificationTemplate
from .seed import DEFAULT_SUBJECTS, LEGACY_KEYS

logger = logging.getLogger("spa99.email")


def base_context():
    site = SiteSettings.load()
    return {
        "site_name": "Spa 99",
        "tagline": "Beyond Luxury",
        "contact_email": site.contact_address,
        "site_url": settings.SITE_URL,
        # Unhashed on purpose: a hashed name changes with every logo edit and would break images in emails already sent.
        "logo_url": f"{settings.SITE_URL}/static/common/img/email/logo-on-dark-2x.png",
        "address": site.address_one_line,
    }


def subject_for(key, **values):
    """The subject line for an email: the NotificationTemplate row (edited in Control), or the built-in default.
    {placeholders} are replaced from `values`; unknown ones are left as typed."""
    row = NotificationTemplate.objects.filter(key=key).first()
    if row is None and key in LEGACY_KEYS:  # an install not yet backfilled still has the old row name
        row = NotificationTemplate.objects.filter(key=LEGACY_KEYS[key]).first()
    text = row.subject if row else DEFAULT_SUBJECTS[key][0]
    return fill_subject(text, values)


def body_for(key):
    """The stored body text of an editable email ('' = use the default)."""
    row = NotificationTemplate.objects.filter(key=key).only("body").first()
    return row.body if row else ""


def render_editable(key, context, body=None, values=None, button_url=None, options=None):
    """(body_html, body_text) of an email whose wording is editable. `body` overrides the stored one (a group mailing's own
    text, a preview); `values` overrides the placeholder values (a preview uses the samples)."""
    spec = emailbody.spec_for(key)
    text = emailbody.effective_body(spec, body if body is not None else body_for(key))
    if values is None:
        values = emailbody.values_for(spec, context)
    url = button_url if button_url is not None else (context or {}).get("url", "")
    options = options or emailsettings.options_for(key)
    return emailbody.render(spec, text, values, button_url=url, button_label=options.button_text or emailbody.button_label_for(spec))


def render_email(template, ctx, body=None, values=None, button_url=None, blocks=None, options=None):
    """(html, text) of the whole email for a ready context (the layout around the body). `body` and `values` as in render_editable;
    the context is given the rendered body as `body_html` / `body_text`. `options` (emailsettings.Options) are the email's footer, heading
    and button settings: the saved ones unless an edit screen gives its own."""
    options = options or emailsettings.options_for(template)
    ctx["footer"] = emailsettings.footer_context(options, ctx)
    layout = "gold_approver" if template == "gold_approver_repeat" else template  # one layout, the repeat panel shows on is_repeat
    spec = emailbody.spec_for(template)
    personal = False
    if blocks and template == "mailing":  # a group mailing built from parts (mailings/blocks.py); no parts = the old body
        from mailings import blocks as mailing_blocks

        shown = dict(values if values is not None else emailbody.values_for(spec, ctx))
        shown.setdefault("personal_links", ctx.get("personal_links") or {})  # each person's own tracked links, when the parts have them
        ctx["body_html"], ctx["body_text"], preheader = mailing_blocks.render(blocks, shown)
        ctx.setdefault("preheader", preheader)
        layout = "_body"
    elif ctx.get("plain_body") is not None:  # words typed by a person, sent as typed (the Gold decline message)
        ctx["body_html"], ctx["body_text"] = emailbody.render_plain(ctx["plain_body"])
        layout = "_body"
    elif spec is not None and spec.editable:
        ctx["body_html"], ctx["body_text"] = render_editable(template, ctx, body=body, values=values, button_url=button_url, options=options)
        layout = "_body"
    sign = ctx.pop("signature_html", "") or ""
    if sign:  # an Office email's signature: the signature allow-list again, our own picture addresses made absolute
        from common import richtext

        ctx["signature_html"] = mark_safe(richtext.absolute_images(richtext.clean_signature(sign), settings.SITE_URL))  # safe only because it has just been through clean_signature
        ctx["heading"] = ""  # a personal email has no big title repeating its subject
        personal = True
    if layout == "_body":
        if options.heading and not personal:
            ctx["heading"] = fill_subject(options.heading, values if values is not None else emailbody.values_for(spec, ctx))
        ctx.setdefault("heading", ctx.get("subject", "").removeprefix("[Test] "))
        ctx.setdefault("preheader", emailbody.preview_text(ctx["body_text"]))
    return render_to_string(f"notifications/emails/{layout}.html", ctx), render_to_string(f"notifications/emails/{layout}.txt", ctx)


def _staff_sample_context(key):
    """A realistic context for previewing the structured staff emails (their layout needs an applicant and links)."""
    if key not in ("gold_approver", "gold_approver_repeat", "gold_final", "gold_sent_back"):
        return {}
    site = settings.SITE_URL
    rows = [("Name", "James Smith"), ("Email", "james.smith@example.com"), ("Mobile", "+44 7700 900123")]
    return {
        "name": "James Smith", "potential_label": "High" if key != "gold_final" else "Low", "is_repeat": key == "gold_approver_repeat",
        "repeat_reference": "GC-7K2M9Q", "sent_back_by": "Barry", "note": "Please check the property count.",
        "approve_url": f"{site}/example-link/", "decline_url": f"{site}/example-link/", "respond_url": f"{site}/example-link/",
        "view_url": f"{site}/example-link/", "confirm_url": f"{site}/example-link/", "send_back_url": f"{site}/example-link/",
        "sections": [{"title": "Contact", "rows": rows}, {"title": "Property", "rows": [("Where", "London"), ("Size", "10 to 50 units")]}],
    }


def preview_email(key, subject, body, extra=None, blocks=None, posted=None, shared=None, sender_user=None):
    """The email as it would look with the sample values: {"subject", "html", "text", "from"}. `body` blank = the default; `extra` is added to
    the context (the unsubscribe link and notice of a News mailing); `posted` holds footer, sender, heading and button settings typed on
    the edit screen and not saved yet; `shared` (brand, address, contact) is the shared footer typed on the Footer tab."""
    spec = emailbody.spec_for(key)
    values = emailbody.sample_values(spec)
    ctx = {**base_context(), "subject": fill_subject(subject, values), "url": f"{settings.SITE_URL}/example-link/",
           **_staff_sample_context(key), **(extra or {})}
    options = emailsettings.options_for(key, posted, shared)
    if sender_user is not None:  # a group send's own sender (the staff member picked on its form), whatever the email's own setting says
        options = replace(options, sender_user=str(sender_user) if sender_user else None)
    if blocks:  # a personal-link button shows the sample link in a preview
        from mailings import blocks as mailing_blocks

        ctx.setdefault("personal_links", mailing_blocks.sample_links())
    html, text = render_email(key, ctx, body=body if body and body.strip() else spec.default_body, values=values, blocks=blocks, options=options)
    return {"subject": ctx["subject"], "html": html, "text": text, "from": _from_label(options), "reply_to": _reply_label(options)}


def _from_label(options):
    """Who the email comes from, in words, for the preview ('Spa 99 <hello@...>' or the person)."""
    from_email, _ = emailsettings.sender_for(options, SiteSettings.load())
    return from_email or settings.DEFAULT_FROM_EMAIL


def _reply_label(options):
    """Where a reply goes: the chosen person's own address, or the contact address."""
    _, reply_to = emailsettings.sender_for(options, SiteSettings.load())
    return (reply_to or [SiteSettings.load().contact_address])[0]


def fill_subject(text, values):
    for name, value in values.items():
        if name == "first_name" and not str(value).strip():
            value = "there"  # the same fallback as the body
        text = text.replace("{" + name + "}", str(value))
    return text


def send_templated(template, to, subject, context=None, cc=None, subject_email="", headers=None, body=None, plain_body=None, blocks=None, attachments=None, from_email=None, reply_to=None, options=None, signature_html=None, signature_text=None):
    """Render the email, send, and log. Returns the EmailLog. Editable emails (notifications/emailbody.py) use the shared
    layout `_body` and the stored or default wording; the Gold approver emails render their own template files.
    `to` and `cc` are lists of addresses. `subject_email` is the person the message is about when it goes to
    someone else (Barry's Gold email), so deleting that person's data finds the log row.
    `headers` are extra mail headers (List-Unsubscribe); `body` replaces the stored wording (a group mailing); `plain_body` is
    text a person typed, sent as typed in the shared layout; `blocks` are a group mailing's parts (used instead of `body`);
    `attachments` is a list of (filename, bytes, mimetype); `from_email` and `reply_to` (a list) replace the sender the email's
    settings choose; `options` (emailsettings.Options) replace its saved footer, sender, heading and button settings (a test send from the edit screen). `signature_html` and `signature_text` go under the text of an Office email: the signature is cleaned by `common.richtext.clean_signature` before it is marked safe, and a key of that name in `context` is ignored. An email with a signature has no heading."""
    to, cc = list(to or []), list(cc or [])
    try:
        blocked = suppression.suppressed_set(to + cc)  # THE guard: every email goes through here
    except Exception as error:  # noqa: BLE001 - cannot tell who is suppressed: fail closed (send nothing), never raise
        logger.error("Email %s not sent: suppression list unavailable (%s)", template, type(error).__name__)
        log = EmailLog(to=", ".join(to), subject=subject[:300], template=template, status=EmailLog.FAILED,
                       subject_email=(subject_email or "").strip().lower(), error="Suppression list unavailable; not sent.")
        try:
            log.save()
        except Exception:  # noqa: BLE001
            pass
        return log
    if blocked:
        to = [a for a in to if suppression.clean(a) not in blocked]
        cc = [a for a in cc if suppression.clean(a) not in blocked]
        logger.warning("Email %s: %d suppressed address(es) skipped", template, len(blocked))
        if not to:  # nobody left to email (a CC alone is not a reason to send)
            log = EmailLog.objects.create(
                to=", ".join(sorted(blocked)), subject=subject[:300], template=template, status=EmailLog.SUPPRESSED,
                subject_email=(subject_email or "").strip().lower(), error="Address is on the suppression list (bounce or complaint).")
            return log
    ctx = {**base_context(), "subject": subject, **(context or {})}
    for key in ("signature_html", "signature_text"):
        ctx.pop(key, None)  # only the arguments below can switch these on, never a context key
    if signature_html:
        ctx["signature_html"] = signature_html
    if signature_text:
        ctx["signature_text"] = signature_text.strip()
    if plain_body is not None:
        ctx["plain_body"] = plain_body
    log = EmailLog(
        to=", ".join(to), cc=", ".join(cc), subject=subject[:300], template=template,
        subject_email=(subject_email or "").strip().lower(),
    )
    try:
        options = options or emailsettings.options_for(template)
        if from_email is None:  # the email's own sender setting (site by default; the person sender needs its address set in System)
            from_email, reply_to = emailsettings.sender_for(options, SiteSettings.load())
        html, text = render_email(template, ctx, body=body, blocks=blocks, options=options)
        message = EmailMultiAlternatives(
            subject=subject,
            body=text,
            from_email=from_email or settings.DEFAULT_FROM_EMAIL,
            to=to,
            cc=cc,
            reply_to=list(reply_to) if reply_to else [ctx["contact_email"]],
            headers=headers or None,
        )
        message.attach_alternative(html, "text/html")
        for name, content, mimetype in attachments or ():
            message.attach(name, content, mimetype)
        message.send(fail_silently=False)
        log.status, log.sent_at = EmailLog.SENT, timezone.now()
        log.message_id = str(getattr(message, "ses_message_id", ""))[:100]
    except Exception as error:  # noqa: BLE001 - any failure is recorded, then the caller carries on
        log.status, log.error = EmailLog.FAILED, f"{type(error).__name__}: {error}"[:1000]
    log.save()
    if log.status == EmailLog.FAILED:  # no address, no traceback (SMTP errors repeat the address): the log row has the detail
        logger.error("Email %s failed (email log %s, %s)", template, log.pk, log.error.split(":")[0])
    return log
