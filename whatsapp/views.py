"""The Office side of WhatsApp: the inbox, a thread, polling, sending, mark read, starting a chat from a lead, person or Gold page, the
staff media link, and the push controls. Short views: they check, call whatsapp.services, answer. `reader` sees chats, `editor`
(approver or Admin and up) sends. The send endpoints answer JSON {ok, message?, error?} so the chat page can show a failure in place."""
import json
from datetime import datetime, timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.core.files.storage import default_storage
from django.db.models import Exists, F, OuterRef, Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import patch_vary_headers
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from office.permissions import can_edit, editor, reader

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
    rows = Message.objects.filter(contact=contact).select_related("template")
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
        "urls": {"poll": reverse("office_whatsapp_poll", args=[contact.pk]), "send": reverse("office_whatsapp_send", args=[contact.pk]),
                 "send_media": reverse("office_whatsapp_send_media", args=[contact.pk]), "send_template": reverse("office_whatsapp_send_template", args=[contact.pk]),
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
    new = list(Message.objects.filter(contact=contact, pk__gt=after).select_related("template").order_by("id")[:100])
    updates = []
    try:
        since = datetime.fromisoformat(request.GET["since"]) if request.GET.get("since") else None
    except ValueError:
        since = None
    if since is not None:
        if timezone.is_naive(since):
            since = timezone.make_aware(since)
        updates = [services.message_dict(m) for m in Message.objects.filter(contact=contact, pk__lte=after, updated_at__gt=since).select_related("template").order_by("id")[:100]]
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
    result, message = services.send_text(contact, request.user, request.POST.get("body", ""))
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
    result, message = services.send_media(contact, request.user, upload, request.POST.get("body", ""))
    if result != services.DONE:
        return _fail(result, 409 if result in (services.WINDOW_CLOSED, services.OPTED_OUT) else (413 if result == services.TOO_BIG else 400))
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
    contact = Contact.objects.filter(pk=request.GET.get("contact")).first() if request.GET.get("contact") else None
    return JsonResponse({"templates": services.template_dicts(contact)})


# ---------- files ----------

@reader
@require_GET
def media(request, pk):
    """A file in a chat, for staff. Photos and PDFs show in the page; anything else downloads."""
    message = get_object_or_404(Message.objects.exclude(media_key=""), pk=pk)
    if not default_storage.exists(message.media_key):
        raise Http404
    inline = message.media_type in ("image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf", "audio/ogg", "audio/mpeg", "audio/mp4", "audio/aac", "video/mp4")
    response = FileResponse(default_storage.open(message.media_key, "rb"), content_type=message.media_type or "application/octet-stream",
                            as_attachment=not inline, filename=message.media_filename or "file")
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, max-age=3600"
    return response


# ---------- start a chat from a lead, person or Gold page; add or fix a mobile ----------

def _start(request, kind, pk):
    from office import tools

    target = tools.target_for(kind, pk)
    mobile, _ = tools.mobile_and_name(target)
    if not mobile:
        from django.contrib import messages

        messages.info(request, "Add a mobile first, so the team can WhatsApp him.")
        return redirect(target.page_url)
    contact = services.get_or_create_contact(mobile)
    query = {}
    if kind == "gold":
        query["gold"] = str(pk)
    if not contact.last_message_at:
        query["picker"] = "1"
    return redirect(reverse("office_whatsapp_thread", args=[contact.pk]) + (f"?{urlencode(query)}" if query else ""))


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
