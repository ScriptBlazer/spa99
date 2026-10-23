# Spa 99: fal image set (replace every site image except the hero)

Decision: PROJECT.md decision log, 2026-10-22 ("Images: replace every site image except the hero ..."). This file is the job list. It covers every image the site shows today, including the ones chosen by data. Status 2026-10-22 (later): superseded by the PROJECT.md decision "Realistic set is live". Every render was turned into a photo by a fal edit of the old render (same layout), not by the fresh prompts below. The prompts below stay as the plan for any image Moishe wants redone from scratch, and for the new rooms with no render yet (`wet-sauna`, `massage-room`, `kitchenette`).

What the rules are, in short:
- Every image is new, photoreal, and has **no people**.
- The Spa 99 logo goes on a wall or surface where a real building would put it: backlit, engraved, etched or inlaid, in warm gold light. It always comes from the **supplied logo PNG**. fal never invents the letters.
- Any **water wall or waterfall becomes the fish tank**, in the look of `docs/design/reference/fal/fish-tank-ref-1.webp` and `fish-tank-ref-2.webp`.
- The look comes from the "Escape the Everyday" ad: warm wood sauna, a dark gym with the gold swan, a travertine relaxation room with loungers, a reception desk with "SPA 99" lit up. Warm wood, travertine, low warm light. No clichés.
- **Names stay the same**, so templates need no change. New names only for N1, N2, N4 and N5, which the docs already name: `wet-sauna`, `cold-plunge`, `massage-room`, `kitchenette`.

## 0. Not replaced (on purpose)

| Name | Why it stays |
|---|---|
| `fish-tank` | The Home hero (and the Home end frame). Moishe: it stays as it is. Note: it shows three men in robes. The "no people" rule is for the new images only. |
| `gold-card` | A still of our own 3D Gold Card (the reduced-motion and no-WebGL fallback). It is not a photo. If the card design changes, re-export it from the 3D scene. |
| N3 (showers) | Not a new name. It is covered by replacing `showers` and `showers-mosaic`. |
| N6 (Gold Card render) | Dropped. The 3D card replaced it (GOLD-CARD-3D.md, G3). |
| `common/img/og.png` | The social share image. It is composed from vector art plus the old water wall render (08), and it is not a fal job. **After this set lands**, recompose it from a new left crop (suggestion: `door-gold` or `reception`), because the water wall no longer exists. Flagged for the frontend. |

## 1. Inventory: every image the site shows

Sizes are the CSS frame at 1440 px (2x pixel density) and at 375 px (3x density). "Min px" is the smallest source that stays sharp everywhere. Generate at the model's 2K or 4K setting, then upscale to at least the min px if needed. These are the old images: a "water wall: yes" means the new image gets the fish tank.

| Name | Shown on (template or data) | Frames it must fill | Focus now | Water wall | Min px |
|---|---|---|---|---|---|
| `dry-sauna` | Home R2 heat (1:1, 26vw / 95vw); Home "What's inside" preview (3:2 desktop, 4:3 phone, 42vw); The spa dry sauna feature (`Facility.image_name`, 3:2 desktop, 4:3 phone, 62vw); Memberships Tier 2 (`Plan.render`, a wide band about 288x170); journey tile (4:5, 480w) | 1:1, 3:2, 4:3, 4:5, wide band | 50% 55% (swan on the glass) | no | 2400x1600 |
| `cold-tub` (old) / **`cold-plunge`** (N2) | Home R2 "Then cold" (4:5, 22vw / 72vw; already uses `cold-plunge` when the file exists); The spa cold plunge tile (`Facility.image_name` = `cold-tub`, 3:4); journey tile (4:5) | 4:5, 3:4 | 100% 62% | no | 1536x2048 |
| `relax-loungers` | Home R2 rest (3:2, 34vw); Home preview for the relaxing zone (3:2 / 4:3, 42vw); Memberships Tier 1 (`Plan.render`, band) | 3:2, 4:3, band | 60% 62% | no (round moss panels) | 2400x1600 |
| `showers` | Home "What's inside" preview, shown first (`HOME_PREVIEW_IMAGES`, 3:2 / 4:3, 42vw) | 3:2, 4:3 | 30% 55% | no | 2400x1600 |
| `gym` | Home preview (3:2); The spa gym feature (16:10 desktop, 16:9 phone, 62vw); Memberships Tier 3 (`Plan.render`, band); journey tile (4:5) | 3:2, 16:10, 4:5, band | 40% 55% | no | 2400x1600 |
| `lounge` | Home R4 "The lounge." (`frame--right`, 40vw / 100vw, about 4:5); Home preview for the kitchenette (3:2); The spa kitchenette companion thumbnail (`Facility.image_name`, 4:5, 10vw / 96px); journey tile (4:5) | 4:5, 3:2 | 55% 60% | **yes** (water wall and green wall) | 2400x1600 |
| `door-gold` | The spa S1 door: full screen and the page's **LCP image, preloaded**, plus the door frame (36vw); Memberships single visit thumbnail (`Plan.render`, 56 px) | full screen landscape and portrait, square | 58% 32% desktop, 55% 40% phone | no | 2400x2400 (2880 better) |
| `relaxing-zone` | The spa relaxing zone feature (2:1 desktop, 16:9 phone, 62vw); journey tile (4:5, `img[src*=relaxing-zone]` set to 72% 50%) | 2:1, 16:9, 4:5 | 55% 60%, swan wall about 72% across | no | 2800x1400 |
| `showers-mosaic` | The spa showers tile (`Facility.image_name`, 3:4); journey tile (4:5) | 3:4, 4:5 | 35% 55% | no | 1536x2048 |
| `lockers` | The spa S3 "How a visit works" (4:3 phone; desktop about 7:6, 44vw) | 4:3, 7:6 | 70% 50% | no | 2400x1600 |
| `door-white` | Visit us arrival band (21:9 desktop at 100vw, 4:5 phone) | 21:9, 4:5 | 50% 40% | no | 2880x1920 |
| **`wet-sauna`** (N1) | The spa wet sauna tile (3:4, now a type tile, `image_name` empty); journey tile (4:5) | 3:4, 4:5 | 50% 50% | no | 1536x2048 |
| **`massage-room`** (N4) | The spa massage companion thumbnail (4:5, now a type tile); journey tile (4:5) | 4:5 | 50% 50% | no | 1280x1600 |
| **`kitchenette`** (N5) | Takes over from `lounge` as the kitchenette companion and journey tile (4:5); can also become the Home kitchenette preview (3:2) | 4:5 (3:2 if used on Home) | 55% 60% | no | 1280x1600 |

Built but **not shown** today (in the manifest and `build_images.py`, no template or data uses them):

| Name | Was | Water wall | Note |
|---|---|---|---|
| `hero` | Render 08, a portrait water wall with a carved swan (1367x2119) | **yes** | Superseded by `fish-tank`. Make a portrait fish tank version only if Moishe wants it (for example for a future phone hero). Otherwise remove it from the build. |
| `arrival` | Architect render 16, reception water wall under the gold cove | **yes** | Superseded by `fish-tank` on Home. A candidate for a future The spa arrival image. |
| `reception` | Architect render 13, water curtain, gold cove, "BML SPA" desk | **yes** | A candidate for The spa arrival and the new `og.png`. |
| `corridor` | Architect render 17, marble column, two doors, bench | no | A candidate for "How a visit works". |

Count: 14 images needed for pages that exist now (10 replacements and 4 new), plus 4 optional ones that are built but unused.

## 2. References to attach (every job)

Files are in `docs/design/reference/fal/`. The PNGs are transparent, 2048 px wide, rendered from the site SVGs with cairosvg.

| File | What it is | Use it when |
|---|---|---|
| `logo-on-dark.png` | Horizontal lockup: a gold swan, with "SPA" over "99" to its right in cream | The full lockup on a wall or desk. Tell the model to render the whole lockup in gold (the PNG fixes the shape, the prompt sets the material). |
| `logo-on-light.png` | The same lockup in espresso | The full lockup engraved or debossed into a pale stone or plaster wall (it reads as a dark recess). |
| `mark-gold.png` | The swan alone, gold | Swan-only spots: etched glass, locker doors, small inlays, embroidery. |
| `fish-tank-ref-1.webp`, `fish-tank-ref-2.webp` | Moishe's fish tank look | Every fish tank job (marked "Fish tank: yes"). |
| Look reference: crop of `OneDrive/BML/Spa 99/02 Launch/Ads/Escape the Everyday.png` | Sauna, gym or lounge tile, or the relaxation photo | The jobs that say so. **Crop away all ad text first** (headline, list, tile labels), or the model may copy it. |
| `OneDrive/.../02 Launch/Ads/The coolest part.png`, cropped to the tub | The real cold plunge tub | `cold-plunge` only. Crop out the headline, the work lamp, the wires and the building materials. |

The lockup in the brand files is horizontal: the swan, with "SPA" over "99" beside it. The references show it stacked: the swan above "SPA 99" on one line. We have no stacked SVG, so the prompts ask for **the supplied lockup exactly as given**. If Moishe wants the stacked one-line form, the designer needs that file from the brand AI/PDF. We should not rearrange the letters ourselves.

If the model still distorts the swan or the letters, regenerate with a **plain, empty panel** in that spot and composite the real vector logo in post (with a matching gold material and glow). Never ship a wrong swan.

## 3. House style block (append verbatim to every prompt)

> Photorealistic architectural interior photograph of Spa 99, a private men's luxury spa in London. One consistent building: honed travertine and warm cream plaster walls, warm oak and pale aspen timber, vertical timber slats, brushed bronze and soft gold details, concealed warm LED cove lines in the ceiling and under benches, about 2700K warm light, low and calm, soft shadows, lifted deep-brown blacks (never pure black), no vignette, no grain. Palette kept to Spa Cream #F5F2D8, Swan Gold #E5AC6E, caramel #BB8855 and espresso #492E21, with greens muted. Finished, spotless and empty: no people. Eye-level camera, 24 to 35mm lens, straight verticals, natural depth of field, generous negative space, editorial and quiet. The only branding is the supplied Spa 99 logo reference, reproduced exactly (same swan shape, same letters), where this prompt says. No other text, signs, numbers or lettering anywhere.

For fish tank jobs, add this line after the house style block:

> The fish tank matches the two fish tank references: a large built-in reef aquarium set flush into a wide honed travertine frame, clear blue water with soft light rays, living coral and a few tropical fish, the water's blue kept inside the glass while the room stays warm. Beside it a narrow vertical green wall with a warm light line on its edge.

## 4. Negative list (use for every job)

> people, person, man, woman, face, hands, silhouette, reflection of a person, robe being worn, candles, tea lights, pebbles, river stones, stacked stones, hot stones, stones on towels, flowers, petals, orchids, flowers in water, bamboo, incense, fruit bowls, cucumber slices, bath bombs, television, screens, monitors, computers, office chairs, fireplace, neon, cool blue room light, fluorescent light, harsh downlight hotspots, clutter, construction materials, tools, cables, work lamps, plastic, text, words, letters, numbers, signage, watermark, logo other than the supplied Spa 99 logo, distorted swan, misspelled SPA 99, extra swans, fisheye, tilted verticals, oversaturated greens, oversaturated colours, HDR look, CGI plastic look, cartoon, illustration

For non-tank jobs, also add: `aquarium, fish tank, water wall, waterfall, water curtain` (keep the tank to its rooms).

## 5. The jobs, in order

Order: the cold plunge first, then Home (by appearance order), then The spa (the LCP door first), then Memberships (which reuses Home and The spa images, so it needs no jobs of its own), then Visit us, then the optional ones.

Each prompt below goes **before** the house style block (section 3).

### 1. `cold-plunge` (N2): new
- **Pages:** Home R2 "Then cold." (4:5); The spa cold plunge tile (3:4); journey tile (4:5).
- **Generate:** 3:4 portrait, min 1536x2048. Keep the tub in the centre 60% of the width and the lower two thirds, so the 4:5 and 3:4 crops both hold.
- **Logo:** yes. `logo-on-dark.png`, the full lockup in brushed gold, engraved into the marble wall at the upper right, softly lit by the cove.
- **Fish tank:** no.
- **References:** the logo, plus `The coolest part.png` cropped to the tub (it is the real tub), plus a text-free crop of the Escape ad relaxation photo for the light.
- **Prompt:** "The cold plunge room of the spa. A round cold plunge tub built from vertical warm oak slats with a pale stone rim, filled to the brim with perfectly still, clear, very cold water that has a faint cool glint against the warm room. Beside it a short flight of oak steps with a slim oak handrail. Pale honed marble with soft veining on the floor and walls, a round marble column behind the tub, a warm LED cove line along the ceiling edge washing down the wall. On the right wall, engraved into the marble and lit warm gold, the supplied Spa 99 logo exactly as the reference. A finished room. Vertical composition, camera at standing eye height, slightly to the left of the tub."
- **Then:** keep the old `cold-tub` name working. Either (a) set the cold plunge Facility `image_name` to `cold-plunge` in Control (preferred), or (b) also build this file as `cold-tub` until that edit is made. The Home alt ("Cold plunge pool set into a travertine floor") and the Facility alt describe a sunken pool. Update them to "A round oak cold plunge tub with steps, in a marble room". That is one template line on Home and one Control edit, a frontend follow-up.

### 2. `dry-sauna`: replace, keep the current look but bigger (Moishe 2026-10-22: "quite ok, but looks small"). Keep the warm wood and glowing bench lines of the current image; make the room feel large and wide, taken from inside the room.
- **Pages:** Home R2 heat (1:1), Home preview (3:2 / 4:3), The spa feature (3:2 / 4:3), Memberships Tier 2 band, journey tile (4:5).
- **Generate:** 3:2, min 2400x1600 (3072x2048 better). Keep the door with the swan and the heater inside the centre 50% of the width, so 1:1 and 4:5 crops work at about 50% 55%.
- **Logo:** yes. `mark-gold.png`, the swan only, frosted and etched into the glass door at eye height with a faint gold fill. This fits the alt "a glass door etched with the swan".
- **Fish tank:** no.
- **References:** the mark, plus a text-free crop of the Escape ad "Dry Sauna" tile (aspen and the curved ceiling light).
- **Prompt:** "A Finnish dry sauna. Wide stepped benches in pale aspen across the room, a curved warm cedar ceiling that sweeps down into the back wall with a warm LED line following the curve, warm light strips under each bench lip. A dark metal sauna heater with sauna stones only inside its cage, on a split-stone feature wall. A clear glass door with the supplied swan mark frosted onto it at eye height, exactly as the reference, catching a little gold light. A faint haze of heat. Camera just inside the room, looking across the benches towards the door and the heater."
- **Alt check:** the Home alt says "cedar benches". With aspen benches, change it to "Dry sauna with pale wood benches and a glass door etched with the swan" (frontend follow-up), or ask for cedar benches here. The 3D walk is pale aspen (decision log), so aspen is the recommendation.

### 3. `relax-loungers`: replace
- **Pages:** Home R2 rest (3:2), Home preview for the relaxing zone (3:2 / 4:3), Memberships Tier 1 band (wide, top of the card).
- **Generate:** 3:2, min 2400x1600. Loungers centred at about 60% 62%. Keep the top 40% calm (the tier band crops a wide strip).
- **Logo:** no. This room is the quiet one. The swan is in `relaxing-zone`, so they do not repeat.
- **Fish tank:** no.
- **References:** a text-free crop of the Escape ad relaxation photo (top right, without the television).
- **Prompt:** "A travertine relaxation room in soft daytime light. Three wooden zero-gravity loungers with cream upholstered pads in a row, each with a folded caramel throw, small travertine side tables between them. Vein-cut travertine walls with vertical warm LED lines between the panels, two round panels of muted preserved moss on the end wall, a warm cove line around the ceiling. Calm and still. Camera at the foot of the room, slightly off-centre, looking along the loungers."

### 4. `lounge`: replace (fish tank)
- **Status 2026-10-23: DONE, live.** Redone per Moishe as an edit of the old render with a very wide (about 3 m) reef tank flush in travertine and the long bench with sage pillows (refs: the hero poster frame and both tank refs). The "seen from the side" plan below is superseded. Home R4 focus 28% 55%. Old file: `.private/fal-renders/lounge-old.png`.
- **Pages:** Home R4 "The lounge." (about 4:5, `frame--right`), Home preview for the kitchenette (3:2), interim kitchenette thumbnail and journey tile on The spa.
- **Generate:** 3:2, min 2400x1600. The 4:5 crop at 55% 60% must hold the sofa, the window and the gold cove.
- **Logo:** no. The Home hero right above already shows the tank with the backlit swan, so we do not show the swan twice in a row.
- **Fish tank:** **yes**, but seen **from the side**: the tank runs along the left wall at an angle, partly out of frame, so this is not a second hero.
- **References:** both fish tank references (for the tank and the travertine frame), plus a text-free crop of the Escape ad "Lounge Room" tile (with the fireplace removed).
- **Prompt:** "The spa lounge. A curved cream bouclé sofa and two low caramel armchairs around a round travertine coffee table, by a tall window with soft evening light outside. Along the left wall, seen at a steep angle and running out of frame, the large built-in reef aquarium in its wide travertine frame, glowing softly. A curved gold-leaf ceiling cove with a warm LED line overhead, warm oak floor, vertical timber slats on the right wall. Camera from the far corner, looking towards the window."
- **Alt:** "The lounge: a curved sofa by a window, under a gold-leaf ceiling cove" still fits. Optionally add "beside the fish tank".

### 5. `showers`: replace
- **Pages:** Home "What's inside" preview, shown first (3:2 / 4:3, focus 30% 55%).
- **Generate:** 3:2, min 2400x1600. The showers in the left 60%.
- **Logo:** yes, small. `mark-gold.png` etched on a frosted glass panel at the end of the row.
- **Fish tank:** no.
- **Prompt:** "A row of three open rain showers separated by walnut slatted screens, honed travertine walls and floor with a linear bronze drain, square brushed bronze ceiling rain heads and simple bronze controls, a lit niche in the travertine holding three bronze bottles. Water falls gently from one shower only, the others dry. At the end of the row, a frosted glass panel with the supplied swan mark etched onto it, exactly as the reference. Warm light grazing the stone. Camera at the start of the row, looking along it."

### 6. `gym`: LAST (Moishe: "okayish", 2026-10-22). Do it after the others, only if a new one clearly beats it.
- **Pages:** Home preview (3:2), The spa gym feature (16:10 / 16:9), Memberships Tier 3 band, journey tile (4:5).
- **Generate:** 3:2, min 2400x1600. The swan panel at about 35 to 40% across, so the 4:5 crop at 40% 55% keeps it.
- **Logo:** yes. `logo-on-dark.png`, the full lockup in brushed gold, raised on a dark espresso plaster wall panel, gently backlit (as in the Escape ad gym tile).
- **Fish tank:** no.
- **References:** the logo, plus a text-free crop of the Escape ad "Gym Room" tile.
- **Prompt:** "A dark private gym at night. Smoked oak floor, espresso-brown plaster walls, warm LED cove lines in a slatted dark timber ceiling and backlit open shelves. On a large dark wall panel, the supplied Spa 99 logo in brushed gold with a soft warm halo, exactly as the reference. A neat dumbbell rack, one cable machine, an adjustable bench and one treadmill facing a tall window with the night outside. Never crowded: empty and tidy."

### 7. `door-gold`: replace (The spa LCP)
- **Pages:** The spa S1 door, full screen (and preloaded), plus the door frame; Memberships single visit thumbnail (56 px).
- **Generate:** 1:1, min 2400x2400 (upscale to 2880). The swan centred at about 55% across and 35 to 40% down, with calm space above and below (the screen crops it landscape on desktop and portrait on phone).
- **Logo:** yes. `logo-on-dark.png`, the full lockup frosted and etched into the glass with a gold fill: the swan large, "SPA 99" small below or beside it, as the supplied lockup.
- **Fish tank:** no.
- **References:** the logo, plus the current `door-gold` render (for the composition).
- **Prompt:** "The entrance to the spa: a tall frosted glass door, floor to ceiling, set between warm stone jambs with dark walnut edges and a long vertical brushed bronze pull handle. The supplied Spa 99 logo is etched large into the frosted glass with a soft gold fill, exactly as the reference. Through the glass, a soft blur of warm light and travertine. Head-on, symmetrical, camera at chest height, a little warm light from the ceiling grazing the glass."
- **Alt:** "A frosted glass door etched with a gold swan, between stone jambs" fits.

### 8. `wet-sauna` (N1): new (DONE 2026-10-22, live)
- **Pages:** The spa wet sauna tile (3:4); journey tile (4:5). A 3D walk slot later.
- **Generate:** 3:4 portrait, min 1536x2048.
- **Logo:** yes, small. `mark-gold.png` inlaid in brushed gold in the travertine above the bench, softened by steam.
- **Fish tank:** no.
- **Prompt:** "A steam room clad entirely in honed travertine: a curved travertine bench along two walls, a low vaulted travertine ceiling with a few small warm downlights. Soft steam fills the room at knee height and catches the light. A thin warm LED line under the bench lip. A clear glass door with a bronze handle at the right edge of frame. The supplied swan mark inlaid small in brushed gold in the wall above the bench, exactly as the reference. Vertical composition."
- **Then:** set the wet sauna Facility `image_name` to `wet-sauna` in Control.

### 9. `relaxing-zone`: replace
- **Pages:** The spa relaxing zone feature (2:1 / 16:9); journey tile (4:5 at 72% 50%).
- **Generate:** 2:1, min 2800x1400. The swan wall at about 70 to 75% across, loungers from 20 to 65%.
- **Logo:** yes. `logo-on-light.png`, the full lockup recessed and engraved into the travertine end wall, with warm gold light inside the engraving.
- **Fish tank:** no.
- **References:** the logo, plus the current `relaxing-zone` render (for layout), plus a text-free crop of the Escape ad relaxation photo (for the light).
- **Prompt:** "A long relaxation room in the evening. A row of four upholstered cream zero-gravity loungers on curved oak frames, each with a folded caramel throw, small round travertine side tables. Travertine walls with vertical warm LED lines between the panels, low even warm light. On the end wall to the right, the supplied Spa 99 logo engraved into the travertine with a warm gold glow inside the lines, exactly as the reference. Wide composition, camera from the entrance end."

### 10. `massage-room` (N4): new (DONE 2026-10-22, live)
- **Pages:** The spa massage companion thumbnail (4:5, small); journey tile (4:5).
- **Generate:** 4:5, min 1280x1600. Simple and readable at 96 px: the table as one clear shape.
- **Logo:** yes, small. `mark-gold.png` in brushed gold on the slatted wall behind the table.
- **Fish tank:** no.
- **Prompt:** "A small private massage room: one padded massage table with a plain cream linen cover on a walnut base, a warm oak slatted wall behind it with the supplied swan mark in brushed gold at its centre, exactly as the reference. A travertine niche with neatly folded plain cream towels, a single walnut stool, a bronze wall light, dimmed warm cove light. Vertical composition, camera at the foot of the table."
- **Then:** set the massage room Facility `image_name` to `massage-room` in Control.

### 11. `showers-mosaic`: replace
- **Pages:** The spa showers tile (3:4, focus 35% 55%); journey tile (4:5).
- **Generate:** 3:4 portrait, min 1536x2048. A different view from `showers` (#5): close and vertical.
- **Logo:** no (#5 has it).
- **Fish tank:** no.
- **Prompt:** "A close vertical view of one open rain shower: a square brushed bronze rain head, a fine curtain of falling water lit warm from above, a honed travertine wall behind with a walnut slatted screen at the edge of frame, a few drops on the travertine floor, a small lit niche with bronze bottles. Calm, warm, finished. Vertical composition."
- **Alt:** the Facility alt "Rain showers behind walnut slatted screens" fits.

### 12. `kitchenette` (N5): new (DONE 2026-10-22, live)
- **Pages:** The spa kitchenette companion (4:5); journey tile (4:5). Optionally the Home kitchenette preview later.
- **Generate:** 4:5, min 1280x1600 (if it will also be the Home preview, generate 3:2 at 2400x1600 instead, with the counter in the centre).
- **Logo:** yes, small. `mark-gold.png` inlaid in the walnut panel above the counter.
- **Fish tank:** no.
- **Prompt:** "A small lounge kitchenette: a walnut counter with a honed travertine top, a built-in bronze coffee machine and a bronze tap, a row of plain cream ceramic cups on an open oak shelf, two low caramel bouclé lounge chairs around a small round travertine table, a warm pendant light. The supplied swan mark inlaid in brushed gold in the walnut panel above the counter, exactly as the reference. Vertical composition."
- **Then:** set the kitchenette Facility `image_name` from `lounge` to `kitchenette` in Control. Optionally `HOME_PREVIEW_IMAGES["kitchenette"] = "kitchenette"` (a one-line code change).

### 13. `lockers`: KEEP (Moishe likes it, 2026-10-22). Do not generate.
- **Pages:** The spa S3 "How a visit works" (4:3 phone, about 7:6 desktop, focus 70% 50%).
- **Generate:** 3:2, min 2400x1600. Lockers fill the right 60%.
- **Logo:** yes. `mark-gold.png`, the swan engraved small on each locker door (one per door, all the same size, in a neat grid). This fits the alt "with the swan on each door".
- **Fish tank:** no.
- **Prompt:** "The changing room: a long wall of warm oak lockers in a neat grid, each door with the supplied swan mark engraved small and filled with soft gold, all identical, exactly as the reference; slim bronze handles, no numbers. A long oak bench in front on a travertine floor, a warm LED line under the bench and along the top of the lockers. Camera from the left, looking down the row."

### 14. `door-white`: replace
- **Pages:** Visit us arrival band (21:9 desktop at full width, 4:5 phone).
- **Generate:** 3:2, min 2880x1920. The swan inside the middle 60% of the height (for the 21:9 crop) and centred (for the 4:5 crop).
- **Logo:** yes. `mark-gold.png` (as a shape only), etched white and frosted into the glass, no gold fill. Plus "SPA 99" from `logo-on-light.png` small below it, also white frosted.
- **Fish tank:** no.
- **Rule:** must not read as the same photo as `door-gold`. They are never on the same page, but keep a different angle.
- **Prompt:** "The street-side entrance doors of the spa seen from a little to the left: a pair of tall frosted glass doors in a warm stone surround with walnut edges, the supplied Spa 99 logo etched frosted white into the glass, exactly as the reference. A travertine threshold, a soft warm wash of light from a cove above. Evening, calm."

### Optional (built but not shown; ask Moishe before making)

15. **`reception`** (fish tank: yes; logo: yes). 3:2, min 2400x1600. "The reception: a curved desk of honed cream stone with the supplied Spa 99 logo standing out in backlit gold letters on its front, exactly as the reference; a curved gold-leaf ceiling cove with a warm LED line; behind and to the right, the large reef aquarium in its travertine frame with the green wall beside it. Polished pale stone floor. Nothing on the desk." References: the logo, both tank references, and a crop of the "Almost ready to check in" ad desk (without the trolley, the building materials or the text). A good source for The spa arrival and the new `og.png`.
16. **`arrival`** (fish tank: yes; logo: yes, backlit on the cream plaster wall to the right of the tank). 3:2, min 2400x1600. The reference composition itself, without people, from a wider angle than the hero, with the long cream bench with sage cushions. Only useful if a second page needs the tank.
17. **`corridor`** (logo: no; fish tank: no). 3:2, min 2400x1600. "A quiet corridor: a round pale marble column, two walnut doors with vertical bronze slats, a long travertine bench, warm wall lights, a warm cove line."
18. **`hero`** (fish tank: yes; logo: yes). Portrait 2:3, min 1400x2100. A portrait version of the tank wall with the backlit swan, for a possible future phone hero. Otherwise remove `hero` from `SOURCES` and the manifest.

## 6. After generation (frontend, not this task)

- Put the originals in the gitignored `.private/renders/`, together with the **unchanged** `Fish Tank.jpeg` and the Gold Card still source. `build_images.py` deletes all outputs first and rebuilds only what it finds.
- In `SOURCES`, point each name at its new file, with `crop=None` and **`grade=False`** (the fal images are made in the palette; the grade was for the cold architect renders). Test one with grade on if the set looks too cool. Add `cold-plunge`, `wet-sauna`, `massage-room` and `kitchenette`.
- Data edits in Control (or `backfill_site_data`, exact old values only): cold plunge `cold-tub` to `cold-plunge`, wet sauna to `wet-sauna`, massage room to `massage-room`, kitchenette `lounge` to `kitchenette`. Check `image_focus` against the new pictures.
- Alt text to update: cold plunge (tub, not a pool), dry sauna (aspen if used). The rest still fits.
- Recompose `og.png` (section 0).
- Review the new set at 375 and 1440 on the real pages, especially the crops listed in section 1.

## 7. Model

- **Main:** Nano Banana Pro **edit** on fal (Google Gemini 3 Pro Image, multi-image references). It is the strongest at keeping a supplied logo exact and at reading long prompts. Use 4K output (2K is enough for the 4:5 and 3:4 jobs). Some endpoints have no negative prompt field; then add the negatives as plain sentences ("No people. No candles ...") at the end of the prompt.
- **Second choice / A/B test:** FLUX.2 [pro] edit (up to 10 references, strong photorealism). Use it if the Nano results look too CGI.
- Then a low-creativity upscaler (for example Clarity, creativity at or below 0.2) only where the output is below min px (`door-gold`, `door-white`).
- Check the exact endpoint IDs in the fal catalogue before running. Make 2 to 4 variations per job and pick by hand.

## Status 2026-10-23 (round 4)

- `relaxing-zone`: redone (cushioned loungers with pillows, zoomed out by outpaint). `massage-room`: redone with luxury massage chairs (alt in `.private/fal-renders/massage-room-alt.png`). See PROJECT.md.
