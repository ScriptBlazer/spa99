"""The Office as an installable app: the manifest and a service worker that does nothing else (no push), served from the Office host root so the scope can be "/". Office URLconf only: the
public site, Control and System never serve or link them. Both are public files (no secrets in them); a manifest is fetched without cookies."""
import json

from django.contrib.auth.decorators import login_not_required
from django.http import HttpResponse
from django.templatetags.static import static
from django.shortcuts import render
from django.views.decorators.http import require_GET

# The app icons: the gold swan on an espresso tile, the swan inside the central 60% (the maskable safe zone). Files in static/common/img/app/.
# (file, sizes, purpose) -> built into manifest icons with their static URLs when the manifest is served.
ICONS = [("icon-192.png", "192x192", "any"), ("icon-512.png", "512x512", "any"), ("icon-maskable-512.png", "512x512", "maskable")]

MANIFEST = {"name": "Spa 99 Office", "short_name": "Office", "display": "standalone", "start_url": "/", "scope": "/", "theme_color": "#F4F2ED", "background_color": "#F4F2ED"}


@login_not_required  # PUBLIC on purpose: the browser fetches it without cookies; it holds no secrets
@require_GET
def manifest(request):
    icons = [{"src": static(f"common/img/app/{name}"), "sizes": sizes, "type": "image/png", "purpose": purpose} for name, sizes, purpose in ICONS]
    response = HttpResponse(json.dumps({**MANIFEST, "icons": icons}), content_type="application/manifest+json")
    response["Cache-Control"] = "no-cache"
    return response


@login_not_required  # PUBLIC on purpose: the browser fetches the worker without cookies; it holds no secrets
@require_GET
def service_worker(request):
    response = render(request, "office/sw.js", content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response
