"""The Office side of email chat: the inbox, a thread, polling, sending, a new email, searching for a person, files, his email in a sandboxed frame, and the page
buttons. Short views: they check, call emailchat.services, answer. `reader` sees, `editor` (approver or Admin and up) sends. The send endpoints answer JSON
{ok, message?, error?} so the page can show a failure in place."""
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db.models import Exists, F, OuterRef, Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import patch_vary_headers
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_POST

from common.polling import parse_cursor
from common.ratelimit import rate_limited_json
from office.permissions import can_edit, editor, reader

from . import sender as sender_mod
from . import services
from .models import Attachment, Message, Thread

PAGE = 30
INBOX_PAGE = 30


def _thread(pk):
    return get_object_or_404(Thread.objects.select_related("user", "application"), pk=pk)


def _fail(result, status=400, **extra):
    return JsonResponse({"ok": False, "error": result, "message": services.WORDS.get(result, "That could not be sent."), **extra}, status=status)


def _ok(message, **extra):
    return JsonResponse({"ok": True, "message": services.message_dict(message), **extra})


def _messages(thread):
    return Message.objects.filter(thread=thread).select_related("thread").prefetch_related("attachments")


# ---------- the inbox ----------

def _list_context(request):
    """The thread list: rows[{id, subject, name, has_name, email, preview, direction, status, last_message_at, unread, has_attachment, no_reply, gold, url}], has_next, page, q,
    filter ("", "unread" or "noreply" = Sent with no reply), unread_total, more_url, can_send, replies_to_mailbox, new_url, people_url."""
    q = request.GET.get("q", "").strip()
    only = request.GET.get("filter", "")
    only = "unread" if request.GET.get("unread") == "1" else ("noreply" if request.GET.get("noreply") == "1" else only if only in ("unread", "noreply") else "")
    try:
        page = max(int(request.GET.get("page", "1")), 1)
    except ValueError:
        page = 1
    threads = Thread.objects.exclude(last_message_at__isnull=True)
    for word in q.lower().split():
        threads = threads.filter(Q(subject__icontains=word) | Q(name__icontains=word) | Q(email__icontains=word)
                                 | Exists(Message.objects.filter(thread=OuterRef("pk"), subject__icontains=word)))
    if only == "unread":
        threads = threads.annotate(ra=services._read_after(request.user, "pk")).filter(
            Exists(Message.objects.filter(thread=OuterRef("pk"), direction=Message.IN, spam=False, created_at__gt=OuterRef("ra"))))
    elif only == "noreply":
        threads = threads.filter(last_direction=Message.OUT)
    found = list(threads.order_by(F("last_message_at").desc(nulls_last=True), "-created_at", "-pk")[(page - 1) * INBOX_PAGE:page * INBOX_PAGE + 1])
    more = urlencode({k: v for k, v in {"q": q, "filter": only, "page": page + 1}.items() if v})
    return {"rows": services.inbox_rows(found[:INBOX_PAGE], request.user), "has_next": len(found) > INBOX_PAGE, "page": page, "q": q, "filter": only,
            "unread_total": services.unread_total(request.user), "more_url": f"{reverse('office_email')}?{more}", "can_send": can_edit(request.user),
            "replies_to_mailbox": services.replies_to_mailbox(), "new_url": reverse("office_email_new"), "people_url": reverse("office_email_people"), "section": "email"}


@reader
@require_GET
@never_cache
def inbox(request):
    """The inbox. ?q= (name, address, subject), ?filter=unread|noreply, ?page=. HTMX-style requests (HX-Request header) get the rows only."""
    response = render(request, "emailchat/_rows.html" if request.headers.get("HX-Request") else "emailchat/inbox.html", _list_context(request))
    patch_vary_headers(response, ["HX-Request"])
    return response


@reader
@require_GET
@never_cache
def unread(request):
    """{"unread_total": threads with unread email} for the navigation badge."""
    return JsonResponse({"unread_total": services.unread_total(request.user)})


# ---------- a thread ----------

def _page_of_messages(thread, before=None):
    rows = _messages(thread)
    if before:
        rows = rows.filter(pk__lt=before)
    found = list(rows.order_by("-id")[:PAGE + 1])
    return found[:PAGE][::-1], len(found) > PAGE


def _urls(thread):
    pk = thread.pk
    return {"poll": reverse("office_email_poll", args=[pk]), "send": reverse("office_email_send", args=[pk]), "read": reverse("office_email_read", args=[pk]), "inbox": reverse("office_email"),
            "new": reverse("office_email_new"), "people": reverse("office_email_people")}


@reader
@require_GET
@never_cache
def thread(request, pk):
    """Context: thread {id, email, name, has_name, subject, labels, page_url, url, last_message_at, replies_to_mailbox, suppressed, reason, can_send, limits{file_bytes, send_bytes, files}},
    chat_messages (the newest 30, oldest first, see services.message_dict), sender {from, address, source, has_signature, signature_html} (who the next email goes out as), has_older, older_url, unread{count, first_id}, last_id, cursor (server time for the poll),
    reply_subject (what the subject box is filled with), gold {id, reference, status} when ?gold=<application id>, urls{poll, send, read, inbox, new, people}, plus the list context
    (rows ...) and `em` (the data the page embeds)."""
    thread_ = _thread(pk)
    found, older = _page_of_messages(thread_)
    count, first_id = services.first_unread(request.user, thread_)
    gold = None
    if request.GET.get("gold") and thread_.application_id and str(thread_.application_id) == request.GET["gold"]:
        gold = {"id": str(thread_.application_id), "reference": thread_.application.reference, "status": thread_.application.status}
    context = {"thread": services.thread_dict(thread_, can_send=can_edit(request.user)), "chat_messages": [services.message_dict(m) for m in found], "has_older": older,
               "older_url": reverse("office_email_messages", args=[thread_.pk]) + (f"?before={found[0].pk}" if found else ""), "unread": {"count": count, "first_id": first_id},
               "last_id": found[-1].pk if found else 0, "cursor": timezone.now().isoformat(), "reply_subject": services.reply_subject(thread_), "gold": gold, "urls": _urls(thread_),
               "section": "email", "replies_to_mailbox": services.replies_to_mailbox(), "sender": sender_mod.composer_info(request.user)}
    context.update({k: v for k, v in _list_context(request).items() if k not in context and k not in ("page", "q", "filter", "more_url")})
    context.update({"page": 1, "q": "", "filter": "", "more_url": reverse("office_email") + "?page=2", "selected": str(thread_.pk)})
    context["em"] = {k: context[k] for k in ("thread", "chat_messages", "has_older", "older_url", "unread", "last_id", "cursor", "reply_subject", "gold", "urls", "replies_to_mailbox")}
    return render(request, "emailchat/thread.html", context)


@reader
@require_GET
@never_cache
def messages_before(request, pk):
    """Older emails: ?before=<message id>. JSON {messages (oldest first), has_older, older_url}."""
    thread_ = _thread(pk)
    try:
        before = int(request.GET.get("before", "0")) or None
    except ValueError:
        before = None
    found, older = _page_of_messages(thread_, before)
    return JsonResponse({"messages": [services.message_dict(m) for m in found], "has_older": older,
                         "older_url": reverse("office_email_messages", args=[thread_.pk]) + (f"?before={found[0].pk}" if found else "")})


@reader
@require_GET
@never_cache
def poll(request, pk):
    """Short polling: ?after=<last message id seen>&since=<cursor from the last answer>. JSON {messages (new), updates (messages whose status changed since the cursor), thread,
    unread_total, last_id, cursor}."""
    thread_ = _thread(pk)
    try:
        after = int(request.GET.get("after", "0"))
    except ValueError:
        after = 0
    cursor = timezone.now()
    new = list(_messages(thread_).filter(pk__gt=after).order_by("id")[:100])
    updates = []
    since = parse_cursor(request.GET.get("since"))
    if since is not None:
        updates = [services.message_dict(m) for m in services.poll_updates(_messages(thread_), after, since, cursor).order_by("id")[:100]]
    return JsonResponse({"messages": [services.message_dict(m) for m in new], "updates": updates, "thread": services.thread_dict(thread_, can_send=can_edit(request.user)),
                         "unread_total": services.unread_total(request.user), "last_id": new[-1].pk if new else after, "cursor": cursor.isoformat()})


@reader
@require_POST
def read(request, pk):
    services.mark_read(_thread(pk), request.user)
    return JsonResponse({"ok": True, "unread_total": services.unread_total(request.user)})


# ---------- sending (Approver or Admin and up) ----------

def _after_send(request, thread_, message):
    """From a Gold page the first email marks the application Contacted, once (an audit event)."""
    gold_id = request.POST.get("gold", "")
    if gold_id and thread_.application_id and str(thread_.application_id) == gold_id:
        from gold import actions

        actions.whatsapp_sent(thread_.application, request.user, message.body_text, via="email")


def _uploads(request):
    return request.FILES.getlist("files") + request.FILES.getlist("file")


def _status_for(result):
    return 413 if result == services.TOO_BIG else 400


@editor
@require_POST
def send(request, pk):
    """POST `body_html` (what the editor made; cleaned on the server), `subject` (optional: blank = "Re: " and the last subject), files in `files` (several), `gold`. JSON {ok, message}
    or {ok: false, error, message}: empty, too_long, duplicate, bad_file (a type that is never sent), too_big (413)."""
    thread_ = _thread(pk)
    result, message = services.send(thread_, request.user, request.POST.get("subject", ""), request.POST.get("body_html", ""), _uploads(request))
    if result != services.DONE:
        return _fail(result, _status_for(result))
    _after_send(request, thread_, message)
    return _ok(message)


@editor
@require_POST
def retry(request, pk, message):
    found = get_object_or_404(Message.objects.select_related("thread"), pk=message, thread_id=pk)
    result, again = services.retry(found)
    return _ok(again) if result == services.DONE else _fail(result, 409)


# ---------- a new email, and finding a person ----------

def _recipient(request):
    """(address, person ref, target or None, error) from POST/GET `person` ("lead:<id>", "person:<id>", "gold:<id>") or `to` (an address)."""
    data = request.POST if request.method == "POST" else request.GET
    ref = data.get("person", "")
    if ref:
        kind, _, pk = ref.partition(":")
        if kind not in ("lead", "person", "gold"):
            return "", ref, None, services.BAD_TARGET
        from office import tools

        try:
            target = tools.target_for(kind, pk)
        except (Http404, ValidationError, ValueError):
            return "", ref, None, services.BAD_TARGET
        return services.clean_address(target.main), ref, target, None if services.clean_address(target.main) else services.BAD_ADDRESS
    address = services.clean_address(data.get("to", ""))
    return address, "", None, None if address else services.BAD_ADDRESS


def _links(target, address):
    """What a New email started from a page links its thread to (common.ownership, rule 1b): the person's account, the lead's address or the Gold application. Nothing for a typed address."""
    if target is None:
        return {}
    if target.kind == "person" and target.user is not None:
        return {"user": target.user}
    if target.kind == "gold" and target.application is not None:
        return {"application": target.application}
    return {"lead_email": address} if target.kind == "lead" else {}


@reader
@require_GET
@never_cache
def new_form(request):
    """The New email screen. ?person=lead:<id>|person:<id>|gold:<id> or ?to=<address> pre-fills the recipient. Context: recipient {email, name, person, error}, urls{create, people,
    inbox}, can_send, replies_to_mailbox, limits{...}, plus the list context (rows ...) and `em_new` (the data the page embeds). POST to `create` with `person` or `to`, `subject`, optional `body_html` and `files`."""
    address, ref, target, error = _recipient(request) if (request.GET.get("person") or request.GET.get("to")) else ("", "", None, None)
    name = ""
    if target is not None:
        name = (target.user.get_full_name() if target.user else (target.application.full_name if target.application else "")) or ""
    context = {"recipient": {"email": address, "name": name, "person": ref, "error": services.WORDS.get(error, "") if error else ""}, "can_send": can_edit(request.user),
               "urls": {"create": reverse("office_email_new"), "people": reverse("office_email_people"), "inbox": reverse("office_email")}, "replies_to_mailbox": services.replies_to_mailbox(),
               "limits": {"file_bytes": settings.EMAILCHAT_MAX_ATTACHMENT_BYTES, "send_bytes": settings.EMAILCHAT_MAX_SEND_BYTES, "files": settings.EMAILCHAT_MAX_ATTACHMENTS}, "section": "email",
               "sender": sender_mod.composer_info(request.user)}
    context.update({k: v for k, v in _list_context(request).items() if k not in context and k not in ("page", "q", "filter", "more_url")})
    context.update({"page": 1, "q": "", "filter": "", "more_url": reverse("office_email") + "?page=2", "selected": ""})
    context["em_new"] = {k: context[k] for k in ("recipient", "urls", "limits", "can_send", "replies_to_mailbox")}
    return render(request, "emailchat/new.html", context)


@editor
@require_POST
def new_create(request):
    """POST `person` or `to`, `subject` (required), optional `body_html`, `files`, `gold`. Makes a NEW thread (a person can have many) and, when there is a body or a file, sends the
    first email in it. JSON {ok, thread_url, message}; `Accept: application/json` or `X-Requested-With: fetch` gets JSON, anything else a redirect to the thread."""
    address, ref, target, error = _recipient(request)
    wants_json = request.headers.get("accept", "").startswith("application/json") or request.headers.get("x-requested-with") == "fetch"
    if error:
        return _fail(error) if wants_json else redirect(reverse("office_email_new") + "?" + urlencode({"person": ref} if ref else {}))
    result, thread_ = services.create_thread(address, request.POST.get("subject", ""), request.user, **_links(target, address))
    if result != services.DONE:
        return _fail(result)
    message = None
    if request.POST.get("body_html", "").strip() or _uploads(request):
        try:
            sent, message = services.send(thread_, request.user, thread_.subject, request.POST.get("body_html", ""), _uploads(request))
        except Exception:
            thread_.delete()  # nothing was sent: no empty thread is left behind
            raise
        if sent != services.DONE:
            thread_.delete()  # the send checks failed (empty, too big, a bad file...): a failed attempt leaves no empty thread
            return _fail(sent, _status_for(sent))
        _after_send(request, thread_, message)
    url = reverse("office_email_thread", args=[thread_.pk]) + (f"?gold={target.pk}" if target is not None and target.kind == "gold" else "")
    if not wants_json:
        return redirect(url)
    return JsonResponse({"ok": True, "thread_url": url, "message": services.message_dict(message) if message else None})


def new(request):
    """GET the New email screen (reader), POST to make the thread and send (editor): one URL."""
    return new_create(request) if request.method == "POST" else new_form(request)


@reader
@require_GET
@never_cache
@rate_limited_json("emailchat-people", 120, 60)
def people(request):
    """?q= (two letters at least). JSON {results: [{name, email, kind (the first of kinds), kinds[lead|registered|gold], person ("lead:<id>" ...), suppressed}]}, ten at most.
    Rate limited (120 a minute per address, 429 JSON beyond it): search as you type must not become a way to list everyone."""
    return JsonResponse({"results": services.search_people(request.GET.get("q", ""))})


# ---------- files and his HTML ----------

@reader
@require_GET
def file(request, pk):
    """A file on an email, for staff. Only an image or PDF whose bytes matched its type shows in the page; everything else downloads."""
    item = get_object_or_404(Attachment, pk=pk)
    if not default_storage.exists(item.key):
        raise Http404
    response = FileResponse(default_storage.open(item.key, "rb"), content_type=item.content_type if item.inline_ok else "application/octet-stream",
                            as_attachment=not item.inline_ok, filename=item.filename or "file")
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, max-age=3600"
    return response


@reader
@require_GET
@xframe_options_sameorigin  # the Office page frames it: same origin only
def frame(request, pk):
    """His email's HTML for a sandboxed iframe (<iframe sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox" src=frame_url>: no allow-scripts). Cleaned HTML only,
    outside pictures left out unless ?images=1 (staff chose Show images); `cid:` pictures come from the stored files. A strict CSP forbids scripts, forms, other frames and any
    network load except pictures when ?images=1. The header X-Blocked-Images says how many were left out."""
    message = get_object_or_404(Message.objects.select_related("thread").prefetch_related("attachments"), pk=pk, direction=Message.IN)
    if not message.body_html:
        raise Http404
    images = request.GET.get("images") == "1"
    document, blocked = services.frame_html(message, images)
    response = HttpResponse(document, content_type="text/html; charset=utf-8")
    response["Content-Security-Policy"] = services.frame_csp(images)
    response["X-Content-Type-Options"] = "nosniff"
    response["Referrer-Policy"] = "no-referrer"
    response["Cache-Control"] = "private, no-store"
    response["X-Blocked-Images"] = str(blocked)
    return response


# ---------- the page buttons: Start or Open (lead, person, Gold) ----------

def _start(request, kind, pk):
    from office import tools

    target = tools.target_for(kind, pk)
    latest = services.latest_thread(target.addresses, target.user, target.application)
    gold = f"?gold={pk}" if kind == "gold" else ""
    if latest is not None:
        return redirect(reverse("office_email_thread", args=[latest.pk]) + gold)
    return redirect(reverse("office_email_new") + "?" + urlencode({"person": f"{kind}:{pk}"}))


@reader
@require_GET
def start_person(request, pk):
    return _start(request, "person", pk)


@reader
@require_GET
def start_lead(request, pk):
    return _start(request, "lead", pk)


@reader
@require_GET
def start_gold(request, pk):
    return _start(request, "gold", pk)
