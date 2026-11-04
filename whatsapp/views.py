"""The Office side of WhatsApp: the inbox, a thread, polling, sending, mark read, starting a chat from a lead, person or Gold page, the
staff media link, and the push controls. Short views: they check, call whatsapp.services, answer. `reader` sees chats, `editor`
(approver or Admin and up) sends. The send endpoints answer JSON {ok, message?, error?} so the chat page can show a failure in place."""
import json
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.storage import default_storage
from django.db.models import Exists, F, OuterRef, Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import patch_vary_headers
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from common import ownership
from common.polling import parse_cursor
from office.permissions import admin, can_edit, editor, reader

from . import push, services
from .models import Contact, Message, PushSubscription, WhatsAppPrefs

PAGE = 30
INBOX_PAGE = 30


def _contact(pk):
    return get_object_or_404(Contact.objects.select_related("user", "application"), pk=pk)


def _fail(result, status=400, **extra):
    return JsonResponse({"ok": False, "error": result, "message": services.WORDS.get(result, "That could not be sent."), **extra}, status=status)


def _ok(message):
    return JsonResponse({"ok": True, "message": services.message_dict(message)})


# ---------- the inbox ----------

def _list_context(request):
    """The chat list: rows[{id, name, has_name, gold, phone, preview, preview_kind, direction, status, no_reply, last_message_at, unread, opted_out, window_open, url}],
    has_next, page, q, filter ("", "unread" or "noreply"), unread_total, more_url, can_send, configured."""
    q = request.GET.get("q", "").strip()
    only = "unread" if request.GET.get("unread") == "1" else ("noreply" if request.GET.get("noreply") == "1" else "")
    try:
        page = max(int(request.GET.get("page", "1")), 1)
    except ValueError:
        page = 1
    contacts = Contact.objects.exclude(last_message_at__isnull=True)
    for word in q.lower().split():
        digits = "".join(ch for ch in word if ch.isdigit())
        query = Q(name__icontains=word) | Q(profile_name__icontains=word) | Q(lead_email__icontains=word)
        contacts = contacts.filter(query | (Q(phone__contains=digits) if digits else Q(pk__in=[])))
    if only == "unread":
        contacts = contacts.annotate(ra=services._read_after(request.user, "pk")).filter(
            Exists(Message.objects.filter(contact=OuterRef("pk"), direction=Message.IN, created_at__gt=OuterRef("ra"))))
    elif only == "noreply":
        contacts = contacts.filter(last_direction=Message.OUT, last_inbound_at__isnull=True, last_message_at__lt=timezone.now() - timedelta(days=services.NO_REPLY_DAYS))
    found = list(contacts.order_by(F("last_message_at").desc(nulls_last=True), "-created_at", "-pk")[(page - 1) * INBOX_PAGE:page * INBOX_PAGE + 1])
    more = urlencode({k: v for k, v in {"q": q, "unread": "1" if only == "unread" else "", "noreply": "1" if only == "noreply" else "", "page": page + 1}.items() if v})
    return {"rows": services.inbox_rows(found[:INBOX_PAGE], request.user), "has_next": len(found) > INBOX_PAGE, "page": page, "q": q, "filter": only, "unread_only": only == "unread",
            "unread_total": services.unread_total(request.user), "more_url": f"{reverse('office_whatsapp')}?{more}", "can_send": can_edit(request.user), "configured": services.configured(),
            "section": "whatsapp"}


@reader
@require_GET
@never_cache
def inbox(request):
    """The inbox (see _list_context). ?q= (name, profile name, number, lead address), ?unread=1, ?noreply=1, ?page=. HTMX-style requests (HX-Request header) get the rows only."""
    context = _list_context(request)
    response = render(request, "whatsapp/_rows.html" if request.headers.get("HX-Request") else "whatsapp/inbox.html", context)
    patch_vary_headers(response, ["HX-Request"])
    return response


@reader
@require_GET
@never_cache
def unread(request):
    """{"unread_total": chats with unread messages} for the navigation badge and the title."""
    return JsonResponse({"unread_total": services.unread_total(request.user)})


# ---------- a thread ----------

def _page_of_messages(contact, before=None):
    rows = Message.objects.filter(contact=contact).select_related("template", "reply_to")
    if before:
        rows = rows.filter(pk__lt=before)
    found = list(rows.order_by("-id")[:PAGE + 1])  # newest first; one extra row says there are older ones
    return found[:PAGE][::-1], len(found) > PAGE


@reader
@require_GET
@never_cache
def thread(request, pk):
    """Context: contact {id, name, phone, profile_name, labels, page_url, opted_out, window{state, open, ends_at}, can_send, url, limits{body, image_bytes,
    file_bytes}}, chat_messages (NOT `messages`: that name is Django's own, which the toasts read) (the newest 30, oldest first, see services.message_dict), has_older, older_url, unread{count, first_id}, last_id, cursor
    (server time for the poll), templates (approved, with variables), gold {id, reference, status} when ?gold=<application id>, open_picker, urls{...}."""
    contact = _contact(pk)
    found, older = _page_of_messages(contact)
    count, first_id = services.first_unread(request.user, contact)
    gold = None
    if request.GET.get("gold") and contact.application_id and str(contact.application_id) == request.GET["gold"]:
        gold = {"id": str(contact.application_id), "reference": contact.application.reference, "status": contact.application.status}
    context = {
        "contact": services.contact_dict(contact, request.user, can_send=can_edit(request.user)), "chat_messages": [services.message_dict(m) for m in found],
        "has_older": older, "older_url": reverse("office_whatsapp_messages", args=[contact.pk]) + (f"?before={found[0].pk}" if found else ""),
        "unread": {"count": count, "first_id": first_id}, "last_id": found[-1].pk if found else 0, "cursor": timezone.now().isoformat(),
        "templates": services.template_dicts(contact), "gold": gold, "open_picker": request.GET.get("picker") == "1", "section": "whatsapp", "configured": services.configured(),
        "link_offer": _link_offer(request, contact),
        "urls": {"poll": reverse("office_whatsapp_poll", args=[contact.pk]), "send": reverse("office_whatsapp_send", args=[contact.pk]),
                 "send_media": reverse("office_whatsapp_send_media", args=[contact.pk]), "send_voice": reverse("office_whatsapp_send_voice", args=[contact.pk]), "send_template": reverse("office_whatsapp_send_template", args=[contact.pk]),
                 "read": reverse("office_whatsapp_read", args=[contact.pk]), "inbox": reverse("office_whatsapp"), "templates": reverse("office_whatsapp_templates") + f"?contact={contact.pk}"}}
    context.update({k: v for k, v in _list_context(request).items() if k not in context and k not in ("page", "q", "filter", "unread_only", "more_url")})
    context.update({"page": 1, "q": "", "filter": "", "more_url": reverse("office_whatsapp") + "?page=2", "selected": str(contact.pk)})
    context["wa"] = {"messages": context["chat_messages"], **{k: context[k] for k in ("contact", "has_older", "older_url", "unread", "last_id", "cursor", "templates", "gold", "open_picker", "urls", "configured")}}
    return render(request, "whatsapp/thread.html", context)


@reader
@require_GET
@never_cache
def messages_before(request, pk):
    """Older messages: ?before=<message id>. JSON {messages (oldest first), has_older, older_url}."""
    contact = _contact(pk)
    try:
        before = int(request.GET.get("before", "0")) or None
    except ValueError:
        before = None
    found, older = _page_of_messages(contact, before)
    return JsonResponse({"messages": [services.message_dict(m) for m in found], "has_older": older,
                         "older_url": reverse("office_whatsapp_messages", args=[contact.pk]) + (f"?before={found[0].pk}" if found else "")})


@reader
@require_GET
@never_cache
def poll(request, pk):
    """Short polling: ?after=<last message id seen>&since=<cursor from the last answer>. JSON {messages (new, oldest first), updates (messages
    whose tick or error changed since the cursor), contact (window and opt-out state), unread_total, last_id, cursor}. Send the cursor back next time."""
    contact = _contact(pk)
    try:
        after = int(request.GET.get("after", "0"))
    except ValueError:
        after = 0
    cursor = timezone.now()
    new = list(Message.objects.filter(contact=contact, pk__gt=after).select_related("template", "reply_to").order_by("id")[:100])
    updates = []
    since = parse_cursor(request.GET.get("since"))
    if since is not None:
        updates = [services.message_dict(m) for m in services.poll_updates(Message.objects.filter(contact=contact), after, since, cursor).select_related("template", "reply_to").order_by("id")[:100]]
    return JsonResponse({"messages": [services.message_dict(m) for m in new], "updates": updates, "contact": services.contact_dict(contact, request.user, can_send=can_edit(request.user)),
                         "unread_total": services.unread_total(request.user), "last_id": new[-1].pk if new else after, "cursor": cursor.isoformat()})


@reader
@require_POST
def read(request, pk):
    services.mark_read(_contact(pk), request.user)
    return JsonResponse({"ok": True, "unread_total": services.unread_total(request.user)})


# ---------- sending (Approver or Admin and up) ----------

def _after_send(request, contact, message):
    """On a Gold page the first message marks the application Contacted (it becomes an audit event)."""
    gold_id = request.POST.get("gold", "")
    if gold_id and contact.application_id and str(contact.application_id) == gold_id:
        from gold import actions

        actions.whatsapp_sent(contact.application, request.user, message.body)


@editor
@require_POST
def send(request, pk):
    contact = _contact(pk)
    result, message = services.send_text(contact, request.user, request.POST.get("body", ""), request.POST.get("reply_to"))
    if result != services.DONE:
        return _fail(result, 409 if result in (services.WINDOW_CLOSED, services.OPTED_OUT) else 400)
    _after_send(request, contact, message)
    return _ok(message)


@editor
@require_POST
def send_media(request, pk):
    contact = _contact(pk)
    upload = request.FILES.get("file")
    if upload is None:
        return _fail(services.BAD_FILE)
    result, message = services.send_media(contact, request.user, upload, request.POST.get("body", ""), request.POST.get("reply_to"))
    if result != services.DONE:
        return _fail(result, 409 if result in (services.WINDOW_CLOSED, services.OPTED_OUT) else (413 if result == services.TOO_BIG else 400))
    _after_send(request, contact, message)
    return _ok(message)


@editor
@require_POST
def send_voice(request, pk):
    """POST file `file` (the browser recording: audio/webm, audio/mp4 or audio/ogg, found by its first bytes), `duration` (seconds, the browser's figure), optional `reply_to`.
    Converted to OGG Opus on the server, 5 minutes at most. Same answers as send-media; 503 `voice_unavailable` when ffmpeg is missing (context `voice.available` is false then:
    hide the microphone), 413 too big, 400 `voice_too_long` or a file that is not audio."""
    contact = _contact(pk)
    upload = request.FILES.get("file")
    if upload is None:
        return _fail(services.BAD_FILE)
    result, message = services.send_voice(contact, request.user, upload, request.POST.get("duration"), request.POST.get("reply_to"))
    if result != services.DONE:
        return _fail(result, 409 if result in (services.WINDOW_CLOSED, services.OPTED_OUT) else (413 if result == services.TOO_BIG else (503 if result == services.NO_VOICE else 400)))
    _after_send(request, contact, message)
    return _ok(message)


@editor
@require_POST
def send_template(request, pk):
    """POST template=<id> and var_<key>=<text> for each variable."""
    contact = _contact(pk)
    variables = {name[4:]: value for name, value in request.POST.items() if name.startswith("var_")}
    result, message = services.send_template(contact, request.user, request.POST.get("template", ""), variables)
    if result == services.MISSING_VARIABLES:
        return _fail(result, missing=message)
    if result != services.DONE:
        return _fail(result, 409 if result == services.OPTED_OUT else 400)
    _after_send(request, contact, message)
    return _ok(message)


@editor
@require_POST
def retry(request, pk, message):
    found = get_object_or_404(Message.objects.select_related("contact", "template"), pk=message, contact_id=pk)
    result, again = services.retry(found, request.user)
    return _ok(again) if result == services.DONE else _fail(result, 409)


@reader
@require_GET
def templates(request):
    """JSON {templates: [{id, name, label, category, body, body_html, variables[{key, label, prefill}]}]} (approved `spa99_` only). ?contact=<id> pre-fills First name."""
    try:
        contact = Contact.objects.filter(pk=request.GET.get("contact")).first() if request.GET.get("contact") else None
    except (ValidationError, ValueError):  # not a UUID
        contact = None
    return JsonResponse({"templates": services.template_dicts(contact)})


# ---------- files ----------

@reader
@require_GET
def media(request, pk):
    """A file in a chat, for staff. Photos and PDFs show in the page; anything else downloads."""
    message = get_object_or_404(Message.objects.exclude(media_key=""), pk=pk)
    if not default_storage.exists(message.media_key):
        raise Http404
    inline = message.media_type in ("image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf", "audio/ogg", "audio/mpeg", "audio/mp4", "audio/aac", "video/mp4")  # audio/webm is never stored: voice notes are converted to ogg
    response = FileResponse(default_storage.open(message.media_key, "rb"), content_type=message.media_type or "application/octet-stream",
                            as_attachment=not inline, filename=message.media_filename or "file")
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, max-age=3600"
    return response


# ---------- start or open a chat from a lead, person or Gold page; link it; delete it; add or fix a mobile ----------
# The rule (common.ownership): a GET never writes. Open is a GET and only reads; Start, Link and Delete are POSTs by an editor (Delete: Admin and up).

def _target(ref):
    """The lead, person or Gold page named by `kind:id` (the `from` of a link), or None when it is not a real one."""
    from office import tools

    kind, _, pk = (ref or "").partition(":")
    if kind not in ("person", "lead", "gold"):
        return None
    try:
        return tools.target_for(kind, pk)
    except (Http404, ValidationError, ValueError):
        return None


def _links(target):
    """What a chat takes when staff link it to this page's person: his account, the lead's address or the Gold application."""
    if target.kind == "person":
        return {"user": target.user}
    return {"lead_email": target.main} if target.kind == "lead" else {"application": target.application}


def _thread_url(contact, target):
    query = {"from": f"{target.kind}:{target.pk}"}
    if target.kind == "gold":
        query["gold"] = str(target.pk)
    if not contact.last_message_at:
        query["picker"] = "1"
    return reverse("office_whatsapp_thread", args=[contact.pk]) + f"?{urlencode(query)}"


def _link_offer(request, contact):
    """{ref, name, url} for the thread's "This number isn't linked to <name>. Link it?" line: an editor, a chat nobody holds yet, reached from a page (?from=) whose person has this very number."""
    from office import tools

    target = _target(request.GET.get("from")) if can_edit(request.user) and ownership.is_unlinked(contact) else None
    if target is None or tools.mobile_and_name(target)[0] != contact.phone:
        return None
    return {"ref": f"{target.kind}:{target.pk}", "name": tools.display_name(target), "url": reverse("office_whatsapp_link", args=[contact.pk])}


@reader
@require_http_methods(["GET", "POST"])
def start(request, kind, pk):
    """GET opens his chat for reading (no write: the Gold approver email's Respond link ends here too); no chat yet says so and goes back to the page. POST (an editor) starts the chat on
    his number: a new chat takes this page's links, an existing one is opened untouched and the thread offers the link after staff have seen it."""
    from office import tools

    target = tools.target_for(kind, pk)
    mobile, _ = tools.mobile_and_name(target)
    if not mobile:
        messages.info(request, "Add a mobile first, so the team can WhatsApp him.")
        return redirect(target.page_url)
    if request.method == "POST":
        if not can_edit(request.user):
            raise PermissionDenied
        contact, _ = services.start_chat(mobile, **_links(target))
    else:
        contact = Contact.objects.filter(phone=mobile).first()
        if contact is None:
            messages.info(request, "There is no WhatsApp chat with him yet. Use Start WhatsApp chat.")
            return redirect(target.page_url)
    return redirect(_thread_url(contact, target))


def start_person(request, pk):
    return start(request, "person", pk)


def start_lead(request, pk):
    return start(request, "lead", pk)


def start_gold(request, pk):
    return start(request, "gold", pk)


@editor
@require_POST
def link(request, pk):
    """POST `from` (kind:id of the page the staff member came from): the "Link it?" button. Links an unlinked chat to that page's person, only when it is his number."""
    from office import tools

    contact = _contact(pk)
    target = _target(request.POST.get("from"))
    if target is None or tools.mobile_and_name(target)[0] != contact.phone:
        messages.error(request, "That chat could not be linked from there.")
        return redirect("office_whatsapp_thread", pk=contact.pk)
    if ownership.link(contact, **_links(target)):
        services.resolve_links(contact)
        messages.success(request, f"Linked to {tools.display_name(target)}.")
    else:
        messages.info(request, "Nothing changed: this chat is already linked.")
    return redirect(_thread_url(contact, target))


@admin
@require_POST
def delete(request, pk):
    """Erase one chat: its messages, files and queue records (UK GDPR). Admin and up (the level person delete needs); POST `confirm` must be set; audited without message text."""
    contact = _contact(pk)
    if not request.POST.get("confirm"):
        return redirect("office_whatsapp_thread", pk=contact.pk)
    counts = services.delete_chat(contact, request.user, request)
    messages.success(request, f"The chat and its {counts['whatsapp_messages']} message{'s' if counts['whatsapp_messages'] != 1 else ''} were deleted.")
    return redirect("office_whatsapp")


def _contact_reply(request, target, result, errors):
    from django.contrib import messages

    from outreach import services as outreach

    ok = result in (outreach.DONE, outreach.UNCHANGED)
    if request.headers.get("accept", "").startswith("application/json") or request.headers.get("x-requested-with") == "fetch":
        # the page's own dialog (X-Requested-With: fetch) gets 200 with ok false, so a wrong number never shows as a failed request in the browser console
        return JsonResponse({"ok": ok, "result": result, "errors": errors}, status=200 if ok or request.headers.get("x-requested-with") == "fetch" else 400)
    if ok:
        messages.success(request, "Saved." if result == outreach.DONE else "Nothing changed.")
    else:
        messages.error(request, " ".join(v for k, v in errors.items() if k != "owner"))
    return redirect(target.page_url)


@editor
@require_POST
def lead_contact(request, pk):
    """Add or fix a lead's first name and mobile. POST first_name, mobile_country (ISO, default GB), mobile. Answers JSON when asked
    (Accept: application/json): {ok, result, errors{field: text, owner{name, url}}}; else a toast and back to the page."""
    from office import tools
    from office.forms import ContactForm
    from outreach import services as outreach

    target = tools.target_for("lead", pk)
    if target.kind != "lead":
        return redirect(target.page_url)
    form = ContactForm(request.POST)
    if not form.is_valid():
        return _contact_reply(request, target, outreach.INVALID, {"mobile": "That doesn't look like a valid mobile number."})
    data = form.cleaned_data
    result, errors = outreach.set_lead_contact(target.main, request.user, first_name=data["first_name"] if "first_name" in request.POST else None,
                                               mobile=data["mobile"] if "mobile" in request.POST else None, mobile_country=data["mobile_country"])
    return _contact_reply(request, target, result, errors)


@editor
@require_POST
def person_mobile(request, pk):
    """Add or fix a registered person's mobile. POST mobile_country (ISO, default GB), mobile. Same answers as lead_contact."""
    from office import tools
    from office.forms import ContactForm
    from outreach import services as outreach

    target = tools.target_for("person", pk)
    form = ContactForm(request.POST)
    if not form.is_valid():
        return _contact_reply(request, target, outreach.INVALID, {"mobile": "That doesn't look like a valid mobile number."})
    result, errors = outreach.set_person_mobile(target.user, request.user, form.cleaned_data["mobile"], form.cleaned_data["mobile_country"])
    return _contact_reply(request, target, result, errors)


@editor
@require_POST
def gold_mobile(request, pk):
    """Add or fix a Gold applicant's mobile. POST mobile_country (ISO, default GB), mobile. Same answers as lead_contact."""
    from office import tools
    from office.forms import ContactForm
    from outreach import services as outreach

    target = tools.target_for("gold", pk)
    form = ContactForm(request.POST)
    if not form.is_valid():
        return _contact_reply(request, target, outreach.INVALID, {"mobile": "That doesn't look like a valid mobile number."})
    result, errors = outreach.set_gold_mobile(target.application, request.user, form.cleaned_data["mobile"], form.cleaned_data["mobile_country"])
    return _contact_reply(request, target, result, errors)


# ---------- push controls (this staff member's devices) ----------

def _json_body(request):
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


@reader
@require_GET
@never_cache
def push_config(request):
    """{configured, vapid_public_key, muted, devices (this person's subscribed devices), urls{subscribe, unsubscribe, mute, test}}."""
    return JsonResponse(push_state(request.user))


def push_state(user):
    prefs = WhatsAppPrefs.objects.filter(user=user).first()
    return {"configured": push.configured(), "vapid_public_key": settings.VAPID_PUBLIC_KEY if push.configured() else "", "muted": bool(prefs and prefs.muted),
            "devices": PushSubscription.objects.filter(user=user).count(),
            "urls": {"subscribe": reverse("office_push_subscribe"), "unsubscribe": reverse("office_push_unsubscribe"), "mute": reverse("office_push_mute"), "test": reverse("office_push_test")}}


@reader
@require_POST
def push_subscribe(request):
    """JSON {endpoint, keys: {p256dh, auth}}. One row per endpoint; subscribing again (or from another account on the same device) just takes it over."""
    data = _json_body(request)
    keys = (data or {}).get("keys") or {}
    endpoint = str((data or {}).get("endpoint") or "")
    if not (endpoint.startswith("https://") and len(endpoint) <= 700 and keys.get("p256dh") and keys.get("auth")):
        return JsonResponse({"ok": False, "message": "That subscription is not valid."}, status=400)
    PushSubscription.objects.update_or_create(endpoint=endpoint, defaults={"user": request.user, "p256dh": str(keys["p256dh"])[:200], "auth": str(keys["auth"])[:100],
                                                                           "user_agent": request.META.get("HTTP_USER_AGENT", "")[:300]})
    return JsonResponse({"ok": True})


@reader
@require_POST
def push_unsubscribe(request):
    data = _json_body(request) or {}
    PushSubscription.objects.filter(user=request.user, endpoint=str(data.get("endpoint") or "")).delete()
    return JsonResponse({"ok": True})


@reader
@require_POST
def push_mute(request):
    """JSON {muted: true|false}: mute (or unmute) every device of this person."""
    data = _json_body(request)
    if data is None or not isinstance(data.get("muted"), bool):
        return JsonResponse({"ok": False}, status=400)
    WhatsAppPrefs.objects.update_or_create(user=request.user, defaults={"muted": data["muted"]})
    return JsonResponse({"ok": True, "muted": data["muted"]})


@reader
@require_POST
def push_test(request):
    return JsonResponse({"ok": True, "sent": push.send_test(request.user)})
