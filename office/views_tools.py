"""Views for the person tools: sticky notes, the approach list, Message and Send guide. Short: validate, call the service in
outreach.services (or gold.actions), answer. Notes answer an HTMX request with the notes partial."""
from django.contrib import messages
from urllib.parse import urlencode

from django.http import Http404
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
from .forms import ArchiveForm, MessageForm, OutreachAddForm, StickyNoteForm
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
    """Message a lead or a person: queued email from the site sender, Reply-To the contact address, kept for the timeline."""
    if kind == "gold":
        raise Http404
    target = tools.target_for(kind, pk)
    form = MessageForm(request.POST)
    if not form.is_valid():
        messages.error(request, " ".join(_errors(form)))
        return redirect(target.page_url)
    result, _ = services.send_message(request.user, target.main, form.cleaned_data["message"])
    if result == services.DONE:
        messages.success(request, "Your message is on its way. It is in the timeline.")
    elif result == services.DUPLICATE:
        messages.info(request, "That message was already sent.")
    else:
        messages.error(request, "The message could not be sent.")
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


# ---------- the approach list page ----------

STATES = listing.STATES


@reader
@require_GET
@never_cache
def outreach_page(request):
    """Context: rows[{id, name, email, mobile, source, href, reason, added_by, added_at, done_at, done_by, registered_at, done_url,
    remove_url}], has_next, page, state (open|registered|done), states, tabs[{state, count, url, active}], counts{open, registered, done},
    open_count, registered_count, done_count, columns (the sortable header, see common.sorting), sort, dir, more_url, title, can_edit, section."""
    state = listing.state_from(request.GET)
    sort, direction = listing.sort_from(request.GET, state)
    page = lists.page_number(request)
    found, has_next = lists.cut(listing.queryset(state, sort, direction), page, 25)
    counts = listing.counts()
    tabs = [{"state": name, "count": counts[name], "active": name == state, "url": f"{reverse('office_outreach')}?state={name}"} for name in STATES]
    more = urlencode({"state": state, "sort": sort, "dir": direction, "page": page + 1})
    context = {"rows": tools.outreach_rows(found), "has_next": has_next, "page": page, "state": state, "states": STATES, "tabs": tabs, "counts": counts,
               "title": SiteSettings.load().outreach_title, "section": "outreach", "can_edit": request.user.is_authenticated and tools.can_edit(request.user),
               "open_count": counts["open"], "registered_count": counts["registered"], "done_count": counts["done"],
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
