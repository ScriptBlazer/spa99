"""The four rule sections: Plans and pricing, Hours and closures, Gold rules, Journey. Each page lists the rows as small
forms (prefix = the row id, so ids never clash); a POST saves one row through services.save_form (so the change log and
undo cover it) and, on an error, shows the same page with the field errors (400). `risky_fields` names the fields the
page should confirm (old -> new) before sending."""
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect

from gold.models import GoldRule
from journey.models import Option, Question, SuggestionRule
from plans.models import Closure, OpeningRule, Plan, SiteSettings

from . import forms_rules as f
from . import services
from .permissions import unlocked
from .views import page
from django.views.decorators.http import require_GET, require_POST


def _rows(queryset, form_class, bound):
    return [{"obj": o, "form": bound.get(str(o.pk)) or form_class(instance=o, prefix=str(o.pk))} for o in queryset]


def _add(form_class, bound, key="new", **kwargs):
    return bound.get(key) or form_class(prefix=key, **kwargs)


def _save(request, model, form_class, pk, key, url_name, build, **kwargs):
    """Shared POST: pk None = add. Valid: save through the log and redirect; invalid: the page again with errors."""
    obj = get_object_or_404(model, pk=pk) if pk else None
    form = form_class(request.POST, instance=obj, prefix=key, **kwargs)
    if form.is_valid():
        try:
            messages.success(request, "Saved." if services.save_form(form, request.user) else "Nothing changed.")
            return redirect(url_name)
        except ValidationError as error:  # a rule only the whole row can check
            form.add_error(None, error)
    return build(request, {key: form}, 400)


# ---------- plans ----------

def _plans(request, bound=None, status=200):
    bound = bound or {}
    context = {"rows": _rows(Plan.objects.all(), f.PlanForm, bound), "add_form": _add(f.PlanAddForm, bound),
               "vat_rate": SiteSettings.load().vat_rate, "risky_fields": f.RISKY["plans"]}
    return page(request, "system/plans.html", "plans", context, status)


@require_GET
@unlocked
def plans(request):
    return _plans(request)


@require_POST
@unlocked
def plan_save(request, pk=None):
    return _save(request, Plan, f.PlanAddForm if pk is None else f.PlanForm, pk, "new" if pk is None else str(pk), "system_plans", _plans)


@require_POST
@unlocked
def plan_visibility(request, pk):
    plan = get_object_or_404(Plan, pk=pk)
    services.toggle_visible(plan, request.user, request.POST.get("visible") == "1")
    messages.success(request, "Saved.")
    return redirect("system_plans")


# ---------- hours and closures ----------

def _hours(request, bound=None, status=200):
    bound = bound or {}
    context = {
        "rules": _rows(OpeningRule.objects.all(), f.OpeningRuleForm, bound), "rule_add_form": _add(f.OpeningRuleAddForm, bound, "new-rule"),
        "closures": _rows(Closure.objects.all(), f.ClosureForm, bound), "closure_add_form": _add(f.ClosureForm, bound, "new-closure"),
        "capacity_form": bound.get("capacity") or f.CapacityForm(instance=SiteSettings.load(), prefix="capacity"),
        "risky_fields": f.RISKY["hours"],
    }
    return page(request, "system/hours.html", "hours", context, status)


@require_GET
@unlocked
def hours(request):
    return _hours(request)


@require_POST
@unlocked
def rule_save(request, pk=None):
    key = "new-rule" if pk is None else str(pk)
    return _save(request, OpeningRule, f.OpeningRuleAddForm if pk is None else f.OpeningRuleForm, pk, key, "system_hours", _hours)


@require_POST
@unlocked
def closure_save(request, pk=None):
    return _save(request, Closure, f.ClosureForm, pk, "new-closure" if pk is None else str(pk), "system_hours", _hours)


@require_POST
@unlocked
def closure_delete(request, pk):
    services.delete_logged(get_object_or_404(Closure, pk=pk), request.user)
    messages.success(request, "Closure deleted (kept in the change log).")
    return redirect("system_hours")


@require_POST
@unlocked
def capacity_save(request):
    return _save(request, SiteSettings, f.CapacityForm, SiteSettings.load().pk, "capacity", "system_hours", _hours)


# ---------- Gold rules ----------

def _gold(request, bound=None, status=200):
    bound = bound or {}
    context = {"rows": _rows(GoldRule.objects.all(), f.GoldRuleForm, bound), "add_form": _add(f.GoldRuleAddForm, bound),
               "risky_fields": f.RISKY["gold"]}
    return page(request, "system/gold.html", "gold", context, status)


@require_GET
@unlocked
def gold(request):
    return _gold(request)


@require_POST
@unlocked
def gold_save(request, pk=None):
    return _save(request, GoldRule, f.GoldRuleAddForm if pk is None else f.GoldRuleForm, pk, "new" if pk is None else str(pk), "system_gold", _gold)


# ---------- journey ----------

def _journey(request, bound=None, status=200):
    bound = bound or {}
    questions = []
    for question in Question.objects.prefetch_related("options"):
        questions.append({
            "obj": question, "form": bound.get(str(question.pk)) or f.QuestionForm(instance=question, prefix=str(question.pk)),
            "options": _rows(question.options.all(), f.OptionForm, bound),
            "add_form": bound.get(f"new-{question.pk}") or f.OptionAddForm(prefix=f"new-{question.pk}"),
        })
    context = {"questions": questions, "suggestion_rules": _rows(SuggestionRule.objects.all(), f.SuggestionRuleForm, bound),
               "plan_slugs": list(Plan.objects.values_list("slug", flat=True)), "risky_fields": f.RISKY["journey"]}
    return page(request, "system/journey.html", "journey", context, status)


@require_GET
@unlocked
def journey(request):
    return _journey(request)


@require_POST
@unlocked
def question_save(request, pk):
    return _save(request, Question, f.QuestionForm, pk, str(pk), "system_journey", _journey)


@require_POST
@unlocked
def option_save(request, pk):
    return _save(request, Option, f.OptionForm, pk, str(pk), "system_journey", _journey)


@require_POST
@unlocked
def option_add(request, question_pk):
    question = get_object_or_404(Question, pk=question_pk)
    form = f.OptionAddForm(request.POST, prefix=f"new-{question.pk}", instance=Option(question=question))
    if form.is_valid():
        try:
            services.save_form(form, request.user)
            messages.success(request, "Saved.")
            return redirect("system_journey")
        except ValidationError as error:
            form.add_error(None, error)
    return _journey(request, {f"new-{question.pk}": form}, 400)


@require_POST
@unlocked
def suggestion_save(request, pk):
    return _save(request, SuggestionRule, f.SuggestionRuleForm, pk, str(pk), "system_journey", _journey)
