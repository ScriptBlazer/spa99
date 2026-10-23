# Review: Phase 1 site, full pass (branch `feature/phase1-site`, code at de0a60e)

Reviewer run 2026-10-22/23. 69 commits, 425 files ahead of `main`. Status: **ready to PR**, with the Should fix list done in this branch or straight after.

## What passed (evidence)
- Tests: `manage.py test`: 188 run, OK (common 46, pages 39, users 36, plans 19, journey 17, gold 16, insights 11, notifications 4). Email/SES mocked; no real external calls in app code.
- Prod: `check --deploy` with dummy env: only W004 (HSTS off on purpose). Refuses to start without SECRET_KEY, without DATABASE_URL, and with the default ADMIN_PATH (all three run).
- Fallback: `SPA99_PRIVATE_DIR=/nonexistent` boots on `.private/`, one startup line (settings, env sources, db, media; no secrets) plus one warning per missing key.
- Config parsed: `ci.yml` and `docker-compose.yml` parse as YAML (Ruby YAML). CI runs tests on a Postgres 16 service, plus `makemigrations --check` and the deploy check.
- Migrations: no RunPython/RunSQL anywhere; backfill is `backfill_site_data --dry-run`. No Postgres-only or SQLite-only code found (JSONFields only, no JSON lookups).
- Pages (test client, copy of the seeded DB): `/`, `/the-spa/`, `/memberships/`, `/gold-card/`, `/gold-card/apply/`, `/book/`, `/visit/`, `/privacy/`, `/terms/`, `/journey/` (+ steps, result), `/register/`, `/login/`, robots, sitemap, health: all 200. `/account/` 302 to login. 404 page 404.
- Control host: anonymous 302 to login, non-staff 403 on `/` and `/insights/summary/`, `/admin/` 404 on both hosts, admin path non-default.
- Journey: CSRF enforced (403 without token), first tap saved in DB, resume via state, back works, `step: 99` capped at the next screen, result POST stores the suggestion.
- Register interest: under-18 and missing men-only tick rejected with server wording (400), no CSRF 403, valid 302 to sent, mobile stored E.164, interest tier-2 saved, double submit makes one account, journey session linked.
- Copy: "Tailor your membership" on every page; no "Find your membership", "Explore your membership", "by appointment" or "water wall" in code or rendered pages; "Beyond Luxury", "January 2027" and "Men only" present. Prices match PRICING.md: £299/£399/£499/£99 ex VAT and £358.80/£478.80/£598.80/£118.80 inc VAT.
- Media: every image name in templates, `plans/seed.py`, `HOME_PREVIEW_IMAGES` and `Plan.render` exists in the manifest; every manifest file exists; no orphan files. Hero video: no audio stream, 24 fps, keyframe every 1s, sizes within HERO-VIDEO.md section 3 (1.0/2.2 MB landscape, 0.5/1.0 MB portrait, posters 133/49 KB). The tag adds `<video>` only when the files exist. 10s length and 608px portrait are logged decisions.
- Brand: no raw hex, rgb or fonts outside `tokens.css`/`fonts.css` (3D colours read from tokens). Reduced motion handled in scenes, 3D card, spa and memberships scripts and in CSS; `:focus-visible` outlines present. No third-party URLs.
- Earlier review (2026-10-22-phase1-site.md): Blocker fixed (tasks return status; EmailLog subject link; erasure tests). Should-fix items fixed: data not code, shared device, Gold rate limit, client IP, change password, single visit, docs. Nice-to-haves mostly fixed (og.png 179 KB, reduced-motion hover, step cap, verify POST, maxlength, footer year).

## Blocker
None.

## Should fix
1. **Unconfirmed temperatures and times are seeded and shown.** `plans/seed.py:101-103` seeds "80–90°C", "About 45°C", "8–10°C", "10–15 minutes", "1–3 minutes"; they render on `/the-spa/`. This contradicts PROJECT.md decision log (facts entry: "none seeded") and `docs/design/SPA-PAGE.md:80`. Fix: drop temperatures/times from `FACILITY_SPA_PAGE` (or log a new decision that reverses it).
2. **Backfill undoes a hand edit.** `plans/management/commands/backfill_site_data.py:128` refills `facts` whenever they are empty, but empty means "show none" (field help text), so a room cleared in Control gets its facts back (temperatures included) on every run. Breaks the command's own "changes nothing written by hand" promise. Fix: only fill facts on rows never touched (same guard as `display`, line 119).
3. **Alt texts no longer match the new images** (WCAG 1.1.1, brief item 6). `plans/seed.py:83` cold plunge says "pool set into a travertine floor"; the image is a round slatted oak tub with steps in a marble room. `plans/seed.py:85` showers says "behind walnut slatted screens"; the image shows black-framed glass screens on a fan mosaic wall with a marble column. `pages/templates/pages/home.html:166` lounge alt omits the fish tank, the main subject of the new image. Fix: rewrite the three alts; backfill should update alts it seeded when it swaps an image name.
4. **Journey has no privacy notice link.** Rendered `/journey/` has no link to `/privacy/`, and `journey.js` draws none, yet answers are saved from the first tap. PROJECT.md section 8 ("Privacy notice linked from every form and the journey"). Fix: add the privacy link to the journey shell (`base_reduced.html` or the first screen).
5. **Email and mobile in URLs and logs.** `common/static/common/js/validate.js:323` sends `GET /register/check-email/?email=...` and line 228 `GET /validate/mobile/?mobile=...`; gunicorn (`--access-logfile -`) and Caddy log the full query string. `notifications/services.py:64` logs the recipient address on failure (goes to Sentry too). Brief item 7 (no PII in URLs or logs). Fix: POST the live checks (CSRF header) and log the EmailLog id, not the address.
6. **Control is a placeholder but the docs read as built.** `config/views.py` `control_index` returns the text "Spa 99 Control"; there is no `control` app. `docs/features/admin.md` lists the sections as Phase 1 without saying none are built; edits today go through the hidden Django admin only. Barry's email links to `{CONTROL_URL}/gold/<id>/` (`gold/services.py:190`), which 404s. Fix: mark Control "not built yet" in `admin.md` and PROJECT.md, and hide the email link until it exists.

## Nice to have
- `pages/templatetags/pages_media.py:30` declares AV1 level `av01.0.05M.08` (3.1); the landscape file is level 4.0 (ffprobe level 8). Use `av01.0.08M.08` for landscape and `av01.0.04M.08` for portrait.
- `hero-poster-portrait.webp` is never used (the tag sends only the landscape poster). Phones get the landscape poster. Use it, or drop the file.
- `arrival`, `corridor`, `hero`, `reception` are built and shipped but unused (`reception` has made-up signs). Drop them from `build_images.py` and the manifest until they are needed.
- `gold-card` is in the manifest but not in `build_images.py`. Add a comment there saying how it is made. The `build_images.py:12` docstring still says N1-N6 are not listed.
- `journey/views.py:85` docstring still says "post at the end" (the docs were fixed).
- `pages/templates/pages/home.html` still has alt text typed into the template (e.g. line 166); move it to Section rows like the facility alts.
- `/register/check-email/` tells anyone whether an email has an account (rate limited, 30/min/IP). Accept and log it as a decision, or soften it.
- Uploaded images still have no srcset/width/height (`content/images.py` override branch).
- Empty `.claude/.cc-writes` folders inside `content/static/content/img/`, `content/static/content/video/` and `docs/` (not tracked). Delete them.
- `content` has no tests of its own. Add one test that every seeded image name exists in the manifest (checked by hand in this review).

## Not checked
- Layout at 375px and 1440px, keyboard focus as rendered, contrast as rendered, reduced motion in a browser, video playback, bfcache/back button in a real browser, Lighthouse: no browser available, and port binding is blocked by the sandbox.
- Postgres run (CI covers it; no local Postgres).
- Dockerfile and Caddyfile: no parser available (`docker` and `caddy` not installed). Read by eye only.
- Real SES/SMTP sends, Cloudflare proxy status.
- Images were checked against alts for lounge, cold plunge, dry sauna, kitchenette, massage room, showers, relaxing zone and gym only.

**Verdict: ready to PR into main (no blockers); fix the six Should fix items before launch, ideally in this branch.**
