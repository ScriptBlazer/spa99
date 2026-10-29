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
| Audit log    |                                                             |
+--------------+-------------------------------------------------------------+
```

- **Top bar** (44px, `--sys-surface`, 1px `--sys-line` bottom, sticky). Left: swan mark 16px (gold), "System" 13px 600 `--sys-text`, then the env badge. Right: lock countdown, signed-in menu, Lock button.
- **Env badge**, always visible, every page including unlock and the change log:
  - DEV: `--sys-info-bg` fill, `--sys-info` text, "DEV", 12px 600 mono uppercase, 20px high, 4px radius.
  - LIVE: solid `--sys-danger` fill, white "LIVE" (6.57), same size; plus a **3px `--sys-danger` stripe across the very top of the viewport** above the top bar, and the document title becomes `LIVE · <Section> · System`. On DEV: `DEV · <Section> · System`. The value comes from one server setting (not guessed from the host in JS).
- **Lock countdown**: "Locks in 14 min" 12px `--sys-text-3`, updates each minute, resets on any request. Under 2 minutes it turns `--sys-warn` and gains a "Stay unlocked" small button (pings the server). At 0 the page goes to the unlock screen; if there are unsaved edits, the countdown warning says "Unsaved changes will be lost" and stays until acted on.
- **Signed in**: name or email 13px, opens a small menu (`--sys-shadow-pop`): role ("Superuser" or "System group"), "Open Office" link, "Sign out".
- **Lock**: secondary button 28px "Lock". Locks at once, no confirm.
- **Left list** (220px, `--sys-bg`, 1px `--sys-line` right). Text only, no icons. Items 32px, 13px 500 `--sys-text-2`, padding 0 12px, radius 4px. Hover `--sys-subtle`. Current: `--sys-selected` fill, `--sys-text` 600, `aria-current="page"`, 2px gold bar on the left edge. Order: Dashboard, Plans and pricing, Hours and closures, Gold rules, Journey, Emails, Settings, Team; a hairline; Audit log. A section with unsaved edits shows a 6px `--sys-warn` dot after its label (real state).
- **Content**: padding 24px, max 1200px. Page header: title 18px 600, optional one-line description 13px `--sys-text-2` ("Prices are ex VAT. Changes apply at once."), primary action right-aligned. Below: panels.
- **Panel**: `--sys-surface`, 1px `--sys-line`, radius 6px, no shadow. Panel header 40px: title 15px 600, actions right. Panels stack with 16px gaps.
- **Keyboard**: everything reachable by Tab; focus ring `2px solid var(--sys-accent)`, offset 2px (`:focus-visible`). `/` focuses the page filter, `Ctrl/Cmd+S` saves the current section, `Esc` cancels the cell being edited, `Enter` commits it, `g` then `d` / `a` jumps to Dashboard / Audit log. A `?` opens a small shortcuts list. Shortcuts never fire while typing in a field (except Esc, Enter, Cmd+S).

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

## 7. Audit log

Replaces the Change log page. Nav label "Audit log" (last item, after the hairline); shortcut `g a`. Page title "Audit log". Description: "Every change and every sign-in, newest first. Undo restores the old value as a new entry."

The question this page answers in one glance: **who did what, where, when, and did it work.** Everything else (raw values, hashes, request ids) is one click deeper, never on the surface.

### 7.1 Structure

```
Audit log                                   [✓ Chain verified · 1,284 entries]  [Export CSV]
Every change and every sign-in, newest first. Undo restores the old value as a new entry.
[Person v] [Section v] (All)(Changes)(Security)(Undo)(Failures)  [Today|7 days|30 days|Custom]  [Find a field or value  /]
214 entries in 61 groups                                                   Expand all
------------------------------------------------------------------------------------------
Today  Fri 23 Oct 2026                                                        38 entries   <- sticky
 [✎] Moishe changed 3 fields in Plans and pricing                     [Undo all 3]   14:32
       Gold · Price ex VAT        £95.00  →  £110.00                        [Undo]    [i]
       Gold · Visits a month      8  →  10                                  [Undo]    [i]
       Silver · Visible           On  →  Off                Changed since 14:40       [i]
       81.2.69.160 · Safari 18 on macOS · req 7f3a9c
 [↺] Moishe undid 1 change from 14:05 in Settings                                   14:20
 [!] Sign-in failed for moishe@berko.media · wrong password                          14:02
       81.2.69.160 · Chrome 130 on Windows · /dev-login/
 [⌂] Moishe unlocked System                                                          13:58
```

Three levels, never more: **day → group → item**. A group is one save batch or one security event. Items are field changes inside a batch.

### 7.2 Type hierarchy (exact)

| Level | Size / weight | Colour | Font | Notes |
|---|---|---|---|---|
| Page title | 18px 600 | `--sys-text` | Figtree | One per page |
| Day header | 12px 600 | `--sys-text-2` | Figtree | "Today" / "Yesterday" / weekday, then the date in 12px 400 `--sys-text-3` ("Fri 23 Oct 2026"). Right: "38 entries" 12px mono `--sys-text-3`. 28px high, `--sys-bg` fill, 1px `--sys-line` bottom, `position: sticky` under the filter bar. Sentence case. |
| Group summary | 13px; **who 600**, verb 400, **what 600**, "in" + section 400 | who/what `--sys-text`, verb and section `--sys-text-2` | Figtree | Row min 36px, 16px icon in a 24px column on the left. Time right-aligned, 12px mono `--sys-text-3`, `<time datetime>` with full timestamp in `title`. Group actions sit just left of the time. |
| Item line | 13px 400 | object `--sys-text-2`, field 500 `--sys-text` | Figtree | Indented 32px (text aligns with the summary text, past the icon). Row 32px, hairline between groups only, not between items. Grid: path (min 240px) / diff (1fr) / actions (auto) / details (24px). |
| Diff | 12px | old `--sys-del` on `--sys-del-bg`, line-through; new `--sys-add` on `--sys-add-bg`; arrow `--sys-text-3` | mono | Chips 20px high, padding 0 4px, radius 4px. Screen readers get "was £95.00, now £110.00" (visually hidden), never colour alone. |
| Meta line | 12px 400 | `--sys-text-3` | mono | Last line of the group, indented 32px: `IP · browser · req id` (changes) or `IP · browser · path` (security). Browser parsed ("Safari 18 on macOS"), full UA in the drawer. Request id first 6 chars. |
| Reasons and links | 12px 400 | `--sys-text-3`; links `--sys-accent` underline on hover | Figtree | "Changed since 14:40", "Undone by Moishe · 14:40" |

Weights stay 400 / 500 / 600. Hierarchy comes from weight and grey steps, not size jumps: everything below the page title is 12 or 13px.

**Wording of the summary** (who + verb + what + where): "Moishe changed 3 fields in Plans and pricing", "Moishe changed Gold · Price ex VAT in Plans and pricing" (single item: the diff sits inline on the same line, right of the text, before actions), "Moishe added a closure in Hours and closures", "Moishe removed a closure ...", "A script changed 2 fields in Journey" (no person). The stored plain sentence is the accessible name of the group and the CSV text; the screen shows the structured version.

### 7.3 Categories

One 16px Phosphor icon (regular weight, from `icons.svg`; add the symbols below) plus colour on the icon only. The row stays white. Failures additionally get a 2px left rule. No coloured row fills, no badges on every row.

| Category | Events | Icon | Icon colour | Extra |
|---|---|---|---|---|
| Change | field saves, add, remove | `pencil-simple` (add: `plus`, remove: `minus`) | `--sys-text-2` | none: the default, quietest |
| Security | sign_in, unlock, lock_manual, lock_idle, sign_out, session_expired, export | `sign-in`, `lock-key-open`, `lock-key`, `timer`, `sign-out`, `download-simple` | `--sys-info` | none |
| Access and roles | role_changed, user_deactivated, user_reactivated | `user-gear` | `--sys-info` | summary names old → new roles as diff chips |
| Undo | undo, undo_all | `arrow-counter-clockwise` | `--sys-accent` | "from 14:05" links to the original group |
| Failure | sign_in_failed, unlock_failed, unlock_rate_limited, access_denied | `warning-octagon` | `--sys-danger` | 2px `--sys-danger` left rule on the group; outcome word ("wrong password", "rate limited", "denied") in 13px 600 `--sys-danger` after the summary |

Failures stand out by the red icon, rule and outcome word, not by a red block. `access_denied` is deduped: "Access denied 14 times from 81.2.69.160", time shows the range "13:10 to 13:52".

**Security summaries:** "Moishe signed in", "Sign-in failed for moishe@berko.media · wrong password" (email as entered, mono), "Moishe unlocked System", "Unlock failed for Moishe", "Unlock blocked for Moishe · rate limited", "Moishe locked System", "System locked after 15 idle minutes", "Moishe signed out", "Moishe's sign-in expired after 12 hours", "Moishe changed Daniel's roles" (chips `Viewer` → `Manager, Approver`), "Moishe deactivated Daniel", "Moishe exported 214 entries".

### 7.4 Expand, undo, links

- **Collapse rule.** 1 item: inline on the summary line. 2 to 3 items: shown open. More than 3: collapsed to the summary with a disclosure "Show 7 changes" (12px, `caret-right` rotating 90deg, 100ms; `aria-expanded`, `aria-controls`). "Expand all" / "Collapse all" toggle right of the result count. Expanded state survives Load more but not a filter change.
- **Undo** (24px secondary, per item) and **Undo all N** (24px secondary, on the summary; counts only items still undoable). Risky fields go through the confirm dialog (4.4). After success the button row is replaced by "Undone by you · 14:40" and the new undo group appears at the top (no animation beyond the toast).
- **Disabled states** keep the button visible with `aria-disabled="true"` and a written reason beside it, 12px `--sys-text-3`, never tooltip-only:
  - "Changed since 14:40" (links to the newer entry)
  - "Undone by Moishe · 14:40" replaces the button entirely (links to the undo group)
  - Not undoable (created, deleted, team, file): no button, no reason on the row; the drawer says "Cannot be undone: removals are permanent." Keeps rows quiet.
  - Undo all with some items blocked: "Undo all 2 of 3", title explains which.
- **Links jump in place**: clicking a time link scrolls to the target group (loading pages if needed via `?entry=<id>`), focuses it and gives it a `--sys-selected` fill for 1.5s (opacity fade; instant under reduced motion).

### 7.5 Header, filters, count

- **Integrity badge** (header right, before Export CSV), 24px, radius 4px, 12px 600:
  - OK: `--sys-ok-bg` / `--sys-ok`, `shield-check` icon, "Chain verified · 1,284 entries"; title "Checked 14:30".
  - Checking: neutral `--sys-subtle` / `--sys-text-2`, "Checking chain".
  - Broken: badge becomes `--sys-danger` fill, white "Chain broken", and a full-width banner under the page header (`--sys-danger-bg` fill, 3px `--sys-danger` left rule, 13px `--sys-text`, `role="alert"`): "**The audit chain is broken at entry 1,042.** Entries from there on may have been altered outside System." + link "Show entry 1,042". That entry carries a "Chain breaks here" danger badge and a red rule. The banner cannot be dismissed.
- **Filter bar** (sticky under the top bar; the day header sticks under it). One row at 1440: Person (select), Section (select), type chips (All · Changes · Security · Undo · Failures; toggle buttons, `aria-pressed`, multi-select, "All" clears the rest; 24px, radius 4px, selected = `--sys-selected` fill + `--sys-text` 600), Date (segmented Today · 7 days · 30 days · Custom; Custom shows two date inputs), search ("Find a field or value", `/`). All in the URL, HTMX swaps the list, back button safe. "Clear filters" link appears when any is set.
- **Result count** under the bar, 12px `--sys-text-2`, numbers mono: "214 entries in 61 groups". Announced via `aria-live="polite"` after each swap.
- **Export CSV** (secondary button, `download-simple`): exports the current filter, one row per item (security events one row each) with raw and formatted values, IP, UA, request id, hashes. Each export is itself logged as a Security entry.

### 7.6 Detail drawer

Opened by the 24px `info` icon button on any item or security group, or Enter on a focused row. Right side panel 480px (same as 4.1), `--sys-shadow-pop`, focus moves into it, Esc closes and returns focus. Deep-linkable (`?entry=<id>`).

- Title: the stored plain sentence, 15px 600.
- Field rows (grid `120px 1fr`, 12px label `--sys-text-2`, 13px value): When (`2026-10-23 14:32:07 BST`, mono), Who (name, email mono, user id), Section, Object (`plans.Plan #3 · Gold`, mono), Field (`price_ex_vat`, mono), Kind, Batch id, Request id, IP, Browser (parsed, then full UA mono wrapped), Path (`POST /plans/3/`), Outcome.
- **Old / New**: two blocks, each with a 12px label and a 24px "Copy" button (becomes "Copied" for 1.5s, `aria-live`). Raw JSON pretty-printed, 12px mono, 1.5 line height, `--sys-subtle` fill, radius 4px, padding 8px, max-height 240px scroll, wraps long strings. Formatted value shown above each block in the diff chip style.
- **Integrity**: Entry hash and Previous hash, mono, middle-truncated (`a3f91c…e209bc`) with copy for the full value; "Verified" ok text or "Does not match" danger text.
- Links: "Undo of 14:05 change", "Undone by Moishe · 14:40", "Open Plans and pricing". Undo button here too, same disabled rules.

**Accents and states.** Never a one-sided accent (left/right stripe, inset side shadow, or a ::before bar). Use no border with a soft shadow, a tinted background, or a full hairline. Selected/active states use background tint, weight or an icon. Dirty and edited: warn tint, a full hairline and a text label.

### 7.7 States and paging

- Loading a swap: the list keeps its height and drops to 50% opacity, no spinner; under 150ms nothing changes.
- 50 groups per page; a group is never split across pages. "Load 50 more" (secondary, full width of the list, 32px); while loading "Loading", disabled. Day headers do not repeat when a day continues onto the next page. End: "Start of the log · 23 Sep 2026" 12px `--sys-text-3`.
- Empty, no filters: "Nothing logged yet." Empty with filters: "No entries match these filters." + "Clear filters".
- Load error: inline `--sys-danger-bg` line "Could not load entries. Try again." with a Retry button.

### 7.8 Keyboard

`/` search, `j` / `k` next / previous group (focus ring on the group), `Enter` expand or open the drawer, `u` undo the focused item (opens the confirm when risky), `Esc` closes the drawer. Never while typing.

### 7.9 Phone (below 48em)

- Filter bar: search full width + "Filters" button with count ("Filters 2") opening a bottom sheet holding person, section, type chips, date, and the Export CSV button. Integrity badge stays in the header, shortened to "Verified" / "Chain broken"; the broken banner stays full.
- Day header sticky, 32px.
- Group: line 1 icon + summary (wraps freely); line 2 section and time, 12px. Items stack: path on one line, diff chips on the next (chips wrap, never truncate below 24 characters), actions on a third line with 36px buttons. Meta line wraps; request id moves to the drawer.
- Drawer becomes a full-height sheet; JSON blocks scroll inside; copy buttons 36px.
- No page-level horizontal scroll.

### 7.10 Proposed additions

- Icons to add to `common/static/common/img/icons.svg` (Phosphor, MIT, licence already in `img/`): `pencil-simple`, `plus`, `minus`, `sign-in`, `sign-out`, `lock-key`, `lock-key-open`, `timer`, `user-gear`, `arrow-counter-clockwise`, `warning-octagon`, `shield-check`, `download-simple`, `info`, `caret-right`, `copy`. This is the one exception to "no icons" in System: icons carry category in the log, nowhere else.
- No new colour tokens. All colours above are from 2.1.

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
3. Left list in the specified order with `aria-current`; Audit log separated by a hairline; unsaved dot appears on sections with drafts.
4. Lock button locks at once; countdown updates, turns warn under 2 minutes, offers "Stay unlocked", sends to unlock at 0 and returns to the requested page after unlock.
5. Base text 13px, rows 32px, controls 28px (in-row 24px); phone controls 36px with 16px inputs; no layout shift when a cell enters edit mode.
6. Tables: hairlines, sticky head, numbers right-aligned in mono; inline edit with Enter / Esc / Tab / F2; edited cells marked warn with "Was ..." title; long text edits in the side panel.
7. Save bar appears with drafts, counts them, Cmd/Ctrl+S saves, Discard reverts, leaving with drafts warns; success toast with working Undo (6 s, pauses on hover/focus, `role="status"`).
8. Every risky change (list in 4.4) opens the confirm with old → new diff, environment named in the title, specific action label, red action on LIVE; typed "LIVE" guard where specified; focus trap and Esc work.
9. Unlock screen as specified, wrong-password and rate-limit messages inline; non-developers get the anonymous 404 with no brand, CSS or System wording.
10. Dashboard: six tiles from stored rows only, warn/fail badges on real state, "Unknown" when a source fails; recent changes (10) and read-only stage switches linking to Settings.
11. Audit log (section 7):
    a. Newest first, grouped day → group → item; day header sticky under the sticky filter bar; a group never splits across pages; day headers do not repeat across Load more.
    b. Type exactly as 7.2: summary who/what 600 `--sys-text`, verb/section 400 `--sys-text-2`; items 13px indented 32px; diff 12px mono chips (old struck, new add colours) with visually hidden "was / now"; meta line 12px mono `--sys-text-3`; times mono with full timestamp in `title` and `<time datetime>`.
    c. Category icon and colour per 7.3 on every group; failures have the red icon, 2px red left rule and red outcome word, no red row fill; `access_denied` shows as one deduped group with count and time range.
    d. Single-item groups inline; 2 to 3 items open; more than 3 collapsed with "Show N changes" (`aria-expanded`); Expand all / Collapse all works and survives Load more.
    e. Undo per item and Undo all N per group; risky ones open the confirm; disabled states visible with written reasons ("Changed since 14:40", "Undone by ... · 14:40") that link and jump to the target; not-undoable kinds show no button.
    f. Filters (person, section, type chips with `aria-pressed`, date, search) in the URL, HTMX swap, back button safe, Clear filters; result count "N entries in M groups" updates and is announced.
    g. Integrity: OK badge with entry count; "Checking chain" while unknown; broken = red badge plus undismissable `role="alert"` banner naming the entry, with a working "Show entry" link and the entry marked "Chain breaks here".
    h. Export CSV exports the current filter and then appears in the log as a Security entry.
    i. Drawer: opens from the info button or Enter, deep-links by `?entry=`, traps and returns focus, Esc closes; shows all fields of 7.6, pretty JSON old/new with working Copy ("Copied" announced), hashes middle-truncated with full copy and verified/does-not-match state.
    j. Empty (no filters / with filters), load error with Retry, and loading at 50% opacity with no layout shift.
    k. Keyboard `j` / `k` / `Enter` / `u` / `Esc` / `/` work and never fire while typing.
    l. Phone 375px: search + Filters sheet, stacked groups, chips wrap, 36px buttons, drawer as full sheet, no page-level horizontal scroll.
    m. Contrast: every text pair from 2.1 only; icon colours 3:1 or more on white; category never shown by colour alone (icon shape + words).
12. Contrast: all text pairs as in 2.1 (4.5:1 or more), control borders 3:1 or more, focus ring visible on every interactive element; `--sys-text-3` never on `--sys-selected`.
13. Keyboard: full Tab order, `/`, Cmd/Ctrl+S, Esc, Enter, `g d`, `g a`, `?` work and never fire while typing.
14. Reduced motion removes all transforms; nothing animates on load.
15. Phone at 375px: menu sheet, stacked field rows, sideways-scrolling tables with sticky first column, save bar and dialogs usable; no page-level horizontal scroll.
16. Screenshots at 375 and 1440 of Dashboard, Plans and pricing (with drafts and the confirm open), Audit log (with a collapsed group, an open drawer, and the broken-chain banner forced on DEV), Unlock, and the 404 sent for design review.

---

## Approval page (2026-10-25)

Two panels, "Approvers" and "Final approvers" (header: title and a count badge; one intro line; the add row; the people list). Same hairlines, 4-6px corners and 13px type as the rest of System; no new colours.
- **People rows** (`system-approval.css`): name (bold) and mono email, level chip, "Send to their account email" switch (a real checkbox), Remove. Untick the switch and an address box appears with Save (Save shows only while the choice differs from what is saved). Your own row and anyone you may not change are read-only ("Emails go to ..."). Remove asks in the shared modal: "Remove {name} as approver?" with one consequence line. Phone: name, level and Remove on one line, the email choice under it.
- **Add people** is a searchable multi-select (`system-combobox.js`, ARIA combobox + listbox): chosen people are chips in the box, the list only opens while you type or press Down, filtered by name, email or level, chosen people leave the list. Keys: arrows, Home/End, Enter chooses, Esc closes, Backspace in an empty box removes the last chip, Enter never submits (the Add button does; disabled until someone is chosen). Without JS it is a plain multiple `<select>` and a submit. Everyone already chosen: "Everyone who can hold this role is already here."
- **No final approver**: a warn-tinted note at the top ("No final approver: Low-potential approvals go straight through."), no stripe.
- Below the panels: the CC note linking to Emails. Emails keeps CC and contact and ends with "Approvers are set in Approval." Team shows "Approver" / "Final approver" as read-only info chips beside the level.
