"""Public marketing pages, the journey and Gold application shells, robots.txt and the sitemap.
Every view is public on purpose (marked login_not_required). Copy comes from `content`, plans from `plans`."""
from django.contrib.auth.decorators import login_not_required
import re

from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET

from content import services as content
from journey.models import Option, Question
from plans.models import SiteSettings

from . import services

JOURNEY_SLUGS = {1: "your-time", 2: "what-draws-you", 3: "company", 4: "about-you"}
JOURNEY_RESULT_SLUG = "your-membership"
GOLD_SLUGS = {1: "property", 2: "visits", 3: "you"}
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
    return _page(request, "pages/home.html", "home", time_question=_time_question(),
                 plan_cards=[c for c in cards if not c["is_single"]], single=next((c for c in cards if c["is_single"]), None))


@login_not_required  # PUBLIC marketing page
@require_GET
def spa(request):
    return _page(request, "pages/spa.html", "spa", facilities=services.facility_cards(), hours=services.opening_hours())


@login_not_required  # PUBLIC marketing page
@require_GET
def memberships(request):
    cards = services.purchasable_plans()
    return _page(request, "pages/memberships.html", "memberships", cards=cards, table=services.compare_table(cards),
                 vat_rate=SiteSettings.load().vat_rate.normalize())


@login_not_required  # PUBLIC marketing page
@require_GET
def gold_card(request):
    return _page(request, "pages/gold.html", "gold", groups=services.gold_groups())


@login_not_required  # PUBLIC placeholder: booking opens later
@require_GET
def book(request):
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
            "gold_panel", "gold_line", "others", "continue", "skip", "last", "back", "prefer_not", "start_again",
            "save_error", "result_loading", "result_error", "unavailable", "not_a_fit", "optional"]
    config = {
        "slugs": JOURNEY_SLUGS, "resultSlug": JOURNEY_RESULT_SLUG, "base": reverse("journey"),
        "copy": _copy("journey", keys), "facilityImages": services.journey_facility_images(),
        "iconSprite": static("common/img/icons.svg"),
        "urls": {"register": reverse("register"), "goldApply": reverse("gold_apply"), "home": reverse("home"),
                 "memberships": reverse("memberships")},
    }
    return _page(request, "pages/journey.html", "journey", journey_config=config)


@login_not_required  # PUBLIC: the Gold application (posts to /gold/apply/, no account)
@ensure_csrf_cookie
@require_GET
def gold_apply(request, slug=""):
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


SITEMAP_NAMES = ["home", "spa", "memberships", "gold_card", "book", "visit", "privacy", "terms"]


@login_not_required  # PUBLIC
@require_GET
def sitemap(request):
    urls = "".join(f"<url><loc>{request.build_absolute_uri(reverse(name))}</loc></url>" for name in SITEMAP_NAMES)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    return HttpResponse(xml, content_type="application/xml")
