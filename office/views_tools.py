"""Views for the person tools: sticky notes, the approach list, Send guide and the Email button. Short: validate, call the service in
outreach.services (or gold.actions), answer. Notes answer an HTMX request with the notes partial."""
from django.contrib import messages
from urllib.parse import urlencode

from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from gold import actions as gold_actions
from gold import audit
from gold.models import GoldApplication
from common import sorting
from outreach import listing, services
from outreach.models import OutreachEntry, StickyNote
from plans.models import SiteSettings

from . import lists, tools
from .forms import ArchiveForm, ContactForm, MessageForm, OutreachAddForm, StickyNoteForm
from system import defaults
from .permissions import admin, editor, reader

NOTE_TEXT = {services.EMPTY: "Write the note.", services.TOO_LONG: "Note: keep it to 1000 characters."}


def _errors(form):
    return [m for found in form.errors.values() for m in found]


def _notes_reply(request, target, status=200, errors=()):
    """HTMX: the notes partial (context keys notes, notes_count, note_max, can_note, note_add_url, notes_errors). Otherwise a toast
    and back to the page."""
    if request.headers.get("HX-Request"):
        response = render(request, "office/_notes.html", {**tools.notes_context(target, request.user), "notes_errors": list(errors)}, status=status)
        patch_vary_headers(response, ["HX-Request"])
        return response
    for message in errors:
        messages.error(request, message)
    return redirect(target.page_url)


@editor
@require_POST
def note_add(request, pk, kind):
    target = tools.target_for(kind, pk)
    form = StickyNoteForm(request.POST)
    if not form.is_valid():
        return _notes_reply(request, target, status=400, errors=_errors(form))
    result, _ = services.add_note(target.main, request.user, form.cleaned_data["note"])
    if result == services.DUPLICATE:
        messages.info(request, "That note was already added.")
    elif result != services.DONE:
        return _notes_reply(request, target, status=400, errors=[NOTE_TEXT.get(result, "The note could not be saved.")])
    return _notes_reply(request, target)


@editor
@require_POST
def note_delete(request, pk, note, kind):
    target = tools.target_for(kind, pk)
    found = get_object_or_404(StickyNote, pk=note, email__in=list(target.addresses), deleted_at__isnull=True)  # only this person's notes
    services.delete_note(found, request.user)
    return _notes_reply(request, target)


@editor
@require_POST
def note_edit(request, pk, note, kind):
    """Edit a note by clicking it (R9). POST note. HTMX: the notes partial (400 with the message when it is empty or too long)."""
    target = tools.target_for(kind, pk)
    found = get_object_or_404(StickyNote, pk=note, email__in=list(target.addresses), deleted_at__isnull=True)  # only this person's notes
    form = StickyNoteForm(request.POST)
    if not form.is_valid():
        return _notes_reply(request, target, status=400, errors=_errors(form))
    result = services.edit_note(found, request.user, form.cleaned_data["note"])
    if result == services.MISSING:
        raise Http404
    if result in (services.EMPTY, services.TOO_LONG):
        return _notes_reply(request, target, status=400, errors=[NOTE_TEXT[result]])
    return _notes_reply(request, target)


@editor
@require_POST
def note_restore(request, pk, note, kind):
    """Restore a deleted note from the "Note deleted by X" history line (R8). Idempotent; writes "Note restored by X"."""
    target = tools.target_for(kind, pk)
    found = get_object_or_404(StickyNote, pk=note, email__in=list(target.addresses))
    if services.restore_note(found, request.user) == services.DONE:
        messages.success(request, "Note restored.")
    else:
        messages.info(request, "That note is already back.")
    return redirect(target.page_url)


@editor
@require_POST
def gold_send_guide(request, pk):
    application = get_object_or_404(GoldApplication, pk=pk)
    result, _ = gold_actions.send_guide(application, request.user, channel=audit.OFFICE)
    if result == gold_actions.DONE:
        messages.success(request, f"The guide is on its way to {application.first_name or 'him'}. It is in the history.")
    elif result == gold_actions.DUPLICATE:
        messages.info(request, "The guide was already sent.")
    else:
        messages.warning(request, "Upload the guide in System first.")
    return redirect("office_gold_application", pk=application.pk)


@admin
@require_POST
def gold_delete(request, pk):
    """Delete a Gold application and its history (Admin and up). Written to the System change log. Back to the Gold list."""
    application = get_object_or_404(GoldApplication, pk=pk)
    reference = gold_actions.delete_application(application, request.user, request=request)
    messages.success(request, f"{reference} deleted.")
    return redirect("office_gold")


@editor
@require_POST
def outreach_add(request, pk, kind):
    target = tools.target_for(kind, pk)
    form = OutreachAddForm(request.POST)
    if not form.is_valid():
        messages.error(request, " ".join(_errors(form)))
        return redirect(target.page_url)
    result, _ = services.add_to_list(request.user, user=target.user, lead_email=target.lead_email, application=target.application, reason=form.cleaned_data["reason"])
    title = SiteSettings.load().outreach_title
    if result == services.DONE:
        messages.success(request, f"Added to {title}.")
    elif result == services.ALREADY:
        messages.info(request, f"Already on {title}.")
    else:
        messages.error(request, "Could not add this person.")
    return redirect(target.page_url)


@editor
@require_POST
def message_send(request, pk, kind):
    """The Email button on a lead, person or Gold page: a plain text email from the logged-in person, queued, kept for the timeline. On a Gold page the first one marks New as Contacted."""
    target = tools.target_for(kind, pk)
    form = MessageForm(request.POST)
    if not form.is_valid():
        messages.error(request, " ".join(_errors(form)))
        return redirect(target.page_url)
    blocked = services.email_block(target.main)
    if blocked:
        messages.error(request, f"Not sent. {blocked}")
        return redirect(target.page_url)
    result, message = services.send_message(request.user, target.main, form.cleaned_data["message"])
    if result == services.DUPLICATE:
        messages.info(request, "That message was already sent.")
    elif result != services.DONE:
        messages.error(request, "The email could not be sent.")
    elif message.status == message.FAILED:
        messages.error(request, "The email could not be sent. It shows as failed in the timeline.")
    else:
        messages.success(request, "Your email is on its way. It is in the timeline.")
        if kind == "gold":
            gold_actions.whatsapp_sent(target.application, request.user, message.text, via="email")  # first contact: New becomes Contacted, once
    return redirect(target.page_url)


def _back(request, default):
    """Where to go after an action posted from a list row: the page's own `next` (a path on this site), else `default`."""
    from django.utils.http import url_has_allowed_host_and_scheme

    asked = request.POST.get("next", "")
    return asked if asked.startswith("/") and url_has_allowed_host_and_scheme(asked, allowed_hosts={request.get_host()}) else default


@editor
@require_POST
def lead_archive(request, pk):
    """Archive a lead (R6): out of Leads, its counts and the next-morning email. POST reason (optional, 300). Redirects to Leads (or `next`)."""
    target = tools.target_for("lead", pk)
    if target.kind != "lead":  # he has an account now: he is a Registered person and there is nothing to archive
        return redirect(target.page_url)
    form = ArchiveForm(request.POST)
    if not form.is_valid():
        messages.error(request, " ".join(_errors(form)))
        return redirect(_back(request, target.page_url))
    result, _ = services.archive_lead(target.main, request.user, form.cleaned_data["reason"])
    if result == services.DONE:
        messages.success(request, "Lead archived.")
    elif result == services.ALREADY:
        messages.info(request, "He is already archived.")
    else:
        messages.error(request, "Could not archive this lead.")
    return redirect(_back(request, reverse("office_leads")))


@editor
@require_POST
def lead_unarchive(request, pk):
    target = tools.target_for("lead", pk)
    if target.kind != "lead":
        return redirect(target.page_url)
    if services.unarchive_lead(target.main, request.user) == services.DONE:
        messages.success(request, "Moved back to Leads.")
    else:
        messages.info(request, "He was not archived.")
    return redirect(_back(request, target.page_url))


@editor
@require_POST
def lead_email(request, pk):
    """Change a lead's email (a typo, or a new address he gave), after a bounce or not. POST email. Refused, saying whose it is, when another lead or an account has it."""
    target = tools.target_for("lead", pk)
    if target.kind != "lead":
        return redirect(target.page_url)
    result, info = services.correct_lead_email(target.main, request.POST.get("email", ""), request.user)
    if result == services.DONE:
        messages.success(request, "Email changed.")
    elif result == services.UNCHANGED:
        messages.info(request, "That is the address he already has.")
    elif result == services.TAKEN:
        who = {"account": info["name"], "gold": f"a Gold application ({info['name']})", "archived": "an archived lead", "chat": "a WhatsApp chat"}.get(info["kind"], f"another lead ({info['name']})")
        messages.error(request, f"That address already belongs to {who}.")
    elif result == services.INVALID:
        messages.error(request, info)
    else:
        messages.error(request, "Could not correct this email.")
    return redirect(target.page_url)


@editor
@require_POST
def lead_resend(request, pk):
    """Send the next-morning email to his (corrected) address now, once."""
    target = tools.target_for("lead", pk)
    if target.kind != "lead":
        return redirect(target.page_url)
    result, info = services.resend_follow_up(target.main, request.user)
    if result == services.SENT:
        messages.success(request, "Follow-up sent.")
    elif result == services.BOUNCED:
        messages.error(request, "That address still bounces, so nothing was sent. Correct it first.")
    elif result == services.ALREADY:
        messages.info(request, "The follow-up already went to this address.")
    else:
        messages.error(request, f"The follow-up was not sent ({info or 'try again'}).")
    return redirect(target.page_url)


# ---------- the approach list page ----------

STATES = listing.STATES


@reader
@require_GET
@never_cache
def outreach_page(request):
    """Context: rows[{id, name, email, mobile, source, href, reason, emailed_at, bounced, is_lead, added_by, added_at, done_at, done_by, done_url, remove_url, to_leads_url, archive_url}], has_next, page,
    state (open|done), states, tabs[{state, count, url, active}], counts{open, done}, open_count, done_count, emailed (the Emailed filter, "1" or ""), columns (the sortable header, see common.sorting),
    sort, dir, more_url, title, can_edit, section. Registering takes someone off the list by itself: there is no Registered tab. A fragment request (HX-Request) answers the rows only; ?page=N loads more."""
    state = listing.state_from(request.GET)
    sort, direction = listing.sort_from(request.GET, state)
    emailed = "1" if request.GET.get("emailed") == "1" else ""
    page = lists.page_number(request)
    found, has_next = lists.cut(listing.queryset(state, sort, direction, bool(emailed)), page, 25)
    counts = listing.counts()
    tabs = [{"state": name, "count": counts[name], "active": name == state, "url": f"{reverse('office_outreach')}?{urlencode({'state': name, **({'emailed': '1'} if emailed else {})})}"} for name in STATES]
    more = urlencode({"state": state, "sort": sort, "dir": direction, "page": page + 1, **({"emailed": "1"} if emailed else {})})
    context = {"rows": tools.outreach_rows(found), "has_next": has_next, "page": page, "state": state, "states": STATES, "tabs": tabs, "counts": counts, "emailed": emailed,
               "title": SiteSettings.load().outreach_title, "section": "outreach", "can_edit": request.user.is_authenticated and tools.can_edit(request.user),
               "open_count": counts["open"], "done_count": counts["done"],
               "columns": sorting.header_columns(listing.columns(state), sort, direction, request.path, request.GET), "sort": sort, "dir": direction,
               "more_url": f"{request.path}?{more}"}
    response = render(request, "office/_outreach_rows.html" if request.headers.get("HX-Request") else "office/outreach.html", context)
    patch_vary_headers(response, ["HX-Request"])
    return response


@editor
@require_POST
def outreach_done(request, pk):
    entry = get_object_or_404(OutreachEntry, pk=pk)
    services.mark_done(entry, request.user)
    messages.success(request, "Marked done.")
    return redirect("office_outreach")


@editor
@require_POST
def outreach_remove(request, pk):
    services.remove_entry(get_object_or_404(OutreachEntry, pk=pk))
    messages.success(request, "Removed.")
    return redirect("office_outreach")


def _list_reply(request, ok, message, **extra):
    """A fetch (X-Requested-With: fetch, or Accept: application/json) gets {ok, message, ...}; otherwise a toast and back to the list."""
    if request.headers.get("x-requested-with") == "fetch" or "application/json" in request.headers.get("accept", ""):
        return JsonResponse({"ok": ok, "message": message, **extra}, status=200 if ok else 400)
    (messages.success if ok else messages.error)(request, message)
    return redirect("office_outreach")


@editor
@require_POST
def outreach_to_leads(request, pk):
    """Back to Leads: a lead entry comes off the list and he shows in Leads again. No confirm: the answer carries `undo` = {url, reason} (POST url with reason puts him back on the list)."""
    entry = get_object_or_404(OutreachEntry, pk=pk)
    result, email, reason = services.entry_to_leads(entry)
    if result != services.DONE:
        return _list_reply(request, False, "Only a lead can go back to Leads.")
    return _list_reply(request, True, "Moved back to Leads.", undo={"url": reverse("office_outreach_undo_move"), "email": email, "reason": reason, "archived": False})


@editor
@require_POST
def outreach_archive(request, pk):
    """Archive from the list: the lead is archived (POST reason, optional, 300) and leaves the list. The answer carries `undo` (see outreach_to_leads)."""
    entry = get_object_or_404(OutreachEntry, pk=pk)
    form = ArchiveForm(request.POST)
    if not form.is_valid():
        return _list_reply(request, False, " ".join(_errors(form)))
    reason = entry.reason
    result, email = services.entry_archive(entry, request.user, form.cleaned_data["reason"])
    if result not in (services.DONE, services.ALREADY):
        return _list_reply(request, False, "Only a lead can be archived from here.")
    return _list_reply(request, True, "Archived.", undo={"url": reverse("office_outreach_undo_move"), "email": email, "reason": reason, "archived": True})


@editor
@require_POST
def outreach_undo_move(request):
    """Undo Back to Leads or Archive: POST email, reason, archived ("1" when he was archived): he comes back from Archived if needed and goes back on the list with the same reason."""
    email = (request.POST.get("email") or "").strip().lower()
    if request.POST.get("archived") in ("1", "true", "yes"):
        services.unarchive_lead(email, request.user)
    result, _ = services.add_to_list(request.user, lead_email=email, reason=request.POST.get("reason", ""))
    ok = result in (services.DONE, services.ALREADY)
    return _list_reply(request, ok, "Back on the list." if ok else "He could not be put back on the list.")


# ---------- adding or fixing a number (the Details rows) and marking a Gold application Contacted ----------

def _contact_reply(request, target, result, errors):
    """The Details dialog (fetch) gets 200 with {ok, result, errors{field: text, owner{name, url}}}; any other POST a toast and back to the page."""
    ok = result in (services.DONE, services.UNCHANGED)
    if request.headers.get("accept", "").startswith("application/json") or request.headers.get("x-requested-with") == "fetch":
        return JsonResponse({"ok": ok, "result": result, "errors": errors}, status=200 if ok or request.headers.get("x-requested-with") == "fetch" else 400)
    if ok:
        messages.success(request, "Saved." if result == services.DONE else "Nothing changed.")
    else:
        messages.error(request, " ".join(v for k, v in errors.items() if k != "owner"))
    return redirect(target.page_url)


def _contact_form(request, target):
    """(data, early reply): the validated ContactForm, or the reply to give when it is invalid."""
    form = ContactForm(request.POST)
    if not form.is_valid():
        return None, _contact_reply(request, target, services.INVALID, {"mobile": "That doesn't look like a valid mobile number."})
    return form.cleaned_data, None


@editor
@require_POST
def lead_contact(request, pk):
    """Add or fix a lead's first name and mobile. POST first_name, mobile_country (ISO, default GB), mobile. Blank keeps what is there."""
    target = tools.target_for("lead", pk)
    if target.kind != "lead":
        return redirect(target.page_url)
    data, early = _contact_form(request, target)
    if early:
        return early
    result, errors = services.set_lead_contact(target.main, request.user, first_name=data["first_name"] or None, mobile=data["mobile"] or None, mobile_country=data["mobile_country"])
    return _contact_reply(request, target, result, errors)


@editor
@require_POST
def person_mobile(request, pk):
    """Add or fix a registered person's mobile. POST mobile_country, mobile."""
    target = tools.target_for("person", pk)
    data, early = _contact_form(request, target)
    if early:
        return early
    if not data["mobile"]:
        return _contact_reply(request, target, services.UNCHANGED, {})
    result, errors = services.set_person_mobile(target.user, request.user, data["mobile"], data["mobile_country"])
    return _contact_reply(request, target, result, errors)


@editor
@require_POST
def gold_mobile(request, pk):
    """Add or fix a Gold applicant's mobile. POST mobile_country, mobile."""
    target = tools.target_for("gold", pk)
    data, early = _contact_form(request, target)
    if early:
        return early
    if not data["mobile"]:
        return _contact_reply(request, target, services.UNCHANGED, {})
    result, errors = services.set_gold_mobile(target.application, request.user, data["mobile"], data["mobile_country"])
    return _contact_reply(request, target, result, errors)


@editor
@require_POST
def gold_contacted(request, pk):
    """"Mark contacted" on a Gold page: New becomes Contacted, with an audit event. The WhatsApp button is a wa.me link, which cannot prove a message went, so staff say so themselves."""
    target = tools.target_for("gold", pk)
    if gold_actions.whatsapp_sent(target.application, request.user):
        messages.success(request, "Marked as contacted.")
    else:
        messages.info(request, "Nothing changed: it is not waiting for a first contact.")
    return redirect(target.page_url)
