# Spa 99 System: design brief

Spec: `docs/features/system.md`. Decisions: PROJECT.md rows dated 2026-10-23 (System before Control; recipients move from env to System). Brand: `docs/BRAND.md` supplies the fonts and one accent only.

**Design read.** Internal developer tooling, not a website. The feel of GitHub settings, Linear, the Stripe and Vercel dashboards: neutral, crisp, light, dense, keyboard friendly, obvious save and undo, safe confirms. No hero, no brand showcase, no motion beyond feedback. Dials: variance 1, motion 1, density 8 (phone 6).

**How it differs from the Office (`docs/design/OFFICE.md`).** Office is warm cream, soft shadows, rounded 14-20px cards, big Signika numbers, no lines. System is cool-neutral grey and white, hairlines instead of shadows, 4-6px corners, 13px type, monospace values, tables first. Nobody should mistake one for the other.

---

## 1. CSS library decision: plain CSS with `--sys-*` tokens (no library)

| Option | Licence | Size (min+gz) | Density | Forms and tables | Verdict |
|---|---|---|---|---|---|
| Pico CSS 2.x | MIT | ~11 KB | Low: 48px+ inputs, roomy spacing, built for content sites | Good-looking but spacious; shrinking it means overriding most variables | No |
| Bulma 1.0.x | MIT | ~27 KB (full) | Medium; `is-small` helps | Solid, but class-heavy markup and lots of unused weight | No |
| Primer CSS (GitHub) | MIT | ~40 KB+ | High, exactly the feel | Excellent, but in maintenance mode (GitHub moved to Primer React), big, its own naming | No |
| Open Props 1.x + own CSS | MIT | ~4 KB (subset) | You build it | You build it | Adds tokens we would rename to `--sys-*` anyway |
| **Plain CSS, `--sys-*` tokens** | ours | target under 8 KB gz | Exactly what we set | Exactly what we need (one table, one form row, one button) | **Pick** |

Why: no library clearly wins; the dense ones are heavy or frozen, the small ones are roomy. System needs about eight components (shell, table, field row, button, badge, toggle, dialog, toast), which is less CSS than overriding a library. No vendor folder, no version to pin, nothing to update.

Files (new): `common/static/common/css/system.css` (tokens, shell, components) and `common/static/common/css/system-tables.css` (table, inline edit, diff). Loaded with `fonts.css` and `tokens.css` (read-only, for `--color-espresso` and the font families). System does **not** load `base.css`, `components.css`, `app.css` or any `office*.css`. All tokens scoped to `body.system`, never `:root`. No hex in templates or JS.

---

## 2. Tokens (System only, proposed; live in `system.css`)

### 2.1 Colour

Neutral greys (one family, very slightly warm so espresso sits well) and **one accent: espresso** `#492E21` (primary buttons, focus ring, selected nav, links). Gold `#E5AC6E` appears only in the 16px swan mark and the 2px active-nav bar (decorative, never text: 2.01 on white). Status colours are used only for real state.

| Token | Hex | Use | Contrast (WCAG) |
|---|---|---|---|
| `--sys-bg` | `#F6F6F4` | Page, sidebar | text 16.06, text-2 6.89 |
| `--sys-surface` | `#FFFFFF` | Panels, tables, inputs, dialogs | text 17.38, text-2 7.45, text-3 5.49 |
| `--sys-subtle` | `#EFEFEC` | Table head, row hover, secondary button, code chips | text 15.08, text-2 6.47, text-3 4.76 |
| `--sys-selected` | `#E7E5E1` | Current nav item, selected row | text 13.81, text-2 5.92 (no text-3 here: 4.36) |
| `--sys-line` | `#E3E2DE` | Hairlines between rows, panel edges (decorative) | 1.30 |
| `--sys-control` | `#8D8B85` | Input, select, checkbox borders | 3.41 on surface (1.4.11 pass) |
| `--sys-text` | `#1B1A19` | Primary text, values | as above |
| `--sys-text-2` | `#57554F` | Labels, column heads, meta | 5.92 or more everywhere |
| `--sys-text-3` | `#6B6963` | Help text, timestamps (surface, bg, subtle only) | 4.76 to 5.49 |
| `--sys-accent` | `var(--color-espresso)` | Primary button fill (white text 12.38), focus ring, links | 12.38 on surface |
| `--sys-ok` / `--sys-ok-bg` | `#1A6B43` / `#E6F2EA` | Healthy, saved, "On" | 6.51 on white, 5.65 on its bg |
| `--sys-warn` / `--sys-warn-bg` | `#8A5300` / `#FBF0D9` | Unsaved, lock soon, stale snapshot | 6.33 / 5.60 |
| `--sys-danger` / `--sys-danger-bg` | `#B42318` / `#FCEBE8` | LIVE, errors, destructive | white on danger 6.57; 5.69 on its bg |
| `--sys-info` / `--sys-info-bg` | `#2C5A8F` / `#E7EEF7` | DEV badge, neutral notices | 7.08 / 6.06 |
| `--sys-del` / `--sys-del-bg` | `#8E1F15` / `#FCEBE8` | Old value in a diff (struck through) | 7.72 |
| `--sys-add` / `--sys-add-bg` | `#14532D` / `#E6F2EA` | New value in a diff | 7.92 |
| `--sys-overlay` | `rgb(27 26 25 / 0.32)` | Dialog backdrop | |
| `--sys-shadow-pop` | `0 4px 12px rgb(27 26 25 / 0.10), 0 0 0 1px var(--sys-line)` | Menus, dialogs, toasts only | |

Nothing at rest has a shadow. Separation is hairlines and `--sys-subtle` fills.

### 2.2 Type

```css
--sys-font: var(--font-body);          /* Figtree for all UI */
--sys-mono: ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, monospace;  /* system stack, nothing to download */
--sys-fs: 0.8125rem;    /* 13px base: body, table cells, inputs, buttons */
--sys-fs-sm: 0.75rem;   /* 12px: column heads, meta, badges, help text */
--sys-fs-md: 0.9375rem; /* 15px: panel titles */
--sys-fs-lg: 1.125rem;  /* 18px: page title (one per page) */
--sys-lh: 1.45;
```

Weights 400 and 600 only (500 for nav). Letter spacing 0. Signika is not used in System. Mono (tabular by nature) for: prices, VAT, counts, IDs, emails, dates and times in tables, setting keys, every old → new diff. `font-variant-numeric: tabular-nums` on Figtree numbers elsewhere. No uppercase labels except the env badge.

### 2.3 Space, size, shape

```css
--sys-1: 4px; --sys-2: 8px; --sys-3: 12px; --sys-4: 16px; --sys-5: 24px; --sys-6: 32px;
--sys-row: 32px;          /* table row, nav item, field row */
--sys-control: 28px;      /* input, select, button height */
--sys-control-sm: 24px;   /* in-row buttons (Undo, Edit), toggles */
--sys-radius: 4px;        /* controls, badges, chips */
--sys-radius-lg: 6px;     /* panels, dialogs, toasts */
--sys-nav-w: 220px; --sys-top-h: 44px; --sys-content-max: 1200px;
```

One shape rule: 4px for everything you click or type in, 6px for containers. No pills except the toggle track. Control padding: 0 8px (inputs), 0 10px (buttons). Checkbox and radio 14px. Toggle 28 by 16px.

### 2.4 Motion

Feedback only. Colour and border transitions 100ms ease-out. Dialog: opacity plus `scale(0.98 → 1)`, 120ms. Toast: `translateY(8px → 0)` and opacity, 150ms in, 120ms out. Save bar: slides up 150ms. Nothing animates on page load, on keyboard actions, or in tables. `prefers-reduced-motion: reduce` removes all transforms (opacity only, or instant).

---

## 3. Shell

```
+----------------------------------------------------------------------------+
| [swan] System   [ LIVE ]            Locks in 14 min   moishe@... v  [Lock] |  44px top bar
+--------------+-------------------------------------------------------------+
| Dashboard    |  Plans and pricing                         [ Add plan ]     |
| Plans and p..|  ---------------------------------------------------------- |
| Hours and c..|  table / field rows                                         |
| Gold rules   |                                                             |
| Journey      |                                                             |
| Emails       |                                                             |
| Settings     |                                                             |
| Team         |                                                             |
| ------------ |                                                             |
| Change log   |                                                             |
+--------------+-------------------------------------------------------------+
```

- **Top bar** (44px, `--sys-surface`, 1px `--sys-line` bottom, sticky). Left: swan mark 16px (gold), "System" 13px 600 `--sys-text`, then the env badge. Right: lock countdown, signed-in menu, Lock button.
- **Env badge**, always visible, every page including unlock and the change log:
  - DEV: `--sys-info-bg` fill, `--sys-info` text, "DEV", 12px 600 mono uppercase, 20px high, 4px radius.
  - LIVE: solid `--sys-danger` fill, white "LIVE" (6.57), same size; plus a **3px `--sys-danger` stripe across the very top of the viewport** above the top bar, and the document title becomes `LIVE · <Section> · System`. On DEV: `DEV · <Section> · System`. The value comes from one server setting (not guessed from the host in JS).
- **Lock countdown**: "Locks in 14 min" 12px `--sys-text-3`, updates each minute, resets on any request. Under 2 minutes it turns `--sys-warn` and gains a "Stay unlocked" small button (pings the server). At 0 the page goes to the unlock screen; if there are unsaved edits, the countdown warning says "Unsaved changes will be lost" and stays until acted on.
- **Signed in**: name or email 13px, opens a small menu (`--sys-shadow-pop`): role ("Superuser" or "System group"), "Open Office" link, "Sign out".
- **Lock**: secondary button 28px "Lock". Locks at once, no confirm.
- **Left list** (220px, `--sys-bg`, 1px `--sys-line` right). Text only, no icons. Items 32px, 13px 500 `--sys-text-2`, padding 0 12px, radius 4px. Hover `--sys-subtle`. Current: `--sys-selected` fill, `--sys-text` 600, `aria-current="page"`, 2px gold bar on the left edge. Order: Dashboard, Plans and pricing, Hours and closures, Gold rules, Journey, Emails, Settings, Team; a hairline; Change log. A section with unsaved edits shows a 6px `--sys-warn` dot after its label (real state).
- **Content**: padding 24px, max 1200px. Page header: title 18px 600, optional one-line description 13px `--sys-text-2` ("Prices are ex VAT. Changes apply at once."), primary action right-aligned. Below: panels.
- **Panel**: `--sys-surface`, 1px `--sys-line`, radius 6px, no shadow. Panel header 40px: title 15px 600, actions right. Panels stack with 16px gaps.
- **Keyboard**: everything reachable by Tab; focus ring `2px solid var(--sys-accent)`, offset 2px (`:focus-visible`). `/` focuses the page filter, `Ctrl/Cmd+S` saves the current section, `Esc` cancels the cell being edited, `Enter` commits it, `g` then `d` / `c` jumps to Dashboard / Change log. A `?` opens a small shortcuts list. Shortcuts never fire while typing in a field (except Esc, Enter, Cmd+S).

---

## 4. Density, tables, forms, save and undo

### 4.1 Tables (the main pattern)

- Row 32px, cell padding 0 12px, 13px. Head row 32px on `--sys-subtle`, 12px 600 `--sys-text-2`, sticky under the top bar. **Hairlines** (1px `--sys-line` between rows; no zebra). Hover row `--sys-subtle`.
- Numbers and money right-aligned, mono. Money shown as `£95.00`; VAT as `20.0%`. Text left. Booleans as a toggle or "Yes" / "No".
- Columns used for order get a 16px drag handle (also Alt+Up/Down on the focused row). Hidden rows render in `--sys-text-3` with a "Hidden" badge.
- **Inline edit**: an editable cell looks like text; on hover a 1px `--sys-control` box appears and the cursor becomes text. Click, Enter or F2 turns it into a 28px input inside the 32px row (no row height change). Enter commits to the draft, Esc reverts, Tab moves to the next editable cell. Validation errors: red 1px border plus a 12px message under the table row in `--sys-danger` and an `aria-describedby`.
- An edited cell keeps a 2px `--sys-warn` left border and `--sys-warn-bg` fill until saved; the original value is in its `title` ("Was £95.00").
- Long text (email templates, wording) is not edited in a cell: the row has an "Edit" small button opening a side panel (480px, right, `--sys-shadow-pop`) with a full textarea (mono off, Figtree 13px, 1.5 line height) and the same draft rules.
- Empty table: one 64px row, `--sys-text-2`: "No closures yet." plus the add button.
- Phone (below 48em): tables scroll sideways inside the panel with the first column sticky; tapping a row opens the side panel as a full-height sheet with field rows instead of inline cells.

### 4.2 Field rows (settings-style forms)

- Label left, control right: grid `220px 1fr`, row min 40px, label 13px 500 `--sys-text`, help text 12px `--sys-text-3` under the label. Inputs 28px, width fitted to the value (number 96px, money 112px, email 320px, text up to 480px). Units outside the box in `--sys-text-2` ("£", "%", "min").
- Groups separated by a hairline and a 15px 600 group title, not by boxes inside boxes.
- Below 48em: label stacks above the control, inputs 36px tall and 16px font (no iOS zoom).
- Choices with 2-5 options: segmented control (28px, `--sys-subtle` track, white selected segment with 1px `--sys-line`) or radios, never a select. Booleans: toggle with its state written beside it ("On" / "Off").

### 4.3 Save, undo, toast

- Edits are **drafts** until saved, per section. One section, one Save.
- **Save bar**: when a section has drafts, a 48px bar sticks to the bottom of the content area (`--sys-surface`, 1px top `--sys-line`, `--sys-shadow-pop`): left "3 unsaved changes" (with a "Show" link listing them old → new), right "Discard" (secondary) and "Save" (primary, espresso, white text). `Ctrl/Cmd+S` = Save. Leaving the page with drafts asks "Leave without saving? 3 changes will be lost."
- **Save** posts the section by HTMX; the button shows "Saving..." disabled; on success the warn marks clear and a **toast** appears bottom right (phone: bottom, full width minus 16px): "Saved 3 changes." with an "Undo" button, 6 seconds, pauses on hover/focus, `role="status"`. Undo restores the old values as a new logged change and toasts "Undone."
- On error: the bar turns `--sys-danger-bg` with the server message; drafts stay.

### 4.4 Confirm for risky changes

Risky: any price, VAT rate, stage switch (register interest / subscribe / book), opening date, capacity, one-off closure, Gold thresholds, email recipients, Team role changes, deleting anything, and every Undo of a risky change.

- Save with a risky change opens a dialog (480px, radius 6px, `--sys-shadow-pop`, focus trapped, Esc cancels, focus starts on Cancel):
  - Title: "Change prices on LIVE?" (or "on DEV"). 15px 600.
  - A compact diff table, mono: `Gold · Price ex VAT   £95.00 → £110.00`. Old in `--sys-del` on `--sys-del-bg` struck through, arrow `--sys-text-3`, new in `--sys-add` on `--sys-add-bg`.
  - One plain consequence line where known: "Members see the new price at once." / "Booking opens to the public at once."
  - Buttons: "Cancel" (secondary) and the action named exactly: "Change 1 price". On LIVE the action button is `--sys-danger` fill (white text 6.57); on DEV it is espresso.
- Removing the last superuser or System member, or switching off every stage at once on LIVE: the dialog adds a field "Type LIVE to confirm" and the button stays disabled until it matches.

---

## 5. Unlock screen and 404

**Unlock** (`/unlock/`): `--sys-bg` page, the LIVE stripe and badge if live. A 360px panel centred near the top third (not floating mid-screen): swan 16px + "System" + env badge; title "System is locked" 18px 600; line "Signed in as moishe@... Enter your password to continue." 13px `--sys-text-2`; password field (full width, 32px, `autocomplete="current-password"`, autofocus); "Unlock" primary full width; small link "Not you? Sign out". Wrong password: inline under the field, `--sys-danger`: "That password is not right." After repeated failures, the server's rate-limit line replaces it: "Too many tries. Try again in 10 minutes." Returns to the page that was requested.

**404 for non-developers**: deliberately anonymous. No System CSS, no fonts, no swan, no Spa 99 name, no link. `<title>Not found</title>`, white page, system-ui 16px, `#1B1A19`, 48px margin: heading "Not found" and one line "The requested resource was not found on this server." Identical for every path on the host and for signed-out visitors, HTTP 404, `noindex`.

---

## 6. Dashboard

Page title "Dashboard", no greeting.

**Row 1: tiles** (CSS grid, `repeat(auto-fill, minmax(176px, 1fr))`, 8px gap; 6 across at 1440, 2 across on phone). Tile: `--sys-surface`, 1px `--sys-line`, radius 6px, padding 12px, height 84px. Label 12px `--sys-text-2`; value 18px 600 mono; meta 12px `--sys-text-3`. Status shown with a small badge, not a coloured tile.

| Tile | Value | Meta | State badge |
|---|---|---|---|
| Health | "OK" / "Failing" | "Checked 14:02" | OK green / Failing red (from `/health/`) |
| Queue | `0` pending | "2 failed in 24 h" | Failed > 0: warn |
| Last roll-up | `14:00` | "2 min ago" | Older than expected interval: warn |
| Snapshot | `3 min` old | "Office figures" | Stale: warn |
| People | `128` registered | "31 Gold" | none |
| Gold waiting | `4` | "Oldest 2 days" | none |

All values read stored rows (snapshots, queue table), never page-load sums. A tile that cannot read its source shows "Unknown" and a warn badge.

**Row 2: two panels** (8 / 4 columns at 1440; stacked on phone, stage switches first).
- **Recent changes** (left): last 10 change-log rows in the compact format of section 7 (when, who, what, old → new), no filters, "Open change log" link in the panel header.
- **Stage switches** (right): three field rows, Register interest / Subscribe / Book, each with a read-only "On" (ok badge) or "Off" (neutral badge) and, under it, the opening date in mono. "Change in Settings" link. No toggles here: switches change only in Settings, behind the confirm.

---

## 7. Change log

Page title "Change log". Description: "Every change made in System. Undo restores the old value as a new change."

**Filter bar** (one row, 28px controls, sticky under the page header): Section (select: All, then the eight sections), Person (select), Date (segmented: Today · 7 days · 30 days · Custom; Custom reveals two date inputs), search box ("Find a field or value", `/` focuses it). Filters live in the URL (`?section=plans&user=3&range=7d`), HTMX swaps the table, back button safe. "Clear filters" link when any is set.

**Table** columns (row 32px, hairlines):

| When | Who | Section | What | Change | |
|---|---|---|---|---|---|
| `14:02` today (title: `2026-10-23 14:02:11`) | Moishe | Plans and pricing | Gold · Price ex VAT | `£95.00` → `£110.00` | Undo |

- When: mono, "14:02" for today, "Yesterday 09:40", then `21 Oct 09:40`; full timestamp on hover and in a `<time datetime>`.
- What: the human path, not the model name ("Journey · Q3 · Option 2 · Gold points").
- Change: old (del style) → new (add style), mono chips, truncated at 40 characters with "Show" expanding a line diff for long text (templates).
- Undo: 24px secondary button. Risky fields go through the confirm dialog. Rows already undone show a neutral "Undone by Moishe" badge instead of the button; the undo itself appears as its own row with a badge "Undo of 14:02 change". Undo is disabled with a title ("A later change replaced this value") when the field has moved on since; the row links to the newer change.
- Grouping: changes saved together share one "Saved together" bracket (2px `--sys-line` left rule across the rows) and an "Undo all 3" on the first row.
- 50 rows, then "Load 50 more". Empty: "No changes match these filters."
- Phone: each row becomes a 2-line block (line 1: what + Undo; line 2: when, who, old → new).

---

## 8. Phone

Desktop-first; on phones it must work, not shine.

- Below 64em: the left list collapses into a "Menu" button in the top bar opening a full-height sheet with the same list (Esc and backdrop close). Top bar keeps swan, env badge, Lock; the countdown and name move into the sheet.
- LIVE stripe and badge stay on every screen size.
- Below 48em: field rows stack, controls 36px, inputs 16px font, tables scroll sideways with a sticky first column or open rows in a sheet (4.1), save bar full width with `env(safe-area-inset-bottom)`, dialogs full width bottom sheets.
- Touch targets 36px minimum on phones (rows grow to 40px under `pointer: coarse`).

---

## 9. Copy

Plain, short, exact. Sentence case. Name the thing and the value: "Save", "Discard", "Change 1 price", "Add closure", "Remove", never "Submit" or "OK". No exclamation marks, no "Oops". Errors say what to do: "Enter a price above £0.00." Times 24-hour, dates `23 Oct 2026`, money `£110.00`, percentages one decimal.

---

## 10. Acceptance checklist (frontend)

1. No CSS library added; `system.css` and `system-tables.css` together under 8 KB gzipped; all tokens `--sys-*`, scoped to `body.system`; no hex outside `system.css`; `base.css`, `components.css` and Office CSS not loaded on System.
2. Every page (including unlock) shows the env badge; LIVE has the 3px red top stripe, solid red badge and `LIVE ·` title prefix; DEV has the blue badge and `DEV ·` prefix.
3. Left list in the specified order with `aria-current`; Change log separated by a hairline; unsaved dot appears on sections with drafts.
4. Lock button locks at once; countdown updates, turns warn under 2 minutes, offers "Stay unlocked", sends to unlock at 0 and returns to the requested page after unlock.
5. Base text 13px, rows 32px, controls 28px (in-row 24px); phone controls 36px with 16px inputs; no layout shift when a cell enters edit mode.
6. Tables: hairlines, sticky head, numbers right-aligned in mono; inline edit with Enter / Esc / Tab / F2; edited cells marked warn with "Was ..." title; long text edits in the side panel.
7. Save bar appears with drafts, counts them, Cmd/Ctrl+S saves, Discard reverts, leaving with drafts warns; success toast with working Undo (6 s, pauses on hover/focus, `role="status"`).
8. Every risky change (list in 4.4) opens the confirm with old → new diff, environment named in the title, specific action label, red action on LIVE; typed "LIVE" guard where specified; focus trap and Esc work.
9. Unlock screen as specified, wrong-password and rate-limit messages inline; non-developers get the anonymous 404 with no brand, CSS or System wording.
10. Dashboard: six tiles from stored rows only, warn/fail badges on real state, "Unknown" when a source fails; recent changes (10) and read-only stage switches linking to Settings.
11. Change log: section, person, date and search filters in the URL with HTMX swaps; rows show when (with full timestamp), who, section, human path, old → new, Undo; undone and superseded states; grouped saves with "Undo all"; Load more.
12. Contrast: all text pairs as in 2.1 (4.5:1 or more), control borders 3:1 or more, focus ring visible on every interactive element; `--sys-text-3` never on `--sys-selected`.
13. Keyboard: full Tab order, `/`, Cmd/Ctrl+S, Esc, Enter, `g d`, `g c`, `?` work and never fire while typing.
14. Reduced motion removes all transforms; nothing animates on load.
15. Phone at 375px: menu sheet, stacked field rows, sideways-scrolling tables with sticky first column, save bar and dialogs usable; no page-level horizontal scroll.
16. Screenshots at 375 and 1440 of Dashboard, Plans and pricing (with drafts and the confirm open), Change log, Unlock, and the 404 sent for design review.
