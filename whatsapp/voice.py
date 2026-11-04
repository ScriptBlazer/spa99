"""Voice notes: staff record in the browser (WebM from Chrome and Firefox, MP4 from Safari) and WhatsApp wants OGG with Opus, so the server converts
with ffmpeg. ffmpeg runs as a subprocess with an argument list (never a shell), a timeout, only the `file` protocol, the input format forced from
its own first bytes, in a temporary folder that is always removed. Tests replace `subprocess.run`."""
import logging
import os
import re
import shutil
import subprocess
import tempfile

from django.conf import settings

logger = logging.getLogger("spa99.whatsapp")

OUTPUT_TYPE = "audio/ogg"


class VoiceError(Exception):
    """`code` is one of: no_ffmpeg, bad_file, too_long, too_big, failed."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def binary():
    return shutil.which(settings.FFMPEG_BIN)


def available():
    return bool(binary())


def sniff(data):
    """The demuxer to force, from the file's own first bytes: WebM/Matroska, MP4/M4A, Ogg. None for anything else (the browser's declared type is never trusted)."""
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return "matroska,webm"
    if data[4:8] == b"ftyp":
        return "mov,mp4,m4a,3gp,3g2,mj2"
    if data[:4] == b"OggS":
        return "ogg"
    return None


def command(ffmpeg, source, target, demuxer):
    """The ffmpeg argument list. `-protocol_whitelist file` stops it opening a network address or a playlist's other files; `-t` stops at the cap plus a second so a longer note is detected, not cut silently."""
    return [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-protocol_whitelist", "file", "-f", demuxer, "-i", source,
            "-t", str(settings.WHATSAPP_VOICE_MAX_SECONDS + 1), "-vn", "-map_metadata", "-1", "-c:a", "libopus", "-b:a", "32k", "-ar", "48000", "-ac", "1",
            "-application", "voip", "-f", "ogg", "-progress", "pipe:1", "-y", target]


def _seconds(progress):
    found = re.findall(r"out_time_us=(\d+)", progress or "")
    return int(found[-1]) / 1_000_000 if found else 0.0


def convert(data):
    """(ogg bytes, seconds) from a recording. Raises VoiceError."""
    ffmpeg = binary()
    if not ffmpeg:
        raise VoiceError("no_ffmpeg")
    demuxer = sniff(data)
    if demuxer is None:
        raise VoiceError("bad_file")
    with tempfile.TemporaryDirectory(prefix="spa99-voice-") as folder:  # removed on every path out, including an error or a timeout
        source, target = os.path.join(folder, "in.bin"), os.path.join(folder, "out.ogg")
        with open(source, "wb") as handle:
            handle.write(data)
        try:
            result = subprocess.run(command(ffmpeg, source, target, demuxer), capture_output=True, timeout=settings.WHATSAPP_VOICE_TIMEOUT_SECONDS, check=False, shell=False)
        except subprocess.TimeoutExpired:
            logger.warning("ffmpeg timed out on a voice note")
            raise VoiceError("failed") from None
        except OSError:
            raise VoiceError("no_ffmpeg") from None
        if result.returncode != 0 or not os.path.exists(target):
            logger.warning("ffmpeg could not convert a voice note (exit %s)", result.returncode)
            raise VoiceError("bad_file")
        seconds = _seconds(result.stdout.decode("utf-8", "replace") if isinstance(result.stdout, bytes) else result.stdout)
        if seconds > settings.WHATSAPP_VOICE_MAX_SECONDS:
            raise VoiceError("too_long")
        if os.path.getsize(target) > settings.WHATSAPP_MAX_FILE_BYTES:
            raise VoiceError("too_big")
        with open(target, "rb") as handle:
            out = handle.read()
    if not out.startswith(b"OggS"):
        raise VoiceError("failed")
    return out, seconds
