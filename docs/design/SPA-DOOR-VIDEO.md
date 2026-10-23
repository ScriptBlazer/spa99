# Spa 99: the door video (shot brief for Moishe)

Status 2026-10-23: **an option for later, not the plan.** The spa page now opens on the robe photo (`SPA-OPENER.md`). If you make this video, the page can switch to the door and play it, with no other change. Written in plain words, like the fish tank video you made for Home.

---

## 1. The idea in one line

A slow walk up to the gold swan door, the door opening on its own, and on through it into the warm corridor. About 10 seconds. Nobody in it.

## 2. Start with the still

The video should start on exactly the same picture as the new wide door photo, `door-wide` (SPA-OPENER.md section 6). If you use an image-to-video tool, give it that photo as the first frame. Then the still on the page and the first frame of the video match, and nothing flashes when the video starts.

## 3. Shot by shot

| Time | What you see |
|---|---|
| 0 to 2 s | Standing still a few metres back in reception. The whole doorway in frame: frosted glass door with the gold swan and "SPA 99", walnut frame, stone sides, travertine floor. The door is open a hand's width, warm light spilling through the gap. |
| 2 to 6 s | The camera starts to move forward, slowly and steadily, straight at the door. The door swings open away from the camera, on its own, smoothly (no hand, no person). The swan stays readable as the door turns. |
| 6 to 9 s | The camera passes through the doorway. The corridor beyond: warm travertine walls and floor, a low warm light line along the floor, soft wall lights, and at the far end a lit opening into the next room. |
| 9 to 10 s | The camera keeps gliding gently down the corridor and slows a little. End with the lit opening at the far end centred in frame, about the same size and place in the picture as the door was at the start. |

## 4. Framing, speed and light

- **Framing:** landscape 16:9. Camera at standing eye height, straight lines kept straight (no tilt, no dutch angle). The door sits a little right of centre at the start (about 60% across), so the words on the left of the page sit on the quiet part of the picture.
- **Speed:** a slow walking pace or slower. Think of someone walking in without hurrying. No speeding up, no sudden stops, no shake.
- **Light:** warm and low, like the realistic photos on the site now: warm white (around 2700K), soft shadows, browns never black, nothing blue.
- **Length:** 10 to 13 seconds as you make it. We cut it to a 10 second loop.

## 5. What to avoid

People, hands, reflections of people in the glass, plants, flowers, candles, stones, towels on the floor, signs or extra lettering (only the swan and "SPA 99" on the door), the fish tank (it belongs to Home), fast moves, a camera that spins or tilts, lens flares, blue or green light, a door that flickers or changes shape as it opens, a swan that warps as the door turns.

If the swan warps while the door opens, keep the door opening slower, or start with the door already half open.

## 6. How it loops

A walk forward cannot loop by itself, so we do what we did for the fish tank: a cross-fade.
- The last 3 seconds fade into the first 3 seconds (the same way as option B on Home).
- That is why the shot ends on the lit opening centred in frame (section 3, 9 to 10 s): fading from "an opening ahead" back to "the door ahead" reads as walking on into the next room, not as a jump back.
- Send us the clip as it comes out; we make the loop.

If the loop does not feel right, the other choice is to play it once and stop on the corridor (see the question in the report).

## 7. What to send

Your original file, untouched, in `Software Files/media/` (for example `spa-door.mp4`), as you did for the fish tank. We encode it to the same files as Home (HERO-VIDEO.md section 3), named for this page:

| File | Spec |
|---|---|
| `spa-door-landscape.webm` | 1920 x 1080, AV1, 24 fps, 10 s, no audio, ≤ 1.6 MB |
| `spa-door-landscape.mp4` | 1920 x 1080, H.264 High, CRF about 23, `-movflags +faststart`, no audio, ≤ 2.5 MB |
| `spa-door-portrait.webm` | 608 to 720 wide x 1080 to 1280, AV1, ≤ 0.8 MB (a crop on the door, as the fish tank portrait) |
| `spa-door-portrait.mp4` | same size, H.264, ≤ 1.2 MB |
| `spa-door-poster-landscape.webp` | First frame, 1920 wide, ≤ 160 KB |
| `spa-door-poster-portrait.webp` | First frame, 900 wide, ≤ 90 KB |

Keyframe every second, audio removed, warm grade as the photos, no grain, no vignette. Shoot or generate at least 1080p; we do not upscale. The source note goes in `content/static/content/video/SOURCES.txt`.

For the phone version we crop the middle of the frame. The door and the corridor stay in the middle, so the crop works; if your tool can also make a tall version, send that too.

## 8. A prompt you can paste (image-to-video, with `door-wide` as the first frame)

> Slow, steady forward camera move at standing eye height towards a frosted glass door with a gold swan etched on it, in the reception of a warm, quiet men's luxury spa. The door, already open a little, swings slowly open away from the camera on its own. The camera glides through the doorway into a warm travertine corridor with a soft light line along the floor and warm wall lights, and keeps gliding gently towards a softly lit opening at the far end, which ends centred in the frame. Smooth, calm, cinematic, no camera shake, straight verticals. Warm 2700K light, soft shadows, no people, no hands, no plants, no candles, no text other than the swan and "SPA 99" on the door. 10 seconds.
