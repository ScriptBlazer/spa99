"""Control demo pages (docs/features/control.md). GET only, nothing is saved on the server: the state is printed into the
page once and control.js owns it after that (browser storage). Admin level and up; everyone else gets a plain 404."""
from django.conf import settings
from django.http import Http404
from django.views.decorators.http import require_GET

from common import levels
from common.permissions import level_required
from django.shortcuts import render
from django.utils.decorators import method_decorator
from users import views as user_views

from . import demo, present

NAV = [("rooms", "Rooms", "control_rooms", "squares-four"), ("schedule", "Schedule", "control_schedule", "calendar-blank"),
       ("screens", "Screens", "control_screens", "monitor"),
       ("library", "Library", "control_library", "speaker-high")]
TITLES = {"rooms": "Rooms", "schedule": "Schedule", "screens": "Screens", "library": "Library", "password": "Change password"}
admin_only = level_required(levels.ADMIN, deny=Http404)  # a plain 404 for anyone else (sign-in is enforced before this)


def _person(user):
    name = user.get_full_name() or user.email
    letters = [part[0] for part in (user.first_name, user.last_name) if part] or [user.email[:1]]
    return {"name": name, "initials": "".join(letters[:2]).upper(), "level": levels.LABELS[levels.level_of(user)]}


def _context(request, section):
    state = demo.demo_state()
    screens = state["screens"]
    for room in state["rooms"]:
        room["v"] = present.room_view(room, state, screens, state["alerts"])
    for screen in screens:
        screen["room_name"] = next(r["name"] for r in state["rooms"] if r["slug"] == screen["room"])
        screen["effective"] = present.effective_content(screen)
        screen["label"] = present.SCREEN_LABEL[screen["effective"]]
    people = state["people"]
    nearly_full = people >= state["capacity"] - 2
    return {
        "section": section, "title": f"DEMO · {TITLES[section]} · Control", "nav": NAV, "state": state,
        "person": _person(request.user), "office_url": settings.OFFICE_URL, "alert_count": len(state["alerts"]),
        "strip": {"people": people, "bands": people, "lockers": round(people * 1.2), "nearly_full": nearly_full and state["open"],
                  "closed": not state["open"]},
        "scenes": [s for s in state["scenes"] if not s.get("hidden")],
        "active": next(s for s in state["scenes"] if s["key"] == state["active_scene"]),
        "options": state["screen_options"], "blank_screen": {"id": "__id__", "effective": "off", "notice": ""},
    }


def _json_state(context):
    """The part of the state the browser needs: without the server-only display strings."""
    state = dict(context["state"])
    state["rooms"] = [{k: v for k, v in room.items() if k != "v"} for room in state["rooms"]]
    state["screens"] = [{k: screen[k] for k in ("id", "name", "room", "content", "power", "notice")} for screen in state["screens"]]
    return state


def _render(request, template, section, **extra):
    context = _context(request, section)
    context["json_state"] = _json_state(context)
    return render(request, template, {**context, **extra})


@admin_only
@require_GET
def rooms(request):
    context = _context(request, "rooms")
    slug = request.GET.get("room", "")
    chosen = next((r for r in context["state"]["rooms"] if r["slug"] == slug), None)
    context["json_state"] = _json_state(context)
    return render(request, "control/rooms.html", {**context, "open_room": chosen})


@admin_only
@require_GET
def schedule(request):
    return _render(request, "control/schedule.html", "schedule")


@admin_only
@require_GET
def screens(request):
    return _render(request, "control/screens.html", "screens")


class ControlPasswordView(user_views.TeamPasswordView):
    """Change your own password (the same view the Office uses), inside the Control shell."""

    template_name = "control/password.html"

    @method_decorator(admin_only)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_context(self.request, "password"))
        context["json_state"] = _json_state(context)
        return context
