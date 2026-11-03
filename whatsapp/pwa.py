"""The Office web app: the manifest and the service worker, served from the Office host root so the scope can be "/". Office URLconf only: the
public site, Control and System never serve or link them. Both are public files (no secrets in them); a manifest is fetched without cookies."""
import json

from django.contrib.auth.decorators import login_not_required
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

# The frontend fills these with the real icons (192, 512, maskable 512) once the artwork exists: {"src": "/static/...", "sizes": "192x192", "type": "image/png", "purpose": "any"}
ICONS = []

MANIFEST = {"name": "Spa 99 Office", "short_name": "Office", "display": "standalone", "start_url": "/", "scope": "/", "theme_color": "#F4F2ED", "background_color": "#F4F2ED"}


@login_not_required  # PUBLIC on purpose: the browser fetches it without cookies; it holds no secrets
@require_GET
def manifest(request):
    response = HttpResponse(json.dumps({**MANIFEST, "icons": ICONS}), content_type="application/manifest+json")
    response["Cache-Control"] = "no-cache"
    return response


@login_not_required  # PUBLIC on purpose: the browser fetches the worker without cookies; it holds no secrets
@require_GET
def service_worker(request):
    response = render(request, "whatsapp/sw.js", content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response
