# Feature: The guided journey

Phase 1. Apps: `journey`, `plans`, `insights`, `common`.

## What it is

A short, comfortable series of screens that feels like choosing, not filling in a form. Not a chat. It learns when a visitor would come, what he'd use and what he does, then suggests the right membership and (for property people) nudges towards Gold. It ends in Register.

Every answer is saved the moment it's given, from the first tap, even if the visitor never finishes. This feeds the statistics.

## Principles

- **Short:** about 4 screens of questions plus the result. Under 2 minutes.
- **Grouped:** related questions share a screen. One idea per screen, not one question per screen.
- **Mixed inputs:** tap tiles (single or multi), a slider or segmented control for frequency, at most one or two short typed answers.
- **Calm feedback:** a choice is acknowledged instantly (soft highlight), saved in the background, and the next part reveals gently.
- **Never lost:** refresh, back button, closing and returning (same device) all resume where he was.
- **Skippable, except two:** every question has a quiet "skip" or "prefer not to say" (skips are saved too), except "When would you come?" and "What would you use?", which need at least one choice ("Choose at least one.", Continue stays disabled until one is chosen; more are allowed). The rule is `Question.min_choices` (0 = optional), set to 1 on `time` and `facilities`, editable in Control. The server enforces it: a required question cannot be skipped or saved empty, `POST /journey/step/` will not move forward past a screen with a required question unanswered, and `POST /journey/result/` computes and stores nothing until they are answered (400 `{"error", "missing": [question keys]}`). The state carries `min_choices`, `required` and `skippable` per question.
- **Progress shown subtly** (thin line or dots), not "Question 3 of 12".

## Draft flow (questions are data, editable in Control)

**Screen 1 — Your time**
- When would you come? (multi): Early morning (5–9am) · Daytime (9am–6pm) · Evening (6–10pm) · Late night (10pm–3am)
- How often? (segmented): Once a week · 2–3 times a week · Most days · Now and then

**Screen 2 — What draws you** (multi tiles, from the real facilities)
- Wet sauna · Dry sauna · Cold plunge · Showers · Relaxing zone · Gym · Massage room · Kitchenette / time to unwind

**Screen 3 — Company**
- Alone, or sometimes with a friend? Alone · Sometimes with a friend (two answers only: guest visits are Tier 3 and Gold only, GST-01; "Often with a friend" was retired 2026-10-23, kept inactive so old answers keep their label)

**Screen 4 — You**
- What do you do? (tiles): Property · Finance · Business owner · Law · Medical · Tech · Creative · Other
- If Property: your link to property (tiles): Owner / investor · Developer · Manager (block, estate, portfolio) · Work at a property or management firm · Agent / broker · Property lawyer
- If Law: is it property law? Yes · No
- How did you hear about us? (small select, tap again to clear): A friend · BML member · Social media · Other ("Instagram" and "Walking past" retired 2026-10-23, kept inactive)

**Result**
- "Your membership: Tier 2" with three short reasons drawn from his answers (e.g. "Evenings suit you", "Two to three visits a week", "Book up to 3 days ahead").
- Other tiers shown smaller, so he can choose differently.
- Gold panel or line depending on potential (below).
- Primary action: **Register for** the chosen tier (button: "Register for Tier 2") (opens sign-up, answers carried over).

## Suggesting a tier (configurable, no hard-coded logic)

Each option carries points per plan, stored in data. The plan with the most points wins, then hard constraints apply:

| Signal | Effect (default) |
|---|---|
| Any evening or late-night time chosen | Tier 1 excluded (daytime only) |
| "Most days" | Strong towards Tier 3 |
| "2–3 times a week" | Towards Tier 2; Tier 3 if also evenings + guests |
| "Once a week" / "Now and then" | Towards Tier 1 (daytime) or Tier 2 (evenings) |
| "Sometimes with a friend" | Towards Tier 3 (guest visits, Tier 3 and Gold only) |
| Ties | Prefer Tier 2 (MEM-03) |

Points, constraints and tie-break are editable in Control. Plans and their features (visits, hours, guests) come from `plans`, so the reasons text updates when plans change.

## Gold nudge

A Gold potential score is worked out from the answers (same engine as the Gold application, see `gold-application.md`):

| Potential | What he sees |
|---|---|
| High (property link with scale) | Tier result plus a prominent Gold panel: "With your property background, you may be invited to hold the Gold Card." → Apply for Gold |
| Medium (property link, unclear scale) | Tier result plus one subtle line with a link to apply |
| Low / none | Tier result only. Gold page still reachable from the menu |

Which answers count as property, and the thresholds, are editable in Control.

## Data saved

| Model | Holds |
|---|---|
| `JourneySession` | Anonymous UUID id plus a secret cookie `key`, last seen, visit count, device type, bot flag, referrer, UTM, current and furthest step, completed flag, linked `User` once known, suggested plan, suggestion detail (points, reasons), Gold potential + score. A Gold application points back at the session (`session.gold_applications`) |
| `Question` | Key, text, help, type (single, multi, scale, text), screen, order, active, `condition` (show only if another answer matches), version |
| `Option` | Question, label, value, order, active, `plan_points` (JSON per plan slug), `gold_points`, `weight` (numeric meaning for statistics, e.g. visits a week), `reason` (text shown when this answer supports the suggestion) |
| `Answer` | Session, question, selected options / text, skipped flag, answered at. One current answer per session + question (unique); changing it updates the row and `django-simple-history` keeps the old ones (options included) |
| `SuggestionRule` | `exclude` (plans, or every daytime-only plan, when conditions match), `add_points`, `tie_break` (preferred plan order). Editable |

- Conditions: `{"question": "industry", "any_of": ["property"]}`; a list means all must match. A question is shown when its condition holds given the answers to the questions before it; answers to hidden questions stay saved but are ignored.
- Endpoints (JSON, public, CSRF protected, rate limited per IP, honeypot field `website`; the CSRF cookie is set by `GET /journey/state/`, send it back as `X-CSRFToken`):
  - `GET /journey/state/?ref=&utm_source=...` session, screens, questions (with `visible`, `options`, saved `answer`, `min_choices`, `required`, `skippable`), `current_step`, `resume_step` and `last_suggestion`. Creates the session and sets the cookie `spa99_journey` (first party, HttpOnly, SameSite=Lax, 1 year). The page passes `document.referrer` as `ref` and any UTM values.
  - `POST /journey/answer/` `{"question", "options": [...], "text", "skipped"}` or `{"answers": [...]}` in one go (for scripts and tests; the page sends one answer at a time). Saving the same answer twice changes nothing. 400 `{"error"}` for anything invalid.
  - `POST /journey/step/` `{"step": 2}` or `{"direction": "next" | "back"}`; remembered so a refresh resumes.
  - `POST /journey/result/` suggested plan with three reasons, the other plans (`not_a_fit` when excluded), Gold nudge (`presentation`: `panel` High, `line` Medium, `none` Low), and `copy.empty` for the no-plans case. Stores the suggestion and marks the journey completed; the page calls it on arriving at the result. `GET /journey/result/` returns the same thing for an existing session but changes nothing (404 with no cookie). Each plan carries `price_line`, `character_line`, `price_whole`, `not_a_fit`, so the page writes no copy of its own.
  - `POST /journey/step/` cannot go further than the screen after the furthest one reached (a posted `99` cannot inflate the funnel).
  - `POST /journey/restart/` "Start again": returns the state of a new empty session (same shape as `GET /journey/state/`, `current_step` 1, `last_suggestion` null); the cookie is replaced; the old session is kept for the statistics.
- Questions or options retired in Control are hidden, never deleted, so old answers stay readable.
- On sign-up the session is linked to the new `User`; on a Gold application the application points at the session.
- No personal data is asked before sign-up except optional industry/role.
- Added to the draft flow: a conditional `property_size` question on screen 4 (1-9, 10-49, 50-199, 200+) so a property person can reach High potential from the journey ("property link with scale"). Hide it in Control if not wanted.
- Seed: `python manage.py seed_phase1` loads these questions, options, points and rules (create-only, never overwrites edits).

## Statistics fed (see `admin.md`)

- Demand by time band and frequency → expected visitors per period.
- Facility interest (e.g. % who want the gym at all).
- Suggested and chosen tier mix; how often people choose differently from the suggestion.
- Industries; property share; Gold potential spread.
- Funnel: started → each screen → result → sign-up. Drop-off per screen.
- Source (heard via, referrer, UTM).

## Edge cases

- Returning visitor on the same device (2026-10-23): reopening always starts at screen 1 with the earlier answers ticked (`session.resume_step` is the first screen); it no longer jumps to the stored result. If he finished before, the state and the page config carry `last_suggestion` `{plan_name, plan_slug, url}` for a small "See my last suggestion" link (copy row `last_suggestion`); the result stays viewable at `url`. "Start again" (`POST /journey/restart/`, copy row `start_again`; `change_answers` carries the same wording but the page reads `start_again`) starts a fresh empty session with a new cookie: screen 1, no answers, no last suggestion. The old session is kept, so statistics and Gold applications linked to it stay intact.
- Signed-in user retaking the journey: new session linked to his account; latest counts for his profile, history kept.
- Bots: honeypot and rate limit on the answer endpoint; sessions with no human signals are excluded from stats.
- Cookie blocked: the journey still works in the page, but nothing can be saved (no cookie means no CSRF token and no session, so the answer posts are refused). The page shows its "couldn't save" message once and carries on with the answers held in the page; those visitors are not in the statistics. There is no "post at the end".
- Shared device: a session is used only by an anonymous browser or by the person who owns it. The `spa99_journey` cookie is dropped at sign-out, and at sign-in when it holds someone else's session; an anonymous session becomes the signed-in person's. Sign-up and Gold never read or link a session owned by another person.
- Answer text boxes allow as many characters as the server does (`max_text_length` in the state, 500).

## Acceptance checks

- Each tap is in the DB within a second; refresh mid-journey resumes on the same screen with answers shown.
- Back button returns to the previous screen with answers intact.
- Changing a plan's points in Control changes the suggestion without a deploy.
- Unfinished sessions appear in the funnel.
- Works and looks right at 375px and 1440px; keyboard and screen reader usable; reduced motion respected.
