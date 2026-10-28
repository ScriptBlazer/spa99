"""System > Assistant (Developer level, unlocked, CSRF): Overview and test console, Knowledge notes, FAQ (views_faq), Personality and rules,
Limits. Every save goes through the change log (undoable). The hard rules stay in code (chat/prompt.py, chat/services.py)."""
import json

from django.contrib import messages
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Count, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from chat import config, knowledge, services as chat_services
from chat.models import AssistantSettings, Conversation, KnowledgeNote, Message
from chat.prompt import SYSTEM_RULES, personality

from . import defaults, services
from .forms_faq import CapForm, LimitsForm, NoteForm, PersonalityForm
from .models import SiteDefaults
from .permissions import unlocked
from .views import form_status, page, saved


# ---------- overview and test console ----------

def _pounds(pence):
    return f"{pence / 100:.2f}"


@unlocked
@require_GET
def assistant(request):
    cap = SiteDefaults.load().chat_monthly_cap_gbp
    cfg = AssistantSettings.load()
    midnight = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    spent_today = Message.objects.filter(created_at__gte=midnight).aggregate(total=Sum("cost_pence"))["total"] or 0
    real = Conversation.objects.filter(staff_test=False)
    context = {
        "spent_pounds": _pounds(chat_services.spent_this_month_pence()), "cap": cap, "spent_today_pounds": _pounds(spent_today),
        "daily_cap": f"{cap * cfg.daily_cap_percent / 100:.2f}", "today": real.filter(created_at__gte=midnight).count(),
        "month": real.filter(created_at__gte=chat_services.month_start()).count(), "key_set": bool(settings.ANTHROPIC_API_KEY), "enabled": cfg.enabled,
    }
    return page(request, "system/assistant.html", "assistant", context)


@unlocked
@require_POST
def assistant_switch(request):
    """Turn the assistant on or off: the button and every chat request follow at once."""
    row = AssistantSettings.load()
    row.enabled = not row.enabled
    services.save_logged(row, request.user, fields=["enabled"])
    saved(request, "The assistant is on." if row.enabled else "The assistant is off.")
    return redirect("system_assistant")


@unlocked
@require_POST
def assistant_test(request):
    """One test turn with the live knowledge, with or without prices. Not rate limited, counted in spend, marked staff_test. JSON out."""
    text = (request.POST.get("message") or "").strip()[:1000]
    if not text or not settings.ANTHROPIC_API_KEY:
        return JsonResponse({"error": "Write a question first." if settings.ANTHROPIC_API_KEY else "No API key is set."}, status=400)
    prices = request.POST.get("prices") == "yes"
    conversation = None
    try:
        conversation = Conversation.objects.filter(pk=request.POST.get("conversation_id") or None, staff_test=True, user=request.user).first()
    except (ValidationError, ValueError):
        pass
    if conversation is None:
        conversation = Conversation.objects.create(staff_test=True, user=request.user)
    Message.objects.create(conversation=conversation, role=Message.USER, text=text)
    conversation.message_count += 1
    conversation.save(update_fields=["message_count", "updated_at"])
    conversation._force_prices = prices
    raw = "".join(chat_services.reply_events(request, conversation))
    events = []
    for block in raw.strip().split("\n\n"):
        name, data = block.split("\n", 1)
        events.append([name[7:], json.loads(data[6:])])
    knowledge_text, digest = knowledge.build(prices)
    sent = "\n\n".join([SYSTEM_RULES, personality(config.get()), knowledge_text])
    reply = "".join(d.get("text") or d.get("message", "") for name, d in events if name in ("delta", "error"))
    return JsonResponse({"conversation_id": str(conversation.pk), "text": reply, "events": events, "system": sent, "digest": digest, "prices": prices})


# ---------- knowledge notes ----------

def _notes_page(request, bound=None, status=200):
    bound = bound or {}
    rows = [{"obj": o, "form": bound.get(str(o.pk)) or NoteForm(instance=o, prefix=str(o.pk))} for o in KnowledgeNote.objects.all()]
    return page(request, "system/assistant_notes.html", "assistant", {"rows": rows, "add_form": bound.get("new") or NoteForm(prefix="new")}, status)


@unlocked
@require_GET
def notes(request):
    return _notes_page(request)


@unlocked
@require_POST
def note_save(request, pk=None):
    obj = get_object_or_404(KnowledgeNote, pk=pk) if pk else None
    key = "new" if pk is None else str(pk)
    form = NoteForm(request.POST, instance=obj, prefix=key)
    if form.is_valid():
        try:
            if services.save_form(form, request.user):
                saved(request)
            else:
                messages.info(request, "Nothing changed.")
            return redirect("system_notes")
        except ValidationError as error:
            form.add_error(None, error)
    return _notes_page(request, {key: form}, form_status(form))


# ---------- personality and limits (singletons) ----------

def _singleton_save(request, form, url_name):
    """Save a valid singleton form through the change log; True when it was handled (redirect), else the page shows the errors."""
    if form.is_valid():
        try:
            if services.save_form(form, request.user):
                config.forget(request)
                defaults.forget(request)
                saved(request)
            else:
                messages.info(request, "Nothing changed.")
            return True
        except ValidationError as error:
            form.add_error(None, error)
    return False


def _personality_context(request, form=None, status=200):
    form = form or PersonalityForm(instance=AssistantSettings.load())
    forms_ = [{"form": form, "action": "/assistant/personality/save/", "key": "personality",
               "note": "These add to the built-in rules (Spa 99 topics only, no price before an email, no code, no promises). They can never replace them."}]
    return page(request, "system/assistant_form.html", "assistant",
                {"forms": forms_, "tab": "personality", "description": "How the assistant sounds. The hard rules stay in code."}, status)


@unlocked
@require_GET
def personality_page(request):
    return _personality_context(request)


@unlocked
@require_POST
def personality_save(request):
    form = PersonalityForm(request.POST, instance=AssistantSettings.load())
    if _singleton_save(request, form, "system_personality"):
        return redirect("system_personality")
    return _personality_context(request, form, form_status(form))


def _limits_context(request, limits=None, cap=None, status=200):
    limits = limits or LimitsForm(instance=AssistantSettings.load())
    cap = cap or CapForm(instance=SiteDefaults.load())
    forms_ = [{"form": limits, "action": "/assistant/limits/save/", "key": "limits", "title": "Switch and limits", "note": "Rates apply per browser and per IP address."},
              {"form": cap, "action": "/assistant/limits/cap/", "key": "cap", "title": "Spending", "note": "The same value as System > Defaults > Website and journey."}]
    return page(request, "system/assistant_form.html", "assistant", {"forms": forms_, "tab": "limits", "description": "Switch the assistant on or off, and how much and how fast it may be used."}, status)


@unlocked
@require_GET
def limits(request):
    return _limits_context(request)


@unlocked
@require_POST
def limits_save(request):
    form = LimitsForm(request.POST, instance=AssistantSettings.load())
    if _singleton_save(request, form, "system_limits"):
        return redirect("system_limits")
    return _limits_context(request, limits=form, status=form_status(form))


@unlocked
@require_POST
def cap_save(request):
    form = CapForm(request.POST, instance=SiteDefaults.load())
    if _singleton_save(request, form, "system_limits"):
        return redirect("system_limits")
    return _limits_context(request, cap=form, status=form_status(form))
