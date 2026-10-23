Check fal is connected (run the fal account check). Don't generate anything until it passes.

Then read docs/PROJECT.md (especially every 2026-10-23 row), docs/BRAND.md, docs/design/FAL-IMAGES.md and docs/design/SPA-OPENER.md. Continue on branch feature/phase1-site.

Only two fal jobs. Nothing else gets remade: I like all the other images and my own mock-ups as they are.

1. Lounge, with a much wider fish tank.
   - Today `lounge` shows the fish tank almost square. Redo it so the tank is very wide, about 3 metres: a long landscape reef aquarium set flush in travertine, with the long bench and sage pillows in front, like in my hero video.
   - Edit the current photo (.private/fal-renders/lounge.png) with fal. Use these as references:
     - a frame from content/static/content/video/hero-poster-landscape.webp for the tank and bench;
     - docs/design/reference/fal/fish-tank-ref-1.webp and -2.webp.
   - Keep the rest of the room, the light, the colours and the realism. No people.

2. Robe, widened for the desktop opener.
   - The robe mock-up (.private/fal-renders/robe.png) is only 768x1376, so it looks soft as the full-screen desktop opener on The spa.
   - Widen and upscale the same photo with fal (outpaint to a wide 16:9 at about 2400 px and upscale). Never redraw the robe, the swan or the room.
   - Keep the portrait original as `robe-portrait`.

Then:
- Save the results as .private/fal-renders/lounge.png and robe.png (keep the old ones as *-old.png).
- Build them into the site with: `python3 scripts/build_images_ffmpeg.py .private/fal-renders lounge robe` (Pillow can't be installed in the sandbox).
- Check The spa and Home in the browser (my dev server is on localhost:8000) and show me before committing.
- Log the decision in docs/PROJECT.md.
