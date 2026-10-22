# Feature: The guided journey

Phase 1. Apps: `journey`, `plans`, `insights`, `common`.

## What it is

A short, comfortable series of screens that feels like choosing, not filling in a form. Not a chat. It learns when a visitor would come, what he'd use and what he does, then suggests the right membership and (for property people) nudges towards Gold. It ends in register interest.

Every answer is saved the moment it's given, from the first tap, even if the visitor never finishes. This feeds the statistics.

## Principles

- **Short:** about 4 screens of questions plus the result. Under 2 minutes.
- **Grouped:** related questions share a screen. One idea per screen, not one question per screen.
- **Mixed inputs:** tap tiles (single or multi), a slider or segmented control for frequency, at most one or two short typed answers.
- **Calm feedback:** a choice is acknowledged instantly (soft highlight), saved in the background, and the next part reveals gently.
- **Never lost:** refresh, back button, closing and returning (same device) all resume where he was.
- **Always skippable:** every question has a quiet "skip" or "prefer not to say". Skips are saved too.
- **Progress shown subtly** (thin line or dots), not "Question 3 of 12".

## Draft flow (questions are data, editable in Control)

**Screen 1 — Your time**
- When would you come? (multi): Early morning (5–9am) · Daytime (9am–6pm) · Evening (6–10pm) · Late night (10pm–3am)
- How often? (segmented): Once a week · 2–3 times a week · Most days · Now and then

**Screen 2 — What draws you** (multi tiles, from the real facilities)
- Wet sauna · Dry sauna · Cold plunge · Showers · Relaxing zone · Gym · Massage room · Kitchenette / time to unwind

**Screen 3 — Company**
- Alone, or sometimes with a friend? Alone · Sometimes with someone · Often with someone

**Screen 4 — You**
- What do you do? (tiles): Property · Finance · Business owner · Law · Medical · Tech · Creative · Other
- If Property: your link to property (tiles): Owner / investor · Developer · Manager (block, estate, portfolio) · Work at a property or management firm · Agent / broker · Property lawyer
- If Law: is it property law? Yes · No
- How did you hear about us? (small select): Instagram · A friend · BML · Walking past · Other

**Result**
- "Your membership: Tier 2" with three short reasons drawn from his answers (e.g. "Evenings suit you", "Two to three visits a week", "Book up to 3 days ahead").
- Other tiers shown smaller, so he can choose differently.
- Gold panel or line depending on potential (below).
- Primary action: **Register interest** in the chosen tier (opens sign-up, answers carried over).

## Suggesting a tier (configurable, no hard-coded logic)

Each option carries points per plan, stored in data. The plan with the most points wins, then hard constraints apply:

| Signal | Effect (default) |
|---|---|
| Any evening or late-night time chosen | Tier 1 excluded (daytime only) |
| "Most days" | Strong towards Tier 3 |
| "2–3 times a week" | Towards Tier 2; Tier 3 if also evenings + guests |
| "Once a week" / "Now and then" | Towards Tier 1 (daytime) or Tier 2 (evenings) |
| "Often with someone" | Towards Tier 3 (guest visits) |
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
| `JourneySession` | Anonymous UUID (first-party cookie), started/last seen, device type, referrer, UTM, current step, completed flag, linked `User` or `GoldApplication` once known, suggested plan, Gold potential |
| `Question` | Key, text, type (single, multi, scale, short text), screen, order, active, version |
| `Option` | Question, label, value, order, active, plan points, Gold points |
| `Answer` | Session, question, selected options / text, answered at, skipped flag. Changing an answer updates it and keeps history |
| `SuggestionRule` | Constraint rules and tie-break, editable |

- Each tap posts to a small JSON endpoint (`POST /journey/answer/`), CSRF protected, rate limited. Debounced for text.
- Questions or options retired in Control are hidden, never deleted, so old answers stay readable.
- On sign-up or Gold application, the session is linked to that record.
- No personal data is asked before sign-up except optional industry/role.

## Statistics fed (see `admin.md`)

- Demand by time band and frequency → expected visitors per period.
- Facility interest (e.g. % who want the gym at all).
- Suggested and chosen tier mix; how often people choose differently from the suggestion.
- Industries; property share; Gold potential spread.
- Funnel: started → each screen → result → sign-up. Drop-off per screen.
- Source (heard via, referrer, UTM).

## Edge cases

- Returning visitor on the same device: resume, with "Start again" available.
- Signed-in user retaking the journey: new session linked to his account; latest counts for his profile, history kept.
- Bots: honeypot and rate limit on the answer endpoint; sessions with no human signals are excluded from stats.
- Cookie blocked: journey still works in-page; saving falls back to the page's own state and posts at the end.

## Acceptance checks

- Each tap is in the DB within a second; refresh mid-journey resumes on the same screen with answers shown.
- Back button returns to the previous screen with answers intact.
- Changing a plan's points in Control changes the suggestion without a deploy.
- Unfinished sessions appear in the funnel.
- Works and looks right at 375px and 1440px; keyboard and screen reader usable; reduced motion respected.
