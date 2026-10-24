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

from . import demo, plan, present

# key, label, url name, icon. The first four are also the phone's bottom tabs; the rest live under "More".
NAV = [("overview", "Overview", "control_overview", "map-trifold"), ("rooms", "Rooms", "control_rooms", "squares-four-r"),
       ("music", "Music", "control_music", "music-notes"), ("screens", "Screens", "control_screens", "monitor-r"),
       ("schedule", "Schedule", "control_schedule", "calendar-blank-r"), ("library", "Library", "control_library", "film-strip")]
TITLES = {"overview": "Overview", "rooms": "Rooms", "music": "Music", "screens": "Screens", "schedule": "Schedule",
          "library": "Library", "password": "Change password"}
admin_only = level_required(levels.ADMIN, deny=Http404)  # a plain 404 for anyone else (sign-in is enforced before this)


def _person(user):
    name = user.get_full_name() or user.email
    letters = [part[0] for part in (user.first_name, user.last_name) if part] or [user.email[:1]]
    return {"name": name, "initials": "".join(letters[:2]).upper(), "level": levels.LABELS[levels.level_of(user)]}


def _status_sentence(state):
    people = state["people"]
    if not state["open"]:
        return f"Closed. Opens at {state['opens_at']}."
    guests = "1 guest in" if people == 1 else f"{people} guests in"
    if people >= state["capacity"] - 2:
        return f"Nearly full. {guests}."
    return f"{state['hours_line']}. {guests}."


def _zone_rows(state):
    """What each zone plays at the start (DEMO values), so the page reads without JavaScript."""
    rows = []
    for zone in state["zones"]:
        start = state["zone_start"].get(zone["id"])
        playlist = next((p for p in state["spotify"] if start and p["id"] == start[0]), None)
        track = playlist["tracks"][start[1]] if playlist else None
        rows.append({"id": zone["id"], "name": zone["name"], "rooms": zone["rooms"], "playing": bool(track),
                     "title": track["title"] if track else "", "artist": track["artist"] if track else "",
                     "source": f"Spotify, {playlist['name']}" if playlist else "", "field": playlist["field"] if playlist else 0,
                     "state": "Playing" if track else "Off"})
    return rows


def _plan(state):
    by_slug = {r["slug"]: r for r in state["rooms"]}
    out = {}
    for key, phone in (("desktop", False), ("phone", True)):
        drawing = plan.build(phone)
        for shape in drawing["shapes"]:
            room = by_slug.get(shape["slug"]) if shape["slug"] else None
            shape["room"] = room
            if room:
                shape["aria"] = present.plan_aria(shape["name"], room)
        out[key] = drawing
    return out


def _context(request, section):
    state = demo.demo_state()
    screens = state["screens"]
    for room in state["rooms"]:
        room["v"] = present.room_view(room, state, screens, state["alerts"])
    for screen in screens:
        screen["room_name"] = next(r["name"] for r in state["rooms"] if r["slug"] == screen["room"])
        screen["effective"] = present.effective_slide(screen)
        screen["label"] = present.screen_text(screen)
    people = state["people"]
    nearly_full = people >= state["capacity"] - 2
    return {
        "section": section, "title": f"DEMO · {TITLES[section]} · Control", "page_title": TITLES[section], "nav": NAV,
        "nav_phone": NAV[:4], "nav_more": NAV[4:], "state": state,
        "person": _person(request.user), "office_url": settings.OFFICE_URL, "alert_count": len(state["alerts"]),
        "strip": {"people": people, "bands": people, "lockers": round(people * 1.2), "nearly_full": nearly_full and state["open"],
                  "closed": not state["open"]},
        "sentence": _status_sentence(state), "zone_rows": _zone_rows(state),
        "scenes": [s for s in state["scenes"] if not s.get("hidden")],
        "active": next(s for s in state["scenes"] if s["key"] == state["active_scene"]),
        "options": state["screen_options"], "blank_screen": {"id": "__id__", "effective": "off", "notice": ""},
    }


def _json_state(context):
    """The part of the state the browser needs: without the server-only display strings."""
    state = dict(context["state"])
    state["rooms"] = [{**{k: v for k, v in room.items() if k != "v"}, "photo": room["v"]["photo_urls"], "lamps": room["v"]["lamps"]}
                      for room in state["rooms"]]
    state["screens"] = [{k: screen[k] for k in ("id", "name", "room", "show", "power", "loop", "playing", "notice")} for screen in state["screens"]]
    return state


def _render(request, template, section, **extra):
    context = _context(request, section)
    context["json_state"] = _json_state(context)
    return render(request, template, {**context, **extra})


def _open_room(context, request):
    slug = request.GET.get("room", "")
    return next((r for r in context["state"]["rooms"] if r["slug"] == slug), None)


@admin_only
@require_GET
def overview(request):
    context = _context(request, "overview")
    context["json_state"] = _json_state(context)
    return render(request, "control/overview.html", {**context, "plan": _plan(context["state"]), "open_room": _open_room(context, request)})


@admin_only
@require_GET
def rooms(request):
    context = _context(request, "rooms")
    context["json_state"] = _json_state(context)
    return render(request, "control/rooms.html", {**context, "open_room": _open_room(context, request)})


@admin_only
@require_GET
def music(request):
    return _render(request, "control/music.html", "music")


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
