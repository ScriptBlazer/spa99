# Feature: The website

Phase 1. Apps: `content`, `plans`, `common`. Look and feel: `BRAND.md`.

## What it is

A stunning, visuals-led site that feels like walking into the spa: lots of space, one idea per screen, big editorial type, slow soft motion. Mobile first. Fast. AA contrast. Reduced motion respected.

All copy and images come from `content` (editable in Control). Plan details come from `plans`.

## Reading content in templates

`{% load content_tags %}{% page_content "home" as home %}` then `{{ home.hero.heading }}`, `.body`, `.image`, `.cta_label`, `.cta_url`. Unknown sections are empty, never an error. Plans: `plans.services.plan_display(plan)` / `visible_plans()` (price ex VAT and inc VAT, facts, perks). Facilities: `plans.services.visible_facilities()`. `site_settings` (stage switches, wording, contact email) is in every template context. Seed copy keys: `python manage.py seed_phase1`.

## Pages

| Page | Content |
|---|---|
| **Home** | Full-bleed hero, "Beyond Luxury". The spa in a few calm scenes. Entry to the journey ("Find your membership"). Memberships teaser. Gold teaser. Opening January 2027 |
| **The spa** | Facilities: wet sauna, dry sauna, cold plunge and showers, relaxing zone, gym, massage room, kitchenette. One image and a line each. How a visit works (book, arrive, stay as long as you like) |
| **Memberships** | Tier 1, 2, 3 and single visit from `plans` (price ex VAT shown with inc VAT), what each includes. Tier 2 highlighted. "Not sure? Find yours" → journey. Register per tier |
| **Gold Card** | What it is, who it's for (property), perks. Apply |
| **Journey** | See `journey.md` |
| **Book** | Finished-looking placeholder: "Booking opens soon." Register to hear first. No fake working buttons |
| **Register / Sign in / Account** | See `register-interest.md` |
| **Visit us** | BML House, 99c Vale Road, London N4 1PR (2026-10-26). Map (static image, no third-party tracking). Contact: hello@spa99.uk |
| **Privacy, Terms** | Legal text (to be supplied) |
| **404 / error** | Branded, plain words, back to home |

## Images

- Phase 1 uses the AI renders from `01 Branding/Assets`, optimised (AVIF/WebP, responsive sizes, lazy-loaded). Not asset 07 (stones).
- More renders via fal.ai in the same look where gaps exist (e.g. relaxing zone, cold plunge, entrance).
- Swan pattern and mark as vector SVG.

## Rules

- Men only (OPS-01): stated calmly, not loudly.
- Prices ex VAT with inc VAT shown (GEN-01).
- No third-party trackers. Self-hosted fonts.
- SEO basics: titles, descriptions, Open Graph image, sitemap, local business schema.

## Acceptance checks

- Changing copy or a plan in Control updates the page.
- Lighthouse: performance and accessibility 90+ on mobile.
- Looks right at 375px and 1440px.

## As built (Phase 1 frontend)

**Routes** (app `pages`, plus `users` and the data endpoints): `/` home, `/the-spa/`, `/memberships/`, `/gold-card/`, `/gold-card/apply/` (and `/property/`, `/visits/`, `/you/`, `/sent/`), `/book/`, `/visit/`, `/privacy/`, `/terms/`, `/journey/` (and `/your-time/`, `/what-draws-you/`, `/company/`, `/about-you/`, `/your-membership/`), `/register/`, `/login/`, `/account/`, `/robots.txt`, `/sitemap.xml`. The result screen is `/journey/your-membership/` because `/journey/result/` is the JSON endpoint.

**Layout and styles.** `common/templates/base.html` (site header and footer), `base_reduced.html` (journey, Gold application, errors: lockup and "Leave"), `base_bare.html` (Control sign in). One stylesheet entry `common/css/app.css` imports `tokens`, `fonts`, `base`, `components`, `pages`, `journey`, `scenes`. Only brand tokens; `fonts.css` adds size-adjusted fallbacks to `--font-display` and `--font-body`. Fonts, marks, the icon sprite and the swan pattern are in `common/static/common/`.

**Scripts** (`common/static/common/js/`, ES modules, no libraries). `app.js` loads the shared modules (`buttons`, `modal`, `messages`, `validate`, `reveal`, `nav`); page modules are loaded by their own templates: `home-entry`, `spa-index`, `compare`, `journey`, `gold-apply`, `register`, `account`, `forms`. `api.js` and `choices.js` are shared helpers. The journey and Gold application are drawn by script from the JSON endpoints; there is no HTMX.

**Images.** `python scripts/build_images.py "<originals folder>"` writes WebP and JPEG sets to `content/static/content/img/` and `content/image_manifest.json`. `{% photo "name" alt="..." sizes="..." override=section.image %}` renders a `<picture>`; an uploaded `Section.image` or `Facility.image` always wins, and a name without files (the new renders N1 to N6) shows a calm placeholder. The render for a facility is the `image_name` field on the Facility (checked against the manifest in Control).

**Copy.** Every heading and line comes from `content` sections (keys use underscores, see `content/seed.py`); multi-line lists (Gold roles, address) are one line per row. Plan rows, the compare table, the booking lines on Book and the Gold perk groups come from the `plans` rows.

**Decisions taken for the open questions (to confirm):** hero is render 08 cropped to remove the candle; merch is held; the "change tier whenever you need to" line is removed; Visit us shows the address, the contact email and opening hours only (no map, no arrival line).

**Not in Phase 1 because the backend does not support it:** editing name, email or mobile on the account page (the page says to write to the contact email), "Single visit" in the interest picker (interest is monthly plans only), the portfolio-value toggle on the Gold application (size is unit ranges only). Cookies blocked: the journey needs the first-party cookie to save.

**Immersive marketing pages (Home built; part 2 builds the rest).** Spec: `docs/design/IMMERSIVE.md`. A marketing template sets `{% block html_attrs %} data-page="marketing"{% endblock %}` and `{% block header_mode %}overlay{% endblock %}` (or `solid`); only then does it get the fixed header, the `motion` class (set by the inline script in `_head.html`, never under reduced motion, dropped after 4s if scenes.js does not report ready) and GSAP. `html[data-smooth="on"]` (default, set in `base.html`) allows Lenis on desktop with a fine pointer; remove the attribute value to switch it off. `common/css/scenes.css` holds the static layout (default) and the motion layout (all under `html.motion`), the veil, glow, header states and page transitions. `common/js/scenes.js` has the scene registry `SCENES[data-scene]` plus the patterns (lineRise, wordLight, fadeUp, pinnedScene, windowTo, drawSwan, count, glow, header); add a scene by adding a function and a `data-scene`. Vendor libraries are self-hosted in `common/static/common/vendor/` (gsap 3.13.0 and plugins, lenis 1.3.27). `common/_mark_draw.html` is the swan as fill and line groups. Optional media: `pages_media` tags skip the hero video when `content/static/content/video/hero-*.mp4/.webm` do not exist and skip the steam layer when `common/img/hero-steam.webp` does not exist. Home uses the cold plunge render when it exists, otherwise `door-white`. Journey, forms and account never load GSAP.

## Memberships page data (backend, 2026-10-22)

Context of `pages.views.memberships`: `cards` (all), `tiers` (cards with `interest_allowed`, plan order), `single` (the single-visit card), `table` (compare rows), `selected_slug` (preselected tier or ""), `vat_rate`.

Card keys added: `tagline` (row, else Daytime / Any time / Unlimited), `pills` (list of text), `visits_count` (int or None), `image` (FieldFile; wins), `image_url` (uploaded URL or ""), `render` (manifest name; show `images.picture(render)` when no image), `image_alt` ("" = decorative), `highlight`, `slug`, `price_whole`, `price_inc`, `period`.

`table` = list of rows `{label, cells: [{text, featured, slug}]}`, columns in card order (Tier 1, 2, 3, Single visit). Perk rows (Merch, Leil Shishi) are added from data; "No" where a plan lacks the perk. Row groups for hairlines: the frontend groups by label.

Content rows on page `memberships`: `continue` (body + cta_label), `recommended_label` (heading), `single_note` (body), `not_sure` (heading "Not sure?", cta_label), `price_note`.

Services: `plans.services.plan_pills(plan)`, `hours_ranges()`, `pages.services.selected_plan_slug(request, cards)`. Existing databases: run `seed_phase1` (creates the new rows) then `backfill_site_data --dry-run` and `backfill_site_data` (taglines, renders, Leil Shishi pill, "Not sure?" wording). Plan `render` is checked against the image manifest in the admin form.

## The spa page data (backend, 2026-10-22)

Spec: `docs/design/SPA-PAGE.md`. Context of `pages.views.spa`:

- `facilities`: flat list of cards (all visible rooms, in order) for the chips. Card keys: `slug, name, line, description, display` (feature / tile / companion), `facts` (list of up to 4 texts), `image` (uploaded FieldFile, wins), `image_name` (built render, "" unless it exists in the manifest; else the brand tile), `focus` (CSS object-position), `alt`, `detail_image` (FieldFile), `detail_image_name` ("" unless it exists), `detail_alt` ("" = decorative).
- `sections`: from `spa_sections(cards)`. Items are `{"kind": "feature", "side": "left"|"right", "feature": card, "companion": card|None}` or `{"kind": "tiles", "tiles": [card, ...]}` (rows of 1 to 4; 5 gives 3 + 2). First feature is left (the opening frame is right), then alternate. A companion with no feature straight before it, or a second one, is a tile. Hiding or reordering a room only changes this list.
- `room_count` (int, visible rooms), `hours` (`opening_hours()` rows), `hours_facts` (`{"range": "5am to 3am", "hours": 22}` or None).
- `visit_pills`: `{"book": [...], "arrive": [...], "stay": [...]}` from `visit_pills()`. Book: window from visible monthly plans ("Book 1 to 7 days ahead"), cancel hours only when all plans agree, then the `booking_pending` row while booking is closed, then `step_1_pills`. Arrive: `step_2_pills`. Stay: "Open 5am to 3am", "Closed for Shabbos and Yom Tov", then `step_3_pills`.
- `next_from`: the `next_from` row with `{price}` and `{price_inc}` filled from the lowest visible monthly plan (with the pound sign), "" if none.

Content rows on page `spa`: `intro` (body uses `{rooms}`, replaced with the visible room count in words: "Eight spaces, one quiet visit."), `facts_rooms`, `facts_hours`, `facts_men`, `tiles_intro`, `how_it_works`, `step_1..3`, `step_1_pills`, `step_2_pills`, `step_3_pills` (one pill per line), `booking_pending`, `next` (button "Tailor your membership"), `next_from`, `next_link`. Read them with `{% page_content "spa" as spa %}`.

Facility fields (Control): `display, image_name, image_focus, detail_image, detail_image_name, detail_alt, facts`. Control rejects image names that are not in the manifest and facts that are not up to 4 texts of 32 characters or fewer. Seed values are in `plans/seed.py` (`FACILITY_SPA_PAGE`); existing databases get them with `backfill_site_data` (empty slots only).

## Review round, 2026-10-26 (Moishe + Barry)

Decisions are in docs/PROJECT.md (row dated 2026-10-26) and docs/SPA99_RULES.md (project overrides). What the backend does:

- **Hours.** `plans.services.open_all_day()` is true when the open periods plus the daily cleaning window fill 24 hours. Then `pages.hours_summary()` says "Open 24 hours a day", `pages.hours_note()` says "Open 24 hours a day. Cleaning hours 3am to 5am. Closed Shabbos and Yom Tov." (Home, footer), `opening_hours()` starts with ("Open", "24 hours a day") and lists the window as "Cleaning hours", and `hours_facts()` returns `{"range": "24 hours a day", "hours": 24, "all_day": True, "cleaning": "3am to 5am"}`. If someone edits the rules so they no longer fill the day, the old words ("Open 5am to 2am") come back, so the site never says something untrue. The spa opener row takes a new `{cleaning}` placeholder.
- **Off-peak and Peak.** Labels only (the stored keys `daytime` and `evening` and `Plan.hours` values are unchanged). Pills, facts, compare "When" row, Gold figure and journey copy say Off-peak / Peak.
- **Facility facts.** Dry sauna 110-120°C, wet sauna 60-80°C, cold plunge 9-11°C (seed; edit in Control). The gym has display `compact` (one smaller picture, shorter section, no bottle inset); the massage room is a full `feature` section.
- **Leil Shishi switch.** Site settings "show Leil Shishi" (`SiteSettings.show_leil_shishi`, default off). `plans.services.shown_perks()` filters the perk out of plan cards, pills, the compare table, Register and the Gold Card page. The perks stay on the plans.
- **Gold in the compare table.** `pages.services.compare_cards(cards)` adds the Gold Card as the last column (the template reads it with `{% compare_columns cards as columns %}`). `Plan.annual_fee` (ex VAT, empty = not decided) is edited in System > Plans (More row of the Gold Card). Default £199 a year (2026-10-26, ex VAT). Empty shows "By application" in both price rows; set shows "£X a year" (inc VAT in the second row).
- **Tier 3** card says "Unlimited" (smaller numeral, `.tier-num--word`).
- **Address.** `SiteSettings.address_street` default "BML House, 99c Vale Road". Existing installs: edit it in the admin (no backfill written; a new live database gets it from the model default).
- **Every visit.** The kit row is Towels, Robe, Slippers, Ice bucket, Toiletries (the ice bucket picture `ice-bucket` was added 2026-10-26; it is also the journey `ice_bucket` tile, via `JOURNEY_EXTRA_IMAGES` in `pages/services.py`). Free drinks and free ice lollies are pills on the Arrive step and in the Memberships "Every visit" line.

## To do for the booking build

- **Shabbos and Yom Tov cut-off (decided 2026-10-26, not built):** bookings are allowed up to 1 hour before closing (see the CAL-07 override in `docs/SPA99_RULES.md`). Apply it in the booking rules when the booking system is built.
