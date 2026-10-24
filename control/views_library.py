"""Control media Library: JSON endpoints plus one minimal page. Admin level and up (plain 404 otherwise). Every write is a
POST with the CSRF token (header X-CSRFToken); bodies are JSON or ordinary form fields. Files are stored by uuid in the
default storage and handed out as storage URLs (signed on live)."""
import json
import logging
import re

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Max, Sum
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from common.ratelimit import rate_limited_json

from . import media_rules
from .models import MediaAsset, Playlist, PlaylistItem
from .views import _context, _json_state, admin_only

logger = logging.getLogger("spa99.control")
TAG_RE = re.compile(r"[^a-z0-9 \-]")
KINDS_FOR = {Playlist.MUSIC: {MediaAsset.AUDIO}, Playlist.SCREENS: {MediaAsset.VIDEO, MediaAsset.IMAGE}}


def _fail(message, status=400):
    return JsonResponse({"error": message}, status=status)


def _data(request):
    if request.content_type == "application/json":
        try:
            body = json.loads(request.body or b"{}")
        except ValueError:
            return {}
        return body if isinstance(body, dict) else {}
    return request.POST


def _tags(value):
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, list):
        return []
    clean = []
    for tag in value:
        tag = TAG_RE.sub("", str(tag).lower()).strip()[:30]
        if tag and tag not in clean:
            clean.append(tag)
    return clean[:8]


def _kind_tags(kind, tags):
    """Music belongs to audio only; screens media (video, pictures) always carries "screens"; audio always carries "music"."""
    if kind == MediaAsset.AUDIO:
        return ["music"] + [t for t in tags if t != "music"]
    return ["screens"] + [t for t in tags if t not in ("music", "screens")]


def asset_json(asset, playlists=None):
    """`playlists` = the playlists using this file (id, name, kind); the browser adds the screens and zones it knows about."""
    return {"id": str(asset.id), "title": asset.title, "artist": asset.artist, "kind": asset.kind, "mime": asset.mime,
            "size_bytes": asset.size_bytes, "duration_seconds": asset.duration_seconds, "width": asset.width, "height": asset.height,
            "tags": asset.tags, "peaks": asset.peaks, "url": asset.file.url, "poster_url": asset.poster.url if asset.poster else None,
            "uploaded_by": (asset.uploaded_by.get_full_name() or asset.uploaded_by.email) if asset.uploaded_by_id else "",
            "created_at": asset.created_at.isoformat(), "playlists": playlists or []}


def playlist_json(playlist):
    items = playlist.items.select_related("asset", "asset__uploaded_by")
    return {"id": str(playlist.id), "name": playlist.name, "kind": playlist.kind,
            "items": [{"id": item.id, "position": item.position, "seconds": item.seconds, "asset": asset_json(item.asset)} for item in items]}


def summary():
    """Library size against the total limit (the meter on the page)."""
    used = MediaAsset.objects.aggregate(total=Sum("size_bytes"))["total"] or 0
    return {"used_bytes": used, "max_bytes": media_rules.library_max_bytes()}


def _used_in(rows):
    """{asset id: [playlist, ...]} for these assets, in one query."""
    found = {}
    for item in PlaylistItem.objects.filter(asset__in=rows).select_related("playlist"):
        entry = {"id": str(item.playlist_id), "name": item.playlist.name, "kind": item.playlist.kind}
        if entry not in found.setdefault(str(item.asset_id), []):
            found[str(item.asset_id)].append(entry)
    return found


def _remove_file(asset):
    for field in (asset.file, asset.poster):
        try:
            if field:
                field.delete(save=False)
        except Exception:  # a missing or unreachable file must not block removing the row
            logger.exception("Could not delete media file for asset %s", asset.pk)


def _save_history(asset, user):
    asset._history_user = user
    asset.save()


# ---------- page and assets ----------

@admin_only
@require_GET
def library(request):
    """The page. The files are listed here too, so it reads without JavaScript; library.js takes over when it runs."""
    found = list(MediaAsset.objects.all()[:200])
    limits = {k: media_rules.limit_bytes(k) for k in ("audio", "video", "image")}
    context = _context(request, "library")
    context["json_state"] = _json_state(context)
    return render(request, "control/library.html", {
        **context, "assets": found, "summary": summary(), "limits": limits,
        "limit_mb": {k: v // (1024 * 1024) for k, v in limits.items()}, "types_text": media_rules.TYPES_TEXT,
        "accept": ",".join(f".{e}" for e in sorted(media_rules.ALLOWED_EXT)) + ",.jpeg"})


@admin_only
@require_GET
def assets(request):
    found = MediaAsset.objects.all()
    if request.GET.get("kind") in {"audio", "video", "image"}:
        found = found.filter(kind=request.GET["kind"])
    if request.GET.get("q"):
        found = found.filter(title__icontains=request.GET["q"][:100])
    rows = list(found.select_related("uploaded_by")[:500])
    tag = TAG_RE.sub("", request.GET.get("tag", "").lower()).strip()
    if tag:  # JSON contains is not portable between SQLite and Postgres, so tags are filtered here (library is small)
        rows = [a for a in rows if tag in a.tags]
    used = _used_in(rows)
    return JsonResponse({"assets": [asset_json(a, used.get(str(a.id))) for a in rows], "library": summary()})


def _upload_failed(request, message, status):
    """JSON for the page script; a plain form post (no JavaScript) goes back to the page with the message."""
    if request.POST.get("next") == "page":
        messages.error(request, message)
        return redirect("control_library")
    return _fail(message, status)


@admin_only
@require_POST
@rate_limited_json("control-upload", 40, 600)
def upload(request):
    file = request.FILES.get("file")
    if not file:
        return _upload_failed(request, "Choose a file to upload.", 400)
    try:
        info = media_rules.inspect(file)
    except media_rules.Rejected as error:
        return _upload_failed(request, str(error), error.status)
    if summary()["used_bytes"] + info["size"] > media_rules.library_max_bytes():
        return _upload_failed(request, "The Library is full. Delete something to make room.", 507)
    title = (request.POST.get("title") or re.sub(r"\.[A-Za-z0-9]{1,5}$", "", file.name or "")).strip()[:120] or "Untitled"
    asset = MediaAsset(title=title, kind=info["kind"], ext=info["ext"], mime=info["mime"], size_bytes=info["size"],
                       width=info["width"], height=info["height"], uploaded_by=request.user,
                       tags=_kind_tags(info["kind"], _tags(request.POST.get("tags", ""))))
    asset.file.save(file.name, file, save=False)  # the name is replaced by the uuid path (asset_path)
    try:
        _save_history(asset, request.user)
    except Exception:
        _remove_file(asset)
        raise
    if request.POST.get("next") == "page":
        messages.success(request, f"{asset.title} added to the Library.")
        return redirect("control_library")
    return JsonResponse({**asset_json(asset), "library": summary()}, status=201)


@admin_only
@require_POST
def asset_update(request, pk):
    asset = get_object_or_404(MediaAsset, pk=pk)
    data = _data(request)
    if "title" in data:
        title = str(data["title"]).strip()[:120]
        if not title:
            return _fail("Give it a name.")
        asset.title = title
    if "artist" in data:
        if asset.kind != MediaAsset.AUDIO:
            return _fail("Only music files have an artist.")
        asset.artist = str(data["artist"]).strip()[:120]
    if "tags" in data:
        asset.tags = _kind_tags(asset.kind, _tags(data["tags"]))
    _save_history(asset, request.user)
    return JsonResponse(asset_json(asset, _used_in([asset]).get(str(asset.id))))


def _peaks(value):
    """About 200 numbers from 0 to 1 (JSON text from a form, or a list). Anything else is ignored."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return None
    if not isinstance(value, list) or not 8 <= len(value) <= 400:
        return None
    try:
        numbers = [round(min(1.0, max(0.0, float(v))), 3) for v in value]
    except (TypeError, ValueError):
        return None
    return numbers


@admin_only
@require_POST
def asset_duration(request, pk):
    """The browser reports what it saw after the upload: length, video size, audio waveform peaks, a video poster frame.
    JSON, or a form with an optional `poster` file (jpg, up to 1 MB)."""
    asset = get_object_or_404(MediaAsset, pk=pk)
    data = _data(request)
    try:
        seconds = float(data.get("duration_seconds"))
    except (TypeError, ValueError):
        return _fail("Send duration_seconds as a number.")
    if not 0 < seconds < 24 * 3600 or asset.kind == MediaAsset.IMAGE:
        return _fail("That duration is not valid for this file.")
    asset.duration_seconds = round(seconds, 2)
    fields = ["duration_seconds"]
    if asset.kind == MediaAsset.VIDEO:
        for field in ("width", "height"):
            try:
                value = int(data.get(field))
            except (TypeError, ValueError):
                continue
            if 0 < value < 20000:
                setattr(asset, field, value)
                fields.append(field)
        poster = request.FILES.get("poster")
        if poster:
            head = poster.read(16)
            poster.seek(0)
            if not media_rules.is_jpeg(head) or poster.size > 1_048_576:
                return _fail("The poster must be a jpg under 1 MB.")
            if asset.poster:
                asset.poster.delete(save=False)
            asset.poster.save("poster.jpg", poster, save=False)
            fields.append("poster")
    if asset.kind == MediaAsset.AUDIO and data.get("peaks") is not None:
        peaks = _peaks(data.get("peaks"))
        if peaks:
            asset.peaks = peaks
            fields.append("peaks")
    asset.save(update_fields=fields)
    return JsonResponse(asset_json(asset, _used_in([asset]).get(str(asset.id))))


@admin_only
@require_POST
def asset_delete(request, pk):
    asset = get_object_or_404(MediaAsset, pk=pk)
    asset._history_user = request.user
    asset_id = str(asset.pk)
    with transaction.atomic():
        files = [f for f in (asset.file, asset.poster) if f]
        asset.delete()
    for file in files:
        try:
            file.delete(save=False)
        except Exception:
            logger.exception("Could not delete media file for asset %s", asset_id)
    return JsonResponse({"deleted": asset_id, "library": summary()})


# ---------- playlists ----------

def _playlist(pk):
    return get_object_or_404(Playlist, pk=pk)


@admin_only
@require_GET
def playlists(request):
    found = Playlist.objects.all()
    if request.GET.get("kind") in KINDS_FOR:
        found = found.filter(kind=request.GET["kind"])
    return JsonResponse({"playlists": [playlist_json(p) for p in found]})


@admin_only
@require_POST
def playlist_create(request):
    data = _data(request)
    name, kind = str(data.get("name", "")).strip()[:120], data.get("kind")
    if not name or kind not in KINDS_FOR:
        return _fail("Give the playlist a name and a kind (music or screens).")
    return JsonResponse(playlist_json(Playlist.objects.create(name=name, kind=kind, created_by=request.user)), status=201)


@admin_only
@require_POST
def playlist_update(request, pk):
    playlist = _playlist(pk)
    name = str(_data(request).get("name", "")).strip()[:120]
    if not name:
        return _fail("Give the playlist a name.")
    playlist.name = name
    playlist.save(update_fields=["name"])
    return JsonResponse(playlist_json(playlist))


@admin_only
@require_POST
def playlist_delete(request, pk):
    playlist = _playlist(pk)
    playlist.delete()  # items go with it; the media files stay in the Library
    return JsonResponse({"deleted": str(pk)})


def _renumber(playlist, ordered_items):
    """Gives items positions 1..n without ever clashing with the unique (playlist, position): park them high first."""
    ordered_items = list(ordered_items)
    base = (playlist.items.aggregate(m=Max("position"))["m"] or 0) + len(ordered_items) + 1
    for offset, item in enumerate(ordered_items):
        PlaylistItem.objects.filter(pk=item.pk).update(position=base + offset)
    for number, item in enumerate(ordered_items, start=1):
        PlaylistItem.objects.filter(pk=item.pk).update(position=number)


@admin_only
@require_POST
def item_add(request, pk):
    data = _data(request)
    try:
        with transaction.atomic():
            playlist = Playlist.objects.select_for_update().get(pk=pk)
            asset = MediaAsset.objects.filter(pk=data.get("asset_id")).first()
            if not asset:
                return _fail("That file is not in the Library.", 404)
            if asset.kind not in KINDS_FOR[playlist.kind]:
                return _fail(f"A {playlist.kind} playlist cannot hold {asset.kind} files.")
            position = (playlist.items.aggregate(m=Max("position"))["m"] or 0) + 1
            PlaylistItem.objects.create(playlist=playlist, asset=asset, position=position)
    except Playlist.DoesNotExist:
        raise Http404
    except (IntegrityError, ValueError):
        return _fail("Could not add that file. Try again.")
    return JsonResponse(playlist_json(playlist), status=201)


@admin_only
@require_POST
def item_remove(request, pk):
    playlist = _playlist(pk)
    with transaction.atomic():
        item = playlist.items.filter(pk=_data(request).get("item_id") or 0).first() if str(_data(request).get("item_id", "")).isdigit() else None
        if not item:
            return _fail("That item is not in this playlist.", 404)
        item.delete()
        _renumber(playlist, playlist.items.all())
    return JsonResponse(playlist_json(playlist))


@admin_only
@require_POST
def item_seconds(request, pk):
    """How long a picture stays on screen in a screens playlist: 4 to 60 seconds (videos play their own length)."""
    playlist = _playlist(pk)
    data = _data(request)
    item = playlist.items.select_related("asset").filter(pk=data.get("item_id") or 0).first() if str(data.get("item_id", "")).isdigit() else None
    if not item:
        return _fail("That item is not in this playlist.", 404)
    if item.asset.kind != MediaAsset.IMAGE:
        return _fail("Only pictures have a time on screen. Videos play their full length.")
    try:
        seconds = int(data.get("seconds"))
    except (TypeError, ValueError):
        return _fail("Send seconds as a number from 4 to 60.")
    if not 4 <= seconds <= 60:
        return _fail("Pictures can stay on screen for 4 to 60 seconds.")
    item.seconds = seconds
    item.save(update_fields=["seconds"])
    return JsonResponse(playlist_json(playlist))


@admin_only
@require_POST
def item_reorder(request, pk):
    """Body: item_ids = the playlist's item ids in the new order (all of them, each once)."""
    playlist = _playlist(pk)
    ids = _data(request).get("item_ids")
    if not isinstance(ids, list):
        return _fail("Send item_ids as a list.")
    with transaction.atomic():
        current = {item.pk: item for item in playlist.items.select_for_update()}
        try:
            ordered = [int(i) for i in ids]
        except (TypeError, ValueError):
            return _fail("item_ids must be numbers.")
        if sorted(ordered) != sorted(current):
            return _fail("item_ids must list every item in the playlist exactly once.")
        _renumber(playlist, [current[i] for i in ordered])
    return JsonResponse(playlist_json(playlist))
