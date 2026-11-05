# Office 2: design

For `docs/features/office-2.md`, which wins if the two differ (read as of commit 81f3c2e). Phone (375) first, computer (1440) second. "Phone" means below `64em`, as in the rest of the Office.

Owner changes already applied here: no link to the website anywhere in the Office, no number filters on Leads, Gold reads £199 + VAT everywhere including the public site, nothing answers the 020 number, and leads emailed with no mobile move to Archived.

**How this was checked.** Chromium ran with `--single-process --no-zygote --disable-gpu`. A throwaway mock using the real `office.css`, `app.css` and self-hosted fonts was measured at 320, 375, 1280 and 1440 and screenshotted at 375 and 1440: Home, Revenue and Approvals, plus the Reach out buttons and the add-your-number form. Widths marked "measured" come from that run. There was no horizontal scroll at any width. Not seen: a real iPhone, or the built pages. Contrast ratios are calculated. All figures below are samples.

**Tokens.** Existing `--office-*` and brand tokens throughout. Only additions:

| Addition (proposed, add to BRAND "Office tokens" when built) | Value | Why |
|---|---|---|
| `--office-ring-pair` | `7.5rem` | Two rings to a card. `--office-ring` is 6rem on phone (too small for money) and 9.5rem on computer (does not fit a third of the page). |
| Icon `i-coin` in `_icons.html` | `<circle cx="12" cy="12" r="8.5"/><path d="M14.6 9.2a2.5 2.5 0 0 0-4.8.9c0 1.5.7 2.3.7 3.5 0 .9-.5 1.6-1.3 2h5.9M8.9 12.5h4.3"/>` | Revenue tab. A pound in a circle, same 24 grid and 1.5 stroke as the set. |

No new colours.

## The press, used everywhere

One behaviour for rings, cards, rows and tiles, so it is specified once.

- On press: background `--office-sunken`, instantly, plus scale 0.99 on rows and cards. On release: fades back over `--office-dur-lift` (250ms) with `--ease-soft`.
- CSS `:active` alone is not enough. iOS barely shows it on a quick tap and it can clear before the page changes. Add one small delegated script: `pointerdown` adds `.is-pressed` to the closest `[data-press]`, and it stays at least 120ms. `pointercancel` clears it, so a scroll that starts on a row never flashes it.
- A control inside a row (Approve, Mark done, Archive) does not press the row.
- A row with no link (an activity row with no `href`) has no press and no pointer cursor.
- Reduced motion: the tone stays and the scale goes. It is feedback, not movement.
- Computer: the existing hover stays. Hover only under `(hover: hover) and (pointer: fine)`.

Text on the pressed tone stays AA: espresso 10.13, muted 5.38.

## 1. Phone Home

**Top of the page.** Header shows the mark and "Home". No greeting, no range bar, no website link (owner, 5 Nov). The payment warning stays first when there is one, because it has a deadline.

**Order on phone.** Decided by what Barry opens the phone for: first what needs him, then what it is worth, then the rest as it is today.

1. Payment warning (only when due)
2. Waiting for approval
3. Approved
4. Revenue
5. The journey
6. Leads
7. Recent activity
8. What people want
9. Site visitors
10. Page views
11. Latest registrations

Hidden on phone only: greeting, range bar, Gold applications, Waiting for you, Hot leads.

**Range.** Phone stays on All. Today the range is chosen by `data.range` and a saved default, and the server cannot see the screen width, so hiding the bar with CSS is not enough. A phone could silently show 30 days with no way to change it. The dashboard script must ask for `range=all` below `64em`.

**The three cards.** `o-card`, gap `--space-3`, padding `--space-4 --space-3 --space-3`. Title `--text-lg` Signika. Gold is always left and Memberships right, so the eye learns the places.

Every ring has the same four parts:

| Part | Style | Waiting for approval | Approved | Revenue |
|---|---|---|---|---|
| Middle | Signika 500, 1.5rem, tabular, no wrap | `9` | `3` | `£597` |
| Line 1 | `--text-sm`, weight 600 | Gold | Gold | Gold |
| Line 2 | `--text-sm`, muted | waiting | approved | estimate |
| Line 3 | `--text-sm`, muted | of 12 applied | of 12 applied | of £2,388 possible |

Memberships reads `16 / Memberships / waiting / of 50 registered`, then `32 / Memberships / approved / of 50 registered`, then `£150k / Memberships / estimate / of £224k possible`.

Three short lines, not one sentence: "Memberships approved" wrapped unevenly at 375 in the mock and pushed the rings out of line. With three lines every ring in every card lines up, and line 3 stays on one line even at 320 (measured).

**What the arc means.** Always the middle number over the total in line 3, so every ring reads "x of y".

- Gold total: every application (waiting + approved + declined).
- Membership total: every registered person (waiting + approved + declined).
- Revenue total: the estimate plus what those waiting would add.
- Declined people count in the people totals, so 16 + 32 is not 50 when 2 are declined. That is correct and matches the Registered line (section 4).

**Revenue card.** Title "Revenue", under it `--text-sm` muted "12-month estimate, excluding VAT". This line never goes.

**Money in a ring.** Whole pounds with a comma up to £9,999 (`£597`, `£9,950`). From £10,000, compact: `£57.5k`, `£150k`. From £1m, `£1.25m`. Sample widths at 1.5rem: `£150k` 61px against 99px of room inside the ring at 375 (measured). Exact figures are on the Revenue page, and in the `aria-label` of the link.

**The ring.** `--office-ring-pair`, `width: min(var(--office-ring-pair), 100%)`, stroke 7.5 in the 100 viewBox (9px). Thinner than the journey rings, because two large rings at 10.4 felt heavy.

- Colour keeps the Office rule: Gold is ochre on ochre track, Memberships is clay on clay track.
- Ochre on surface is 2.81, under 3:1, so the arc must never be the only carrier. The SVG stays `aria-hidden` and the words carry the number.
- Zero total: closed track, no arc dot, line 3 reads "none yet".
- Reuse the `.o-ring-*` markup, not its size or stroke.

**Motion.** Arcs draw with the existing keyframes and `--office-dur-ring`, both rings of a card together on phone (BRAND: no stagger on phone), 100ms apart on computer. Once a session only: Home is opened many times a day, so later visits show the final state. Numbers never count, because money never animates and all rings should behave alike. Reduced motion: static.

**Tapping.**

| Card | Target | Opens |
|---|---|---|
| Waiting, Gold | The left half | Gold, `?status=waiting` |
| Waiting, Memberships | The right half | Approvals, Waiting |
| Approved, Gold | The left half | Gold, `?status=approved` |
| Approved, Memberships | The right half | Registered, Membership |
| Revenue | The whole card, one link (`o-card--link`) | Revenue page |

- Each ring link fills its half of the card from the card's title to its foot, gap `--space-2`. At 375 a target is 148 x 205 (measured). There is no small circle to aim at.
- The title of a two-way card has no target, because it cannot choose between two places. Revenue goes to one place, so its whole card is one link.
- Screen reader label, for example: "9 Gold applications waiting, of 12 applied".

**Computer.** Greeting and range stay; Gold applications, Waiting for you and Hot leads stay.

- The three cards sit in their own row under the greeting and everything else moves down one row.
- Side by side from `80em`: at 1280 a card is 299 wide, at 1440 it is 350, and the ring holds 120 (measured). Below `80em` they stack full width, because at 1024 a third of the page leaves rings about 70px wide. This adds no new token: the Office already uses `80em`.
- Card padding stays `--space-4`, not the usual computer `--space-5`, or the rings shrink.
- These cards are true totals and ignore the range. They must not morph when the range changes.

## 2. Phone tabs

Five, left to right. Bar height `--office-tabbar-h`, existing active pill.

| Tab | Icon | Label | Width at 320, in a 64px slot (measured) |
|---|---|---|---|
| Home | `dashboard` | Home | 32 |
| Approach list | `list-checks` | Approach | 52 |
| Analytics | `analytics` | Analytics | 49 |
| Leads | `address-book` | Leads | 31 |
| Revenue | `i-coin` (new) | Revenue | 46 |

"Approach list" does not fit, so the phone says "Approach". It comes from `office_outreach_title|first_word` so it follows the System setting; the header and the computer rail keep the full title.

No tab badges. Gold's badge goes with its tab because the waiting number now sits on Home, and a calm bar is the point.

Assistant is hidden on phone, stays on computer. The computer rail keeps every item and gains Revenue and Approvals. The WhatsApp item and the More button and sheet are removed.

**No tab, how you get there.** Each of these keeps the bar visible with Home lit, because each is reached from Home. Use a `data-under-home` body attribute styling the Home icon pill, without `aria-current` on Home, so assistive tech still hears the true page. Each page header has `o-back` to where you came from.

| Page | Reached from |
|---|---|
| Approvals | Waiting ring, the Registered line, Revenue "See who is waiting" |
| Gold | Gold rings, the link on Approvals, the person menu |
| Registered | Approved ring, Registered tile on Leads, "See everyone" on Home, the person menu |
| Invited | The person menu |

**People without `can_see_all`.** Today the Gold item is the only one they get. If Gold is simply hidden on phone their tab bar is empty, so hide it only when `office_can.can_see_all`. They still see one Gold tab.

**Person menu** (`o-person`), in this order. Notifications goes with push. Two groups, separated by `--space-2`, no rule.

1. Name, role
2. Registered
3. Gold, with waiting count in `o-count`
4. Invited (only with `can_export`)
5. Change password
6. Sign out

Items 2 to 4 show on phone only, because the rail has them on computer. All rows `min-height: 2.75rem`. The disc itself grows to 2.75rem as a target on `pointer: coarse` (it is 2.25rem today).

## 3. Revenue page

Header "Revenue". Light page, same cards. Honest in three places: the card label, the line under the number, the note at the foot.

**Phone order**

1. **Total card** (`o-card`).
   - `--text-sm` muted: "Estimate from approved people"
   - `--office-stat-lg` Signika: `£150,213`
   - `--text-sm` muted: "A year, excluding VAT. Not money received."
   - The four-figure grid (below). The big number is the answer; the grid is for anyone checking it.

2. **The four-figure grid**, one component used everywhere on the page. Three columns, tabular, right aligned. Excluding VAT is weight 600, because that is the number all prices are stated in.

   ```
                      A year     A month
   Excluding VAT    £150,213     £12,518
   Including VAT    £180,256     £15,021
   ```

   It held at 320 without wrapping (measured). No year/month or VAT switch: a switch hides half of what Barry asked to see, and he should never wonder which state it is in.

3. **By plan and tier**, one card per plan in plan order, Gold last. Head: name in `--text-lg`, count at the right ("17 members"). Then the grid. Foot in `--text-sm` muted: "Average £4,788 a year for each member". Gold's foot reads "£199 + VAT a year for each member".

4. **Possible, from those waiting.** A different material, so it cannot be read as part of the money: `--office-sunken` with no shadow, against surface cards with a shadow, and no big number.
   - Heading: "Possible, from those waiting"
   - Line: "Not counted above. Only if they are approved."
   - The grid, then rows of `--text-sm`: "Tier 2, 8 waiting ... £38,304" (a year, excluding VAT)
   - Quiet link: "See who is waiting", to Approvals

5. **Note**, muted, on the page: "An estimate for 12 months at today's prices. Each member counts at his own price, including a kept sale price. VAT at 20%."

**Empty:** the total card shows `£0` and "Nothing approved yet, so there is nothing to estimate." The Possible panel still shows if people wait.

**Rules for the numbers**

- Work in exact pence and round only for display, whole pounds. So rows may differ from a total by £1; never add up the rounded figures.
- Gold comes from `Plan.annual_fee`, not a typed 199 (it is editable in System > Plans).
- VAT comes from the VAT setting. The note quotes that setting too.
- Membership year is his own monthly price x 12.
- Declined counts in neither approved nor possible.

**Computer.** 12 columns. Row 1: total card spans 7, Possible panel spans 5, equal height, so the two are visibly side by side and visibly different. Row 2: one full-width table (`o-card`) in place of the plan cards: Plan, Members, Year ex VAT, Month ex VAT, Year inc VAT, Month inc VAT, Average a member a year, then a bold All row. Gold's cell has "£199 + VAT" under the name. Note below. Everything fits at 1440 with no scroll inside the table (mock). Never show this table on phone.

**Gold wording elsewhere.** Everywhere the Office shows the Gold price it reads "£199 + VAT". On the public site, the compare table's "£199 a year" becomes "£199 + VAT a year". `{% gold_fee_note %}` already reads correctly.

## 4. Approval lists

New page, header "Approvals". Back to Home.

**Top, in order.**

1. Note in `--text-sm` muted: "For Barry's eyes. Nothing here changes anything for the member: his membership and emails stay as they are." It never collapses and it appears on all three tabs. It is what lets him tap freely.
2. Tabs: `o-seg` with Waiting, Approved, Declined and counts. New modifier `.o-seg--counts`: below `48em` the count stacks under the label (`display: block`, `min-height: 3.25rem`, padding `0 var(--space-1)`). "Approved 1,032" on one line needs 105px and a tab at 320 has 91 (measured), so it would overrun.
3. Search, name or email. Plan in the filter sheet. Sort newest first.
4. Quiet link: "Gold applications: 9 waiting", to Gold. Gold approval works as today, so this only joins the two.

**Waiting row, phone.** One surface card, gap `--space-3`.

- Name, weight 600.
- Email, `--text-sm` muted.
- "Tier 2, £399 a month, registered 2 days ago", `--text-sm` muted. His own price; a kept sale price reads "£249 a month (sale price)". Sample.
- Two controls, equal columns, `--control-h` (52px high, 148 wide at 375, 120 at 320, measured), gap `--space-2`.
  - **Decline, left:** no fill, muted text.
  - **Approve, right, under the right thumb:** `btn-secondary` tone with the check icon.

Not red and not espresso. Red would say something bad happens to him, and nothing does. Espresso would stack a dark bar in every card; the page is a calm list of small choices.

The row body opens his person page with the shared press. The controls sit above the row link.

**Row, computer.** A table row: Name and email, Plan and price, Registered, then Decline and Approve at the right in `btn-sm` (40px).

**Undo.** The tap acts at once, nothing asks "are you sure". A confirm on every row of 48 people would be its own annoyance when undo is free.

- The row is replaced **in place** by a strip of the **same height**: `--office-sunken`, no shadow, "Marcus Feld approved." on the left, quiet "Undo" on the right (44px).
- Fix the card's height in JS before the swap. If the strip shrinks, the next row jumps under his thumb and the next tap lands on the wrong person. This is the main way a mis-tap would otherwise repeat.
- The strip stays until he leaves or reloads, no timer. A toast would vanish in 6 seconds and cover the list.
- The swap is instant, no exit animation (BRAND 7B). The tab counts update. `role="status"` announces it.
- Failure: the row comes back, toast "That did not save. Please try again."
- On the Approved and Declined tabs each row has a quiet "Back to waiting" (44px), so a mistake found next week can still be fixed. Row line: "Approved by Barry, 3 Nov". One step only: back to waiting, then decide again.

**Empty states** (`o-empty-row`)

- Waiting: "No one is waiting. New registrations appear here."
- Approved: "No one approved yet."
- Declined: "No one declined."
- Search with no result: "No one matches that." with Clear.

**Registered page line.** First thing on the page: a tonal row (`--office-sunken`, `--office-radius`, `min-height: 3.25rem`, chevron right), whole row one link with the press, to Approvals Waiting.

- `32 approved, 16 left to approve`
- With declined: `32 approved, 16 left to approve, 2 declined`. Otherwise the Registered total on Leads (50) cannot be matched by what he sees.
- None left: `All 48 approved`, linking to the Approved tab.
- No one yet: the line does not show.

## 5. Registered list

The list shows approved people. Every registered count elsewhere stays the true total, with no "moved on from leads".

**Computer.** Two full tables stacked, each its own `o-card` with a heading ("Membership", "Gold"), its own count, sort and Show more. The filter bar stays above, with one `o-seg`: All, Membership, Gold (`?table=`).

- **Membership columns:** as today, including Gold.
- **Gold table columns:** Name and email, Approved, Verified, Marketing, Registered. No Plan, no Gold column.

**Phone.** One table at a time. The `.o-seg--counts` switch replaces All: Membership, Gold.

Stacked tables cannot work here: the first would load forever by itself and the second would never be reached. The URL keeps `?table=gold` so the back button returns to the same table.

**Filters.** The existing ones stay. Plan only applies to Membership, so it hides on Gold. Sale price and Payment stay.

**The Gold column.** Text only: "Applied", in `.o-badge--st-applied`. Shows for an application still in play (waiting, sent back, awaiting final approval). Empty for everyone else, including an approved Gold member and a declined applicant, because a declined one is no longer going anywhere. It links to the application on computer. On phone it is a plain tag on the badges line, as the row keeps one target (office-mobile rule); his person page has the link.

## 6. Leads and Approach list

**Leads, top tiles.** Two links, `o-leadsum-tile--link`, two columns, with the press. Grid becomes `repeat(2, ...)`.

| Tile | Number | Computer line | Opens |
|---|---|---|---|
| Leads | True total: no account, not archived, not on the Approach list | No account yet | Leads, filters cleared |
| Registered | True total of registered people | Have an account | Registered |

They ignore the range and filters, and the total drops after the group send. Hot leads goes, and with it the `hot` filter link and the "Went on to register" wording.

**No number filter** (owner, 5 Nov). The mobile stays visible on the row when there is one.

**Emailed.**

- Tag: a text pill "Emailed 5 Nov", new `.o-badge--emailed` (`--office-sunken`, espresso, 10.13; on the phone card, on the badges line). Shown on Leads and the Approach list.
- Filter on Leads: a chip "Emailed" in the filter sheet (`o-chip`), next to the existing chips.
- Filter on the Approach list: same chip, in the bar, because this list has so few filters that a sheet would be silly.
- Bounced leads show the existing "Possible fake" pill **instead of** Emailed, since the email did not reach them. They stay in Leads.

**Archived, reason "Emailed, no number".** The existing Archived view holds them with no new design: the reason sits in `c-reason`. Their "Archived by" line reads "Group email, 5 Nov", not "Archived by the team". Adding a number, by staff or through the link, moves him to the Approach list and his row leaves Archived.

**Bounces arrive after the send.** A lead with no mobile is archived when the email goes, but the bounce comes minutes later. When it does, he must return from Archived to Leads with Possible fake, and the reason clears. Otherwise bounced addresses hide in Archived as if the email had reached them.

**New leads must give a mobile** (spec). At the journey's email step the mobile stops being optional, and the line encouraging it goes. Keep the existing field and error wording.

**Approach list, tabs.** Open and Done. The Registered tab goes, because registering removes him automatically.

**Approach list, row actions.** On a phone card, under the content:

- `Mark done`, `btn-secondary btn-sm`, 44px on coarse pointers.
- Two quiet links to the right of it: `Back to Leads`, `Archive`. Both `o-quiet`, 44px.

Rows that are not leads (Gold applicants, staff additions) keep `Remove` instead of these two, as they have no Leads to go back to.

- **Back to Leads:** no confirm. The row goes, toast "Moved back to Leads." with Undo. Same pattern as the Archived view.
- **Archive:** opens the existing archive dialog, so the optional reason is kept. Toast with Undo.

**Whole-row tap.** Every list row in every list is one link with the shared press: `.o-rowlink::after`, `data-press`. That includes the Home lists (`o-latest-row`, `o-feed-row`, `o-wait-link`) and the Approach list, where a row with no `href` today should link to his page if he has one. Row controls keep `position: relative; z-index: 1`.

**Add to list.** On lead and person pages the button becomes the quiet link Gold already uses: `o-quiet o-addlist`, icon, "Add to Approach list", underlined on touch (there is no hover to reveal it), centred under the two reach out buttons, 44px. Once on the list, the existing `_onlist.html` state replaces it.

**Auto-loading on scroll.** All long lists below `64em`: Leads, Archived, Approach, Registered, Gold, Approvals, Invited, Assistant.

- `IntersectionObserver` on `.o-more-row`, `rootMargin: 0px 0px 600px 0px`, so the next rows are usually there before he arrives. Never a scroll listener.
- Keep the `Show more` link in the markup. It is what shows with no script, and it stays the only way on computer, where the extra click is no cost and the page has a foot.
- **Loading:** three dots, 8px, `--office-muted`, gap `--space-2`, centred in a row `min-height: 3.25rem`. Opacity only, 0.25 to 1, 1200ms `ease-in-out`, 160ms apart. Shows only after 150ms, so a quick load does not flicker. `role="status"` with hidden text "Loading". No spinner: BRAND bans rotation, and a small slow breath is enough.
- **Reduced motion:** the word "Loading" in `--text-sm` muted, no dots.
- **End of the list:** `--text-sm` muted, centred: "That is everyone." Only after at least one load; a short list has the count in its total line already.
- **Failure:** "Could not load more." and a quiet "Try again", 44px. The observer stops until he taps.
- **Clearing the bar:** `.o-main` padding-bottom becomes `calc(var(--office-tabbar-h) + env(safe-area-inset-bottom) + var(--space-5))`. Add `scroll-margin-bottom` of the same to the more row and end line. Check with `body[data-has-bar]`, which sets its own value.
- **Coming back.** Tap a row, open his page, go back: he must land on the same row, even with 200 loaded. Keep the loaded page number in `history.replaceState` and restore both rows and scroll position. A list that returns to the top after each person makes the auto-load worse than a button.
- Do not move focus on load. Filter changes reset to page 1.

## 7. WhatsApp button

A plain link, nothing else. All Start, Open, unconfigured, view-only and STOP states go.

```html
<a class="btn btn-primary btn-block o-wa-btn" href="https://wa.me/447700900123"
   target="_blank" rel="noopener noreferrer" aria-label="WhatsApp Daniel on +44 7700 900123">
  <svg class="o-icon"><use href="#i-whatsapp"/></svg><span>WhatsApp</span>
</a>
```

**Label:** "WhatsApp", one word, next to "Email". Verbs like "Start chat" promised something the Office no longer does. The number in `wa.me` is digits only.

**With Email, in Reach out.** Two equal buttons in one row on phone (`o-channels` with two columns, gap `--space-2`), 146 wide at 375 and 118 at 320, label fits in both (measured). WhatsApp left, Email right. It is the channel the business now runs on, so WhatsApp is the one primary. Gold page: both secondary as today, so Approve stays the one primary. In the narrow computer rail keep the stack, WhatsApp on top.

**No mobile.** No grey disabled button: it looks broken and offers nothing. Email fills the row and takes the primary, and one muted line sits under it: "Add a number to WhatsApp him." The only Add stays in the Details row, as it is today. For view-only staff: "No mobile on file."

## 8. Sender dropdown

System's own style, so `.system select` (`--sys-ctl`) and `.se-field`, not Office components. Native select: it is the fastest control on a phone and takes no maintenance.

- **Label:** "Sender", the word System already uses.
- **Default:** the first option, the site address: `Spa 99 <hello@spa99.uk>`.
- **Listed:** then each staff member with a @spa99.uk address, by first name: `Barry Lobenstein <barry@spa99.uk>`. Name and address both, since two people can share a first name. Select only, no typing. Inactive staff are not listed.
- **Help under it,** `sys-muted se-help`: "Replies go to {reply_to}.", updated with the choice. Keeps today's truth from the radios.
- **Width:** `max-width: 28rem`. Long addresses truncate inside the native control, so keep name first.

**Where.**

- Automatic emails: `emails_edit.html`, panel "Footer and sender", replacing the site or person radios.
- Group send: `emails_mailing_form.html`, its own `se-block` after Who and Kind.
- The Preview shows the chosen From.

**When a chosen person goes.** The send falls back to hello@ and the page shows `sys-note warn`: "Moishe has no @spa99.uk address now. This sends from hello@ until you choose." An email must never fail or stop because a person left. Today's "Until then this email is not sent" case for the next-morning email goes with the radios.

## 9. Add-your-number page

Public, no sign-in, `noindex`. Reuses the members' entrance: `users/_shell_top.html` and `_shell_bottom.html` (espresso, swan mark, picture beside the form from `64em`), 7B restrained motion. Fields use the same parts as registration, so this adds almost no CSS. The form fitted a 375 x 812 screen in the mock, which had tighter spacing than the real page, so expect a short scroll at worst and check the button clears the fold.

**Form**

| Part | Copy | Component |
|---|---|---|
| Heading | Add your number. | `h1` |
| One line | So Barry can reach you on WhatsApp. | `signin-lead` |
| Email | Filled in and read-only | `common/_field_static.html` |
| Country | Country, default UK | `.mobile-row` |
| Mobile | Mobile, hint "UK numbers can start with 07." | `.mobile-row`, `type="tel"`, `autocomplete="tel-national"`, `enterkeyhint="done"` |
| Consent | See below | `common/_check.html`, no pre-tick |
| Button | Add my number, working text "Saving" | `btn-primary btn-block` (gold on espresso, 6.17) |
| Foot | How we use your details | The existing privacy link |

**Consent.** The existing tick fits exactly, so use it word for word from `journey/copy.py` with its consent version: "Yes, Spa 99 may email and WhatsApp me about opening and offers. I can stop at any time." Required for this page, because the page exists to let us WhatsApp him. If unticked: "Please tick this so Barry can message you."

**Errors** (inline, `.feedback`)

- Wrong number: the existing "That mobile does not look right. Check the country and the number."
- Number taken: "That number is already with us. Please check it, or message us on WhatsApp." It does not say whose.

**After**

| State | Heading | Line | Action |
|---|---|---|---|
| Success, same page | Thank you. | Barry will be in touch on WhatsApp. | None |
| Used link | Your number is already with us. | Barry will be in touch on WhatsApp. | None |
| Expired or tampered, same words for both | This link has ended. | Message Barry on WhatsApp instead. | `common/_whatsapp_button.html` |

Expired does not say why and shows no email: a tampered link must learn nothing. Success has no button; he is finished, and asking him to go anywhere spoils that. The success state replaces the form and uses the existing 7B rise.

**Copy points.** "Add", not "Submit". The email is shown so he knows it is his and does not have to type anything.

## 10. Default group email wording

A starter in `start_cards`, fully editable in the composer: "Barry's invitation". Group: all leads. Kind: News, so the unsubscribe link stays.

**Subject:** A word from Barry at Spa 99

**Body:**

> Hello {first_name},
>
> I would very much like you to join Spa 99. I approve each member personally, and those I approve receive special discounts and prices.
>
> Please WhatsApp me on {whatsapp_number}.
>
> Or, if it is easier, give me the number you have WhatsApp on and I will message you.
>
> [ Add your number ]
>
> Barry
> Spa 99

No deadline, no "limited", no hype: he is asking, and asking once is enough. "Hello there," is already the fallback for no first name. The button is his personal signed link (`has_personal_links`). `{whatsapp_number}` is the System > Settings number. Since it is signed by Barry, the sender dropdown should be set to Barry for this send if he has a @spa99.uk address.

**Before it sends.** This send moves people, so the confirm modal must say so, in plain counts:

> **Send to 412 leads?**
> 230 have a mobile and stay in Leads, tagged Emailed.
> 182 have no mobile and move to Archived, reason "Emailed, no number".
> Anyone whose email bounces stays in Leads as Possible fake.

## Questions for the owner

1. **Who sees Approvals and Revenue?** The spec says "Barry's view only", and a View-only team member sees every tab today. Designed default: both pages, their tabs and their Home cards only for people with the Approver permission or Admin level and up; a person without access gets none of them. Is that right, or Barry alone?
2. **"Free*" for Gold on the public site.** It is written as "free*" with the fee note today, and `docs/PRICING.md` says Free. Does "£199 + VAT everywhere" replace "free*", or does "free*" stay beside the note? Designed default: "free*" stays, and the price cell reads "£199 + VAT a year".
3. **Someone on Tier 2 with a Gold application.** Is he counted in both Waiting rings, and if both are approved, does Revenue count both prices? Designed default: yes to the rings, and Revenue counts one plan, the one he is on.
