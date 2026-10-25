# System code view: design brief

Spec: `docs/features/system-code-view.md` (2026-10-25). Look: `docs/design/SYSTEM.md`, unchanged. Modal and toast: `docs/design/FEEDBACK.md`. Brand rule: never a one-sided accent; tint, full hairline, or no border + soft shadow.

**Design read.** A view switch inside existing developer tooling, like GitHub's Code / Preview toggle or a Vercel config tab. Same shell, same tokens, same 13px density. "More dev" comes from the content (mono code, line numbers, diffs), not from a new skin: no dark editor, no new chrome. Dials: variance 1, motion 1, density 8.

## 1. Where it lives

**Replaces the page body in place.** The page header stays; every panel below it gets `hidden`; one `.sc-panel` takes their place inside `.sys-main`. No overlay, no drawer: the 480px drawer is too narrow for code, an overlay hides the header that names the page, and an in-place swap needs no z-index or focus trap.

- URL gains `?view=code` (`history.replaceState`), so reload and back keep the view. Closing removes it.
- `.sc-panel` = a `.sys-panel` (white, 1px `--sys-line`, 6px radius, no shadow), `display: grid; grid-template-rows: 40px 1fr 28px` (toolbar, body, status).
- Height: `height: calc(100dvh - var(--sys-top-h) - var(--sys-stripe) - 148px); min-height: 360px`. The page itself does not scroll; the editor scrolls inside.
- The page's save bar is hidden while the code view is open. If the page has unsaved drafts when `</>` is pressed: `confirmModal` "Open code without your 3 unsaved changes?" body "The code shows what is saved. Your drafts stay on the page.", buttons "Cancel" / "Open code".
- Phone (below 48em): same swap, panel full bleed (`margin-inline: calc(-1 * var(--sys-3))`, radius 0), height `calc(100dvh - var(--sys-top-h) - 120px)`, min 320px. Code never wraps; the body scrolls sideways inside the panel. No page-level horizontal scroll.

## 2. The icon

- **Markup**: `_page_header.html` takes an optional `code_url`. When set, render at the far right of `.sys-head` (after any `.sys-actions`; `margin-left: auto` if alone):
  `<button type="button" class="sc-toggle" data-system-code="{{ code_url }}" aria-pressed="false" aria-controls="sc-panel" aria-label="Rules as code" title="Rules as code (`)">`
- Glyph: Phosphor `code` (regular, the `</>` shape), 16px, add to `system-icons.svg` with `x` (close). No text label.
- Box 28 x 28px (`--sys-ctl`, matches header buttons), radius `--sys-radius`, no border, transparent.
- States: rest icon `--sys-text-3`; hover `--sys-subtle` fill, icon `--sys-text`; pressed (`aria-pressed="true"`, view open) `--sys-selected` fill, icon `--sys-text`; focus the System ring (2px `--sys-accent`, offset 2px). 100ms colour transition only.
- Phone: hit area 36 x 36px (icon stays 16px). Under `pointer: coarse` the tooltip is not relied on.
- Keyboard: `` ` `` (backtick) toggles the view when not typing. Add to `_keys.html`: "`` ` `` Rules as code", "Ctrl Enter Review (Cmd on Mac)", "Esc Close the code view".

## 3. Toolbar and status strip

**Toolbar** (40px, padding 0 `--sys-3`, 1px `--sys-line` bottom, flex, gap `--sys-2`):
- Left: file name `spa99 / rules / plans.py`, 12px mono `--sys-text-2`; then a state badge (existing `.sys-badge`, 20px): "Read only" (`--sys-subtle` / `--sys-text-2`), "Editing" (`--sys-warn-bg` / `--sys-warn`), "Review" (`--sys-info-bg` / `--sys-info`).
- Right, by state (all `.sys-btn sm`, 24px; phone 36px):
  - Read only: "Copy", "Edit".
  - Editing: "Discard" (only when dirty), "Review" (`.primary`, disabled until the text differs).
  - Review: "Back to code", "Apply 4 changes" (`.primary`; `.danger` on LIVE when any change is risky).
  - Always last: close, 24px square, `x` icon 12px, `aria-label="Close code view"`.
- Phone: file name drops to `plans.py`; Copy moves into the status strip.

**Status strip** (28px, `--sys-bg`, 1px `--sys-line` top, 12px mono `--sys-text-3`, padding 0 `--sys-3`): left `Ln 14, Col 9`; right `42 lines · 1.8 / 128 KB`. Over 96 KB the size turns `--sys-warn`. Errors take over the left side (section 6).

## 4. Editor

**Build constraint**: a `<textarea>` layered exactly over a highlighted `<pre>`, no library. Both share one rule so they never drift:
`font: 400 var(--sc-fs)/var(--sc-lh) var(--sys-mono); letter-spacing: 0; tab-size: 4; white-space: pre; overflow-wrap: normal; font-variant-ligatures: none; padding: var(--sys-2) var(--sys-3);` The textarea is on top with `color: transparent; caret-color: var(--sys-text); background: transparent; resize: none`; the pre is `aria-hidden="true"`. Scroll is synced from textarea to pre and gutter.

- **Font**: the existing `--sys-mono` system stack (SF Mono, Menlo, Consolas). Nothing to download, no CDN. 13px / 20px line height (fixed px so gutter rows, tints and markers align by `line * 20px`). Phone: 16px / 24px (no iOS zoom on focus).
- **Gutter**: 48px wide (56px past 999 lines), `--sc-gutter` fill, no border (the tint alone separates it from the code). Numbers right-aligned, padding-right 8px, 12px mono `--sc-ln`, `user-select: none`, `aria-hidden`. Current line number `--sys-text` 600.
- **Current line**: full-width `--sc-line` row drawn in the pre layer (behind text), only while the editor has focus. No border.
- **Selection**: `textarea::selection { background: var(--sc-sel); }` Semi-transparent, so highlighted text from the pre shows through (comment text stays 4.59:1 on it).
- **Read-only state**: the same view with the textarea `readonly`; caret hidden; text selectable for copy. "Edit" removes `readonly`, focuses at line 1 col 1.
- **Read-only fields** (`id`, key slugs): the value in `--sc-ro` (no syntax colour) and the generator writes a trailing `# read only` comment aligned to column 34. Changing one is a server error on that line.
- **Header comment** (lines 1 to 2) in comment colour; line 2 carries the generated timestamp, which is what "fresh" looks like.
- **Editing keys**: Tab inserts 4 spaces (with a selection: indents those lines); Shift+Tab outdents; Enter keeps the current indent (+4 after `{`, `[`, `(`); Ctrl/Cmd+Enter = Review; Esc = close (section 7). Ctrl+M toggles "Tab moves focus" for keyboard users; when on, the status strip shows "Tab moves focus".

## 5. Syntax colours (light, AA on white, current line, diff tints and danger tint)

| Token | Value | Applies to | On white | Worst case |
|---|---|---|---|---|
| `--sc-name` | `var(--sys-text)` | `PLANS`, `=`; 600 weight | 17.38 | 13.5 sel |
| `--sc-key` | `var(--sys-info)` #2C5A8F | dict keys `"name"` | 7.08 | 5.50 sel |
| `--sc-str` | `var(--sys-ok)` #1A6B43 | string values | 6.51 | 5.06 sel |
| `--sc-num` | `var(--sys-warn)` #8A5300 | ints, decimals-as-strings stay `--sc-str` | 6.33 | 4.92 sel |
| `--sc-kw` | `#8A2F6B` (new, plum) | `True`, `False`, `None`; 600 weight | 7.78 | 6.05 sel |
| `--sc-com` | `var(--sys-text-3)` | comments incl. `# read only`; italic off | 5.49 | 4.59 sel, 4.75 on del/danger tint |
| `--sc-punc` | `var(--sys-text-2)` | `{ } [ ] : ,` | 7.45 | 5.79 sel |
| `--sc-ro` | `var(--sys-text-3)` | read-only values | 5.49 | 4.59 sel |

Tokens get classes in the pre: `.sc-k .sc-s .sc-n .sc-kw .sc-c .sc-p .sc-ro .sc-id`. Unknown text falls back to `--sys-text`.

## 6. Errors

Server returns `{line, col, message}` per error (parse errors and field validation both map to a line).
- **Line marker**: full-width `--sc-err` (= `--sys-danger-bg`) row in the pre layer, behind text. No border of any kind.
- **Gutter**: the line number turns `--sys-danger` 600 and a 12px `warning-octagon` icon in `--sys-danger` sits left of it (gutter grows to 64px while errors exist). The icon has `title` = the message.
- **Column**: a 2px-high `--sys-danger` underline (wavy where supported) under the token starting at `col`, in the pre layer.
- **Status strip** becomes `--sys-danger-bg`, text `--sys-text` 12px: "Line 14, column 9: Enter a price above £0.00." With more than one: "2 problems · Line 14 ..." and Next / Previous (F8 / Shift+F8). Clicking the message moves the caret to that line and column and scrolls it to the vertical middle.
- The caret jumps to the first error after a failed Review or Apply. A hidden `role="alert"` region announces "2 problems. Nothing was saved. First: line 14, column 9, Enter a price above £0.00."
- Markers clear on the next edit of that line.

## 7. Review

Review (button or Ctrl/Cmd+Enter) posts to preview. The button reads "Checking" and is disabled; the body keeps its height at 50% opacity (nothing under 150ms). On success the editor body is replaced by the review body in the same panel (inline, not a modal: diffs are wider than the 420px modal). Badge "Review".

**Review body** (scrolls inside the panel), two blocks separated by a full hairline:
1. **Field changes** first (what will actually happen), heading 12px 600 `--sys-text-2` "4 changes in 2 plans". Rows 32px, grid `minmax(240px, auto) 1fr auto`: path `Tier 1 · price_ex_vat` (object `--sys-text-2`, field mono 500 `--sys-text`), the existing `_audit_diff.html` chips (old struck on `--sys-danger-bg`, new on `--sys-ok-bg`, hidden "was / now"), and for risky fields a `.sys-badge` "Confirm" (`--sys-warn-bg` / `--sys-warn`). Hairlines between rows. New rows show "added" in place of the old chip; removed closures show "removed".
2. **Code diff**, unified, same mono 13/20 and syntax colours. Columns: old line no (40px), new line no (40px), sign (16px), code. Added rows: full-width `--sys-ok-bg`, sign `+` in `--sys-add` 600. Removed rows: full-width `--sys-danger-bg`, sign `−` in `--sys-del` 600. Context rows white. Runs of more than 6 unchanged lines collapse to a 24px `--sys-subtle` row "Show 18 unchanged lines" (12px `--sys-text-3`, a button). Screen readers get "added line 14" / "removed line 14" (visually hidden), never colour alone.

**No changes**: body shows one 64px line, `--sys-text-2`: "Nothing to change. The code matches what is saved." Apply hidden.

**Apply**: if any change is risky, the shared `confirmModal` opens with `details` = the risky rows only (same chips), title "Change prices on LIVE?" (or the System wording from SYSTEM.md 4.4), tone `danger` on LIVE, confirm label "Apply 4 changes". Then Apply shows "Applying", disabled. One request, all or nothing.

**Back to code** (or Esc in review) returns to the editor with the caret where it was.

## 8. States and copy (British English, no exclamation marks)

| State | Shown |
|---|---|
| Loading | Panel at full height, gutter visible, "Loading code" 12px `--sys-text-3` at top left of the body. No spinner, no skeleton lines. |
| Load failed | Body: "Could not load the code." + "Try again" (`.sys-btn sm`). |
| Read only | Toolbar "Read only"; status as section 3. |
| Saved | Toast (existing): "Saved 4 changes." with "Undo all" (6 s). View returns to read only with fresh code (new timestamp in line 2); scroll position kept. |
| Errors | Section 6. Toolbar stays "Editing". |
| Stale (409) | A strip under the toolbar, full width, `--sys-warn-bg`, full 1px `--sys-line` top and bottom, 13px `--sys-text`: "**Changed since you opened it.** Someone saved this page after you opened the code." Buttons: "Copy my version", "Load the latest" (if dirty, `confirmModal` "Load the latest code? Your edits will be lost." "Keep editing" / "Load the latest"). `role="alert"`. Apply disabled until resolved. |
| Network | Toast error (stays): "Could not reach System. Your code is still here." |
| Too large | Status size turns `--sys-danger` past 128 KB; Review disabled with the reason in the strip: "Over 128 KB. Shorten it to review." |
| Close with edits | `confirmModal` tone danger: "Close without applying?" / "Your edits will be lost." / "Keep editing" (focused) and "Close". |
| Copy | Button reads "Copied" for 1.5 s, announced via `aria-live="polite"`. |

## 9. Accessibility

- Focus order: `</>` toggle, toolbar (file name is text, not focusable), badge skipped, action buttons, close, editor (or review list), status strip buttons. Opening moves focus to the editor (read only: the textarea, so arrow keys scroll and select); closing returns it to the toggle.
- Textarea: `id="sc-input"`, `aria-label="Plans rules as code"`, `aria-multiline="true"`, `aria-readonly` mirrors state, `aria-describedby` = the status strip and the key hint ("Tab inserts 4 spaces. Ctrl M to move focus with Tab. Ctrl Enter to review."), `spellcheck="false" autocapitalize="off" autocomplete="off" autocorrect="off"`. On error, `aria-invalid="true"` and `aria-errormessage` = the strip.
- Panel: `<section id="sc-panel" aria-label="Rules as code">`. Review count heading is announced (`aria-live="polite"`).
- Contrast: every pair in section 5 is 4.5:1 or more, including on selection and tints. Diff signs plus hidden text carry meaning, not colour.
- Motion: none on open, swap or review (System motion 1). Only 100ms colour transitions on buttons and the existing toast/modal motion. `prefers-reduced-motion` already strips transforms in `system.css`.

## 10. Tokens to add (System only, in `system.css` under `body.system`; frontend lists them in BRAND.md section 8, marked "System code view, derived")

```css
--sc-fs: 13px; --sc-lh: 20px;            /* phone (below 48em): 16px / 24px */
--sc-gutter: var(--sys-bg);              /* #F6F6F4 */
--sc-ln: var(--sys-text-3);
--sc-line: #F7F6F3;                      /* new: current-line tint, text 16.08, comment 5.08 */
--sc-sel: rgb(73 46 33 / .10);           /* new: espresso tint, composites to #EDEAE9 */
--sc-err: var(--sys-danger-bg);
--sc-name: var(--sys-text); --sc-key: var(--sys-info); --sc-str: var(--sys-ok); --sc-num: var(--sys-warn);
--sc-kw: #8A2F6B;                        /* new: plum, 7.78 on white */
--sc-com: var(--sys-text-3); --sc-punc: var(--sys-text-2); --sc-ro: var(--sys-text-3);
```

Only three new values (`--sc-line`, `--sc-sel`, `--sc-kw`); the rest alias existing `--sys-*`. New CSS file `common/static/common/css/system-code.css`, loaded only on rule pages. Icons `code` and `x` (Phosphor, MIT) added to `system-icons.svg`.

## 11. Acceptance (screenshots at 375 and 1440)

1. Plans page with code open (read only), editing with a current line, an error on line 14, the review (field list + diff with a collapsed run), the risky confirm, and the stale strip.
2. Page header identical to today when closed; the toggle is the only addition.
3. Editor text and highlight never drift after typing, Tab, paste, or scrolling 200+ lines; phone input 16px.
4. No one-sided borders anywhere: error lines, diff rows, the stale strip and the current line are tints only.
