"""System > Team > a person (/team/<id>/): level, approval ticks, Office email, login email and password, on one page. Short views: the rules and the guards live in
team.py, team_account.py and approval.py (the ticks use the same code as System > Approval). Behind the unlock like every Team view. The sending address and signature
are saved by views_team_email (their old address now redirects here)."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET, require_POST

from common import levels

from . import approval as approval_service
from . import team as team_service
from . import team_account
from .permissions import unlocked
from .services import ChangeRefused
from .views import page, saved
from .views_team_email import sender_context, sender_values


def _target(pk):
    return get_object_or_404(team_service.team_queryset(), pk=pk)  # team members only; members are managed in the Office


def render_person(request, target, sender=None, status=200):
    """The page. `sender`: the Office email form as typed (a preview, or a refused value); else what is stored."""
    actor = request.user
    level = levels.held_level(target)
    context = {
        "person": target, "level": level, "level_label": levels.LABELS[level], "level_choices": team_service.level_choices(actor),
        "can_manage": levels.can_manage(actor, target), "is_self": actor.pk == target.pk, "invite_pending": not target.has_usable_password(),
        "approval": approval_service.person(actor, target), "sender": sender or sender_context(target, *sender_values(target)),
        "can_edit_email": team_service.can_edit_email(actor, target),
    }
    return page(request, "system/team_person.html", "team", context, status=status)


def _back(request, pk, action, text="Saved.", nothing="Nothing changed."):
    """Run a change; a refusal is an error message, never a crash. Always back to the person's page."""
    try:
        done = action()
        saved(request, text) if done is not False else messages.info(request, nothing)
    except ChangeRefused as error:
        messages.error(request, str(error))
    return redirect("system_team_person", pk=pk)


@unlocked
@require_GET
def team_person(request, pk):
    return render_person(request, _target(pk))


@unlocked
@require_POST
def team_person_roles(request, pk):
    """The Gold, Membership and Final approver ticks, and where Gold approval emails go."""
    target = _target(pk)
    wanted = {role: request.POST.get(role) == "1" for role in (approval_service.APPROVER, approval_service.MEMBERSHIP, approval_service.FINAL)}
    delivery = (request.POST.get("use_account_email") == "1", request.POST.get("other_email", "")) if request.POST.get("delivery") == "1" else None
    return _back(request, pk, lambda: approval_service.set_for_person(request.user, target, wanted, delivery))


@unlocked
@require_POST
def team_person_email(request, pk):
    target = _target(pk)
    return _back(request, pk, lambda: team_account.change_email(request.user, target, request.POST.get("new_email", "")),
                 "Email changed. They are signed out everywhere and both addresses were told.")


@unlocked
@require_POST
@sensitive_post_parameters("new_password", "new_password_again")
def team_person_password(request, pk):
    target = _target(pk)
    return _back(request, pk, lambda: team_account.set_password(request.user, target, request.POST.get("new_password", ""), request.POST.get("new_password_again", "")),
                 "Password set. They are signed out everywhere and have been emailed.")


@unlocked
@require_POST
def team_person_reset(request, pk):
    target = _target(pk)
    return _back(request, pk, lambda: team_account.send_reset_link(request.user, target), "A password reset link is on its way. It works for one hour.")
