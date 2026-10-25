# System Emails (full section): design brief

Spec: `docs/features/system-emails.md`. Decisions: PROJECT.md 2026-10-25 (Emails as a full section, Approval moved out, SES rows, code view stays for rules only). Look: `docs/design/SYSTEM.md` unchanged (13px, hairlines, 4-6px corners, no shadow at rest). Feedback: `docs/design/FEEDBACK.md` (shared toast, centred modal, problems modal, never browser dialogs). Brand rule: never a one-sided accent; tint, full hairline, or no border with soft shadow. This also applies to anything copied from older System parts.

**Design read.** Developer tooling for writing to members, in the spirit of the Postmark and Resend dashboards: the System shell, plain screens, the real email shown beside the words. Dials: variance 1, motion 1, density 8 (phone 6). No code view here (`code_url` stays unset). One stylesheet: `common/static/common/css/system-emails.css`, classes prefixed `se-`; reuse `sys-*` wherever it exists.

## 1. Section frame

- Page header (`_page_header.html`): "Emails", description "What the site sends, and what you send." Below it a sub-nav `nav.se-tabs[aria-label="Emails"]`: Overview, Automatic emails, Group sends, Invites. Each is a real URL (`/emails/`, `/emails/automatic/`, `/emails/sends/`, `/emails/invites/`), so links with `aria-current="page"`, not ARIA tabs (back button, reload and deep links work; no roving tabindex needed).
- `.se-tabs`: flex, gap `--sys-1`, margin-bottom `--sys-4`. Item 28px, padding 0 `--sys-3`, `--sys-radius`, 13px 500 `--sys-text-2`; hover `--sys-subtle`; current `--sys-selected` fill, `--sys-text` 600 (same as the left nav; no underline bar). Count after a label where useful, 12px mono `--sys-text-3` ("Group sends 2" = scheduled or sending).
- Phone (below 48em): `.se-tabs` scrolls sideways (`overflow-x: auto`, no scrollbar, `scroll-snap-type: x`), items 36px, the current one scrolled into view on load.
- **SES gate note** (`.sys-note.warn.se-gate`, full width, top of Group sends and Invites while not in production): "Amazon has not approved production sending yet, so group sends and invites are off. Drafts and tests to yourself work." Link "See status" to Overview. On dev: `.sys-note` (info) "Development: emails are printed in the server log, not sent."

## 2. Overview (`/emails/`)

1. **SES strip** `.sys-panel.se-ses`, one row 48px, padding 0 `--sys-4`: label "Amazon SES" 13px 600, state badge, one line, then right "Checked 14:30" 12px mono `--sys-text-3` + "Check now" (`.sys-btn.sm`).
   - Production: `.sys-badge.ok` "Production" + "Approved. Up to 50,000 a day, 14 a second." (numbers from `GetAccount`).
   - Sandbox: `.sys-badge.warn` "Sandbox" + "Only verified addresses, 200 a day. Group sends and invites are off."
   - Dev: `.sys-badge.info` "Printed only" + "Development: emails go to the server log."
   - Check failed: `.sys-badge` neutral "Unknown" + "Could not reach Amazon. Showing the last known state from 25 Oct, 14:30." Gate stays closed when unknown.
   - Phone: badge and line wrap under the label; Check now goes full width under them (36px).
2. **Tiles** (`.sys-tiles` / `.sys-tile`, 5 across at 1440, 2 on phone): Sent today, This week, Bounces (7 days, with rate), Complaints (7 days, with rate), Suppressed (value is a link to System > Email suppressions). Bounce rate tile gets `.sys-badge.warn` above 2% and `.danger` above 5%; complaints `.warn` above 0.05%, `.danger` above 0.1% (Amazon's review lines). The badge says the word ("High"), never colour alone.
3. **Copies and contact** panel: the existing form (contact address, Gold approver CC) as field rows, unchanged behaviour (`data-problems`, risky confirm), ending with "Approvers are set in Approval."

## 3. Automatic emails

**List** (`.sys-table.se-auto`): Email (name 13px 500, e.g. "Confirm email"), Sent when ("After sign-up", "When a Gold application is approved"), Subject (mono off, ellipsis at 48ch), Last edited ("24 Oct, 18:02 · Moishe" or "Default" in `--sys-text-3`), and an "Edited" `.sys-badge` when it differs from the default. Whole row is a link to the editor (the name is the real `<a>`; row hover `--sys-subtle`). Phone: Name + Sent when stacked in cell one, Subject under them in `--sys-text-2`, Last edited hidden.

**Editor** (`/emails/automatic/<key>/`), a full page (the 480px drawer is too narrow for a preview).
- Header: back link "Automatic emails", title = email name, description = when it is sent. Actions right: "Send me a test" (secondary), "Reset to default" (secondary, only when Edited).
- Desktop grid `.se-compose`: `grid-template-columns: minmax(360px, 1fr) minmax(0, var(--se-preview-w))`, gap `--sys-4`, both columns in `.sys-panel`s. Left "Wording", right "Preview" (sticky at `top: calc(var(--sys-top-h) + var(--sys-stripe) + 16px)`).
- **Wording panel**: field rows stacked (label above, full width): Subject (28px input, placeholders allowed), Button text (only for emails with a button), Body (the token editor, below), then the placeholder palette.
- **Token editor** `.se-editor`: the code-view technique (a transparent `<textarea>` over an `aria-hidden` `<pre>`; both share one font rule: Figtree 13px / 20px, no padding difference, `white-space: pre-wrap`). Min height 280px, grows with content to 560px then scrolls; 1px `--sys-control` border, `--sys-radius`, focus ring as System. In the pre layer a known placeholder `{first_name}` is drawn as a chip using background and `box-shadow: 0 0 0 2px` of `--se-token-bg` with `--se-token` text (no padding, so the caret stays aligned); unknown: `--sys-danger-bg` tint, `--sys-danger` text and a wavy 1px underline. `{button}` must sit on its own line; it shows as a chip like the rest.
- **Palette** `.se-palette` under the body: label "Placeholders" 12px `--sys-text-2`, then a wrap of `.se-token` buttons (24px, mono 12px, `--se-token-bg`, `--se-token`, `--sys-radius`), each with a 12px `--sys-text-3` meaning beside it on hover/focus via `title` and in a visually hidden span ("{first_name}, Member's first name"). Clicking inserts at the caret (or the last-focused field: subject or body) and returns focus there. Only this email's placeholders are listed.
- **Errors**: while typing, an unknown placeholder shows inline under the field as `.sys-error`: "{frist_name} is not a placeholder for this email. Pick one from the list." Save with problems opens the problems modal (Subject / Body, short message), closes back to the first bad token with the caret on it. `{button}` missing in an email that needs it: "This email needs {button} so people can confirm."
- **Preview panel**: header "Preview" + segmented `.sys-seg` "Desktop" / "Phone" (buttons with `aria-pressed`). Body: `--sys-bg` fill, padding `--sys-4`, the email in an `<iframe class="se-frame" title="Email preview, desktop width" sandbox>` whose `srcdoc` is the real `_base.html` render with sample values (Desktop 640px wide, Phone 375px, centred, 1px `--sys-line`, no shadow). Above the frame, 12px `--sys-text-2`: "Subject: Confirm your Spa 99 email" and "Sample: Daniel, Gold". Refresh: HTMX POST 400ms after the last keystroke; while waiting the old frame stays at `opacity: .6` (100ms); first load a `--sys-subtle` block with the email's proportions. Preview error: "Could not draw the preview. Your wording is safe." + Retry.
- **Save**: the shared `.sys-savebar` ("2 unsaved changes", Discard, Save; Cmd/Ctrl+S). Logged; toast "Saved." with Undo. **Reset to default**: `confirmModal` title "Reset Confirm email to the default wording?", body "Your subject and wording are replaced. Undo is in the audit log.", button "Reset". **Send me a test**: sends the current draft (saved or not) to the signed-in account email; toast "Test sent to moishe@... ." (dev: "Test printed in the server log."). Disabled with errors, reason beside it: "Fix the placeholders first."
- Phone/tablet (below 64em): one column; a `.sys-seg` "Write" / "Preview" at the top switches panels (one idea per screen); the width toggle hides (phone width only). Editor font 16px / 24px.

## 4. Group sends

**List** (`.sys-table.se-sends`): Subject, Group, Kind (News / Service), Status, People (mono), When. Header action "New group send" (primary; allowed in sandbox, only sending is gated). Status chips (`.sys-badge`): Draft (neutral), Scheduled (info, "Thu 5 Nov, 09:00"), Sending (info + inline `.se-progress` and "412 / 1,200" mono), Sent (ok), Stopped (neutral), Cancelled (neutral). Empty: one 64px row "No group sends yet." + "New group send".

**Composer** (`/emails/sends/new/`, `/emails/sends/<id>/`): the same `.se-compose` grid. Left panel, top to bottom, each block headed by a 13px 600 label:
1. **Who** `fieldset.se-groups` (radio cards, `grid-template-columns: repeat(auto-fill, minmax(200px, 1fr))`, gap `--sys-2`). Card `.se-group`: 1px `--sys-line`, `--sys-radius-lg`, padding `--sys-3`; name 13px 600, count 13px mono right, one line 12px `--sys-text-2`. Chosen: `--sys-selected` fill, 1px `--sys-control` full border, a check icon. Cards: Everyone registered; By tier (reveals a tier `.sys-seg`); Gold members; Opted in to news; Email not confirmed; Registered between (reveals two date inputs); Gold applicants (reveals a status select). Phone: one column, cards 48px min.
2. **Kind** `.sys-seg` two radios: "News" / "Service message", and the one line under it changes: News "Goes only to people who chose to hear news. Includes an unsubscribe link." Service "Goes to everyone in the group. Only for things they need to know, such as booking opening."
3. **Count line** `.se-count` (`aria-live="polite"`): "312 will get this. 872 not opted in and 4 suppressed are skipped." Counting state: "Counting" in `--sys-text-3`. Zero: `.sys-note.warn` "Nobody in this group can get this. Try another group or kind."
4. **Message**: Subject + Body with the token editor and palette (news also carries `{unsubscribe}`, added automatically in the footer and shown in the preview; not removable).
5. **When** `.sys-seg` "Send now" / "Schedule"; Schedule reveals date + time inputs with "London time" beside them.
- Bottom actions (in the save bar): "Save draft", "Send me a test", then the primary named exactly: "Send to 312" or "Schedule for Thu 5 Nov, 09:00". Primary disabled by the SES gate with the reason written beside it, 12px `--sys-text-3`: "Off until Amazon approves production sending."
- **Confirm** (`confirmModal`, danger tone on LIVE): title "Send to 312 people?", body "News: Opening week. People who are not opted in and suppressed addresses are skipped. This cannot be unsent." Button "Send to 312". Scheduled: title "Schedule for Thu 5 Nov, 09:00?", body adds "You can cancel until then."
- **Sending** (detail page): a panel with `.se-progress` (6px bar, `--sys-subtle` track, `--sys-accent` fill, `role="progressbar"` with `aria-valuenow/max`), "Sending 412 of 1,200" mono, "About 2 minutes left", and "Stop sending" (secondary; confirm "Stop sending? 788 people will not get it."). HTMX polls every 5s. A visually hidden `role="status"` region announces at start, every 25%, and at the end (not on every tick).
- **Done**: `.sys-note.success` "Sent to 1,196 on 5 Nov at 09:04. 4 skipped (suppressed)." + "Bounces so far: 2" linking to suppressions. The message is read-only; "Copy to a new send".
- **Errors**: worker failure mid-send: `.sys-note.error` "Sending stopped at 412 of 1,200: Amazon refused the rest. Nothing was sent twice." + "Resume".

## 5. Invites

- **Add** panel: `.sys-seg` "Paste" / "Upload CSV". Paste: textarea (mono off, 8 rows) with help "One person per line: name, email." Upload: `.se-drop` 96px area, 1px dashed `--sys-control` full border, `--sys-radius-lg`, "Drop a CSV here or choose a file" (the text is a real file input label); drag-over `--sys-subtle` fill. Then "Check list" (primary).
- **Review** panel: filter chips (`.sys-pill`, `aria-pressed`): "All 59", "Ready 48", "Duplicate 3", "Already a member 5", "Suppressed 1", "Invalid 2". Table `.se-review`: Name, Email (mono), Check badge: Ready (ok), Duplicate (neutral, "Same as row 12"), Already a member (info), Suppressed (danger), Invalid email (danger). Invalid rows are editable in place (System inline edit) and re-check on Enter; everything not Ready is skipped and says so. Actions: "Start again" (secondary), "Send 48 invites" (primary, same SES gate and reason). Confirm: "Send 48 invites?", body "11 are skipped. Each person gets a personal Register link." The invite wording itself is the "Register for Spa 99" automatic email (link "Edit the invite wording").
- **Invite list** (`.sys-table.se-invites`, under the panels): Name, Email, Status (Sent neutral, Link opened info, Registered ok, Bounced danger), Sent ("25 Oct"), and "Send again" (`.sys-btn.sm`, not for Registered/Bounced). Summary above it, 12px mono: "120 invited · 41 opened · 23 registered · 2 bounced". "Link opened" counts visits to the personal link (no pixels; tracking stays off).
- Sending invites uses the group-send progress pattern inline in the panel.

## 6. Unsubscribe page (website, not System)

- `/unsubscribe/<token>/`, website shell (light brand, header and footer), `--color-cream` page, content centred, headline width `--measure-display`, body `--measure`, top padding `--space-6`.
- Opens already done: "You're unsubscribed from Spa 99 news." (Signika, `--text-2xl`, `--tracking-display`, `--color-espresso`), one line under it in Figtree `--text-body` `--color-text-muted`: "You'll still get emails about your account and bookings."
- Signed-in owner of the address: one secondary button "Subscribe again" (POST); after it: "You're subscribed to Spa 99 news again." Not signed in: text link "Sign in to subscribe again".
- Bad or old link: "This link has expired. You can change emails in My Spa 99." No error codes.
- Build note for the developer: the mail-client one-click (List-Unsubscribe-Post) is a POST; the page itself should unsubscribe through a POST sent on load (with a `<noscript>` button), so link scanners that only GET do not unsubscribe people.
- Motion 7B: the group rises 12px (8px phone) and fades in, 0.8s `--ease-soft`; instant under reduced motion. AA: espresso on cream 10.95, muted 5.32.

## 7. Tokens (proposed additions to BRAND.md "System" section, derived, no new hues)

| Token | Value | Use | Contrast |
|---|---|---|---|
| `--se-token` | `var(--sys-info)` #2C5A8F | placeholder chip text | 6.06 on its bg, 7.08 on white |
| `--se-token-bg` | `var(--sys-info-bg)` #E7EEF7 | placeholder chip fill | decoration |
| `--se-preview-w` | `640px` | desktop preview frame (email is 560 + 2 x 24 padding + air) | |
| `--se-preview-phone` | `375px` | phone preview frame | |

Everything else is existing `--sys-*`. The email frame keeps its own colours from `_base.html` (cream, espresso header, white body, espresso button).

## 8. States checklist

Empty (each list, one row + action), loading (counts "Counting", preview dimmed old frame, list "Loading" disabled button), error (inline `.sys-note.error` + Retry, never a page jump), sending (progress + live region), done (success note + toast "Sent to 1,196."), gated (visible disabled control + written reason, `aria-disabled="true"`, never tooltip only).

## 9. Accessibility

- Focus order: skip link, left nav, `.se-tabs`, header actions, left column (fields top to bottom, palette after body), preview controls, save bar.
- Palette insert returns focus to the field it inserted into. The editor textarea keeps a real `<label>`; token chips in the pre are `aria-hidden`; errors tied with `aria-describedby`.
- Radio cards are real `<input type="radio">` in a `<fieldset>` with `<legend>Who</legend>`; revealed controls follow their card in tab order.
- Live regions: `.se-count` polite; sending status polite at milestones; toast as FEEDBACK.md. Preview refresh is silent.
- Touch targets 36px on phone (`pointer: coarse` rows 40px); inputs 16px on phone.
- Reduced motion: only opacity changes (preview dim, toast, modal); no progress bar easing.

## 10. Copy (British English, calm, no exclamation marks)

Buttons name the thing: "Send me a test", "Save draft", "Send to 312", "Schedule for Thu 5 Nov, 09:00", "Send 48 invites", "Stop sending", "Reset", "Check list", "Subscribe again". Never "Submit", "OK", "Blast", "Campaign". Times 24-hour London, dates `5 Nov 2026`, counts with thousands commas in mono.
