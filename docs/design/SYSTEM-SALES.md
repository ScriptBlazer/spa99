# Sales: design brief

Spec: `docs/features/sales.md`. Brand: `docs/BRAND.md` (tokens, 7B motion, "never a one-sided accent"). System look: `docs/design/SYSTEM.md` and `docs/design/SYSTEM-EMAILS.md` (13px, hairlines, 4-6px corners, no shadow at rest). Feedback: `docs/design/FEEDBACK.md` (shared toast, the one modal via `confirmModal`, never browser dialogs).

**Design read.** Three surfaces, two languages. On the website a sale is a quiet notice from the front desk, not a promotion: one slim espresso line above the header, the regular price stays the headline number, the sale is one calm sentence beside it. No red, no strike-through, no badges, no racing digits. In System it is plain developer tooling in the existing `sys-*` language. Dials: website variance 2, motion 1, density 3; System variance 1, motion 1, density 8 (phone 6).

**Rules that apply everywhere here.** Only tokens from BRAND.md (plus the marked additions in section 6). No one-sided borders or stripes: separation is tone (background step), a full hairline, or nothing. No em dashes in any copy. Prices never animate.

---

## 1. Public sale bar

### 1.1 Where it shows

- Every page that uses the full site header (`common/_header.html`): Home, The spa, Virtual tour index, Memberships, Gold Card, Book, Visit us, Register, Sign in, legal pages, unsubscribe.
- Not shown on: reduced-header pages (journey, Gold application, error pages: `base_reduced.html` overrides the block empty, they are one task each), My Spa 99 (`member_base.html`, the membership screen says the kept price instead), the full-screen tour rooms if they are a fixed canvas, Office, System, bare pages.
- Markup: a new `{% block sale_bar %}{% include "common/_sale_bar.html" %}{% endblock %}` in `base.html` **after the skip link and before the header block**. The include renders nothing unless a sale is live (or a developer is previewing, 1.9). The server decides on each request; the client only counts down and removes it at the end.

### 1.2 Anatomy

```
375px
+---------------------------------------------+
| Christmas sale · 20% off · 3d 04h        [x]|  44px, espresso-raised
+---------------------------------------------+
| [swan] SPA 99                          Menu |  header (unchanged)

1440px
+-----------------------------------------------------------------------------------+
|        Christmas sale · 20% off Tier 2 and Tier 3 · ends in 3d 04h 12m  ->     [x]|  40px
+-----------------------------------------------------------------------------------+
| [swan] SPA 99        The spa  Virtual tour  Memberships  Gold Card  Visit us  Sign in |
```

```html
<div class="sale-bar on-dark" data-sale-bar data-sale="{{ sale.pk }}" data-ends="{{ sale.ends_at|date:'c' }}" data-now="{{ now|date:'c' }}">
  <div class="container sale-bar-inner">
    <a class="sale-bar-link" href="{% url 'memberships' %}#plans">
      <span class="sale-bar-name">Christmas sale</span>
      <span class="sale-bar-sep" aria-hidden="true">·</span>
      <span class="sale-bar-offer"><span class="sale-bar-pct">20% off</span><span class="sale-bar-plans"> Tier 2 and Tier 3</span></span>
      <span class="sale-bar-sep" aria-hidden="true">·</span>
      <span class="sale-bar-time" aria-hidden="true"><span class="sale-bar-ends">ends in </span><span data-sale-count>3d 04h 12m</span></span>
      <span class="sr-only">Ends {{ sale.ends_at|date:"l j F, H:i" }}.</span>
      {% include "common/_icon.html" with name="arrow-right" %}
    </a>
    <button type="button" class="sale-bar-close" data-sale-close aria-label="Hide the sale bar">{% include "common/_icon.html" with name="x" %}</button>
  </div>
</div>
```

The whole message is one link to Memberships (`#plans`, the tier cards). The close button sits outside the link. The server renders the countdown text so it is right with no JS.

### 1.3 Look

| Part | Token / value |
|---|---|
| Bar background | `--color-espresso-raised` (`#553729`): one tone step lighter than the espresso header, so the two read as separate bands with no line between them. No border at all, top or bottom. |
| Height | `--sale-h` (new, 6.1): `2.75rem` (44px) on phone, `2.5rem` (40px) from 64em. Fixed height, one line, never wraps. |
| Type | Figtree `--text-sm` (14px), `--leading-snug`, `--tracking-body`, `font-variant-numeric: tabular-nums` on the whole bar. |
| Name | `--color-gold`, weight 500 (5.32 on espresso-raised). The only gold text. |
| Offer | `--color-text-inverse` (cream, 9.45), weight 400. |
| "ends in" and the `·` separators | `--color-text-muted-inverse` (5.61). Separators get `margin-inline: var(--space-2)`. |
| Countdown digits | `--color-text-inverse`, weight 500, tabular. |
| Arrow | `arrow-right`, 1rem, `--color-text-muted-inverse`, `margin-left: var(--space-2)`. Desktop only. |
| Close | 44px square (`--chip-h`) on phone, 40px from 64em; icon `x` 1rem in `--color-text-muted-inverse`; hover (fine pointer) `--color-text-inverse`. No background, no circle. |
| Layout | `.sale-bar-inner`: `position: relative; height: 100%; display: flex; align-items: center;`. Phone: text left aligned at the page margin, close flush right (`margin-right: calc(var(--space-3) * -1)` so the glyph lines up with "Menu"). From 48em: the link is centred in the container, close absolutely at the right edge. |
| Truncation | `.sale-bar-link { min-width: 0; white-space: nowrap; }`. Only the name may ellipsis (`.sale-bar-name { overflow: hidden; text-overflow: ellipsis; max-width: 12rem }` on phone). Offer and countdown never truncate. |
| Focus | `outline: 2px solid var(--color-focus-inverse); outline-offset: -2px;` on the link and the close (inside the bar, so it is never clipped). |
| Hover (fine pointer) | the offer text underlines: 1px, `text-underline-offset: 4px`, colour cream. Nothing scales or moves. |
| Theme | The site is light only (`color-scheme: light`, header always espresso), so the bar has one look. It never turns cream. `prefers-contrast: more`: background `--color-espresso`, separators cream. |

### 1.4 What it says

Desktop (from 48em): `{name} · {pct}% off {plans} · ends in {countdown}`
Phone (below 48em): `{name} · {pct}% off · {countdown}` (plans and "ends in" hidden with `display: none`; the tier cards say which plans).

Plans wording (server, one helper used by the bar and System preview):
- One or two plans: "Tier 2", "Tier 2 and Tier 3". Three: "Tier 1, Tier 2 and Tier 3" (plan names from Plans and pricing, not hard coded).
- All three tiers: "all memberships". All three tiers and single visit: "all memberships and single visits". Single visit alone: "single visits".

Percent: whole number, no decimals ("20% off").

### 1.5 Countdown

Format, by time left (minutes always rounded **up**, so it never shows "0m" while live):

| Time left | Desktop | Phone |
|---|---|---|
| 1 day or more | `3d 04h 12m` | `3d 04h` |
| Under 1 day | `4h 12m` | `4h 12m` |
| Under 1 hour | `12m` | `12m` |
| Under 1 minute | `1m` | `1m` |
| Zero | bar leaves (1.7) | same |

- Days unpadded; hours and minutes after the first unit are two digits (`3d 04h 07m`, `4h 07m`). The leading unit is unpadded (`4h`, not `04h`). Units are lower-case letters with no space between number and unit, one space between groups.
- Ticks once a minute, on the minute boundary of the end time (one `setTimeout` to the next boundary, then again), never `setInterval(1000)`. The digits swap instantly, no fade or roll: tabular numerals keep the width still.
- Clock skew: offset = server `data-now` minus client now at load; all maths uses `Date.now() + offset`. `visibilitychange` to visible recomputes at once and reschedules.
- Screen readers: the moving countdown is `aria-hidden`; the link's accessible text ends with the fixed `sr-only` "Ends Thursday 24 December, 23:59." Never `aria-live`.

### 1.6 Header, hero and scroll

The bar is **in normal flow and scrolls away**. It never overlays the header or the hero, and it never follows the page down.

- **Sticky-header pages** (`.site-header { position: sticky; top: 0 }`): nothing to change. The bar sits above, scrolls off, the header sticks at 0 as today.
- **Marketing pages** (`html[data-page="marketing"]`, fixed header at `inset: 0 0 auto 0`): the header must start below the bar and dock at 0 as the bar scrolls off. Use transform only (BRAND 7):
  - `html.has-sale` (set server side on `<html>` when the bar renders) gives the fixed header `transform: translateY(var(--sale-shift, 0px))`.
  - Supported browsers: CSS scroll-driven animation, no JS. `@supports (animation-timeline: scroll())` → `html.has-sale[data-page="marketing"] .site-header { animation: sale-dock linear both; animation-timeline: scroll(root); animation-range: 0 var(--sale-h); }` with `@keyframes sale-dock { from { transform: translateY(var(--sale-h)); } to { transform: none; } }`.
  - Otherwise: `sale-bar.js` watches the bar with one IntersectionObserver (thresholds 0 to 1 in 0.05 steps) and sets `--sale-shift` to `ratio × sale-h` on the header. No scroll listener.
  - No JS and no scroll timeline: `html.has-sale:not(.js)[data-page="marketing"] .site-header { position: absolute; top: var(--sale-h); }` (it scrolls with the page; the static layout already keeps the header solid).
  - This is position tracking the scroll, not an animation: it stays on under reduced motion.
- **First screens**: so a 100svh hero still fits one screen, subtract the bar once, only for the first scene of each page: `html.has-sale` → `.hero-first`, the spa door scene, `.gold-hero`, `.mem-stage`, `.book-hero`, `.signin`, `.register--solo .register-grid` get `min-height: calc(<their current value> - var(--sale-h))`. Nothing else changes; `--header-h` and `--scene-pad-top` are untouched.
- **Pins** (Home hero, The spa door): call `ScrollTrigger.refresh()` after the bar is removed (dismiss or end). Nothing else in `scenes.js` changes.
- **Page transitions**: `.sale-bar { view-transition-name: sale-bar; }` so the bar stays put while the page cross-fades (safe: the bar is solid, it has no backdrop blur, unlike the header).
- **Anchors**: `scroll-padding-top` stays `var(--header-h) + space`; the bar has scrolled away by then.
- **Menu dialog**: unchanged, covers the bar.
- Stacking: the bar is not positioned above the header layer; no new z-index.

### 1.7 Dismiss and end

- **Dismiss** (`×`): bar fades `opacity 1 → 0` over `--duration-base` (400ms) `--ease-soft`, then gets `hidden`, `html` gets `sale-off` (drops `has-sale` rules, header shift goes to 0), and focus moves to the header brand link. Stores `sessionStorage['spa99.sale.dismissed'] = '<sale pk>'` inside `try { } catch (e) { }` (private mode and blocked storage must not break the page; the bar simply hides for this page only).
- **No flash on the next page**: add to the inline script in `common/_head.html`: `try{if(sessionStorage.getItem("spa99.sale.dismissed")===d.dataset.sale)d.classList.add("sale-off")}catch(e){}` with `data-sale="{{ sale.pk }}"` on `<html>` when a sale is live. `html.sale-off .sale-bar { display: none; }` plus the `has-sale` rules scoped `:not(.sale-off)`. A new sale (new pk) shows again.
- **End** (countdown reaches zero): same fade and removal. If the bar is out of view at that moment (IntersectionObserver says not intersecting), remove it without fade and `window.scrollBy(0, -barHeight)` in the same frame so the page does not jump. The next request renders no bar (server).
- **Reduced motion**: the fade is instant (`--duration-base` is 0ms there); everything else is the same.
- No entrance animation: the bar is there on first paint (BRAND 7B: navigation and sticky things are not animated).

### 1.8 Files

- `common/templates/common/_sale_bar.html`, `common/static/common/css/sale-bar.css` (loaded from `_assets.html` only when `sale_bar` is in context), `common/static/common/js/sale-bar.js` (module, about 1.5 KB: countdown, dismiss, end, IO fallback).

### 1.9 Preview (developer only)

From System "Preview on site" the site renders as if the sale were live for that browser session only (signed session flag, never a public URL parameter). The bar gets one extra item before the name: `Preview` in `--color-text-muted-inverse`, 1px full `--color-hairline-inverse` border, `--radius-sm`, `0 var(--space-2)`, and a text link "End preview" just left of the close button. Countdown counts to the sale's end. Prices on Memberships and Register show the sale lines (section 2). Upcoming sales show "Preview · starts 1 Dec, 09:00" on desktop, "Preview" on phone.

---

## 2. Prices during a sale (Memberships, Register, My Spa 99)

**Principle.** The regular price stays the headline number on every card. No strike-through, no "was / now", no percent badge, no red. The sale is one calm line under the price, introduced by the gold swan glyph (`.mark-glyph`, decoration only, `aria-hidden`). Plans not in the sale show nothing extra.

Sale price shown in whole pounds when whole (`£76`), with pence when not (`£80.75`), ex VAT like every price on the site. Months always written as a number ("3 months", "1 month").

### 2.1 Memberships page (tier cards and single visit)

- In `.tier-price-group`, after `.tier-inc`: `<p class="tier-sale"><span class="mark-glyph" aria-hidden="true"></span>Christmas sale: £76 a month for your first 3 months</p>`.
- `.tier-sale`: `margin-top: var(--space-3)`, `--text-sm`, `--leading-snug`, weight 500, max two lines. Colour `--color-text` on the cream card (10.95); selected card (espresso) `--color-gold` (6.17). The glyph is `--color-gold` on both (decoration).
- Single visit row: "Christmas sale: £36 a visit for your first 3 months", same style, after the inc VAT line.
- The tier card input's `aria-describedby` already includes `tp-{slug}`; the line sits inside that group, so it is read with the price.
- Continue bar / phone sticky tag (`data-summary-price`): add the line under the price in `--color-text-muted` (5.32): "Christmas sale: £76 for 3 months". Driven by a new `data-sale` attribute on the radio (empty when not in sale).
- Page-level: no banner, no extra section. The bar is the announcement.
- Motion: none. The line is part of the card and reveals with it.

### 2.2 Register

- The plan card on the espresso stage (`.plan-card`), between `.plan-character` and `.plan-vat`: `<p class="plan-sale" data-plan-sale><span class="mark-glyph" aria-hidden="true"></span>Register during the Christmas sale and keep £76 a month for your first 3 months.</p>`
- `.plan-sale`: `margin-top: var(--space-3)`, `--text-sm`, `--leading-snug`, `--color-gold` (6.17 on espresso, 5.32 on espresso-raised), weight 500.
- Plan chips carry `data-sale-price` and `data-sale-months` (empty when that plan is not in the sale); `register.js` fills or hides `[data-plan-sale]` when the chip changes, in the same instant swap as the name and price (no animation, inside the existing `aria-live="polite"` region).
- Under the submit button, after "Registering is free...", only while a sale applies to the chosen plan: `<p class="no-payment">Your sale price is saved with your registration.</p>` (same class, no new style).

### 2.3 My Spa 99, Membership screen

- When the registration stored a sale, under the price lead (`.lead.num[data-price]`) and before "Nothing to pay now...": `<p class="m-sale"><span class="mark-glyph" aria-hidden="true"></span>You keep £76 a month for your first 3 months, from the Christmas sale.</p>` in `--color-text` (cream page), `--text-body`, weight 500.
- If they switch to a plan that was not in that sale, the line disappears and the choice tile for their sale plan gets the tag line "Your Christmas sale price" instead of its tagline. Switching asks first (shared modal): title "Switch to Tier 1?", body "Your Christmas sale price is for Tier 2. Switching to Tier 1 means paying the full price.", button "Switch to Tier 1".
- Choice tiles during a live sale (not yet stored, e.g. a member registered before the sale): no sale lines; the sale is for people who register during it.

---

## 3. System: Sales section

Nav label "Sales", after "Plans and pricing". URLs `/sales/`, `/sales/new/`, `/sales/<id>/`. Developer level, behind the unlock, every change logged with undo. One stylesheet `common/static/common/css/system-sales.css`, classes prefixed `ss-`; reuse `sys-*` everywhere it exists (`sys-head`, `sys-actions`, `sys-panel` with `header h2`, `sys-table`, `sys-scroll`, `sys-num`, `sys-badge`, `sys-note`, `sys-row`, `sys-ctl`, `sys-unit`, `sys-error`, `sys-seg`, `sys-pill`, `sys-btn` / `.primary` / `.danger` / `.sm`, `sys-savebar`, `sys-empty`, `sys-muted`).

### 3.1 List (`/sales/`)

- Header (`_page_header.html` then `.sys-actions`): title "Sales", description "A sale shows a bar on the site and keeps its price for people who register during it. London time." Action: "New sale" (`.sys-btn.primary`).
- Three `.sys-panel`s in this order, each only when it has rows: **Live**, **Upcoming**, **Past**. Header: `h2` plus a count in 12px mono `--sys-text-3`. Past shows the latest 10 with "Show all" (`.sys-more`).
- Table `.sys-table.ss-list` columns: Name (the real `<a>` to the sale, 13px 500), Off (`sys-num` mono "20%"), Plans ("Tier 2, Tier 3"; "All memberships"), Runs (mono "1 Dec, 09:00 to 24 Dec, 23:59"), Months (`sys-num` mono "3"), Registered (`sys-num` mono, people who registered with it), Status, actions.
- Status (`.sys-badge`): Live `ok` "Live", plus "ends in 3d 04h" in 12px mono `--sys-text-3` beside it (same format as the bar, server-rendered, refresh on load only); Upcoming `info` "Starts 1 Dec"; Past neutral "Ended", or "Ended early" when End now was used.
- Row actions (`.sys-btn.sm`): Live: "Preview", "End now" (secondary, red only inside the confirm). Upcoming: "Preview", "Delete". Past: "Copy" (opens New sale prefilled, name blank).
- **Empty** (no sales at all): one `.sys-panel` with `.sys-empty`: "No sales yet." and `.sys-btn.sm.primary` "New sale". Second line 12px `--sys-text-3`: "Only one sale can run at a time."
- Phone (below 48em): name, status and Runs stack in cell one; Off and Plans on a second line in `--sys-text-2`; Months and Registered hidden; actions 36px under the row.

### 3.2 Create and edit (`/sales/new/`, `/sales/<id>/`)

Header: back link "Sales" (`.se-back` pattern), title "New sale" or the sale name with its status badge, actions right: "Preview on site" (secondary, opens a new tab, available once saved), "End now" (live only), "Delete" (upcoming only).

Two panels, `.sys-cols` (8 / 4) at 1440, stacked below 64em.

**Left: `.sys-panel` "Sale"**, field rows (`_field_row.html`, label left 220px, help under the label):

| Field | Control | Help |
|---|---|---|
| Name | text, 320px, max 40 | "Shown in the bar, as written." |
| Off | number 96px, `sys-unit` "%" after, 1 to 90 | none |
| Plans | four `.sys-pill` checkboxes in a `fieldset` (`legend` = "Plans", visually the row label): Tier 1, Tier 2, Tier 3, Single visit (names from Plans and pricing) | "Tick at least one." |
| Starts | `.sys-seg` radios "Now" / "At a time"; "At a time" reveals date + time inputs (`type="time" step="60"`), `sys-unit` "London time" after | none |
| Ends | date + time inputs, `sys-unit` "London time"; under them 12px `--sys-text-3`, live: "Runs 23 days, 14 hours." | none |
| Months at sale price | number 96px, `sys-unit` "months", 1 to 24 | "For people who register during the sale." |

**Right: `.sys-panel` "What people see"** (`.ss-preview`, updates as you type, no request needed except plan prices which are in the page):
- "Bar" label 12px `--sys-text-2`, then the bar copy as plain 13px text in a `--sys-subtle` box, `--sys-radius`, padding `--sys-2 --sys-3`: "Christmas sale · 20% off Tier 2 and Tier 3 · ends in 23d 14h 00m". No brand colours in System.
- "Prices" label, then a small table `.sys-table.ss-prices`: Plan, Price (mono `£95.00`), Sale price (mono `£76.00`), For ("3 months"). Only ticked plans. Plain values, not the del/add diff colours (this is not a change).
- Phone: this panel follows the form and is collapsed behind "What people see" (`<details>`), open by default from 64em.

**Locked while live.** On a live sale, Off, Plans, Starts and Months render read-only: value in 13px mono (`.ss-locked`, no input, no disabled grey box), and under it 12px `--sys-text-3`, with the `lock-simple` icon 12px before it: "Locked while live: 41 people have this price." (zero registered: "Locked while live, so everyone gets the same offer."). Name and Ends stay editable. Ends cannot be set earlier than now ("Use End now to stop it today."). Past sales are fully read-only with a `.sys-note` "This sale has ended. Copy it to run it again." and a "Copy" button.

**Save.** Shared `.sys-savebar` ("1 unsaved change", Discard, "Save sale"; Cmd/Ctrl+S). New sale on LIVE opens `confirmModal`: title "Save Christmas sale on LIVE?", body "It starts on 1 Dec at 09:00 for Tier 2 and Tier 3. The bar appears on every page then." ("It starts now..." when Now). Editing the end of a live sale: title "Change when Christmas sale ends?", body with the old and new time as System diff chips (`sys-old` / `sys-new`), "The countdown on the site changes at once." Danger tone on LIVE, espresso on DEV (System 4.4). Success toast "Saved." with Undo.

**Errors** (inline `.sys-error` under the field, problems modal on save, as System):
- Off: "Enter a whole number from 1 to 90."
- Plans: "Tick at least one plan."
- Ends: "End after the start." / "End in the future."
- Months: "Enter 1 to 24 months."
- Overlap (under Starts, and in the problems modal): "This overlaps Black Friday (27 Nov to 1 Dec). Only one sale can run at a time." with a link to that sale.

### 3.3 End now

`.sys-btn` "End now" in the header (and row action). Shared modal, `tone: 'danger'` on LIVE:
- Title: "End Christmas sale now?"
- Body: "The bar and the sale prices leave the site at once. The 41 people who registered keep their price."
- Buttons: "Cancel" (focused first), "End sale now".
- After: status becomes "Ended early", toast "Christmas sale ended." with Undo (Undo restores the original end time, only while that time is still in the future; otherwise the Undo is not offered).

**Delete** (upcoming only): title "Delete Christmas sale?", body "It has not started, so nobody has this price.", button "Delete sale".

### 3.4 Preview

"Preview on site" opens the home page in a new tab with the developer preview on (1.9). Beside the button, 12px `--sys-text-3`: "Only you see the preview, in this browser." The preview ends when the tab session ends or via "End preview" in the bar.

### 3.5 States

Empty (3.1), loading (save button "Saving", disabled), error (`.sys-note.error` "Could not save the sale. Your changes are still here." + Retry), locked (3.2), gated by overlap (Save stays enabled; the error explains). Disabled controls always carry a written reason, never tooltip only.

---

## 4. Accessibility

- Bar: one link and one button, both reachable right after the skip link; 44px targets on phone; AA pairs listed in 1.3; countdown hidden from screen readers with a fixed sr-only end time; no live region; dismiss moves focus to the header brand.
- Price lines are real text inside the existing described-by groups; the swan glyph is `aria-hidden`; meaning never depends on colour (no strike-through to decode).
- System: `fieldset`/`legend` for Plans and Starts; read-only locked values are plain text with the reason in the DOM; modal focus starts on Cancel; all copy in full sentences.
- Reduced motion: the bar fade becomes instant; header docking still tracks the scroll (it is position, not decoration); nothing else here moves.

## 5. Copy (British English, calm, no exclamation marks)

| Where | Text |
|---|---|
| Bar, desktop | Christmas sale · 20% off Tier 2 and Tier 3 · ends in 3d 04h 12m |
| Bar, phone | Christmas sale · 20% off · 3d 04h |
| Bar, sr-only | Ends Thursday 24 December, 23:59. |
| Bar close | aria-label "Hide the sale bar" |
| Bar, preview | Preview · starts 1 Dec, 09:00 / End preview |
| Tier card | Christmas sale: £76 a month for your first 3 months |
| Single visit | Christmas sale: £36 a visit for your first 3 months |
| Continue bar | Christmas sale: £76 for 3 months |
| Register plan card | Register during the Christmas sale and keep £76 a month for your first 3 months. |
| Register, under submit | Your sale price is saved with your registration. |
| My Spa 99 | You keep £76 a month for your first 3 months, from the Christmas sale. |
| My Spa 99 switch | Switch to Tier 1? / Your Christmas sale price is for Tier 2. Switching to Tier 1 means paying the full price. / Switch to Tier 1 |
| System list | Sales / A sale shows a bar on the site and keeps its price for people who register during it. London time. / New sale / No sales yet. / Only one sale can run at a time. |
| System statuses | Live · ends in 3d 04h / Starts 1 Dec / Ended / Ended early |
| System form | Name: Shown in the bar, as written. / Plans: Tick at least one. / Months at sale price: For people who register during the sale. / Runs 23 days, 14 hours. |
| Locked | Locked while live: 41 people have this price. / Locked while live, so everyone gets the same offer. / Use End now to stop it today. |
| Past | This sale has ended. Copy it to run it again. |
| End now | End Christmas sale now? / The bar and the sale prices leave the site at once. The 41 people who registered keep their price. / End sale now / Christmas sale ended. |
| Delete | Delete Christmas sale? / It has not started, so nobody has this price. / Delete sale |
| Preview | Preview on site / Only you see the preview, in this browser. |

Never: "Hurry", "Don't miss out", "Limited time", "Deal", "Save X%", "was £95", "Only X left".

## 6. Tokens

### 6.1 Proposed additions to BRAND.md section 8 (website, `tokens.css`)

| Token | Value | Use |
|---|---|---|
| `--sale-h` | `2.75rem`; `2.5rem` from 64em | **Proposed (Sales), derived.** Height of the sale bar; drives the header dock and first-screen offset. |

No new colours. The bar uses existing `--color-espresso-raised`, `--color-gold`, `--color-text-inverse`, `--color-text-muted-inverse`, `--color-hairline-inverse`, `--color-focus-inverse`; price lines use `--color-text`, `--color-text-muted`, `--color-gold`. Motion: `--duration-base` (400ms) with `--ease-soft` for the one fade. `--sale-shift` is a runtime variable set by `sale-bar.js`, not a token.

### 6.2 System

None. Everything is existing `--sys-*`.

## 7. Acceptance checklist

1. Bar renders server side only while a sale is live (or previewing), on full-header pages only, after the skip link and above the header; espresso-raised, no borders, one line, 44px phone / 40px desktop.
2. Copy and countdown exactly as 1.4 and 1.5 (rounded up, padded after the first unit, phone drops minutes over a day); tabular numerals; ticks on minute boundaries; skew-corrected; no jitter.
3. Marketing pages: header starts under the bar and docks at 0 as it scrolls away (scroll timeline, IO fallback, no-JS absolute fallback); first screens still fit at 375x667 and 1440x800; pins refresh after removal; no overlap of bar and header at any scroll position.
4. Dismiss fades (400ms, instant under reduced motion), stores the sale pk in sessionStorage inside try/catch, does not flash on the next page, moves focus to the header brand; a new sale shows again.
5. At zero the bar leaves without a page jump; a reload shows no bar.
6. Tier cards, single visit, continue bar, register plan card and My Spa 99 show the sale lines of section 2 with the regular price unchanged; no strike-through, no red, no badges; register line follows the chosen chip.
7. System Sales: list grouped Live / Upcoming / Past with the badges and empty state of 3.1; form fields, preview panel, locked fields with written reasons, overlap error, save confirm, End now and Delete modals, toasts with Undo, all in existing `sys-*` classes; no one-sided borders anywhere.
8. AA everywhere (pairs in 1.3 and 2); 44px targets on the public phone bar, 36px in System on phone; screenshots at 375 and 1440 of Home with the bar (top and scrolled 20px), Memberships with a selected sale card, Register with a sale plan, System list (all three groups and empty) and the edit form of a live sale with locked fields, sent for design review.
