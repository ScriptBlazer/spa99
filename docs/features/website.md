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
