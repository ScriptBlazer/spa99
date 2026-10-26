"""Optimise the brand renders for the site. Needs Pillow (not a runtime dependency): `pip install pillow`.

    python scripts/build_images.py "<folder with the originals>"

Only names whose original file is in that folder are rebuilt; every other image and its manifest entry is kept.
The realistic fal photos (2026-10-22) live in SPA99_PRIVATE_DIR/media/fal-renders (fallback .private/fal-renders),
named <name>.png. The old architect renders are backed up in .private/img-backup-2026-10-22-renders.

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
    # Realistic fal photos made from the old renders (Moishe, 2026-10-22). Water walls became the fish tank
    # (arrival, lounge, reception). No grade: they are graded warm already.
    **{name: (f"{name}.png", None) for name in [
        "relaxing-zone", "gym", "dry-sauna", "door-gold", "door-white", "lockers", "arrival", "lounge",
        "relax-loungers", "showers", "reception", "corridor", "showers-mosaic", "cold-plunge",
        "wet-sauna", "massage-room", "kitchenette",
        # 2026-10-26: the ice bucket (journey tile and The spa kit) and the tour's small gym (the tour photo only; The spa keeps `gym`).
        "ice-bucket", "gym-tour",
        # Moishe's own mock-ups, used as they are (2026-10-23), cropped to the page shapes:
        "towel-bench", "towel-bench-portrait", "slippers", "slippers-portrait", "toiletries", "towel-rail",
        "tote", "bottle-gym", "robe", "robe-portrait"]},
    "cold-tub": ("cold-plunge.png", None),  # old name, still used by the cold plunge Facility until Control points it at cold-plunge
    # Kept from the earlier sets (built from the architect / Gemini folder).
    "hero": ("untitled_Gemini 3 Portrait_2026-08-25_12-21-20.png", (0, 0.03, 0.89, 0.80)),  # unused, water wall
    "fish-tank": ("Fish Tank.jpeg", None, True),  # 01 reception with the large fish tank: the Home hero still (Moishe, 2026-10-22)
}


def grade(image):
    image = ImageEnhance.Brightness(ImageEnhance.Color(image).enhance(0.85)).enhance(0.94)
    r, g, b = image.split()
    return Image.merge("RGB", (r, g.point(lambda v: round(v * 0.98)), b.point(lambda v: round(v * 0.93))))


def main(folder):
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    for name, (filename, crop, *rest) in SOURCES.items():
        if not (Path(folder) / filename).exists():
            continue  # not in this folder: keep the built files and manifest entry as they are
        for old in [*OUT.glob(f"{name}-*.webp"), *OUT.glob(f"{name}-*.jpg")]:  # clean so removed sizes do not linger
            if old.stem.rsplit("-", 1)[0] == name:
                old.unlink()
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
