"""Uploaded email pictures: what the file really is (magic bytes, never the name), its size in pixels (read from the header, no Pillow),
and saving it. Served to mail clients by mailings.views.email_image."""
import struct

from django.core.files.base import ContentFile

from .models import MailingImage

MAX_BYTES = 2 * 1024 * 1024
MAX_PIXELS = 10000  # a side longer than this is not an email picture (and a corrupt header should not become a huge number)


class ImageError(Exception):
    """A plain-words reason a file cannot be used."""


def detect(data):
    """'image/png', 'image/jpeg', 'image/gif' from the first bytes, or ''."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    return ""


def dimensions(data, content_type):
    """(width, height) from the file header, or (None, None) when it cannot be read cheaply."""
    try:
        if content_type == "image/png" and data[12:16] == b"IHDR":
            return struct.unpack(">II", data[16:24])
        if content_type == "image/gif":
            return struct.unpack("<HH", data[6:10])
        if content_type == "image/jpeg":
            return _jpeg_size(data)
    except struct.error:
        pass
    return None, None


def _jpeg_size(data):
    """Walk the JPEG segments to the first start-of-frame marker."""
    i, n = 2, len(data)
    while i + 9 < n:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker == 0xFF:
            i += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        length = struct.unpack(">H", data[i + 2:i + 4])[0]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack(">HH", data[i + 5:i + 9])
            return width, height
        i += 2 + length
    return None, None


def save_upload(upload, user=None):
    """Check and store an uploaded file. Returns the MailingImage. Raises ImageError."""
    if upload is None:
        raise ImageError("Choose an image to upload.")
    if upload.size > MAX_BYTES:
        raise ImageError(f"The image is larger than {MAX_BYTES // 1024 // 1024} MB.")
    data = upload.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ImageError(f"The image is larger than {MAX_BYTES // 1024 // 1024} MB.")
    content_type = detect(data)
    if not content_type:
        raise ImageError("Only JPEG, PNG or GIF images can be used.")
    width, height = dimensions(data, content_type)
    if width is not None and (not width or not height or width > MAX_PIXELS or height > MAX_PIXELS):
        raise ImageError("This image's size is not usable.")
    image = MailingImage(content_type=content_type, size=len(data), width=width, height=height, uploaded_by=user if getattr(user, "pk", None) else None)
    image.file.save("upload", ContentFile(data), save=False)  # the name comes from image_path: random, never the uploaded one
    image.save()
    return image
