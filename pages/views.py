"""Public marketing pages, the journey and Gold application shells, robots.txt and the sitemap.
Every view is public on purpose (marked login_not_required). Copy comes from `content`, plans from `plans`."""
from django.contrib.auth.decorators import login_not_required
import re

from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET

from content import services as content
from journey import services as journey_services
from journey.copy import GATE as JOURNEY_GATE
from journey.models import Option, Question
from gold.models import GoldApplication
from plans.models import SiteSettings

from . import services
from .access import memberships_visible

JOURNEY_SLUGS = {1: "your-time", 2: "what-draws-you", 3: "company", 4: "about-you"}
JOURNEY_RESULT_SLUG = "your-membership"
GOLD_SLUGS = {1: "about-you", 2: "visits", 3: "you"}
GOLD_SENT_SLUG = "sent"


def _page(request, template, key, **context):
    return render(request, template, {"meta": content.page_meta(key), "page_key": key, **context})


def _time_question():
    question = Question.objects.filter(key="time", active=True).first()
    if question is None:
        return None
    options = [
        {"value": o.value, "label": services.split_label(o.label)[0], "sub": services.split_label(o.label)[1]}
        for o in Option.objects.filter(question=question, active=True).order_by("order", "value")
    ]
    return {"text": question.text, "options": options} if options else None


@login_not_required  # PUBLIC marketing page
@require_GET
def home(request):
    cards = services.purchasable_plans()
    rooms = services.room_index()
    half = (len(rooms) + 1) // 2
    gold_perks = [perk for _, perks in (services.gold_groups() or []) for perk in perks]
    return _page(request, "pages/home.html", "home", time_question=_time_question(), rooms=rooms,
                 room_groups=[g for g in (rooms[:half], rooms[half:]) if g], facts=services.hours_facts(),
                 gold_perks=gold_perks, closure=services.closure_title(),
                 lines={r["slug"].replace("-", "_"): r["line"] for r in rooms},
                 plan_cards=[c for c in cards if not c["is_single"]], single=next((c for c in cards if c["is_single"]), None))


@login_not_required  # PUBLIC marketing page
@require_GET
def spa(request):
    cards = services.facility_cards()
    copy = content.page_content("spa")
    moments = services.spa_moments(copy)
    return _page(request, "pages/spa.html", "spa", facilities=cards,
                 sections=services.place_moments(services.spa_sections(cards), moments), tote=moments.get("tote"),
                 opener_lines=services.opener_lines(copy), opener=services.opener_picture(copy),
                 arrive_kit=services.arrive_kit(copy),
                 room_count=len(cards), visit_pills=services.visit_pills(copy), next_from=services.next_from_line(copy),
                 hours=services.opening_hours(), hours_facts=services.hours_facts())


@login_not_required  # PUBLIC marketing page
@require_GET
def memberships(request):
    if not memberships_visible(request):  # hidden until opening: the journey is the way in (team members can still look)
        return redirect("journey")
    cards = services.purchasable_plans()
    gold_cta = not (request.user.is_authenticated and GoldApplication.objects.filter(user=request.user).exists())
    return _page(request, "pages/memberships.html", "memberships", cards=cards, gold_cta=gold_cta, table=services.compare_table(cards),
                 tiers=[c for c in cards if c["interest_allowed"]], single=next((c for c in cards if c["is_single"]), None),
                 selected_slug=services.selected_plan_slug(request, cards), every_visit=services.every_visit(),
                 vat_rate=SiteSettings.load().vat_rate.normalize())


@login_not_required  # PUBLIC marketing page
@require_GET
def gold_card(request):
    return _page(request, "pages/gold.html", "gold", groups=services.gold_groups(), gold=services.gold_facts(),
                 hours_facts=services.hours_facts())


@login_not_required  # PUBLIC teaser for visitors; signed-in members go to Book a visit inside My Spa 99
@require_GET
def book(request):
    if request.user.is_authenticated:
        return redirect("account_book")
    cards = services.purchasable_plans()
    return _page(request, "pages/book.html", "book", booking_lines=services.booking_lines(cards))


@login_not_required  # PUBLIC marketing page
@require_GET
def visit(request):
    return _page(request, "pages/visit.html", "visit", hours=services.opening_hours())


@login_not_required  # PUBLIC legal page
@require_GET
def privacy(request):
    return _page(request, "pages/legal.html", "privacy")


@login_not_required  # PUBLIC legal page
@require_GET
def terms(request):
    return _page(request, "pages/legal.html", "terms")


@login_not_required  # PUBLIC virtual tour (server-rendered fallback; the 3D layer is progressive)
@require_GET
def tour(request, slug=services.TOUR_LOUNGE):
    if slug == services.TOUR_LOUNGE and request.resolver_match.url_name == "tour_room":
        return redirect("tour", permanent=True)
    copy = content.page_content("tour")
    rooms = services.tour_rooms(copy)
    room = next((r for r in rooms if r["slug"] == slug), None)
    if room is None:
        raise Http404("No such room")
    meta = content.page_meta("tour")
    meta = {**meta, "title": f"{room['name']}, virtual tour"}
    return render(request, "pages/tour.html", {
        "meta": meta, "page_key": "tour", "room": room, "rooms": rooms, "copy": copy,
        "tour_config": services.tour_config(rooms, slug, copy), "stacked_logo": services.stacked_logo_svg()})


def _check_slug(slug, known):
    """Unknown screen names are a 404 (screen-N is allowed: the screens are data and can grow)."""
    if slug and slug not in known and not re.fullmatch(r"screen-\d+", slug):
        raise Http404("No such screen")


def _copy(page_key, keys):
    """Section copy as plain dicts for the scripts (json_script)."""
    sections = content.page_content(page_key)
    return {
        key: {"heading": sections[key].heading, "body": sections[key].body, "cta": sections[key].cta_label}
        for key in keys
    }


@login_not_required  # PUBLIC: the guided journey (JSON endpoints do the saving; this is the shell)
@ensure_csrf_cookie
@require_GET
def journey(request, slug=""):
    _check_slug(slug, {*JOURNEY_SLUGS.values(), JOURNEY_RESULT_SLUG})
    keys = ["screen_1", "screen_2", "screen_3", "screen_4", "result_label", "why", "result_cta", "change_answers",
            "gold_panel", "gold_line", "others", "explore_memberships", "continue", "skip", "last", "back", "prefer_not", "start_again",
            "save_error", "result_loading", "result_error", "unavailable", "not_a_fit", "optional", "last_suggestion", "need_one", "result_empty"]
    session = journey_services.session_from_cookies(request.COOKIES, request.user)
    shown = memberships_visible(request)
    config = {
        "slugs": JOURNEY_SLUGS, "resultSlug": JOURNEY_RESULT_SLUG, "base": reverse("journey"),
        "copy": _copy("journey", keys), "gate": JOURNEY_GATE, "facilityImages": services.journey_facility_images(),
        "iconSprite": static("common/img/icons.svg"),
        "lastSuggestion": journey_services.last_suggestion(session) if session is not None else None,
        "urls": {"restart": reverse("journey:restart"), "lead": reverse("journey:lead"), "privacy": reverse("privacy"), "register": reverse("register"), "goldApply": reverse("gold_apply"), "home": reverse("home"),
                 "memberships": reverse("memberships") if shown else reverse("journey"),
                 "membershipsPage": reverse("memberships")},  # the result link: he has passed the gate by then
        "membershipsHidden": not shown,
    }
    if not shown:  # Memberships is hidden: fallbacks send him back into the journey, not to a page that is not there
        again = config["copy"]["start_again"]["cta"] or "Start again"
        config["copy"]["result_empty"] = {"heading": config["copy"]["result_empty"]["heading"],
                                          "body": "Answer a few questions and we will suggest the membership that suits you.", "cta": again}
        for key in ("result_error", "unavailable"):
            config["copy"][key]["cta"] = again
    return _page(request, "pages/journey.html", "journey", journey_config=config)


@login_not_required  # PUBLIC: the Gold application (posts to /gold/apply/, no account)
@ensure_csrf_cookie
@require_GET
def gold_apply(request, slug=""):
    if slug == "property":  # step 1 was renamed to about-you (2026-10-23): keep old links working
        return redirect("gold_apply_step", slug=GOLD_SLUGS[1])
    _check_slug(slug, {*GOLD_SLUGS.values(), GOLD_SENT_SLUG})
    keys = ["screen_1", "screen_2", "screen_3", "sent", "closed"]
    config = {
        "slugs": GOLD_SLUGS, "sentSlug": GOLD_SENT_SLUG, "base": reverse("gold_apply"),
        "copy": _copy("gold-apply", keys), "open": SiteSettings.load().register_interest_open,
        "journeyCopy": _copy("journey", ["continue", "skip", "back", "prefer_not", "screen_1", "screen_2", "screen_3"]),
        "facilityImages": services.journey_facility_images(), "iconSprite": static("common/img/icons.svg"),
        "urls": {"home": reverse("home"), "privacy": reverse("privacy"), "terms": reverse("terms"),
                 "journey": reverse("journey_page", args=[JOURNEY_SLUGS[1]])},
    }
    return _page(request, "pages/gold_apply.html", "gold-apply", gold_config=config)


@login_not_required  # PUBLIC
@require_GET
def robots(request):
    lines = ["User-agent: *", "Allow: /", "Disallow: /account/", "Disallow: /journey/", "Disallow: /gold-card/apply/",
             f"Sitemap: {request.build_absolute_uri(reverse('sitemap'))}"]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")


SITEMAP_NAMES = ["home", "spa", "tour", "memberships", "gold_card", "visit", "privacy", "terms"]


@login_not_required  # PUBLIC
@require_GET
def sitemap(request):
    names = SITEMAP_NAMES if SiteSettings.load().memberships_public else [n for n in SITEMAP_NAMES if n != "memberships"]
    urls = "".join(f"<url><loc>{request.build_absolute_uri(reverse(name))}</loc></url>" for name in names)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    return HttpResponse(xml, content_type="application/xml")
