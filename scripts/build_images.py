"""Optimise the brand renders for the site. Needs Pillow (not a runtime dependency): `pip install pillow`.

    python scripts/build_images.py "<folder with the original renders>"

Writes resized WebP and JPEG files (480 / 800 / 1600 / 2400 px wide, never upscaled; JPEG fallback up to 1600) to
content/static/content/img/ and a manifest (content/image_manifest.json) the `{% photo %}` tag reads.
Source numbers are the contact-sheet numbers (docs/design/BRIEF.md section 10). Crops are fractions
(left, top, right, bottom) of the original. New renders (N1 to N6) are not listed: the tag shows a
finished placeholder until their files are added here or uploaded in Control.
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageEnhance

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "content" / "static" / "content" / "img"
MANIFEST = ROOT / "content" / "image_manifest.json"
WIDTHS = [480, 800, 1600, 2400]
QUALITY = 78
JPEG_MAX = 1600

# name: (original file, crop or None) or (original file, crop or None, grade). grade=True warms the architect renders so they sit
# on espresso (docs/design/IMMERSIVE-R2.md 5.3): colour x0.85, brightness x0.94, channels R x1.00, G x0.98, B x0.93.
SOURCES = {
    # 08 backlit travertine water wall. Crop the right edge: it holds the lounger with the candle.
    "hero": ("untitled_Gemini 3 Portrait_2026-08-25_12-21-20.png", (0, 0.03, 0.89, 0.80)),
    "relaxing-zone": ("untitled_Gemini 3 Portrait_2026-08-25_12-17-17.png", None),  # 04
    "gym": ("untitled_Gemini 3 Square 2K_2026-08-25_12-17-10.png", None),  # 12
    "dry-sauna": ("untitled_Gemini 3 Square 2K_2026-08-25_12-18-26.png", None),  # 14
    "door-gold": ("untitled_Gemini 3 Square 2K_2026-08-25_12-16-03.png", None),  # 09
    "door-white": ("untitled_Gemini 3 Square 2K_2026-08-25_12-16-09.png", None),  # 10
    "lockers": ("untitled_Gemini 3 Square 2K_2026-08-25_13-32-08.png", None),  # 20
    # Architect renders (docs/design/IMMERSIVE-R2.md 5.2), graded.
    "arrival": ("WhatsApp Image 2026-08-26 at 19.03.34 (3).jpeg", (0.08, 0, 1, 1), True),  # 16 water wall under the gold cove
    "lounge": ("WhatsApp Image 2026-08-26 at 19.03.34 (2).jpeg", None, True),  # 15
    "relax-loungers": ("WhatsApp Image 2026-08-20 at 10.23.31 (4).jpeg", None, True),  # 08
    "showers": ("WhatsApp Image 2026-08-20 at 10.23.31 (5).jpeg", (0, 0, 0.84, 1), True),  # 09
    "cold-tub": ("WhatsApp Image 2026-08-20 at 10.23.31 (5).jpeg", (0.52, 0.28, 1, 1), True),  # 09, interim cold, small use only
    "reception": ("WhatsApp Image 2026-08-26 at 19.03.33 (2).jpeg", (0.40, 0, 1, 1), True),  # 13, until the lettering is cleaned
    "corridor": ("WhatsApp Image 2026-08-26 at 19.03.34 (5).jpeg", None, True),  # 17
    "showers-mosaic": ("Showers.jpeg", (0, 0, 0.80, 1), True),  # 04
}


def grade(image):
    image = ImageEnhance.Brightness(ImageEnhance.Color(image).enhance(0.85)).enhance(0.94)
    r, g, b = image.split()
    return Image.merge("RGB", (r, g.point(lambda v: round(v * 0.98)), b.point(lambda v: round(v * 0.93))))


def main(folder):
    OUT.mkdir(parents=True, exist_ok=True)
    for old in [*OUT.glob('*.webp'), *OUT.glob('*.jpg')]:  # start clean so removed sizes do not linger
        old.unlink()
    manifest = {}
    for name, (filename, crop, *rest) in SOURCES.items():
        image = Image.open(Path(folder) / filename).convert("RGB")
        if rest and rest[0]:
            image = grade(image)
        if crop:
            w, h = image.size
            image = image.crop((round(crop[0] * w), round(crop[1] * h), round(crop[2] * w), round(crop[3] * h)))
        widths = [w for w in WIDTHS if w <= image.width] or [image.width]
        if image.width not in widths and image.width < WIDTHS[-1] and image.width > widths[-1] * 1.15:
            widths.append(image.width)
        for width in widths:
            height = round(image.height * width / image.width)
            resized = image.resize((width, height), Image.LANCZOS)
            resized.save(OUT / f"{name}-{width}.webp", "WEBP", quality=QUALITY, method=6)
            if width <= JPEG_MAX:  # JPEG is only the fallback for old browsers: keep it small
                resized.save(OUT / f"{name}-{width}.jpg", "JPEG", quality=QUALITY, optimize=True, progressive=True)
        manifest[name] = {"width": image.width, "height": image.height, "widths": widths}
        print(name, widths)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main(sys.argv[1])
