"""System > Emails (Developer level, unlocked, CSRF): automatic emails, group mailings and invites. Short views; the logic is in
system/emails.py, mailings/sending.py and mailings/invites.py. A page that is a form answers with a toast and a redirect, or with
JSON when the script asks for it (`Accept: application/json` or `X-Requested-With: fetch`)."""
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from common.ratelimit import hit
from mailings import invites, segments, sending
from mailings.models import Invite, Mailing
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
    return page(request, "system/emails_edit.html", "emails", {**logic.edit_context(spec, form, row), "ses": ses.ses_status()}, status=status)


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
    messages.info(request, status["message"] or "Amazon SES allows sending.")
    return redirect("system_emails")


# ---------- mailings ----------

@unlocked
@require_GET
def mailings(request):
    return page(request, "system/emails_mailings.html", "emails", {"mailings": logic.mailing_list(request.GET.get("page")), "ses": ses.ses_status()})


def _mailing_page(request, form, mailing, status=200):
    spec = emailbody.SPECS["mailing"]
    saved_params = mailing.params if mailing else {}
    groups = segments.catalog()
    for group in groups:  # each option carries the value to show: what was typed, else what was saved
        for param in group["params"]:
            param["value"] = (form.data.get(param["name"]) if form.is_bound else saved_params.get(param["name"])) or ""
    context = {"form": form, "mailing": mailing, "groups": groups, "kind_choices": Mailing.KIND_CHOICES, "ses": ses.ses_status(),
               "placeholders": logic.spec_info(spec)["placeholders"],
               "count_url": reverse("system_mailing_count"), "preview_url": reverse("system_mailing_preview")}
    return page(request, "system/emails_mailing_form.html", "emails", context, status=status)


@unlocked
@require_http_methods(["GET", "POST"])
def mailing_edit(request, pk=None):
    """New mailing (no pk) or edit a draft."""
    mailing = get_object_or_404(Mailing, pk=pk) if pk else None
    if mailing is not None and not mailing.editable:
        messages.error(request, "Only a draft can be edited.")
        return redirect("system_mailing", pk=mailing.pk)
    form = logic.MailingForm(request.POST or None, instance=mailing)
    if request.method == "POST" and form.is_valid():
        row = form.save(commit=False)
        row.params = form.params
        if row.created_by_id is None:
            row.created_by = request.user
        row.save()
        messages.success(request, "Saved as a draft.")
        return redirect("system_mailing", pk=row.pk)
    return _mailing_page(request, form, mailing, status=400 if request.method == "POST" else 200)


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
        "live_count": segments.count(mailing.group, mailing.params, mailing.kind) if draft and mailing.group in segments.GROUPS else None,
        "group": segments.GROUPS.get(mailing.group), "can_send": draft and mailing.status == Mailing.DRAFT and state["allowed"] and not blockers,
        "recipients": logic.mailing_recipients(mailing, status, request.GET.get("page")), "status_filter": status,
        "progress_url": reverse("system_mailing_progress", args=[mailing.pk]),
        "preview": preview_email("mailing", mailing.subject, mailing.body, logic.mailing_extra(mailing.kind, mailing.group)),
    }
    return page(request, "system/emails_mailing.html", "emails", context)


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
    if errors or kind not in (Mailing.NEWS, Mailing.SERVICE):
        return JsonResponse({"count": None, "errors": errors or {"kind": ["Choose News or Service message."]}})
    return JsonResponse({"count": segments.count(group, params, kind), "errors": {}})


@unlocked
@require_POST
def mailing_preview(request):
    """Preview of what is typed on the mailing form with the sample name: {"ok", "subject", "html", "text", "errors"}."""
    subject, body = request.POST.get("subject", ""), request.POST.get("body", "")
    errors = emailbody.validate(emailbody.SPECS["mailing"], subject=subject, body=body)
    if errors:
        return JsonResponse({"ok": False, "errors": errors, "subject": "", "html": "", "text": ""})
    extra = logic.mailing_extra(request.POST.get("kind", Mailing.NEWS), request.POST.get("group", ""))
    return JsonResponse({"ok": True, "errors": {}, **preview_email("mailing", subject, body, extra)})


@unlocked
@require_POST
def mailing_test(request, pk):
    """Send this mailing to the signed-in developer only (their own first name; News tests carry a real unsubscribe link)."""
    mailing = get_object_or_404(Mailing, pk=pk)
    back = reverse("system_mailing", args=[mailing.pk])
    if _limited(request, "system-email-test", 5, 600):
        return _respond(request, False, "Too many test emails. Please wait a few minutes.", back, status=429)
    errors = sending.check_mailing(mailing) if mailing.group in segments.GROUPS else {"group": ["Choose a group."]}
    errors.pop("group", None)  # a test needs no audience
    if errors:
        return _respond(request, False, " ".join(m for ms in errors.values() for m in ms), back)
    from mailings import tokens

    context, headers = {"first_name": request.user.first_name, **logic.mailing_extra(mailing.kind, mailing.group)}, None
    if mailing.kind == Mailing.NEWS:  # a real unsubscribe link for the developer's own address
        context["unsubscribe_url"] = tokens.unsubscribe_url(request.user.email)
        headers = tokens.list_unsubscribe_headers(context["unsubscribe_url"])
    log = send_templated("mailing", [request.user.email], "[Test] " + sending.subject_line(mailing.subject, request.user.first_name),
                         context, headers=headers, body=mailing.body, subject_email=request.user.email)
    ok = log.status == EmailLog.SENT
    audit.log_event(SystemEvent.EMAIL_TEST, request, user=request.user, outcome=SystemEvent.OK if ok else SystemEvent.FAILED,
                    detail={"mailing": str(mailing.pk), "status": log.status},
                    sentence=f"{request.user.email} sent themselves a test of the mailing '{mailing.name}' ({log.status})")
    return _respond(request, ok, "A test is on its way to you." if ok else f"The test could not be sent ({log.get_status_display()}).", back)


def _mailing_action(request, pk, action, done):
    mailing = get_object_or_404(Mailing, pk=pk)
    back = reverse("system_mailing", args=[mailing.pk])
    try:
        action(mailing)
    except sending.MailingError as error:
        return _respond(request, False, str(error), back)
    return _respond(request, True, done, back)


@unlocked
@require_POST
def mailing_send(request, pk):
    """Send now. `expected_count` (the number the person saw) must still be right, else nothing is sent."""
    if _limited(request, "system-mailing-start", 6, 600):
        return _respond(request, False, "Too many sends. Please wait a few minutes.", reverse("system_mailing", args=[pk]), status=429)

    def run(mailing):
        expected = request.POST.get("expected_count", "")
        if expected.isdigit() and mailing.group in segments.GROUPS:
            now = segments.count(mailing.group, mailing.params, mailing.kind)
            if now != int(expected):
                raise sending.MailingError(f"The group changed: it is now {now} people, not {expected}. Check it and send again.")
        sending.start(mailing, request.user, request)
    return _mailing_action(request, pk, run, "Sending has started.")


@unlocked
@require_POST
def mailing_schedule(request, pk):
    if _limited(request, "system-mailing-start", 6, 600):
        return _respond(request, False, "Too many sends. Please wait a few minutes.", reverse("system_mailing", args=[pk]), status=429)
    when = logic.parse_when(request.POST.get("scheduled_at"))

    def run(mailing):
        if when is None:
            raise sending.MailingError("Choose a date and time.")
        sending.schedule(mailing, when, request.user, request)
    return _mailing_action(request, pk, run, "Scheduled.")


@unlocked
@require_POST
def mailing_cancel(request, pk):
    return _mailing_action(request, pk, lambda m: sending.cancel(m, request.user, request), "Cancelled.")


@unlocked
@require_POST
def mailing_resume(request, pk):
    return _mailing_action(request, pk, sending.resume, "Sending carries on.")


@unlocked
@require_POST
def mailing_delete(request, pk):
    mailing = get_object_or_404(Mailing, pk=pk)
    if mailing.status != Mailing.DRAFT:
        return _respond(request, False, "Only a draft can be deleted.", reverse("system_mailing", args=[pk]))
    mailing.delete()
    return _respond(request, True, "Draft deleted.", reverse("system_mailings"))


# ---------- invites ----------

@unlocked
@require_GET
def invites_list(request):
    return page(request, "system/emails_invites.html", "emails", {"batches": logic.invite_batches(), "ses": ses.ses_status()})


@unlocked
@require_GET
def invites_new(request):
    return page(request, "system/emails_invites_new.html", "emails", {"max_rows": invites.MAX_ROWS, "max_bytes": invites.MAX_BYTES, "ses": ses.ses_status()})


def _uploaded_text(request):
    """(text, error) from the pasted box or the uploaded file."""
    upload = request.FILES.get("file")
    if upload is not None:
        if upload.size > invites.MAX_BYTES:
            return "", f"The file is larger than {invites.MAX_BYTES // 1024 // 1024} MB."
        return upload.read().decode("utf-8-sig", errors="replace"), ""
    return request.POST.get("text", ""), ""


@unlocked
@require_POST
def invites_review(request):
    """Check the list and show the report (nothing is written). The page sends `text` back with Send."""
    text, error = _uploaded_text(request)
    report = invites.check(text) if not error else {"rows": [], "counts": {}, "errors": [error], "ok": 0, "total": 0}
    context = {"report": report, "text": text, "ses": ses.ses_status(), "status_labels": invites.STATUS_LABELS}
    return page(request, "system/emails_invites_review.html", "emails", context, status=400 if report["errors"] else 200)


@unlocked
@require_POST
def invites_send(request):
    """Make the batch from the checked list (checked again here) and queue the sending. `expected_ok` must match the report."""
    new = reverse("system_invites_new")
    if _limited(request, "system-invites-start", 6, 600):
        return _respond(request, False, "Too many sends. Please wait a few minutes.", new, status=429)
    try:
        ses.require_sending_allowed()
    except ses.SendingRefused as error:
        return _respond(request, False, str(error), new)
    text = request.POST.get("text", "")
    expected = request.POST.get("expected_ok", "")
    report = invites.check(text)
    if report["errors"]:
        return _respond(request, False, " ".join(report["errors"]), new)
    if not report["ok"]:
        return _respond(request, False, "Nobody in this list can be invited.", new)
    if expected.isdigit() and int(expected) != report["ok"]:
        return _respond(request, False, f"The list changed: {report['ok']} can be invited now, not {expected}. Check it and send again.", new)
    batch_id, report = invites.create_batch(text, request.user)
    try:
        sending.start_invites(batch_id, request.user, request)
    except sending.MailingError as error:
        return _respond(request, False, str(error), new)
    return _respond(request, True, f"Sending {report['ok']} invite{'' if report['ok'] == 1 else 's'}.", reverse("system_invite_batch", args=[batch_id]),
                    extra={"batch": str(batch_id), "invites": report["ok"]})


@unlocked
@require_GET
def invite_batch(request, batch):
    if not Invite.objects.filter(batch_id=batch).exists():
        raise Http404
    status = request.GET.get("status", "")
    context = {"batch": batch, "summary": invites.batch_summary(batch), "invites": logic.invite_page(batch, status, request.GET.get("page")),
               "status_filter": status, "status_choices": Invite.STATUS_CHOICES, "ses": ses.ses_status(),
               "progress_url": reverse("system_invite_progress", args=[batch])}
    return page(request, "system/emails_invite_batch.html", "emails", context)


@unlocked
@require_GET
def invite_progress(request, batch):
    return JsonResponse(invites.batch_summary(batch))


@unlocked
@require_POST
def invite_resume(request, batch):
    """Queue the worker again for a batch that still has invites waiting (it never sends one twice)."""
    back = reverse("system_invite_batch", args=[batch])
    try:
        sending.start_invites_resume(batch)
    except sending.MailingError as error:
        return _respond(request, False, str(error), back)
    return _respond(request, True, "Sending carries on.", back)
