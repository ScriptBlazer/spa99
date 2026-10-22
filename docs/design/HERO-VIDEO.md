# Spa 99: hero video brief

For whoever makes the Home hero loop (text-to-video, stock, or a shoot later). Used by scene H1 in `docs/design/IMMERSIVE.md`. Brand: `docs/BRAND.md`.

## 1. What the loop must do

- **6 to 10 seconds, seamless.** Locked-off camera (no pan, no dolly): camera moves cannot loop cleanly. Motion comes from the subject (water, steam, light).
- **Low-key and warm.** Most of the frame dark espresso brown, highlights warm (about 2700K). Blacks lifted to brown, never pure black, never blue. Greens desaturated.
- **Quiet bottom-left third.** Headline and buttons sit bottom left on a veil, so the busiest part of the motion sits centre or right, upper two thirds.
- **Centre-safe for a 9:16 crop.** The subject must survive a centre portrait crop, or generate a separate portrait version.
- **Materials:** honed travertine, walnut, cedar, brushed brass, still water, steam, concealed warm LED light. The gold swan mark at most once, small, never as signage.
- **Never:** people, faces, hands, bodies, women, towels on faces, candles, pebbles or stacked stones, flowers or petals, orchids, bamboo, incense, fruit, text, logos other than the swan, neon, blue or fluorescent light, lens flares, fast motion, slow-motion splashes.

## 2. Three concepts

### A. The water wall (recommended)

Render 08 comes alive. A backlit travertine wall with a thin sheet of water running down its face, light glowing up from a slot at its base, the swan carved into the stone. It is the image already on the site, so the still and the video match, and the poster frame works as the living still.

**Prompt (16:9, then 9:16):**
> Locked-off cinematic shot, no camera movement. A tall wall of honed cream travertine in a dark, warm, luxurious men's spa. A thin, even sheet of clear water flows slowly down the face of the stone, catching warm light from a concealed LED strip at the base of the wall, so the falling water glimmers softly in fine vertical ripples. A minimal line-carved swan, formed from the letter S, sits in the stone at eye level slightly right of centre, water running over it. The rest of the room falls off into deep espresso-brown shadow with a hint of walnut panelling on the far left. Mood: quiet, still, expensive, calm. Photorealistic, 35mm lens, shallow depth of field, warm 2700K light, lifted brown blacks, muted palette of cream, caramel, espresso brown and soft gold. Gentle continuous motion only, suitable for a seamless 8 second loop. 24 fps.

**Negative:** people, hands, faces, candles, stones, pebbles, plants in foreground, flowers, petals, text, watermark, signage, neon, blue light, fluorescent light, camera movement, zoom, splashes, slow motion, lens flare, fog machine look.

**Loop note:** water sheets loop well. Trim to a clean 8s and cross-dissolve the last 1s over the first 1s in the edit.

### B. Steam and cedar

The heat. Inside the dry sauna (render 14): low warm light from behind the cedar backrest, a slow drift of steam rising from the heater on the right and crossing the frame, the glass door with the etched swan soft in the background.

**Prompt:**
> Locked-off cinematic shot, no camera movement. Interior of a dark, warm cedar sauna in a luxury men's spa. Horizontal cedar benches in the lower half of the frame, lit by a concealed warm LED strip behind the backrest so the wood glows amber. Soft wisps of steam rise slowly from a sauna heater at the right edge of frame and drift lazily left through a beam of warm light. In the soft-focus background, a frosted glass door with a minimal line-etched swan formed from the letter S. Deep espresso-brown shadows, warm 2700K light, lifted brown blacks, muted palette of cedar, caramel, espresso and soft gold. Photorealistic, 35mm lens, shallow depth of field. Slow, continuous, calm motion only, suitable for a seamless 8 second loop. 24 fps.

**Negative:** as A, plus: sauna stones piled as decoration (the heater may show its functional stones, small and in shadow), ladle and bucket, towels, thermometer close-up, thick white fog, smoke.

**Loop note:** steam needs a cross-dissolve of 1.5s. Check the dissolve frame for doubled wisps.

### C. The cold plunge edge

The cold. A low, close view across the still surface of the cold plunge to its travertine lip, a slow, almost invisible overflow sliding over the edge into a slot. A line of warm light reflected in the water wobbles very gently. A brass grab rail just in frame.

**Prompt:**
> Locked-off cinematic shot, no camera movement, low angle just above the waterline. The perfectly still, clear water of a small cold plunge pool set into dark honed travertine in a luxury men's spa. At the far edge the water slides very slowly over a smooth travertine lip into a narrow overflow slot, a thin glassy sheet. A single line of warm light from a concealed LED strip reflects in the surface and moves in slow, gentle ripples. A brushed brass grab rail enters the frame from the upper right. Dark, warm surroundings in espresso brown and caramel, the water itself faintly cool but never blue. Photorealistic, 50mm lens, shallow depth of field, lifted brown blacks, muted palette. Slow, continuous, calm motion only, suitable for a seamless 8 second loop. 24 fps.

**Negative:** as A, plus: turquoise or blue pool water, mosaic tiles, swimming pool lanes, ice cubes, droplets falling in slow motion, bubbles, people's feet.

**Loop note:** ripples loop easily; keep the overflow sheet constant.

## 3. Delivery

| File | Spec |
|---|---|
| `hero-landscape.webm` | 1920×1080, AV1, 24 fps, 8 s, no audio, ≤ 1.6 MB |
| `hero-landscape.mp4` | 1920×1080, H.264 High, CRF about 23, `-movflags +faststart`, no audio, ≤ 2.5 MB |
| `hero-portrait.webm` | 720×1280, AV1, ≤ 0.8 MB |
| `hero-portrait.mp4` | 720×1280, H.264, ≤ 1.2 MB |
| `hero-poster-landscape.webp` | First frame, 1920 wide, ≤ 160 KB |
| `hero-poster-portrait.webp` | First frame, 900 wide, ≤ 90 KB |

- Keyframe every 1s. First and last frames match (that is the poster).
- Grade to the renders: warm white balance, lifted brown blacks, greens down about 30%, no vignette, no grain.
- Generate at the highest resolution the tool allows, then grade and encode; do not upscale a 720p generation to 1080p.
- Put files in `content/static/content/video/`. The template tag only adds the video when the files exist; otherwise the living still runs.

## 4. Steam overlay (for the living still)

One still image used until a video exists: **soft steam on pure black**, 1600×900 WebP, ≤ 60 KB. It is laid over render 08 with `mix-blend-mode: screen`, so black disappears and only the steam shows.

**Prompt:**
> Soft, thin wisps of warm white steam drifting upward on a pure black background, lit from below with warm light, photographic, very subtle, no hard edges, plenty of empty black space, wisps concentrated in the upper middle of the frame.

**Negative:** smoke, fire, colour, blue tint, text, objects, hands.

## 5. Stock fallback (Pexels, Coverr, Mixkit)

Filter every result for: no people, no candles or stones, warm or neutral light (cool footage can be warmed only so far), at least 8 s, 1080p or better, a locked-off camera.

| Concept | Search terms |
|---|---|
| A. Water wall | "water wall stone", "water feature wall slow", "water flowing down stone wall", "travertine water", "backlit water wall", "water sheet close up", "wall fountain dark" |
| B. Steam | "sauna steam", "steam rising dark background", "wooden sauna interior", "steam light beam", "hammam steam", "steam slow motion warm light" |
| C. Still water | "infinity edge water close up", "pool overflow edge", "water surface ripples dark", "calm water reflection warm light", "water surface light reflection slow" |
| Steam overlay | "steam on black background", "smoke overlay black" (warm it in grade), "vapour overlay" |
| Texture alternates | "warm light on stone texture", "light moving across wall", "shadow of water ripples on wall" |

Search tips: add "4k", "slow", "macro". On Pexels, use the orientation filter for portrait versions. Check each licence (Pexels and Coverr allow commercial use without attribution; keep a note of the source URL in `content/static/content/video/SOURCES.txt`).
