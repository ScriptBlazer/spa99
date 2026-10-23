"""Build site images with ffmpeg + cwebp when Pillow is not available (same rules as build_images.py).

    python3 scripts/build_images_ffmpeg.py "<folder with <name>.png originals>" name [name ...]

Writes <name>-<width>.webp (480/800/1600/2400, never upscaled; the source width is added when it is >15% over the
last step) and JPEG fallbacks up to 1600 to content/static/content/img/, removes that name's old sizes, and updates
its entry in content/image_manifest.json. Other names are left alone. Needs ffmpeg, ffprobe and cwebp on PATH.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "content" / "static" / "content" / "img"
MANIFEST = ROOT / "content" / "image_manifest.json"
WIDTHS = [480, 800, 1600, 2400]
JPEG_MAX = 1600


def size(path):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)])
    w, h = out.decode().strip().split(",")
    return int(w), int(h)


def build(folder, names):
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    with tempfile.TemporaryDirectory() as tmp:
        for name in names:
            src = Path(folder) / f"{name}.png"
            if not src.exists():
                print("missing", src)
                continue
            w, h = size(src)
            widths = [x for x in WIDTHS if x <= w] or [w]
            if w not in widths and w < WIDTHS[-1] and w > widths[-1] * 1.15:
                widths.append(w)
            for old in [*OUT.glob(f"{name}-*.webp"), *OUT.glob(f"{name}-*.jpg")]:
                if old.stem.rsplit("-", 1)[0] == name:
                    old.unlink()
            for width in widths:
                height = round(h * width / w)
                png = Path(tmp) / f"{name}-{width}.png"
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", f"scale={width}:{height}:flags=lanczos",
                                "-pix_fmt", "rgb24", str(png)], check=True)
                subprocess.run(["cwebp", "-quiet", "-q", "78", "-m", "6", str(png), "-o", str(OUT / f"{name}-{width}.webp")], check=True)
                if width <= JPEG_MAX:
                    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(png), "-q:v", "4", "-pix_fmt", "yuvj420p",
                                    str(OUT / f"{name}-{width}.jpg")], check=True)
            manifest[name] = {"width": w, "height": h, "widths": widths}
            print(name, w, h, widths)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2:])
