"""The code view endpoints (System host, Developer level, behind the unlock, CSRF). JSON in and out; the logic is in
system/codeview/service.py. See docs/features/system-code-view.md for the response shapes."""
import json

from django.http import Http404, JsonResponse
from django.views.decorators.http import require_GET, require_POST

from common.ratelimit import hit

from . import codeview
from .codeview import service
from .codeview.parse import MAX_BYTES
from .permissions import unlocked

LIMIT, WINDOW = 60, 60  # previews and applies per person per minute


def _section(key):
    if codeview.section(key) is None:
        raise Http404
    return key


def _fail(status, message):
    return JsonResponse({"ok": False, "message": message, "errors": [{"line": 1, "col": 1, "message": message}]}, status=status)


def _read(request):
    """(code, version, confirm_risky) from the JSON body, or a JsonResponse to send back."""
    if int(request.META.get("CONTENT_LENGTH") or 0) > MAX_BYTES * 2:
        return _fail(413, "Over 128 KB. Shorten it to review.")
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return _fail(400, "Send JSON like {\"code\": \"...\", \"version\": \"...\"}.")
    if not isinstance(body, dict) or not isinstance(body.get("code"), str) or not isinstance(body.get("version"), str):
        return _fail(400, "Send JSON like {\"code\": \"...\", \"version\": \"...\"}.")
    return body["code"], body["version"], body.get("confirm_risky") is True


def _limited(request):
    return None if hit("system-code", request.user.pk, LIMIT, WINDOW) else JsonResponse(
        {"ok": False, "message": "Too many requests. Please wait a moment."}, status=429, headers={"Retry-After": str(WINDOW)})


@unlocked
@require_GET
def code(request, section):
    return JsonResponse(service.get(_section(section)))


@unlocked
@require_POST
def code_preview(request, section):
    _section(section)
    body = _limited(request) or _read(request)
    if isinstance(body, JsonResponse):
        return body
    status, payload = service.preview(section, body[0], body[1])
    return JsonResponse(payload, status=status)


@unlocked
@require_POST
def code_apply(request, section):
    _section(section)
    body = _limited(request) or _read(request)
    if isinstance(body, JsonResponse):
        return body
    status, payload = service.apply(request, section, body[0], body[1], body[2])
    return JsonResponse(payload, status=status)
