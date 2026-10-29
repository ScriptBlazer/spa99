"""System > Emails (Developer level, unlocked, CSRF): automatic emails, group mailings and invites. Short views; the logic is in
system/emails.py, mailings/sending.py and mailings/invites.py. A page that is a form answers with a toast and a redirect, or with
JSON when the script asks for it (`Accept: application/json` or `X-Requested-With: fetch`)."""
import csv
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from common.ratelimit import hit
from mailings import automatic as auto_emails, blocks as mailing_blocks, images, invites, lists, segments, sending, tokens
from mailings import saved as templates_store
from mailings.models import ContactList, Invite, Mailing, MailingTemplate
from notifications import emailbody, ses
from notifications.models import EmailLog
from notifications.seed import DEFAULT_SUBJECTS
from notifications.services import fill_subject, preview_email, send_templated

from . import audit, emails as logic, services
from .models import SystemEvent
from .permissions import unlocked
from .views import form_status, page, saved


def _wants_json(request):
    return "application/json" in request.headers.get("accept", "") or request.headers.get("x-requested-with") == "fetch"


def _respond(request, ok, message, to, status=None, extra=None):
    """JSON {"ok", "message", ...} for a script; else a toast and a redirect to `to`."""
    if _wants_json(request):
        return JsonResponse({"ok": ok, "message": message, **(extra or {})}, status=status or (200 if ok else 400))
    (messages.success if ok else messages.error)(request, message)
    return redirect(to)


def _limited(request, scope, limit, window):
    """True (answer 429) when this person has done this too often."""
    return not hit(scope, request.user.pk, limit, window)


def _spec(key):
    spec = emailbody.SPECS.get(key)
    if spec is None or not spec.listed:
        raise Http404
    return spec


# ---------- automatic emails ----------

@unlocked
@require_GET
def automatic(request):
    return page(request, "system/emails_automatic.html", "emails", {"emails": logic.automatic_list(), "ses": ses.ses_status()})


def _edit(request, key, form=None, status=200):
    spec = _spec(key)
    row = logic.template_row(key, create=True)
    form = form or logic.TemplateForm(instance=row, spec=spec)
    return page(request, "system/emails_edit.html", "emails", {**logic.edit_context(spec, form, row), "ses": ses.ses_status(), "can_send_to_group": auto_emails.can_send_to_group(key)}, status=status)


@unlocked
@require_GET
def automatic_edit(request, key):
    return _edit(request, key)


@unlocked
@require_POST
def automatic_save(request, key):
    spec = _spec(key)
    row = logic.template_row(key, create=True)
    form = logic.TemplateForm(request.POST, instance=row, spec=spec)
    if form.is_valid():
        try:
            if services.save_form(form, request.user):
                saved(request)
            else:
                messages.info(request, "Nothing changed.")
            return redirect("system_email_edit", key=key)
        except ValidationError as error:  # the row changed since the page was made
            form.add_error(None, error)
    return _edit(request, key, form, status=form_status(form))


def _posted_text(request, spec):
    """(subject, body, errors) from a preview or test request. Blank body = the default wording."""
    subject = request.POST.get("subject", DEFAULT_SUBJECTS[spec.key][0])
    body = request.POST.get("body") if spec.editable else ""
    body = (body or "").replace("\r\n", "\n")
    return subject, body, emailbody.validate(spec, subject=subject, body=body if spec.editable else None)


@unlocked
@require_POST
def automatic_preview(request, key):
    """Live preview with the sample values: {"ok", "subject", "html", "text", "errors"}. Problems are in `errors` (status 200: typing
    half a placeholder is normal), with no html."""
    spec = _spec(key)
    subject, body, errors = _posted_text(request, spec)
    if errors:
        return JsonResponse({"ok": False, "errors": errors, "subject": "", "html": "", "text": ""})
    return JsonResponse({"ok": True, "errors": {}, **preview_email(key, subject, body)})


@unlocked
@require_POST
def automatic_test(request, key):
    """Send the email as typed (or as saved when nothing is posted), with sample values, to the signed-in developer only."""
    spec = _spec(key)
    back = reverse("system_email_edit", args=[key])
    if not spec.editable:
        return _respond(request, False, "This email has no test send: its layout is a real application.", back)
    if _limited(request, "system-email-test", 5, 600):
        return _respond(request, False, "Too many test emails. Please wait a few minutes.", back, status=429)
    if "subject" in request.POST or "body" in request.POST:
        subject, body, errors = _posted_text(request, spec)
        if errors:
            return _respond(request, False, " ".join(m for ms in errors.values() for m in ms), back, extra={"errors": errors})
        body = body if body.strip() else spec.default_body
    else:
        row = logic.template_row(key)
        subject, body = (row.subject if row else DEFAULT_SUBJECTS[key][0]), None
    context = emailbody.test_context_for(spec, f"{settings.SITE_URL}/example-link/")
    log = send_templated(key, [request.user.email], "[Test] " + fill_subject(subject, emailbody.sample_values(spec)), context, body=body,
                         subject_email=request.user.email)
    ok = log.status == EmailLog.SENT
    audit.log_event(SystemEvent.EMAIL_TEST, request, user=request.user, outcome=SystemEvent.OK if ok else SystemEvent.FAILED,
                    detail={"template": key, "status": log.status},
                    sentence=f"{request.user.email} sent themselves a test of the '{spec.title}' email ({log.status})")
    return _respond(request, ok, "A test is on its way to you." if ok else f"The test could not be sent ({log.get_status_display()}).", back)


@unlocked
@require_POST
def automatic_reset(request, key):
    """Reset to default: the subject and the wording go back to the built-in text, as one logged (undoable) change."""
    _spec(key)
    row = logic.template_row(key)
    default_subject = DEFAULT_SUBJECTS[key][0]
    back = reverse("system_email_edit", args=[key])
    fields = [name for name, default in (("subject", default_subject), ("body", "")) if row is not None and getattr(row, name) != default]
    if not fields:
        return _respond(request, True, "Already the default.", back)
    row.subject, row.body = default_subject, ""
    services.save_logged(row, request.user, fields=fields)
    if _wants_json(request):
        return JsonResponse({"ok": True, "message": "Back to the default."})
    saved(request, "Back to the default.")
    return redirect(back)


# ---------- SES ----------

@unlocked
@require_POST
def ses_refresh(request):
    """Read the SES account state again now (it is cached for an hour)."""
    if _limited(request, "system-ses-refresh", 6, 600):
        return _respond(request, False, "Please wait a minute before checking again.", reverse("system_emails"), status=429)
    status = ses.ses_status(refresh=True)
    if _wants_json(request):
        return JsonResponse({"ok": True, "ses": status})
    messages.info(request, status["message"] or status["provider"] or "Amazon SES allows sending.")
    return redirect("system_emails")


# ---------- mailings ----------

@unlocked
@require_GET
def mailings(request):
    return page(request, "system/emails_mailings.html", "emails", {"mailings": logic.mailing_list(request.GET.get("page")), "ses": ses.ses_status()})


def _mailing_page(request, form, mailing, status=200, start=None):
    spec = emailbody.SPECS["mailing"]
    saved_params = mailing.params if mailing else {}
    groups = segments.catalog()
    for group in groups:  # each option carries the value to show: what was typed, else what was saved
        for param in group["params"]:
            param["value"] = (form.data.get(param["name"]) if form.is_bound else saved_params.get(param["name"])) or ""
    cards = templates_store.details()
    context = {"form": form, "mailing": mailing, "groups": groups, "kind_choices": Mailing.KIND_CHOICES, "ses": ses.ses_status(),
               "placeholders": logic.spec_info(spec)["placeholders"],
               "count_url": reverse("system_mailing_count"), "preview_url": reverse("system_mailing_preview"),
               # The parts editor (docs/features/email-builder.md, Contract)
               "blocks": logic.editor_blocks(form, mailing, start), "block_errors": form.block_errors or {},
               "block_types": {kind: {name: {"max": limit, "required": required} for name, (limit, required) in fields.items()}
                               for kind, fields in mailing_blocks.TYPES.items()},
               "block_max_parts": mailing_blocks.MAX_PARTS, "image_upload_url": reverse("system_mailing_image_upload"),
               "image_max_bytes": images.MAX_BYTES, "image_view_base": f"{settings.SITE_URL}/email-image/", "starters": templates_store.choices(), "starter_details": cards,
               "start_cards": [("", "Blank", "An empty email with one paragraph.")] + [(d["id"], d["name"], d["description"]) for d in cards], "start": str(start.pk) if start else "",
               "template_save_url": reverse("system_template_save")}
    return page(request, "system/emails_mailing_form.html", "emails", context, status=status)


@unlocked
@require_http_methods(["GET", "POST"])
def mailing_edit(request, pk=None):
    """New mailing (no pk) or edit a draft."""
    mailing = get_object_or_404(Mailing, pk=pk) if pk else None
    if mailing is not None and not mailing.editable:
        messages.error(request, "Only a draft can be edited.")
        return redirect("system_mailing", pk=mailing.pk)
    start = templates_store.resolve(request.GET.get("start")) if mailing is None and request.method == "GET" else None
    form = logic.MailingForm(request.POST or None, instance=mailing, initial=_starter_fields(start))
    if request.method == "POST" and form.is_valid():
        row = form.save(commit=False)
        row.params = form.params
        if row.created_by_id is None:
            row.created_by = request.user
        row.save()
        if _wants_json(request):
            return JsonResponse({"ok": True, "id": str(row.pk), "redirect": reverse("system_mailing", args=[row.pk])})
        messages.success(request, "Saved as a draft.")
        return redirect("system_mailing", pk=row.pk)
    if request.method == "POST" and _wants_json(request):
        return JsonResponse({"ok": False, "errors": form.errors_json()}, status=400)
    return _mailing_page(request, form, mailing, status=400 if request.method == "POST" else 200, start=start)


def _starter_fields(start):
    """Form values for the chosen saved template (New mailing, ?start=<template id or key>)."""
    return {"name": start.name, "subject": start.subject, "kind": start.kind, "group": start.group} if start else {}


@unlocked
@require_GET
def mailing_detail(request, pk):
    mailing = get_object_or_404(Mailing, pk=pk)
    status = request.GET.get("status", "")
    draft = mailing.status in (Mailing.DRAFT, Mailing.SCHEDULED)
    blockers = sending.check_mailing(mailing) if draft else {}
    state = ses.ses_status()
    context = {
        "mailing": mailing, "progress": sending.progress(mailing), "ses": state, "blockers": blockers,
        "live_count": segments.count(mailing.group, mailing.params, mailing.kind, mailing.has_personal_links) if draft and mailing.group in segments.GROUPS else None,
        "group": segments.GROUPS.get(mailing.group), "can_send": draft and mailing.status == Mailing.DRAFT and state["allowed"] and not blockers,
        "recipients": logic.mailing_recipients(mailing, status, request.GET.get("page")), "status_filter": status,
        "progress_url": reverse("system_mailing_progress", args=[mailing.pk]),
        "preview": _mailing_preview(mailing), "lists": segments.param_choices("list_id") if mailing.automatic_key else [],
        "invite_summary": invites.batch_summary(mailing.pk) if mailing.automatic_key and mailing.status != Mailing.DRAFT else None,
        "confirm_url": reverse("system_mailing_confirm", args=[mailing.pk]), "send_url": reverse("system_mailing_send", args=[mailing.pk]),
        "automatic_spec": emailbody.SPECS.get(mailing.automatic_key),
    }
    return page(request, "system/emails_mailing.html", "emails", context)


def _mailing_preview(mailing):
    """The email as it will look (sample name). An automatic email's wording is read from its own page, so edits there show here."""
    extra = logic.mailing_extra(mailing.kind, mailing.group)
    if mailing.automatic_key:
        row = logic.template_row(mailing.automatic_key)
        return preview_email(mailing.automatic_key, row.subject if row else DEFAULT_SUBJECTS[mailing.automatic_key][0], row.body if row else "", extra)
    return preview_email("mailing", mailing.subject, mailing.body, extra, blocks=mailing.blocks)


@unlocked
@require_GET
def mailing_progress(request, pk):
    mailing = get_object_or_404(Mailing, pk=pk)
    data = sending.progress(mailing)
    return JsonResponse({**data, "started_at": data["started_at"].isoformat() if data["started_at"] else None,
                         "finished_at": data["finished_at"].isoformat() if data["finished_at"] else None})


@unlocked
@require_GET
def mailing_count(request):
    """Live count for the form: GET group, kind and the group's options -> {"count", "errors"}."""
    if _limited(request, "system-mailing-count", 120, 60):
        return JsonResponse({"error": "Too many requests."}, status=429)
    kind = request.GET.get("kind", Mailing.NEWS)
    group = request.GET.get("group", "")
    params, errors = segments.clean_params(group, request.GET)
    if errors or kind not in dict(Mailing.KIND_CHOICES):
        return JsonResponse({"count": None, "errors": errors or {"kind": ["Choose News or Service message."]}})
    if not segments.GROUPS[group].allows(kind):
        return JsonResponse({"count": None, "errors": {"group": [segments.GROUPS[group].kind_error()]}})
    personal = request.GET.get("personal") == "1"  # the parts have a personal-link button
    if personal and segments.GROUPS[group].people not in ("list", "leads"):
        return JsonResponse({"count": None, "errors": {"group": [sending.PERSONAL_REFUSED]}})
    return JsonResponse({"count": segments.count(group, params, kind, personal), "errors": {}})


@unlocked
@require_POST
def mailing_preview(request):
    """Preview of what is typed on the mailing form with the sample name: {"ok", "subject", "html", "text", "errors"}. With a `blocks`
    field (JSON) the parts are previewed and part problems come back as errors.blocks = {"_": [...], "<index>": {field: [...]}}."""
    if _limited(request, "system-mailing-preview", 120, 60):
        return JsonResponse({"ok": False, "errors": {"_": ["Too many previews. Please wait a moment."]}, "subject": "", "html": "", "text": ""}, status=429)
    subject, body = request.POST.get("subject", ""), request.POST.get("body", "")
    parts = None
    if "blocks" in request.POST:
        parts, block_errors = mailing_blocks.clean(request.POST["blocks"])
        errors = emailbody.validate(emailbody.SPECS["mailing"], subject=subject)
        if block_errors:
            errors["blocks"] = block_errors
    else:
        errors = emailbody.validate(emailbody.SPECS["mailing"], subject=subject, body=body)
    if errors:
        return JsonResponse({"ok": False, "errors": errors, "subject": "", "html": "", "text": ""})
    extra = logic.mailing_extra(request.POST.get("kind", Mailing.NEWS), request.POST.get("group", ""))
    return JsonResponse({"ok": True, "errors": {}, **preview_email("mailing", subject, body, extra, blocks=parts)})


@unlocked
@require_POST
def mailing_image_upload(request):
    """Upload one picture for an email (multipart, field `file`): JPEG, PNG or GIF up to 2 MB, checked from the file content.
    Answers {"ok", "id", "url", "width", "height"} (width and height are null when the header could not be read) or {"ok": false, "message"}."""
    if _limited(request, "system-email-image", 30, 600):
        return JsonResponse({"ok": False, "message": "Too many uploads. Please wait a few minutes."}, status=429)
    try:
        image = images.save_upload(request.FILES.get("file"), request.user)
    except images.ImageError as error:
        return JsonResponse({"ok": False, "message": str(error)}, status=400)
    return JsonResponse({"ok": True, "id": str(image.pk), "url": image.url, "width": image.width, "height": image.height})


def _send_test(request, back, subject, kind, group, body, parts, label, detail):
    """Send one mailing's wording to the signed-in developer only (their own first name; News tests carry a real unsubscribe link).
    Needs only a subject and wording that passes the checks: no Who, no saved mailing."""
    errors = sending.wording_errors(subject, body, parts)
    if errors:
        return _respond(request, False, " ".join(m for ms in errors.values() for m in ms), back, extra={"errors": errors})
    context, headers = {"first_name": request.user.first_name, **logic.mailing_extra(kind, group)}, None
    if mailing_blocks.has_personal(parts):  # a test shows the sample link (it explains itself), not a real one
        context["personal_links"] = mailing_blocks.sample_links()
    if kind in Mailing.MARKETING:  # a real unsubscribe link for the developer's own address
        context["unsubscribe_url"] = tokens.unsubscribe_url(request.user.email)
        headers = tokens.list_unsubscribe_headers(context["unsubscribe_url"])
    log = send_templated("mailing", [request.user.email], "[Test] " + sending.subject_line(subject, request.user.first_name),
                         context, headers=headers, body=body, blocks=parts, subject_email=request.user.email)
    ok = log.status == EmailLog.SENT
    audit.log_event(SystemEvent.EMAIL_TEST, request, user=request.user, outcome=SystemEvent.OK if ok else SystemEvent.FAILED,
                    detail={**detail, "status": log.status}, sentence=f"{request.user.email} sent themselves a test of the mailing '{label}' ({log.status})")
    return _respond(request, ok, "A test is on its way to you." if ok else f"The test could not be sent ({log.get_status_display()}).", back)


def _send_automatic_test(request, mailing):
    """Test a draft of an automatic email: the email as it stands, with the sample link, to the signed-in developer only."""
    key, back = mailing.automatic_key, reverse("system_mailing", args=[mailing.pk])
    spec, row = _spec(key), logic.template_row(mailing.automatic_key)
    context = {**emailbody.test_context_for(spec, f"{settings.SITE_URL}/example-link/"), **logic.mailing_extra(mailing.kind, mailing.group)}
    headers = None
    if mailing.kind in Mailing.MARKETING:  # a real unsubscribe link for the developer's own address
        context["unsubscribe_url"] = tokens.unsubscribe_url(request.user.email)
        headers = tokens.list_unsubscribe_headers(context["unsubscribe_url"])
    subject = row.subject if row else DEFAULT_SUBJECTS[key][0]
    log = send_templated(key, [request.user.email], "[Test] " + fill_subject(subject, emailbody.sample_values(spec)), context, headers=headers,
                         subject_email=request.user.email)
    ok = log.status == EmailLog.SENT
    audit.log_event(SystemEvent.EMAIL_TEST, request, user=request.user, outcome=SystemEvent.OK if ok else SystemEvent.FAILED,
                    detail={"mailing": str(mailing.pk), "template": key, "status": log.status},
                    sentence=f"{request.user.email} sent themselves a test of the '{spec.title}' group send ({log.status})")
    return _respond(request, ok, "A test is on its way to you." if ok else f"The test could not be sent ({log.get_status_display()}).", back)


@unlocked
@require_POST
def mailing_test(request, pk):
    """Test a saved draft (as saved), whatever its Who."""
    mailing = get_object_or_404(Mailing, pk=pk)
    if _limited(request, "system-email-test", 5, 600):
        return _respond(request, False, "Too many test emails. Please wait a few minutes.", reverse("system_mailing", args=[mailing.pk]), status=429)
    if mailing.automatic_key:
        return _send_automatic_test(request, mailing)
    return _send_test(request, reverse("system_mailing", args=[mailing.pk]), mailing.subject, mailing.kind, mailing.group, mailing.body,
                      mailing.blocks, mailing.name, {"mailing": str(mailing.pk)})


@unlocked
@require_POST
def mailing_test_posted(request):
    """Test what is on the form without saving and without Who: POST `subject`, `blocks` (JSON, or `body` for the old form) and `kind`
    (default news, which decides the footer). Answers like the other tests: {"ok", "message"} (400 with `errors` when the wording is not valid)."""
    if _limited(request, "system-email-test", 5, 600):  # first: a flood of bad forms must not cost a render each
        return _respond(request, False, "Too many test emails. Please wait a few minutes.", reverse("system_mailing_new"), status=429)
    parts = None
    if "blocks" in request.POST:
        parts, block_errors = mailing_blocks.clean(request.POST["blocks"])
        if block_errors:
            return _respond(request, False, " ".join(mailing_blocks.flat_errors(block_errors)), reverse("system_mailing_new"), extra={"errors": {"blocks": block_errors}})
    kind = request.POST.get("kind", Mailing.NEWS)
    kind = kind if kind in (Mailing.NEWS, Mailing.SERVICE) else Mailing.NEWS
    subject = request.POST.get("subject", "")
    return _send_test(request, reverse("system_mailing_new"), subject, kind, request.POST.get("group", ""), request.POST.get("body", ""), parts,
                      request.POST.get("name") or subject, {"unsaved": True})


def _mailing_action(request, pk, action, done):
    mailing = get_object_or_404(Mailing, pk=pk)
    back = reverse("system_mailing", args=[mailing.pk])
    try:
        action(mailing)
    except sending.MailingError as error:
        return _respond(request, False, str(error), back)
    return _respond(request, True, done, back)


def _counted(mailing):
    """The number of people who would get it now (None when the group itself is not valid: the send check says why)."""
    params, errors = segments.clean_params(mailing.group, mailing.params) if mailing.group in segments.GROUPS else ({}, True)
    return None if errors else segments.count(mailing.group, params, mailing.kind, mailing.has_personal_links)


@unlocked
@require_POST
def mailing_send(request, pk):
    """Send now. The POST must carry `confirm=yes` and the `expected_count` the pop-up showed; if the number changed, nothing is sent."""
    if _limited(request, "system-mailing-start", 6, 600):
        return _respond(request, False, "Too many sends. Please wait a few minutes.", reverse("system_mailing", args=[pk]), status=429)

    def run(mailing):
        sending.require_confirmed(request.POST.get("confirm"), request.POST.get("expected_count"), _counted(mailing))
        sending.start(mailing, request.user, request)
    return _mailing_action(request, pk, run, "Sending has started.")


@unlocked
@require_POST
def mailing_schedule(request, pk):
    if _limited(request, "system-mailing-start", 6, 600):
        return _respond(request, False, "Too many sends. Please wait a few minutes.", reverse("system_mailing", args=[pk]), status=429)
    when = logic.parse_when(request.POST.get("scheduled_at"))

    def run(mailing):
        sending.require_confirmed(request.POST.get("confirm"), request.POST.get("expected_count"), _counted(mailing))
        if when is None:
            raise sending.MailingError("Choose a date and time.")
        sending.schedule(mailing, when, request.user, request, confirmed=int(request.POST["expected_count"]))
    return _mailing_action(request, pk, run, "Scheduled.")


@unlocked
@require_POST
def mailing_cancel(request, pk):
    return _mailing_action(request, pk, lambda m: sending.cancel(m, request.user, request), "Cancelled.")


@unlocked
@require_POST
def mailing_resume(request, pk):
    def run(mailing):
        sending.require_confirmed(request.POST.get("confirm"), None)  # carries on a send that was confirmed: no count, but never by a stray POST
        sending.resume(mailing)
    return _mailing_action(request, pk, run, "Sending carries on.")


@unlocked
@require_POST
def mailing_delete(request, pk):
    mailing = get_object_or_404(Mailing, pk=pk)
    if mailing.status != Mailing.DRAFT:
        return _respond(request, False, "Only a draft can be deleted.", reverse("system_mailing", args=[pk]))
    mailing.delete()
    return _respond(request, True, "Draft deleted.", reverse("system_mailings"))


# ---------- groups and uploaded lists ----------

@unlocked
@require_GET
def groups(request):
    context = {"automatic_groups": segments.overview(), "lists": logic.lists_table(), "batches": logic.invite_batches(), "ses": ses.ses_status()}
    return page(request, "system/emails_groups.html", "emails", context)


def _list_form(request, target=None, error="", name="", category="", status=200, text="", problems=()):
    context = {"target": target, "text": text, "problems": list(problems), "categories": lists.categories(), "max_rows": invites.MAX_ROWS, "max_bytes": invites.MAX_BYTES, "error": error,
               "name": name, "category": category, "ses": ses.ses_status()}
    return page(request, "system/emails_list_new.html", "emails", context, status=status)


@unlocked
@require_GET
def list_new(request):
    return _list_form(request)


@unlocked
@require_GET
def list_add(request, pk):
    return _list_form(request, target=get_object_or_404(ContactList, pk=pk))


def _uploaded_text(request):
    """(text, error) from the pasted box or the uploaded file (read as bytes: the encoding is checked in `invites.decode`)."""
    upload = request.FILES.get("file")
    if upload is not None:
        if upload.size > invites.MAX_BYTES:
            return "", f"The file is larger than {invites.MAX_BYTES // 1024 // 1024} MB."
        text, error = invites.decode(upload.read())
        return invites.canonical(text), error
    return invites.canonical(request.POST.get("text", "")), ""


def _target(request):
    """The list being added to (POST `list`), or None for a new list. 404 for an id that does not exist."""
    value = request.POST.get("list", "")
    if not value:
        return None
    try:
        return get_object_or_404(ContactList, pk=uuid.UUID(value))
    except ValueError:
        raise Http404 from None


@unlocked
@require_POST
def list_review(request):
    """Check the list and show the report (nothing is written but a one-time token). The page sends `text`, `token`, the name and category back with Save."""
    target = _target(request)
    text, error = _uploaded_text(request)
    if request.POST.get("edits") and not error:
        text = lists.apply_edits(text, request.POST["edits"])  # the inline fixes, applied to the list as it was checked
    report = lists.review(text, target) if not error else {**lists.review(""), "errors": [error]}
    name, category = request.POST.get("name", ""), request.POST.get("category", "")
    token = invites.issue_token(request.user, text, str(target.pk) if target else "") if report["can_save"] else ""
    context = {"report": report, "text": text, "token": token, "target": target, "name": name, "category": category, "categories": lists.categories(),
               "ses": ses.ses_status(), "status_labels": report["labels"]}
    return page(request, "system/emails_list_review.html", "emails", context, status=400 if report["errors"] else 200)


@unlocked
@require_POST
def list_fix(request):
    """Go back and fix: the paste form again with exactly the text that was checked, the name and the category, and the problems listed above it.
    Posted back (nothing in the URL); nothing is written."""
    target = _target(request)
    text = invites.canonical(request.POST.get("text", ""))
    report = invites.check(text) if text.strip() else {"rows": [], "errors": []}
    return _list_form(request, target, name=request.POST.get("name", ""), category=request.POST.get("category", ""), text=text,
                      problems=lists.problem_lines(report))


@unlocked
@require_POST
def list_problems(request):
    """The rows that need fixing or have a heads-up, as a CSV download (cells starting with = + - @ are made safe for Excel)."""
    report = invites.check(invites.canonical(request.POST.get("text", "")))
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="list-problems.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(["Row", "Level", "Name", "Email", "What to do"])
    safe = lambda v: f"'{v}" if str(v).startswith(invites.FORMULA_START) else v  # noqa: E731
    for line, level, name, email, message in invites.problem_rows(report):
        writer.writerow([line, "Fix this" if level == invites.ERROR else "Heads-up", safe(name), safe(email), message])
    for error in report["errors"]:
        writer.writerow(["", "Fix this", "", "", error])
    return response


@unlocked
@require_POST
def list_save(request):
    """Save the checked list (checked again here). Nothing is sent. Needs the review page's one-time `token` for exactly this list: a second
    save with the same token (double click, lag, back, two tabs) returns the list that was saved and writes nothing."""
    back = reverse("system_list_new")
    if _limited(request, "system-list-save", 20, 600):
        return _respond(request, False, "Too many saves. Please wait a few minutes.", back, status=429)
    target = _target(request)
    text = invites.canonical(request.POST.get("text", ""))
    try:
        row = invites.find_token(request.POST.get("token", ""), request.user, text, str(target.pk) if target else "")
    except invites.TokenRefused as error:
        return _respond(request, False, str(error), back)

    def done(lst, message, repeated=False):
        return _respond(request, True, message, reverse("system_list", args=[lst.pk]), extra={"list": str(lst.pk), "repeated": repeated})

    if row.batch_id:  # already saved: answer with it, before anything is checked again
        lst = lists.existing_for(row)
        return done(lst, "This list was already saved.", True) if lst else _respond(request, False, "That list no longer exists.", back)
    expected = request.POST.get("expected_ok", "")
    try:
        if target is None:
            lst, report = lists.save_new(request.POST.get("name"), request.POST.get("category"), text, request.user, row, request)
        else:
            lst, preview = target, lists.review(text, target)
            if expected.isdigit() and int(expected) != preview["ok"]:
                raise lists.ListError(f"The list changed: {preview['ok']} can be saved now, not {expected}. Check it and save again.")
            _, report = lists.add_more(target, text, request.user, row, request)
    except lists.ListError as error:
        return _respond(request, False, str(error), reverse("system_list_add", args=[target.pk]) if target else back, extra={"errors": error.errors})
    if report.get("existing"):
        return done(lst, "This list was already saved.", True) if lst else _respond(request, False, "That list no longer exists.", back)
    if target:
        have = report["exists"]
        return done(lst, f"Added {report['ok']} new {'person' if report['ok'] == 1 else 'people'} ({have} {'was' if have == 1 else 'were'} already on the list). Nothing was sent.")
    return done(lst, f"{report['ok']} {'person' if report['ok'] == 1 else 'people'} saved as '{lst.name}'. Nothing was sent.")


@unlocked
@require_GET
def list_detail(request, pk):
    lst = get_object_or_404(ContactList, pk=pk)
    info = segments.list_breakdown(lst.pk)
    status = request.GET.get("status", "all")
    status = status if status in lists.FILTERS else "all"
    counts = lists.status_counts(lst, request.GET.get("q"))
    chips = [(key, "All" if key == "all" else lists.STATUS_LABELS[key], counts[key]) for key in lists.FILTERS if key in ("all", "not_invited") or counts[key]]
    context = {"list": lst, "members": lists.members_page(lst, request.GET.get("q"), request.GET.get("page"), status), "q": request.GET.get("q", ""),
               "status": status, "chips": chips, "reach": lists.invite_reach(lst), "info": info, "categories": lists.categories(), "ses": ses.ses_status()}
    return page(request, "system/emails_list.html", "emails", context)


@unlocked
@require_POST
def list_edit(request, pk):
    lst = get_object_or_404(ContactList, pk=pk)
    back = reverse("system_list", args=[lst.pk])
    try:
        changed = lists.edit(lst, request.user, request.POST.get("name"), request.POST.get("category"), request)
    except lists.ListError as error:
        return _respond(request, False, str(error), back, extra={"errors": error.errors})
    return _respond(request, True, "Saved." if changed else "Nothing changed.", back)


@unlocked
@require_POST
def list_delete(request, pk):
    lst = get_object_or_404(ContactList, pk=pk)
    lists.delete(lst, request.user, request)
    return _respond(request, True, "List deleted.", reverse("system_groups"))


@unlocked
@require_POST
def list_member_remove(request, pk, member):
    lst = get_object_or_404(ContactList, pk=pk)
    removed = lists.remove_member(lst, member, request.user, request)
    return _respond(request, removed, "Removed from the list." if removed else "He is not on this list.", reverse("system_list", args=[lst.pk]))


@unlocked
@require_GET
def invite_batch(request, batch):
    """A past invite batch (from the old Invites tab), read only."""
    if not Invite.objects.filter(batch_id=batch).exists():
        raise Http404
    status = request.GET.get("status", "")
    mailing = Mailing.objects.filter(pk=batch).first()
    context = {"batch": batch, "summary": invites.batch_summary(batch), "invites": logic.invite_page(batch, status, request.GET.get("page")),
               "status_filter": status, "status_choices": Invite.STATUS_CHOICES, "mailing": mailing, "ses": ses.ses_status()}
    return page(request, "system/emails_invite_batch.html", "emails", context)


@unlocked
def invites_moved(request, **kwargs):
    """Every address of the old Invites tab: on to Groups, for good (the past batches are read only there). Nothing is changed or sent."""
    return redirect("system_groups", permanent=True)


# ---------- send an automatic email to a group ----------

@unlocked
@require_POST
def email_to_group(request, key):
    """Start a group send draft pre-filled with this automatic email (its subject and wording are used as they are when it goes out)."""
    spec = _spec(key)
    if not auto_emails.can_send_to_group(key):
        raise Http404
    row = logic.template_row(key, create=True)
    list_id = request.POST.get("list_id")
    if list_id:
        try:
            uuid.UUID(list_id)
        except ValueError:
            raise Http404 from None  # not an id at all: not found, never a server error
    lst = get_object_or_404(ContactList, pk=list_id) if list_id else None  # from a list page: Who is that list
    group, params = ("", {}) if lst is None else (segments.LIST_KEY, {"list_id": str(lst.pk)})
    recent = Mailing.objects.filter(automatic_key=key, status=Mailing.DRAFT, created_by=request.user, created_at__gte=timezone.now() - timedelta(minutes=1)).first()
    if recent is not None:  # a double click: the draft just made is the answer
        if lst is not None and recent.params != params:
            recent.group, recent.params = group, params
            recent.save(update_fields=["group", "params", "updated_at"])
        return _respond(request, True, "Draft ready. Choose who gets it.", reverse("system_mailing", args=[recent.pk]), extra={"id": str(recent.pk)})
    mailing = Mailing.objects.create(name=spec.title, subject=row.subject, kind=auto_emails.SENDABLE[key], group=group, params=params, automatic_key=key, created_by=request.user)
    return _respond(request, True, "Draft ready. Check who it goes to, send yourself a test, then send." if lst else "Draft ready. Choose who gets it.",
                    reverse("system_mailing", args=[mailing.pk]), extra={"id": str(mailing.pk)})


@unlocked
@require_POST
def mailing_auto_save(request, pk):
    """Choose the uploaded list for a draft of an automatic email."""
    mailing = get_object_or_404(Mailing, pk=pk, status=Mailing.DRAFT)
    back = reverse("system_mailing", args=[mailing.pk])
    if not mailing.automatic_key:
        raise Http404
    params, errors = segments.clean_params(segments.LIST_KEY, request.POST)
    if errors:
        return _respond(request, False, " ".join(m for ms in errors.values() for m in ms), back)
    mailing.group, mailing.params = segments.LIST_KEY, params
    mailing.save(update_fields=["group", "params", "updated_at"])
    return _respond(request, True, "Saved.", back)


@unlocked
@require_GET
def mailing_confirm(request, pk):
    """What the send pop-up shows, read now: the email, who, the exact count, skipped and why, From, Reply-To and the provider."""
    mailing = get_object_or_404(Mailing, pk=pk)
    return JsonResponse({"ok": True, **sending.confirm_details(mailing)})


# ---------- saved templates ----------

@unlocked
@require_GET
def templates(request):
    return page(request, "system/emails_templates.html", "emails", {"templates": MailingTemplate.objects.all(), "ses": ses.ses_status()})


def _template_event(request, kind, sentence, template, **detail):
    audit.log_event(kind, request, user=request.user, sentence=sentence, detail={"template": str(template.pk), "name": template.name, **detail})


@unlocked
@require_POST
def template_save(request):
    """Save as template. POST `name`, and either `mailing` (a saved mailing's id) or `subject`, `kind`, `group`, `blocks` (JSON, as on the form).
    A name that exists is refused (409, `exists: true`) unless `overwrite=1`. Answers {"ok", "id", "name", "created"}; errors as
    {"ok": false, "errors": {"name": [...], "blocks": {...}}}."""
    if _limited(request, "system-template-save", 30, 600):
        return JsonResponse({"ok": False, "errors": {"_": ["Too many saves. Please wait a few minutes."]}}, status=429)
    post = request.POST
    subject, kind, group, raw = post.get("subject", ""), post.get("kind", Mailing.NEWS), post.get("group", ""), post.get("blocks", "[]")
    if post.get("mailing"):
        try:
            mailing = get_object_or_404(Mailing, pk=uuid.UUID(post["mailing"]))
        except ValueError:
            raise Http404 from None
        subject, kind, group, raw = mailing.subject, mailing.kind, mailing.group, mailing.blocks or mailing_blocks.from_body(mailing.body)
    try:
        template, created = templates_store.save(post.get("name"), subject, kind, group, raw, request.user, overwrite=post.get("overwrite") == "1")
    except templates_store.TemplateError as error:
        return JsonResponse({"ok": False, "errors": error.errors, "exists": error.exists}, status=409 if error.exists else 400)
    _template_event(request, SystemEvent.TEMPLATE_SAVED, f"{request.user.email} {'saved' if created else 'replaced'} the email template '{template.name}'", template,
                    created=created)
    return JsonResponse({"ok": True, "id": str(template.pk), "name": template.name, "created": created})


@unlocked
@require_POST
def template_rename(request, pk):
    template = get_object_or_404(MailingTemplate, pk=pk)
    old = template.name
    try:
        templates_store.rename(template, request.POST.get("name"), request.user)
    except templates_store.TemplateError as error:
        return _respond(request, False, " ".join(m for ms in error.errors.values() for m in ms), reverse("system_templates"), extra={"errors": error.errors},
                        status=409 if error.exists else 400)
    _template_event(request, SystemEvent.TEMPLATE_RENAMED, f"{request.user.email} renamed the email template '{old}' to '{template.name}'", template, old=old)
    return _respond(request, True, "Renamed.", reverse("system_templates"), extra={"name": template.name})


@unlocked
@require_POST
def template_delete(request, pk):
    """Delete a saved template. Pictures it uses stay (they are separate files, kept for the mailings that sent them)."""
    template = get_object_or_404(MailingTemplate, pk=pk)
    _template_event(request, SystemEvent.TEMPLATE_DELETED, f"{request.user.email} deleted the email template '{template.name}'", template)
    template._history_user = request.user
    template.delete()
    return _respond(request, True, "Template deleted.", reverse("system_templates"))
