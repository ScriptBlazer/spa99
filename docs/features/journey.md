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
- **Skippable, except three (2026-10-26):** every question has a quiet "skip" or "prefer not to say" (skips are saved too), except "When would you come?", "What would you use?" and "What do you do?", which need at least one choice ("Choose at least one.", Continue stays disabled until one is chosen; more are allowed). The rule is `Question.min_choices` (0 = optional), set to 1 on `time`, `facilities` and `industry`, editable in Control. The server enforces it: a required question cannot be skipped or saved empty, `POST /journey/step/` will not move forward past a screen with a required question unanswered, and `POST /journey/result/` computes and stores nothing until they are answered (400 `{"error", "missing": [question keys]}`). The state carries `min_choices`, `required` and `skippable` per question.
- **Progress shown subtly** (thin line or dots), not "Question 3 of 12".

## Draft flow (questions are data, editable in Control)

**Screen 1 — Your time**
- When would you come? (multi): Early morning (5–9am) · Daytime (9am–6pm) · Evening (6–10pm) · Late night (10pm–3am)
- How often? (segmented): Once a week · 2–3 times a week · Most days · Now and then

**Screen 2 — What draws you** (multi tiles, from the real facilities)
- Wet sauna · Dry sauna · Cold plunge · Ice bucket · Relaxing zone · Gym · Massage room · Kitchenette / time to unwind. (2026-10-26: Showers became **Ice bucket**, value `ice_bucket`. The old `showers` option is retired, never deleted, so old answers keep their label. It has no spa picture yet, so its tile shows the calm placeholder.)

**Screen 3 — Company**
- Alone, or sometimes with a friend? Alone · Sometimes with a friend (two answers only: guest visits are Tier 3 and Gold only, GST-01; "Often with a friend" was retired 2026-10-23, kept inactive so old answers keep their label)

**Screen 4 — You**
- What do you do? (**multi tiles, choose at least one**, 2026-10-26): Property · Finance · Business owner · Law · Medical · Tech · Creative · Other. Follow-ups follow the choices: the Property questions show when Property is among them, "Is it property law?" when Law is among them, the "In a few words" text when Other is. No "prefer not to say" on this one.
- If Property: your link to property (tiles): Owner / investor · Developer · Manager (block, estate, portfolio) · Work at a property or management firm · Agent / broker · Property lawyer
- If Law: is it property law? Yes · No
- How did you hear about us? (small select, tap again to clear): A friend · BML member · Social media · Other ("Instagram" and "Walking past" retired 2026-10-23, kept inactive)

**Email gate (2026-10-26)** — between screen 4 and the result, for anyone not signed in
- "One last thing." One field (Email) and one required tick: "Yes, Spa 99 may email me about opening. I can unsubscribe at any time." with a privacy link. Button "See my tailored membership". Until the address is saved there is no suggested membership, no price and the journey is not marked finished (`POST` and `GET /journey/result/` answer 403 `{"needs_email": true}`; the state carries `session.lead_required`). Signed-in visitors skip it (his account is his address). A restart in the same browser carries the address over, so he is not asked twice. **System switch `journey_email_gate` (default on, separate from `memberships_public`):** off means no email screen (`lead_required` is false), straight to the suggestion and price, and Memberships opens for anyone whose journey in this browser reached the result (so the result link never loops back to the journey). With the switch off nobody leaves an email, so people who finish do not become leads in the Office (Leads fills only while it is on). Turned back on, people who passed without an email are asked at their next result.
  - **"Not you? Use another email"** (2026-10-27, content row `not_you` in `content/seed.py`, with a JS fallback): a quiet link at the end of the result, only when the email switch is on, this session holds an email and he is signed out (state `session.has_lead_email`; page config `signedIn`). For a shared device. It posts `POST /journey/restart/` with `{"new_person": true}`: a new session with its own `person_key` and no email, UTM carried, old session untouched; he lands on the first question and meets the email screen again. Refused (403) for signed-in visitors. A plain restart still carries the email. Words live in `journey/copy.py`.
- Stored on the session: `JourneySession.lead_email`, `lead_at`, `lead_privacy_version` (privacy version in force). Personal data, never shown publicly; visible in the Django admin (list, search, CSV export) and, for a registered person whose address differs from his account email, on his Office person page. Leads who never register are not listed in Office yet (they are in the admin). In the UK GDPR export (sessions by user or by that address) and erased with the person (`journey.services.erase_lead`, also from a Gold applicant's erasure); the answers stay anonymously. For a lead who never registers, export and erase by hand with `manage.py lead_data --email X [--erase] [--dry-run]` (prints the sessions and answers as JSON; `--erase` clears the address, `--dry-run` only reports what it would clear). An Office/System screen for this is a follow-up.
- **Passing the gate unlocks Memberships (2026-10-26):** `memberships_visible(request)` (`pages/access.py`) is also True when this browser's journey session (the `spa99_journey` cookie) holds a `lead_email`, and for any signed-in person. So after the gate the nav/footer link, price lines, sale bar and `/memberships/` work for him while the switch is off; everyone else is still sent to the journey. One small query, cached on the request. The result shows a quiet link "Explore all memberships" (copy row `journey` / `explore_memberships`) under "Or choose another", to `/memberships/` (`config.urls.membershipsPage`).
- Bots: the hidden `website` field flags the session as a bot and stores nothing. Endpoint `POST /journey/lead/` `{"email", "consent": true}` (rate limited, CSRF): 200, or 400 `{"errors": {"email", "consent"}}`.

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
- **Gold points from a multi-select (2026-10-26):** for one question the journey takes the **highest** `gold_points` among the options chosen, never the sum (ticking Finance, Business owner and Law is worth 3, not 9). Points from different questions still add. Plan points are unchanged (every chosen option adds its plan points, as `time` and `facilities` always did).
- **Who sees Gold in the journey (2026-10-26, pushed to more people; journey only, the application rating and thresholds are unchanged; High is 6 or more, Medium is 3 or more):**

| Industry (highest chosen wins) | `gold_points` | Result |
|---|---|---|
| Property, Finance, Business owner, Law, Tech | 6 | Full Gold panel |
| Medical, Creative | 3 | The Gold line |
| Other | 0 | Nothing, unless other signals add up |

  Property follow-ups (link, size) and "property law" only add on top. Points are editable per option in System > Journey.
- **Counting:** each option a person chose is one vote for him (Office rule C3 "Answers"), as for `facilities`; `counted_answers` lists `industry:finance`, `industry:law`.
- **Memberships page switch (2026-10-26):** `SiteSettings.memberships_public` (System > Settings, off by default). While off, the Memberships link is removed from the nav, mobile menu and footer, `/memberships/` redirects (302) to the journey, the sale bar points at the journey, and the sitemap leaves it out. Signed-in team members (`is_staff`) can still open the page to check it. People reach Register only through the journey, so prices appear after the email gate. Rule: `pages/access.py` `memberships_visible(request)`; templates use `{% memberships_url %}` / `{% memberships_shown %}` (`common/templatetags/membership_tags.py`).
- On sign-up the session is linked to the new `User`; on a Gold application the application points at the session.
- No personal data is asked before the email gate except optional industry/role (the gate asks for an email, with consent, before the result).
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
