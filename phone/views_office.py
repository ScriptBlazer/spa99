"""The Calls tab on the Office host (/calls/): voicemails (default) and the call log. Any team level above Viewer; a Viewer gets 403. Short views."""
import re

from django.core.exceptions import PermissionDenied  # noqa: F401 - the guard raises it
from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from common.pagination import clamp, num_pages, pager
from office.permissions import calls as calls_only

from . import naming, services
from .models import Call

PAGE_SIZE = 30
RANGE = re.compile(r"bytes=(\d*)-(\d*)$")


def _decorate(rows):
    """Adds `display_number` (07368 912320) and `person` ({name, url, kind} or None) to each call, with two reads for the whole page."""
    rows = list(rows)
    people = services.callers(rows)
    for call in rows:
        call.display_number = naming.friendly_number(call.from_number)
        call.person = people.get(call.from_number)
    return rows


@calls_only
@require_GET
@never_cache
def call_list(request):
    """Context: section "calls", view ("voicemails" or "all"), rows (calls with display_number and person), counts {voicemails, all}, pager (common/_pagination.html),
    page, unheard (unheard voicemails; the sidebar badge is office_voicemails_unheard)."""
    view = "all" if request.GET.get("view") == "all" else "voicemails"
    queryset = Call.objects.select_related("heard_by")
    if view == "voicemails":
        queryset = queryset.filter(kind=Call.VOICEMAIL)
    total = services.capped_count(queryset)
    pages = num_pages(total, PAGE_SIZE)
    page = clamp(request.GET.get("page"), pages)
    rows = _decorate(queryset[(page - 1) * PAGE_SIZE:page * PAGE_SIZE])
    counts = {"voicemails": total if view == "voicemails" else services.capped_count(Call.objects.filter(kind=Call.VOICEMAIL)), "all": total if view == "all" else services.capped_count(Call.objects.all())}
    return render(request, "phone/call_list.html", {"section": "calls", "view": view, "rows": rows, "counts": counts, "pager": pager(page, pages, request.GET), "page": page,
                                                    "unheard": services.unheard_count()})


@calls_only
@require_GET
@never_cache
def call_detail(request, pk):
    """Context: section "calls", call (with display_number, person), audio_url (None when there is no audio yet), heard_url."""
    call = get_object_or_404(Call.objects.select_related("heard_by"), pk=pk)
    _decorate([call])
    if call.kind == Call.VOICEMAIL and not call.has_sound and not call.heard_at:  # nothing to play, so opening it is hearing it
        if services.mark_heard(call, request.user):
            call.heard_at, call.heard_by = timezone.now(), request.user
    return render(request, "phone/call_detail.html", {"section": "calls", "call": call, "audio_ready": bool(call.audio)})


def _ranged(request, call):
    """The file from storage as audio/mpeg, with Range support (Safari needs it). Files are about 1 MB, so it is read whole."""
    with call.audio.open("rb") as handle:
        data = handle.read()
    size = len(data)
    match = RANGE.match(request.headers.get("Range", ""))
    if not match or not (match.group(1) or match.group(2)):
        response = HttpResponse(data, content_type="audio/mpeg")
    else:
        start = int(match.group(1)) if match.group(1) else max(size - int(match.group(2)), 0)
        end = min(int(match.group(2)), size - 1) if match.group(1) and match.group(2) else size - 1
        if start >= size or start > end:
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{size}"
            return response
        response = HttpResponse(data[start:end + 1], status=206, content_type="audio/mpeg")
        response["Content-Range"] = f"bytes {start}-{end}/{size}"
    response["Accept-Ranges"] = "bytes"
    response["Content-Length"] = str(len(response.content))
    return response


@calls_only
@require_GET
def call_audio(request, pk):
    """The recording. On S3 a redirect to a link that lasts 5 minutes; locally the bytes (with Range). 404 when there is no audio."""
    call = get_object_or_404(Call, pk=pk)
    if not call.audio:
        raise Http404
    storage = call.audio.storage
    if getattr(storage, "bucket_name", None):
        response = HttpResponseRedirect(storage.url(call.audio.name, expire=300))
    else:
        response = _ranged(request, call)
    response["Cache-Control"] = "private, no-store"
    return response


@calls_only
@require_POST
def call_heard(request, pk):
    """Marks the voicemail heard by the first person to play it (later plays change nothing). JSON {ok, unheard} for a script, else back to the call."""
    call = get_object_or_404(Call, pk=pk)
    if call.kind == Call.VOICEMAIL:
        services.mark_heard(call, request.user)
    if "application/json" in request.headers.get("accept", "") or request.headers.get("x-requested-with") == "fetch":
        return JsonResponse({"ok": True, "unheard": services.unheard_count()})
    return redirect("office_call", pk=call.pk)
