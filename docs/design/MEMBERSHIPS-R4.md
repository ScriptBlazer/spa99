# Spa 99: Memberships, round 4 (Gold invitation, compare up front)

For the frontend agent. Date 2026-10-26. Owner request (Moishe, 2026-10-26):
1. An "Apply for the Gold Card" button in the left column, to encourage applications.
2. The compare section higher up and more obvious.

Everything in MEMBERSHIPS-R2.md and MEMBERSHIPS-R3.md stays unless a row below changes it. `docs/BRAND.md` wins on any conflict. Restrained motion only (no GSAP on this page). Tokens only; no new tokens are needed.

Files: `pages/templates/pages/memberships.html`, `common/static/common/css/memberships.css`, `pages/views.py` (one context flag), `content/seed.py` + `plans/management/commands/backfill_site_data.py` (copy rows). `memberships.js` and `compare.js` need no logic change (they select `.compare-table` and `input[name="compare"]`, which stay).

---

## 1. Must not change

- Continue stays the one primary action (filled espresso). Nothing else on the page is filled.
- Card sizes, `--tier-h`, `--tier-w`, the tag column width, the selection visuals, the phone sticky tag.
- The compare table's data, the phone column picker, and the sync between the cards and the table.

---

## 2. The Gold invitation (left column)

### 2.1 What it is

A quiet secondary block that sits **below** the choice group, so the eye meets Continue first and Gold second.

```
[swan mark]  The Gold Card is free, by application.
             [ Apply for the Gold Card  → ]      <- outlined, auto width
```

- Wrapper: `<div class="mem-gold mem-fade">` (it rises with the tag, as `.mem-fade` already does).
- Mark: `{% include "common/_mark.html" %}`, `width: 1.25rem`, `color: var(--color-caramel)` (decoration only, so caramel on cream is allowed; BRAND section 2). It sits beside the text, `align-items: flex-start`, gap `--space-2`.
- Hook: `<p class="mem-gold-hook">`, Figtree `--text-sm`, `--color-text` (espresso on cream, 10.95:1). One line at 18rem.
- Button: `<a class="btn btn-secondary mem-gold-btn" href="...">` + `{% include "common/_icon.html" with name="arrow-right" %}`. **Auto width** (never `width: 100%`, so it never matches the full-width Continue). Standard `--control-h` height (touch target). `margin-top: var(--space-3)`. Espresso 1px outline on cream: 10.95:1.
- **Not gold-outlined.** Gold on cream is 1.78:1 (BRAND: decoration only), too weak for the edge or label of a control. The gold note comes from the swan mark and the words, not the button.
- Hover (fine pointer): the arrow moves 3px right, 200ms `--ease-soft`, the same as the "Tailor your membership" link (`.mem-notsure-link`); reuse that rule. Reduced motion: no movement.
- No box, no panel, no border around the block, no one-sided line above it. The separation is space only: `margin-top: var(--space-5)` above it on desktop.

### 2.2 Desktop (80em and up, two columns)

Add a fourth row to the grid. The cards still span the first three rows, so their height and position do not move.

```css
.mem-grid {
  grid-template-rows: auto 1fr auto auto;
  grid-template-areas: "top cards" ". cards" "choice cards" "gold more";
}
.mem-gold { grid-area: gold; }
.mem-more { grid-area: more; }   /* the compare link, section 3.2 */
```

Order in the tag column: title, subtitle, "Not sure?" link, (space), Your choice / name / price / sale line / Continue / "Register. Nothing to pay now.", then `--space-5`, then the Gold block.

Height check at 1440 x 800: the column is about 610px against 560px cards, inside the 100svh stage. At 1280 x 720 the Gold block may fall just below the fold; that is fine, but **Continue must be fully visible in the first viewport at 1280 x 720 and 1440 x 800**. If it is not, reduce the `1fr` spacer gap first, never the space between Continue and its note.

### 2.3 Phone and tablet (below 80em, one column)

DOM order inside `.mem-grid`: `.mem-top`, `fieldset.tiers`, `.mem-more`, `.mem-choice`, `.mem-gold`. This matches the desktop reading order (Continue before Gold), so keyboard and screen-reader order follow what is seen at every width.

- The sticky tag stays pinned while the cards scroll; at the end of the form it settles into its natural place, and the Gold block follows it. That reads as "your choice, Continue, and also the Gold Card".
- `.mem-gold` on a phone: `width: 100%; max-width: 30rem; margin-inline: auto;` (lines up with the stacked cards), `margin-top: var(--space-3)`, left aligned.
- The button stays auto width at 375px (no `.btn-block-phone`): it must read as secondary next to the full-width Continue in the sticky tag.
- The Gold block is **never** in the sticky tag.

### 2.4 Who sees it

New context flag from `memberships()` in `pages/views.py`:

```python
gold_cta = not (request.user.is_authenticated and GoldApplication.objects.filter(user=request.user).exists())
```

(`GoldApplication.user` is linked automatically when the applicant registers with the same email.) Any status hides it: a pending, approved (already Gold), declined or awaiting-final application. Visitors who are not signed in always see it.

Template: `{% if gold_cta and m.gold_cta.cta_label %}...{% endif %}`. Clearing the row's button label in Control hides the block, so the owner has an off switch without code.

Applications closed (`register_interest_open` off): still show it, as the Gold Card page does; the apply page already says "Applications are not open yet."

### 2.5 The old Gold line below the page

Remove `.gold-aside` (the `gold_line` sentence in `.mem-also`) from the template: one Gold invitation per page. The `gold_line` row stays in the database, unused. With it gone, `.plan-aside` (Single visit) spans the row: `.plan-aside { grid-column: 1 / -1; }`, and delete the `.gold-aside` rules.

---

## 3. Compare, moved up and made obvious

### 3.1 Where it is now, where it goes

Now: last on the page, a closed `<details>` with a small "Compare everything" summary, below Every visit, Single visit and the Gold line. Easy to miss.

New order of the page:
1. The stage (form): tag column + cards.
2. **Compare memberships** (open, its own section).
3. `.mem-also`: Every visit, then Single visit.
4. VAT note.

At 1440 x 800 the section starts just under the fold; the link in 3.2 points to it.

### 3.2 The link near the cards: "Compare memberships"

- Element: `<p class="mem-more"><a class="btn-quiet mem-more-link" href="#compare">{{ m.compare.cta_label }} {% include "common/_icon.html" with name="caret-down" %}</a></p>`, inside `.mem-grid`, after the fieldset.
- Style: same as `.mem-notsure-link` (`--text-base`, weight 600, underline 1.5px, offset 0.3em, gap `--space-2`), espresso. Icon 1rem.
- Desktop: grid area `more`, under the cards, `justify-self: end; align-self: end;` so it lines up with the cards' right edge and on the same row as the Gold button. `margin-top: var(--space-3)`.
- Phone: centred under the stacked cards (`text-align: center`), `margin-top: var(--space-2)`.
- Hover (fine pointer): the caret moves 2px down, 200ms `--ease-soft`. Reduced motion: none.
- Smooth scroll, motion allowed only: `@media (prefers-reduced-motion: no-preference) { html:has(.page-mem) { scroll-behavior: smooth; } }`. The existing `scroll-padding-top` keeps the heading clear of the header; `scroll-padding-bottom` already keeps clear of the sticky tag.

### 3.3 The section

Replace `<details class="compare">` with an always-open section:

```html
<section class="compare" id="compare" aria-labelledby="compare-title" data-reveal>
  <div class="compare-head">
    <h2 id="compare-title">{{ m.compare.heading }}</h2>
    <p class="compare-lead">{{ m.compare.body }}</p>
  </div>
  <div class="compare-body" data-compare> ...picker + table unchanged... </div>
</section>
```

- Placement: inside the `.container` that follows the form, as its first child, `margin-top: var(--space-6)` on desktop, `var(--space-5)` on a phone.
- Heading: `h2` default (display face, `--text-xl`, `--tracking-display`, weight 500). Lead: Figtree `--text-body`, `--color-text-muted` (5.32:1), `margin-top: var(--space-2)`. Head block `margin-bottom: var(--space-4)`.
- Panel: the table sits on a raised card so it reads as one object: `.compare-body { background: var(--color-cream-raised); border: 1px solid var(--color-tier-edge); border-radius: var(--radius-md); box-shadow: var(--shadow-tier); padding: var(--space-4); }`, `var(--space-5)` from 48em. A full hairline on all four sides plus a soft shadow (no one-sided line).
- The selected column: on the raised panel `--color-cream-raised` no longer shows, so use `--color-chosen-wash` (gold at 8%) for `td.is-selected, th.is-selected`. Espresso text stays above 10:1. Keep weight 600 on selected cells and the check in the header.
- **Remove** `.compare-table thead th.is-selected { box-shadow: inset 0 2px 0 var(--color-espresso); }`: that is a one-sided accent (BRAND section 9). The wash, weight and check already mark the column.
- Row group lines (`tr.grp-start > * { border-top }`) stay: they are full-width row dividers, not accents.
- Phone: the segmented picker stays above the table inside the panel; padding `--space-3` below 30em so the one visible column has room.
- Delete: the `summary` rules, the `+`/X rotation, `.compare[open] .compare-body` animation, `.compare-summary`. Keep the `html[data-input="pointer"]` focus rule for the tiers only.
- Motion: the whole section uses the existing `data-reveal` group fade up. Nothing else.

---

## 4. Copy (content rows, page `memberships`, editable in Control)

Columns: key, heading, body, cta_label, cta_url.

| Key | Heading | Body | Button label | URL | Status |
|---|---|---|---|---|---|
| `gold_cta` | (empty) | The Gold Card is free, by application. | Apply for the Gold Card | `/gold-card/apply/` | **New row** |
| `compare` | Compare memberships. | Every membership, side by side. | Compare memberships | `#compare` | **Changed** (was "Compare everything", other fields empty) |
| `gold_line` | | | | | Left in the database, no longer shown |

Template use:
- Gold button href: `{{ m.gold_cta.cta_url|default:gold_apply_url }}` with `{% url 'gold_apply' as gold_apply_url %}`. The rest of the site sends "Apply" buttons to `gold_apply` and "About" links to `gold_card`; this is an Apply button.
- Compare link href stays `#compare` in the template (not the row URL), so the anchor cannot be broken from Control. The row URL is informational.

Seed (`content/seed.py`, memberships list):
```python
("compare", "Compare memberships.", "Every membership, side by side.", "Compare memberships", "#compare"),
("gold_cta", "", "The Gold Card is free, by application.", "Apply for the Gold Card", "/gold-card/apply/"),
```

Backfill (`backfill_site_data.py`, same pattern as the 2026-10-26 entries):
- Missing row: create `gold_cta` if it does not exist.
- Exact old wording only: `("memberships", "compare", "heading", "Compare everything", "Compare memberships.")`; fill `compare.body`, `compare.cta_label` and `compare.cta_url` only where they are empty.
- Add a dated line to the command's docstring.

Tone check: no exclamation marks, no "exclusive", no urgency. The sale line, when a sale runs, stays only on the cards and the tag; never on the Gold block (the Gold Card is free).

---

## 5. Acceptance checks

Screenshots at 375 x 667, 1440 x 800 and 1280 x 720 (`.private/shots/memberships-r4/`), signed out and signed in with a Gold application.

1. 1440: the left column reads title, subtitle, Not sure, choice, Continue, note, then the Gold block. Continue is the only filled button; the Gold button is outlined, auto width, with the caramel swan beside the one-line hook.
2. 1440: the cards are in the same place and size as R3 (overlay: no more than 1px). "Compare memberships" with a caret sits under the cards, right aligned, level with the Gold button.
3. Clicking the link scrolls smoothly to the compare heading, clear of the header; under reduced motion it jumps.
4. The compare section is open, directly under the stage, with a heading, a lead and a raised cream panel with an even edge. The selected column has the gold wash and the check; no 2px bar on the header.
5. 375: cards, centred compare link, the sticky tag with Continue (pinned while scrolling the cards, settled at the end), then the Gold block (button not full width). The Gold block never appears in the sticky tag and is never covered by it.
6. Signed in with any Gold application: no Gold block anywhere on the page. Clearing `gold_cta` button label in Control also hides it.
7. The Gold line under Single visit is gone; Single visit spans its row.
8. Keyboard: Tab order is the cards (one stop, arrows inside), compare link, Continue, Gold button, at every width. Focus rings unchanged.
9. Contrast: Gold hook and button 10.95:1; compare lead 5.32:1 on cream; selected cells espresso on cream-raised plus the 8% wash above 10:1.
