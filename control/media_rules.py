"""What may be uploaded: the type is found by reading the first bytes (never the file name or the browser's claim), then the
size limit for that kind is applied. Limits are settings (CONTROL_MAX_*_MB)."""
import struct

from django.conf import settings

from .models import MediaAsset

HEAD = 4096
# One list, shown in the Library and enforced here (docs/design/CONTROL.md 10.3). Browsers play these everywhere.
ALLOWED_EXT = {"mp3", "m4a", "wav", "mp4", "webm", "jpg", "png", "webp"}
KIND_WORD = {"audio": "Music", "video": "Videos", "image": "Pictures"}
TYPES_TEXT = "Music: MP3, M4A or WAV. Video: MP4 (H.264) or WebM. Pictures: JPG, PNG or WebP."
HEIC_BRANDS = (b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1", b"avif")


class Rejected(Exception):
    """Carries a message that is safe to show the uploader, and the HTTP status to answer with."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def sniff(head):
    """-> (kind, ext, mime) from the first bytes, or None."""
    if head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0):
        if head[:3] != b"ID3" and head[1] & 0x06 == 0:  # layer bits 00 = AAC in ADTS
            return MediaAsset.AUDIO, "aac", "audio/aac"
        return MediaAsset.AUDIO, "mp3", "audio/mpeg"
    if head[:4] == b"OggS":
        return MediaAsset.AUDIO, "ogg", "audio/ogg"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return MediaAsset.AUDIO, "wav", "audio/wav"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return MediaAsset.IMAGE, "webp", "image/webp"
    if head[:3] == b"\xff\xd8\xff":
        return MediaAsset.IMAGE, "jpg", "image/jpeg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return MediaAsset.IMAGE, "png", "image/png"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return MediaAsset.VIDEO, "webm", "video/webm"
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in HEIC_BRANDS:
            return MediaAsset.IMAGE, "heic", "image/heic"
        if brand in (b"M4A ", b"M4B ", b"M4P "):
            return MediaAsset.AUDIO, "m4a", "audio/mp4"
        return MediaAsset.VIDEO, "mp4", "video/mp4"
    return None


def library_max_bytes():
    return int(settings.CONTROL_LIBRARY_MAX_GB * 1024 ** 3)


def is_jpeg(head):
    return head[:3] == b"\xff\xd8\xff"


def limit_bytes(kind):
    return {"audio": settings.CONTROL_MAX_AUDIO_MB, "video": settings.CONTROL_MAX_VIDEO_MB, "image": settings.CONTROL_MAX_IMAGE_MB}[kind] * 1024 * 1024


def _not_h264(head):
    """Cheap check for mp4: when the header shows another video codec and no h264 ('avc1'), refuse."""
    return any(codec in head for codec in (b"hvc1", b"hev1", b"av01", b"vp09")) and b"avc1" not in head


def image_size(head, ext):
    try:
        if ext == "png":
            return struct.unpack(">II", head[16:24])
        if ext == "webp" and head[12:16] == b"VP8X":
            return 1 + int.from_bytes(head[24:27], "little"), 1 + int.from_bytes(head[27:30], "little")
        if ext == "webp" and head[12:16] == b"VP8 ":
            w, h = struct.unpack("<HH", head[26:30])
            return w & 0x3FFF, h & 0x3FFF
        if ext == "jpg":
            i = 2
            while i + 9 < len(head):
                if head[i] != 0xFF:
                    break
                marker = head[i + 1]
                if marker in (0xC0, 0xC1, 0xC2):
                    h, w = struct.unpack(">HH", head[i + 5:i + 9])
                    return w, h
                i += 2 + struct.unpack(">H", head[i + 2:i + 4])[0]
    except struct.error:
        pass
    return None, None


def inspect(upload):
    """Checks an UploadedFile. Returns dict(kind, ext, mime, size, width, height) or raises Rejected."""
    head = upload.read(HEAD)
    upload.seek(0)
    found = sniff(head)
    if not found:
        raise Rejected("This type can't be used. For music use MP3, M4A or WAV.", 415)
    kind, ext, mime = found
    if ext == "heic":
        raise Rejected("HEIC pictures can't be shown on screens. Save it as JPG and try again.", 415)
    if ext not in ALLOWED_EXT:
        raise Rejected("This type can't be used. For music use MP3, M4A or WAV.", 415)
    if ext == "mp4" and _not_h264(head):
        raise Rejected("That video is not H.264. Re-export it as MP4 (H.264) or WebM.", 415)
    if upload.size == 0:
        raise Rejected("That file is empty.", 400)
    if upload.size > limit_bytes(kind):
        raise Rejected(f"This file is {round(upload.size / (1024 * 1024))} MB. {KIND_WORD[kind]} can be up to {limit_bytes(kind) // (1024 * 1024)} MB.", 413)
    width, height = image_size(head, ext) if kind == "image" else (None, None)
    return {"kind": kind, "ext": ext, "mime": mime, "size": upload.size, "width": width, "height": height}
