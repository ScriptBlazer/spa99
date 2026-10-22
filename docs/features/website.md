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
| **Memberships** | Tier 1, 2, 3 and single visit from `plans` (price ex VAT shown with inc VAT), what each includes. Tier 2 highlighted. "Not sure? Find yours" → journey. Register interest per tier |
| **Gold Card** | What it is, who it's for (property), perks. Apply |
| **Journey** | See `journey.md` |
| **Book** | Finished-looking placeholder: "Booking opens soon." Register interest to hear first. No fake working buttons |
| **Register interest / Sign in / Account** | See `register-interest.md` |
| **Visit us** | 99 Vale Road, London N4 1PR. Map (static image, no third-party tracking). Contact: hello@spa99.uk |
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

**Layout and styles.** `common/templates/base.html` (site header and footer), `base_reduced.html` (journey, Gold application, errors: lockup and "Leave"), `base_bare.html` (Control sign in). One stylesheet entry `common/css/app.css` imports `tokens`, `fonts`, `base`, `components`, `pages`, `journey`. Only brand tokens; `fonts.css` adds size-adjusted fallbacks to `--font-display` and `--font-body`. Fonts, marks, the icon sprite and the swan pattern are in `common/static/common/`.

**Scripts** (`common/static/common/js/`, ES modules, no libraries). `app.js` loads the shared modules (`buttons`, `modal`, `messages`, `validate`, `reveal`, `nav`); page modules are loaded by their own templates: `home-entry`, `spa-index`, `compare`, `journey`, `gold-apply`, `register`, `account`, `forms`. `api.js` and `choices.js` are shared helpers. The journey and Gold application are drawn by script from the JSON endpoints; there is no HTMX.

**Images.** `python scripts/build_images.py "<originals folder>"` writes WebP and JPEG sets to `content/static/content/img/` and `content/image_manifest.json`. `{% photo "name" alt="..." sizes="..." override=section.image %}` renders a `<picture>`; an uploaded `Section.image` or `Facility.image` always wins, and a name without files (the new renders N1 to N6) shows a calm placeholder. Map of facility to render: `pages/services.py` (`FACILITY_IMAGES`).

**Copy.** Every heading and line comes from `content` sections (keys use underscores, see `content/seed.py`); multi-line lists (Gold roles, address) are one line per row. Plan rows, the compare table, the booking lines on Book and the Gold perk groups come from the `plans` rows.

**Decisions taken for the open questions (to confirm):** hero is render 08 cropped to remove the candle; merch is held; the "change tier whenever you need to" line is removed; Visit us shows the address, the contact email and opening hours only (no map, no arrival line).

**Not in Phase 1 because the backend does not support it:** editing name, email or mobile on the account page (the page says to write to the contact email), "Single visit" in the interest picker (interest is monthly plans only), the portfolio-value toggle on the Gold application (size is unit ranges only). Cookies blocked: the journey needs the first-party cookie to save.
