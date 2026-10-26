# Spa 99: My Spa 99 (the member dashboard)

For the frontend agent (and a short backend list, section 9). Date 2026-10-23. Branch `feature/member-dashboard`. Decision: PROJECT.md 2026-10-23 (members get their own dashboard at `spa99.uk/account/`, app-style, no marketing menu; Book moves inside as "Book a visit"; the website menu shows "My Spa 99" when signed in). `docs/BRAND.md` wins on any conflict.

**Design read.** The members' room of a private club, seen through a phone. Brand look (espresso, cream, gold), not the Office: the light Office palettes and `--office-*` tokens are never used here. Only the Office phone *pattern* is borrowed (bottom tabs, safe areas, `100dvh`). Calm, few words, one idea per screen. Dials: variance 4, motion 3, density 3 (phone 2).

**Motion mode:** BRAND 7B (restrained). CSS and the shared reveal script. No GSAP, no WebGL, no swan drawing.

---

## 1. Information architecture

Four sections, the same on phone (tabs) and desktop (sidebar). Labels are always shown with the icon.

| Tab | Route | Icon (Phosphor, regular, 24px) | One idea |
|---|---|---|---|
| **Home** | `/account/` | `house-simple` | Where you stand, and what happens next |
| **Book** (title "Book a visit") | `/account/book/` | `calendar-blank` | Your first visit, in January |
| **Membership** | `/account/membership/` | `identification-card` | Your plan (or your Gold Card) |
| **You** | `/account/you/` | `user-circle` | Your details, emails, privacy, sign out |

Sub-screen: **Change password** `/account/password/` (exists) sits under You. Existing POST endpoints stay: `/account/interest/`, `/account/export/`, `/account/delete/`, `/account/password/`. Add the four icons to `common/img/icons.svg` (Phosphor, MIT, licence file already there).

### What each shows

| Section | Real data today | "Opens January 2027" (finished, not empty) |
|---|---|---|
| Home | Greeting (`account_greeting`), verify banner if unverified, plan status line (Gold / registered plan / none), opening month (`{opening}`) | Next visit tile, Visits tile |
| Book a visit | Their plan's booking window (`booking_lines` for the interest plan), opening hours (`hours_ranges` / `hours_summary`), closed for Shabbos and Yom Tov, their email for the reassurance line | The booking itself |
| Membership | Gold: flat Gold Card, "Gold member since" (`gold_since`). Others: registered plan, price ex/inc VAT, change interest (choice tiles), journey suggestion if any | Payments / billing row |
| You | Name, email, mobile (read-only, change by email), account ID + Copy, Change password, marketing emails on/off, Download my data, Delete my account, Back to the website, Sign out | None |

---

## 2. The shell

### 2.1 Desktop (from 64em): left sidebar

```
┌──────────────┬───────────────────────────────────────────────────────────┐
│ [stacked     │                                                           │
│  swan, gold] │   Good evening, Daniel.                (Signika, 2xl)     │
│              │   Tier 2 interest. We open in January 2027.               │
│ ▣ Home       │                                                           │
│ ▢ Book       │   ┌──────────────────────────┐ ┌───────────────┐          │
│ ▢ Membership │   │ espresso feature tile    │ │ cream tile    │          │
│ ▢ You        │   │ Your first visit         │ │ Membership    │          │
│              │   └──────────────────────────┘ └───────────────┘          │
│              │                                                           │
│ ← Back to    │                                                           │
│   the website│                                                           │
└──────────────┴───────────────────────────────────────────────────────────┘
```

- Sidebar `--member-rail-w` (16rem), full height, sticky, `--color-espresso` with the swan pattern at `--color-pattern` behind the lower half only. Padding `--space-5` `--space-4`.
- Top: `logo-stacked-gold.svg`, 72px tall, links to `/account/`, label "My Spa 99, home".
- Nav rows: 48px, Figtree 500 `--text-base`, icon 24px + label, `--color-text-muted-inverse` (6.50). Current: `--color-gold` text and icon (6.17) on an `--color-espresso-raised` pill (gold 5.32), `--radius-sm`, `aria-current="page"`. Hover (fine pointer): cream text, no movement.
- Bottom: "Back to the website" (`arrow-left` 16px + `--text-sm`, muted inverse, links to `/`). Sign out lives on You, not here.
- Content area: cream, padding `--space-6` top, `--space-7` left, content column `--member-content-max` (52rem), left aligned. No marketing header, no footer. One line at the very bottom of the content: "Men only. 18 and over." `--text-sm` muted.

### 2.2 Phone and tablet (below 64em): app

- `html` and `body` `min-height: 100dvh`; `viewport-fit=cover` on this layout's viewport meta; `<meta name="theme-color" content="#492E21">`; `-webkit-tap-highlight-color: transparent`; `touch-action: manipulation`; `overscroll-behavior-y: none` on `body`; inputs 16px; no hover styles (hover only under `(hover: hover) and (pointer: fine)`).
- **Top bar** `--member-topbar-h` (3.5rem) + `env(safe-area-inset-top)`, solid espresso. Left: the swan mark 28px gold, links to `/account/`. Right: "Website" (`--text-sm`, muted inverse, 44px target) to `/`. No screen title here: the screen's own large title does that.
- **Bottom tabs** `--member-tabbar-h` (4rem) + `env(safe-area-inset-bottom)`, fixed, `--color-tabbar` (espresso 96%) with `backdrop-filter: blur(16px)` (solid espresso fallback and under `prefers-reduced-transparency`), `--shadow-bar` upward, no top line. Four equal cells, each the full 64px tall target: icon 24px over Figtree 600 `--text-sm` label (minimum 14px, not 12px: this is a guest, not staff). Inactive muted inverse; current gold, icon on a 56 x 32px `--color-espresso-raised` pill.
- Content padding bottom: `calc(var(--member-tabbar-h) + env(safe-area-inset-bottom) + var(--space-5))` so nothing sits under the bar. Sides `--page-margin`, plus `env(safe-area-inset-left/right)`.
- Sub-screen (Change password): tabs hidden; top bar left shows "‹ You" (44px) instead of the mark. The form's button sits in the flow, not fixed.
- While a text field has focus (delete password on You), hide the tab bar (class on `body` from `focusin` / `focusout`) so it never floats over the keyboard.
- Messages (`_messages.html`) show as one toast above the tab bar (phone) or top right of the content (desktop), 4 s, dismissable.

### 2.3 Layout file

One base for all member screens, e.g. `users/templates/users/member/base.html` (own head with `data-page="member"`, own viewport meta, `app.css` + a new `member.css`, shared `app.js`; never `scenes.js`). Page transitions: the site's View Transitions cross-fade (opacity only, 240 ms out, 480 ms in) with `view-transition-name` on the sidebar, top bar and tab bar so they stay put while the content fades.

---

## 3. Home

Cream page. Phone order, top to bottom:

1. **Verify banner** (unverified only): cream-raised strip, 1px `--color-hairline`, `--radius-md`. "Please confirm your email. We sent a link to {email}." Quiet button "Send it again" (existing resend form).
2. **Greeting**: "Good evening, Daniel." Signika `--text-2xl`, `--tracking-display`, `--leading-tight`.
3. **Status line** (one, `--text-lg`, muted):
   - Gold: "Gold member. We open in {opening}."
   - Registered: "Tier 2 interest. We open in {opening}."
   - None: "No membership chosen yet." plus quiet link "Choose one" to Membership.
4. **Next visit tile** (the one dark element on the screen): espresso, swan pattern, `--radius-md`, padding `--space-5`. Small label "Next visit" (muted inverse), Signika `--text-xl` cream "Your first visit, in {opening}.", body "Booking opens when the doors do." Whole tile links to Book. `arrow-right` gold at bottom right.
5. **Two cream tiles** side by side from 48em (stacked on phone), cream-raised, 1px hairline, `--radius-md`:
   - **Membership**: label "Membership", value Signika `--text-lg` "Gold member" / "Tier 2 interest" / "Not chosen yet". Links to Membership.
   - **Visits**: label "Visits", value "Your visits will show here from {opening}." No zero, no empty chart.

Desktop: greeting and status on top; Next visit tile spans 7 of 12 columns, the two cream tiles stack in the remaining 5.

Not on Home: account ID, details, privacy (all on You).

---

## 4. Book a visit

One screen that previews booking without pretending it works. No buttons that look like time slots, no calendar grid, no disabled controls.

Layout:
1. **Hero band**, espresso with the swan pattern, full width of the content (phone: edge to edge under the top bar). Gold swan mark 40px (static, no draw), Signika `--text-2xl` cream: "Your first visit, in January." Body muted inverse: "Booking opens when the doors do. You'll choose your time here." Below: the month in the "Launching" style (`--tracking-launch`, gold, weight 600): "{opening}".
2. **How it will work** (cream), heading Signika `--text-xl`. Three rows, each a short label and one line, separated by space (no rules), static pills (`--pill-h`, cream-raised, espresso text, not links):
   - **Choose your day**: from their plan, e.g. "Tier 2 books two days ahead." (`booking_lines` for the interest plan; Gold or no plan: show all lines in one quiet list).
   - **Choose your time**: "Open 5am to 3am." "Closed for Shabbos and Yom Tov." (from hours data, never typed in the template).
   - **Stay as long as you like**: the Stay pills from `visit_pills()` (the spa page source), so this screen never disagrees with The spa.
3. **Reassurance** (cream-raised panel, `check` icon gold-on-espresso dot or espresso on cream): "You're on the list. We'll write to {email} when booking opens." No new field, no toggle. Unverified: "Confirm your email so we can tell you when booking opens." with "Send it again".
4. One quiet link: "See the spa" to `/the-spa/` (opens the website, same tab).

Copy check: the reassurance promises one service email to registered people when booking opens. Moishe to confirm that email will be sent (it matches the register copy "We'll write before the doors open").

---

## 5. Membership

**Gold holder**
- The flat Gold Card (`common/_gold_card.html`, CSS only, no 3D, no swing, no sheen loop), max 22rem wide, centred on phone, left on desktop.
- "Gold member since 12 March 2026." `--text-lg`. Below: "Your Gold Card perks start when we open in {opening}." Quiet link "What Gold includes" to `/gold-card/`.
- No change control (server already refuses). Line: "To change anything, write to {contact_address}."

**Registered or none**
- Heading Signika `--text-2xl`: "Tier 2" (or "Choose your membership").
- Price line `num`: "£X a month, ex VAT (£Y inc VAT)". Under it: "Nothing to pay now. Billing opens in {opening}."
- Journey line, when a finished journey is linked: "Based on your answers: Tier 2." If it differs from the interest, add quiet link "Switch to Tier 2" (same POST).
- **Change**: always visible choice tiles, not a hidden form. One tile per `interest_cards` card: name (Signika `--text-lg`), tagline, price ex VAT. `--tile-min-h`, cream-raised, `--color-control-line` 1px, `--radius-md`. Current: espresso fill, cream text, gold `check`. Tapping another tile marks it chosen instantly (radio inside a `role="radiogroup"`, label "Membership you're interested in") and reveals one button under the group: "Keep Tier 3" (primary). Success message "Your interest is updated." Phone: tiles full width, stacked. Desktop: 2 x 2 grid.
- Quiet link "Compare memberships" to `/memberships/`.

---

## 6. You

Grouped list, cream-raised panels with rows separated by space (no rules), headings Signika `--text-lg`:

1. **Your details**: Name, Email, Mobile (label muted `--text-sm` above value `--text-base`). Line: "To change these, write to {contact_address}."
2. **Account ID**: the code in `num` `--text-xl`, quiet "Copy" (label swaps to "Copied"). Line from content `id_note`.
3. **Password**: row "Change password" with `arrow-right`, whole row 56px, links to the sub-screen.
4. **Emails from Spa 99**: one switch (brand-skinned, 44px target), label "News and invitations", sub line "Now and then, never often." Saves on change (POST), toast "Saved." Booking and account emails are not affected and the line under says so: "We'll always send emails about your account."
5. **Privacy**: "Download my data" (quiet button), "Delete my account" (quiet danger text, `--color-danger`), opening the existing inline password field and confirm modal (copy unchanged).
6. **Back to the website** (row, `arrow-left`) and **Sign out** (secondary button, full width on phone). Sign out is last, alone.

---

## 7. Website menu and `/book/`

- **Remove Book** from `common/_header.html` (desktop nav and the menu dialog) and `common/_footer.html`.
- **Signed in**: "My Spa 99" to `/account/` in the header actions, the menu actions and the footer (replaces "Account"). **Signed out**: "Sign in" (unchanged).
- **Sign in lands on `/account/`**: `LOGIN_REDIRECT_URL = "/account/"` (it is `/` today in `config/settings/base.py`), a safe `next` still wins. Verify and register-confirm already land on the account.
- **Old `/book/` (recommendation)**: signed in, `302` to `/account/book/`. Signed out, keep the existing public teaser at `/book/` (no sign-in wall: most visitors have no account yet), with its "Register" button plus a quiet "Already registered? Sign in" link to `/login/?next=/account/book/`. Drop `/book/` from the sitemap (not in the menu any more). Not a `301` (the answer depends on the visitor). Internal links that pointed to `{% url 'book' %}` from signed-in surfaces go to `account_book`.

---

## 8. Tokens

Use existing brand tokens only: `--color-espresso`, `--color-espresso-raised`, `--color-cream`, `--color-cream-raised`, `--color-gold`, `--color-text-muted`, `--color-text-muted-inverse`, `--color-hairline`, `--color-control-line`, `--color-pattern`, `--color-focus` / `--color-focus-inverse`, `--color-danger`, `--shadow-bar`, `--radius-sm`, `--radius-md`, `--pill-h`, `--tile-min-h`, `--control-h`, `--tracking-launch`, the type and space scales, `--ease-soft`, `--duration-*`, `--rise`.

**Proposed additions** (derived, for `tokens.css` and BRAND section 8):

```css
/* My Spa 99 (docs/design/MEMBER.md 8). Derived. */
--member-rail-w: 16rem;                 /* proposed: desktop sidebar */
--member-topbar-h: 3.5rem;              /* proposed: phone top bar, plus safe area */
--member-tabbar-h: 4rem;                /* proposed: phone tab bar, plus safe area */
--member-content-max: 52rem;            /* proposed: content column, desktop */
--color-tabbar: rgb(73 46 33 / 0.96);   /* proposed: tab bar over content; gold 6.0+, muted inverse 6.2+ over cream content */
```

Contrast used: gold on espresso 6.17, gold on espresso-raised 5.32, muted inverse on espresso 6.50, cream on espresso 10.95, espresso on cream-raised 11.71, muted on cream-raised 5.69. Gold never as text on cream.

---

## 9. Backend items (small)

1. Routes and views: `/account/` (home), `/account/book/`, `/account/membership/`, `/account/you/`; the current `account` view splits; `account_interest` redirects back to Membership.
2. Context: `is_gold`, `gold_since`, `interest` + its card, `verified`, the latest finished linked journey's suggested plan, the interest plan's booking line, hours, `visit_pills()["stay"]`.
3. `POST /account/emails/` to set marketing consent (with timestamp), rate limited.
4. `LOGIN_REDIRECT_URL = "/account/"`; `/book/` view: signed-in redirect; sitemap drops `/book/`.

---

## 10. Motion (7B)

- Screen title group: hero entrance on load (0.8 s, rise `--rise`). Tiles: one card collection (1 s, 0.1 s delay); stagger 0.1 s on desktop for the 2 to 3 Home tiles only, none on phone.
- Sidebar, top bar, tab bar, toasts' position: never animated. Current tab changes instantly.
- Press: tiles and buttons scale 0.99 on press (0.25 s), 1.01 hover on fine pointer only. Tall tiles (Next visit) use opacity 0.9 on hover instead of scale.
- Choice tiles: chosen state instant; the "Keep ..." button fades in (0.4 s, opacity only).
- Toast: opacity in 240 ms, out 240 ms.
- Reduced motion: everything visible at once; no view transition.

**Accents and states.** Never a one-sided accent (left/right stripe, inset side shadow, or a ::before bar). Use no border with a soft shadow, a tinted background, or a full hairline. Selected/active states use background tint, weight or an icon. The "confirm your email" banner: no border, `--shadow-toast`, raised cream, info icon.

## 11. Accessibility

- `<nav aria-label="My Spa 99">` for both sidebar and tab bar (only one in the DOM per breakpoint, or the other `hidden`). `aria-current="page"` on the current item. Labels always visible.
- Skip link "Skip to content". Page titles "Home | My Spa 99", "Book a visit | My Spa 99", and so on. One `h1` per screen (the large title).
- Targets 44px minimum (tabs 64px, rows 56px). Focus ring: espresso on cream, gold on espresso, 2px with 2px offset, never removed.
- Choice tiles are real radios; the switch is a `button role="switch" aria-checked` or a checkbox; the copy button announces "Copied" via `aria-live="polite"`.
- 200% zoom and 320px width: no sideways scroll; tab labels may shrink to `--text-sm` but never truncate.

## 12. Acceptance checklist

1. Sign in with no `next` lands on `/account/`; with a safe `next`, lands there.
2. 375: top bar with swan and "Website", four labelled tabs, current in gold on its pill; nothing under the home indicator or the notch; no tap flash; no zoom on focusing a field; `100dvh`, no jump when the address bar hides.
3. 1440: espresso sidebar with stacked swan, four items, "Back to the website" at the bottom; cream content column, no marketing header or footer.
4. No `--office-*` token and no Office colour anywhere in member templates or `member.css`.
5. Home shows the greeting, the right status line for Gold / registered / none, the Next visit tile and the two tiles; unverified shows the banner with a working resend.
6. Book a visit has no fake controls; its lines come from plan and hours data and match The spa; the reassurance shows the member's email.
7. Gold holder: Membership shows the flat card and "Gold member since ..."; no change control. Others: choice tiles, instant chosen state, "Keep ..." saves and shows "Your interest is updated."
8. You: details, copy ID, password sub-screen (tabs hidden, "‹ You"), emails switch saves, export downloads, delete asks for the password and confirms, sign out works.
9. Website: Book gone from header, menu and footer; signed in shows "My Spa 99"; signed out shows "Sign in". `/book/` signed in redirects to `/account/book/`; signed out shows the teaser with the sign-in link carrying `next`.
10. No GSAP, WebGL or swan drawing loads on member pages; reduced motion shows everything at once.
11. Copy: UK English, no exclamation marks, no hype; every screen has one large title and at most one primary button.
12. Lighthouse 375 mid phone: accessibility 95+, CLS 0, LCP 2.5 s or less.
