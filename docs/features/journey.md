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
- **Superseded 2026-11-21 (see "Required answers" below): nothing is skippable now. Was: skippable, except three (2026-10-26):** every question has a quiet "skip" or "prefer not to say" (skips are saved too), except "When would you come?", "What would you use?" and "What industry are you in?", which need at least one choice ("Choose at least one.", Continue stays disabled until one is chosen; more are allowed). The rule is `Question.min_choices` (0 = optional), set to 1 on `time`, `facilities` and `industry`, editable in Control. The server enforces it: a required question cannot be skipped or saved empty, `POST /journey/step/` will not move forward past a screen with a required question unanswered, and `POST /journey/result/` computes and stores nothing until they are answered (400 `{"error", "missing": [question keys]}`). The state carries `min_choices`, `required` and `skippable` per question.
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
- What industry are you in? (2026-10-29, was "What do you do?"; key `industry`) (**multi tiles, choose at least one**, 2026-10-26): Property · Finance · Business owner · Law · Medical · Tech · Creative · Other. Follow-ups follow the choices: the Property questions show when Property is among them, "Is it property law?" when Law is among them, the "In a few words" text when Other is. No "prefer not to say" on this one.
- If Property: your link to property (tiles): Owner / investor · Developer · Manager (block, estate, portfolio) · Work at a property or management firm · Agent / broker · Property lawyer
- If Law: is it property law? Yes · No
- How did you hear about us? (small select, tap again to clear): A friend · BML staff member (2026-10-29, was "BML member", value `bml`) · Social media · Barry's status (2026-10-29, value `barry_status`, before Other) · Other ("Instagram" and "Walking past" retired 2026-10-23, kept inactive)

**Email gate (2026-10-26)** — between screen 4 and the result, for anyone not signed in
- **Updated 2026-11-03 (WhatsApp):** the step takes **first name, email and mobile (a country select, default +44, and the number), all required**, and one required tick: "Yes, Spa 99 may email and WhatsApp me about opening. I can stop at any time." Words in `journey/copy.py` (`GATE`, `CONSENT_VERSION`). `POST /journey/lead/` `{first_name, email, mobile_country, mobile, consent}` answers every field error at once (`first_name`, `email`, `mobile`, `consent`). Stored on the session: `lead_first_name`, `lead_mobile` (E.164), `lead_consent_version` (like `lead_privacy_version`); carried across a restart in the same browser, cleared by "Not you?". Register pre-fills first name and mobile from it. The Ask us chat still asks for an email only (its own email-only consent words, `CHAT_CONSENT`), so those leads have no name or mobile. Older leads keep working with blanks.
- **Updated 2026-11-04:** the **mobile is required again** (first name, email and mobile; WhatsApp is the channel). The earlier same-day optional wording was dropped before release. The tick, chosen by the owner: "Yes, Spa 99 may email and WhatsApp me about opening and offers. I can stop at any time." (`CONSENT_VERSION` is `2026-11-04-2`; earlier versions keep their own text in the Office, `journey.copy.consent_text`.) Register and the Gold form also require a mobile.
- Before: "One last thing." One field (Email) and one required tick: "Yes, Spa 99 may email me about opening. I can unsubscribe at any time." with a privacy link. Button "See my tailored membership". Until the address is saved there is no suggested membership, no price and the journey is not marked finished (`POST` and `GET /journey/result/` answer 403 `{"needs_email": true}`; the state carries `session.lead_required`). Signed-in visitors skip it (his account is his address). A restart in the same browser carries the address over, so he is not asked twice. **System switch `journey_email_gate` (default on, separate from `memberships_public`):** off means no email screen (`lead_required` is false), straight to the suggestion and price, and Memberships opens for anyone whose journey in this browser reached the result (so the result link never loops back to the journey). With the switch off nobody leaves an email, so people who finish do not become leads in the Office (Leads fills only while it is on). Turned back on, people who passed without an email are asked at their next result.
  - **"Not you? Start again"** (was "Use another email" until 2026-11-03, when the email step began asking first name and mobile too: it now clears all three; backfill entry in `backfill_site_data`; 2026-10-27, content row `not_you` in `content/seed.py`, with a JS fallback): a quiet link at the end of the result, only when the email switch is on, this session holds an email and he is signed out (state `session.has_lead_email`; page config `signedIn`). For a shared device. It posts `POST /journey/restart/` with `{"new_person": true}`: a new session with its own `person_key` and no email, UTM carried, old session untouched; he lands on the first question and meets the email screen again. Refused (403) for signed-in visitors. A plain restart still carries the email. Words live in `journey/copy.py`.
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
- **Invite link (1.0.2):** `/invite/<token>/` now lands here (`/journey/`, "your time") by default (System > Defaults > "Invitation link goes to"). With an invite in the session the email step starts filled in with the invite's email (editable; consent never pre-ticked; no name is asked). Gate off: straight on. Register then pre-fills as before. A different email at Register leaves the invite `opened`. See `docs/features/system-emails.md`.
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

## How did you hear about us? (2026-11-21)
Options: A friend, BML staff member, Social media, Barry's status, News Update, Midweek, Other (then "Where?"). Moishe: News Update and Midweek added (both papers that carry our ads); no "Prefer not to say" on this question, as Other covers it. Live gets the two options from `backfill_site_data`.

## Required answers (2026-11-21)

Moishe: nothing is optional in the journey. Real people must never get stuck.

- **Required whenever shown (at least one choice):** `time`, `frequency`, `facilities`, `company`, `industry`, `property_link`, `property_size`, `property_law`, `heard_via`. **Typed follow-ups too:** `industry_other` ("In a few words", when Other is among the industries) and `heard_via_other` ("Where?", when Other is the answer): at least one non-blank character after trimming; one letter is enough. A hidden question (its condition is not met) is never required, so changing an answer so a follow-up hides cannot block anyone.
- **"In a few words" (later the same day, Moishe):** it sits right under Industry, above the property questions (screen 4 order: industry 1, industry_other 2, property_link 3, property_size 4, property_law 5, heard_via 6, heard_via_other 7). It is **needed only when Other is the only industry ticked**; with Other plus another industry it still shows but may be left blank. Rule in code: `journey.services.required_now` (a typed follow-up with `min_choices` is needed only while every choice on its parent is one its condition wants, `conditions.only_wanted_chosen`), mirrored in `journey.js` `isRequired`; the "Please write a few words." hint shows only while it is needed. "Where?" keeps the same rule, which means always needed once Other is picked (How did you hear is a single choice). A small line above each box says which Other it is for: its help text, "You picked Other under Industry." / "You picked Other under How did you hear about us." (editable in Control). Backfill `_industry_other_under_industry_2026_11_21` moves the order only when screen 4 has exactly the old numbers; `_other_box_context_2026_11_21` fills the two lines only when blank. Single-choice questions now say "Choose one." (multi-choice: "Choose at least one.").
- **How it is marked:** `Question.min_choices` is 1 on all eleven (seed `MIN_CHOICES` / `REQUIRED_KEYS`). On a `text` question any value above 0 means "text required" (documented in the field help). No migration. The state carries `required: true`, `skippable: false`.
- **Gone:** "Prefer not to say" (property link, property size), the "Skip this part" button (Continue is now the only button and stays inactive until the screen's visible required questions are answered), and the "(optional)" label on typed questions. The copy rows `skip`, `prefer_not` and `optional` are no longer read (rows left on live are harmless). New copy row `need_text`: "Please write a few words." (shown under a typed question; also what Continue says when only text is missing). "Choose at least one." is unchanged. The "About you." line no longer says Optional.
- **Server:** `save_answer` refuses `skipped`, an empty choice list, and blank or whitespace text on a visible required question (400). `set_step` forward and `engine.complete` (`POST /journey/result/`) refuse while any visible required question before the target screen is unanswered (400 `{"error", "missing": [keys]}`); the check for a text question is `text_value.strip()`. A question Control sets to 0 can still be skipped (the old behaviour is kept for it).
- **Page script:** `journey.js` uses the same visibility rules as `journey/conditions.py` and the same "met" rule (`isMet`). Typed text counts from the first letter (only the saving waits for a pause; Continue saves it first, and on the last screen the result waits for every save), so Continue never lags behind what he typed. An answer on a retired option counts as unanswered on the page, as on the server. Clearing a required answer is kept on the page and not sent (the server would refuse it).
- **Old data:** finished journeys that skipped questions keep working (results, Office, CSV); stored answers are not rewritten. The result page still opens for them: when a finished journey has a missing answer, `/journey/result/` shows the result from what he answered and stores nothing. A journey still open must answer the missing questions to finish.
- **Gold application:** it reuses the journey endpoints only to save the visit answers (`time`, `frequency`, `facilities`, `company`), the industry and "In a few words", and reads them for prefill. It never moves journey steps or finishes a journey, so nothing is blocked. Un-ticking a visit answer or clearing "In a few words" in the Gold form is no longer saved to the journey (the server refuses an empty required answer; it already did for `time` and `facilities`), so the earlier journey answer stays. The Gold form's own rules are unchanged.
- **Live data:** questions live in the DB. `backfill_site_data` (`_journey_required_2026_11_21`) moves `min_choices` 0 to 1 on those eleven (only from 0), adds the `need_text` row and edits the "About you." line only while it has its exact old wording. `--dry-run` lists and saves nothing; running twice changes nothing the second time.
- **Tests:** `journey/tests/test_required.py` walks whole journeys through the real endpoints on every branch (plain, Property with link and size, Law, Other with text, every follow-up at once, every single option as the minimal answer, changing an answer so follow-ups hide or appear), checks refusals and blank text, runs the real required/visibility functions of `journey.js` under node against the server on 120 random partial journeys (skipped when node is not installed), and covers the backfill.
