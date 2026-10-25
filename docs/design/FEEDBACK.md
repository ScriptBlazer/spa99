# Feedback: toasts and the one modal

2026-10-25. Moishe: notifications are big, bulky and off-theme; modals must be one common, centred, professional component, never the browser's. Supersedes the toast/modal parts of MEMBER.md (69, 184-187), OFFICE.md 7.6, SYSTEM.md 4.3-4.4 (visuals only, behaviour kept), CONTROL.md dialog/toast styling.

One component, five skins. Markup, JS and behaviour are shared; each host only sets the `--fb-*` variables (section 4).

## 1. Toast

```
 phone 375                              desktop 1440
 +-----------------------------+        +--------------------------------------------+
 |                             |        |                                            |
 |                             |        |                                            |
 | +-------------------------+ |        |                    +-----------------------+|
 | | (v) You're signed out. x| |        |                    | (v) Saved.        Undo x||
 | +-------------------------+ |        |                    +-----------------------+|
 |  16px gutters, above bars   |        |                       360px, 24px from edges|
 | [ tab bar / safe area     ] |        +--------------------------------------------+
 +-----------------------------+
```

**Shape**
- One line where possible: icon, text, optional action, close. Min height 48px. No title, no heading, never a paragraph (two lines max; longer copy belongs inline or in a modal).
- Padding `var(--space-2)` block, `var(--space-3)` start, `var(--space-1)` end (the close button's 44px hit area supplies the rest). Gap `var(--space-2)`.
- Width: phone `calc(100% - 2 * var(--space-3))` (16px gutters, plus `env(safe-area-inset-left/right)`); from 64em fixed `22.5rem` (360px).
- Radius `--fb-radius`. Edge: 1px `--fb-edge` (inset box-shadow, no layout). Shadow `--fb-shadow`.
- Type: `--font-body`, `--text-sm` (14px), weight 500, `--leading-snug`, `--tracking-body`, colour `--fb-text`. Action button: same size, weight 600, `--fb-text`, underline on hover only.

**Icon (state is never colour alone)**: 16px inline SVG, stroke 1.5, round caps, in a 20px box, coloured by kind. Shapes differ:

| Kind | Shape | Hidden prefix (screen readers) | Colour var |
|---|---|---|---|
| success | check in circle | "Done: " | `--fb-ok` |
| info | "i" in circle | "Note: " | `--fb-info` |
| warning | "!" in triangle | "Warning: " | `--fb-warn` |
| error | "!" in circle | "Error: " | `--fb-danger` |

**Close**: a 12px "x" (stroke 1.5, `--fb-muted`) centred in a 44 x 44 hit area, `aria-label="Dismiss"`. Visible hover/focus disc 28px, `--fb-hover`. Focus ring 2px `--fb-focus`, offset 2px. Replaces the underlined "Dismiss" text.

**Position**
- Phone (below 64em): bottom, centred, `bottom: calc(var(--fb-bar, 0px) + env(safe-area-inset-bottom) + var(--space-3))`. `--fb-bar` = the host's bottom bar (member `--member-tabbar-h`, Office `--office-tabbar-h` or the decision bar, Control `--ctl-tab-h` (+64px with mini player)), 0 on the public site and System. When the keyboard is up (`m-typing`) or no bar is shown, `--fb-bar: 0`.
- Desktop (64em up): bottom right, `right: var(--space-4)`, `bottom: var(--space-4)` (24px) on every host. Member moves from top right to bottom right so all hosts agree.
- Public site: no longer inline in `.container` at the top of `<main>`; it floats like everywhere else. z-index above header and bars, below the modal.

**Stacking**: newest at the bottom (nearest the thumb), gap `var(--space-2)`, max 3. A fourth removes the oldest non-error toast; if all three are errors, the oldest error goes. Same text twice in a row replaces the old one (no duplicates).

**Timing**
- success, info: 4s. With an action (Undo): 6s. warning: 6s. error: stays until dismissed, or until the cause clears (e.g. journey save succeeds and calls `dismiss`).
- Timers pause on hover, on focus inside the toast, and while the tab is hidden.

**Motion** (CSS transitions, not keyframes, so a quick second toast retargets)
- In: opacity 0 to 1 and `translateY(var(--rise))` to 0, 240ms (`--duration-ack`), `--ease-soft`. Via `@starting-style` (fallback: `data-in` attribute set next frame).
- Out: opacity to 0, 160ms, no movement, then removed. The others close up instantly (no layout animation). This is the one sanctioned exit fade (BRAND 7B bans exit animation; a toast blinking out reads as a glitch). Already accepted in MEMBER.md.
- Reduced motion: in and out instant, no travel.

**Accessibility**: two live regions exist in the page from load, inside `<section class="toasts" aria-label="Notifications">`: `<ol role="status" aria-live="polite">` (success, info, warning) and `<ol role="alert" aria-live="assertive">` (error). Server messages are rendered as a `<template>`, then moved into the regions 100ms after load so they are announced. Focus is never moved to a toast. Toasts are not in the tab order except their buttons.

**Copy**: one short sentence, full stop, no exclamation marks, no "Success!". "You're signed out." "Saved." "We couldn't save that. Please try again."

## 2. The modal (confirm, alert)

```
 phone 375                          desktop 1440
 +---------------------------+      +--------------------------------------+
 |///// tint + 4px blur /////|      |/////////////////////////////////////|
 | +-----------------------+ |      |////  +------------------------+  ////|
 | | Delete your account?  | |      |////  | Delete your account?   |  ////|
 | | Your bookings and     | |      |////  | Your bookings and data |  ////|
 | | data are removed.     | |      |////  | are removed. This...   |  ////|
 | |                       | |      |////  |      [Cancel] [Delete] |  ////|
 | | [ Cancel ][ Delete  ] | |      |////  +------------------------+  ////|
 | +-----------------------+ |      |///////////  420px, centred  /////////|
 +---------------------------+      +--------------------------------------+
```

**Decision: centred on every screen, never a bottom sheet.** A confirm or error interrupts; Moishe asked for centred; one shape everywhere is calmer than two; and the short content never needs the reach of a sheet. Bottom sheets stay for content panels (Office `.o-sheet`, Control panels, System menu), not for this modal. The current phone bottom-sheet rules for `.modal`, `.office .modal`, `.sys-dialog` and `.ctl-dialog` go.

**Box**
- Native `<dialog>` opened with `showModal()`, `margin: auto`, width `min(26.25rem, 100vw - 2 * var(--space-3))` (420px; phone full width with 16px gutters), `max-height: calc(100dvh - 2 * var(--space-4))`, body scrolls if needed.
- Padding `var(--space-4)` (24px) all round. Radius `--fb-modal-radius`. Background `--fb-surface`, text `--fb-text`, shadow `--fb-modal-shadow`, no border.
- Backdrop: `--fb-overlay` plus `backdrop-filter: blur(4px)`; no blur under `prefers-reduced-transparency: reduce`.

**Type**
- Optional icon (alert only, tones warning and error; confirm never): 20px, same shapes as toasts, inline before the title, `--fb-warn` / `--fb-danger`.
- Title: `--fb-title-font` weight 500, `--text-lg` (20px), `--leading-tight`, `--tracking-display`. Down from `--text-xl`: this is a question, not a headline.
- Body: `--text-base`, `--leading-snug`, `--fb-muted`, `margin-top: var(--space-2)`. One or two sentences.

**Buttons**: row at the end, `margin-top: var(--space-4)`, gap `var(--space-2)`, right aligned. Order: secondary (Cancel) left, primary or destructive right. Height `--chip-h` (44px), radius `--fb-btn-radius`, `--text-sm` weight 600, padding-inline `var(--space-3)`, min width 6rem. Phone (below 30em): both buttons share the row 50/50; if a label would wrap, they stack with the action on top.

| Style | Fill | Text | Edge |
|---|---|---|---|
| primary | `--fb-primary` | `--fb-on-primary` | none |
| destructive | `--fb-danger-fill` | `--fb-on-danger` | none |
| secondary | transparent | `--fb-text` | 1px `--fb-line` |

Labels name the action ("Delete account", "Reset demo"), never "OK/Yes". Alert's single button: "Close" (primary).

**Keyboard and focus**: focus trapped (native). Initial focus: Cancel when tone is `danger`, otherwise the primary button; alert focuses its button. Esc and a backdrop click resolve `false` (cancel). Enter activates the focused button only. On close, focus returns to the element that opened it (stored by the script; native return is not relied on). Page scroll locked while open (`body:has(dialog[open])`, already in components.css).

**Motion**: open: opacity 0 to 1 and `scale(0.98)` to 1, 200ms, `--ease-soft`, origin centre; backdrop opacity 200ms. Close: instant (BRAND 7B). Reduced motion: opens instantly.

**API** (one module, `common/static/common/js/feedback.js`; also `window.spa99Feedback` for System's non-module script)

```js
toast(text, { kind = 'success', action /* {label, onClick} */, timeout })   // returns the element
dismiss(toastElement)
confirmModal({ title, body, confirmLabel = 'Confirm', cancelLabel = 'Cancel', tone = 'neutral' /* | 'danger' */,
               details /* optional Node, e.g. System's diff */, guard /* optional word to type, e.g. 'LIVE' */ }) // Promise<boolean>
alertModal({ title, body, tone = 'info' /* | 'success' | 'warning' | 'error' */, closeLabel = 'Close' })         // Promise<void>
```
- `message`/`danger` accepted as aliases during migration. `data-confirm*` attributes keep working (`data-confirm-body`, old `data-confirm-message` alias).
- A second call while open queues; it never replaces the open one.
- Control's `formDialog(build)` stays (it is a small form, not a confirm) but uses the same dialog element, classes and motion.
- **No `window.alert/confirm/prompt` anywhere, ever.** If the dialog element is missing, the script creates it. If `HTMLDialogElement.prototype.showModal` is missing, the same markup is shown as `<div role="dialog" aria-modal="true">` in a fixed overlay with the same look, a script focus trap, `inert` on the page, Esc to cancel. Never resolve `true` without the person choosing.

## 3. Inline, toast or modal

| Situation | Use | Example |
|---|---|---|
| A field is wrong or missing | Inline, under the field, `aria-describedby`, focus the first bad field on submit | "Enter a valid email." |
| Whole form refused by the server (rate limit, wrong password) | Inline, at the top of the form | Sign-in errors |
| An action worked | Toast success | "Saved." "You're signed out." |
| Background save or network failed, work is safe | Toast error (stays) | Journey and Gold save errors |
| Something destructive or hard to undo is about to happen | `confirmModal`, tone danger | Delete account, Decline application |
| A blocking error the person must read before going on (session expired, cannot continue) | `alertModal`, tone error | "Your session ended. Sign in again." |
| Reversible bulk change | Toast with Undo, no modal | Control "All music muted." |

Never a modal for field errors, never a toast for something that needs a decision.

## 4. Theming per host (`--fb-*`)

| Var | Public + member | Office | System | Control (dark) |
|---|---|---|---|---|
| toast surface | `--color-espresso` (on `.on-dark` scenes `--color-espresso-raised`) | `--office-surface` | `--sys-surface` | `--ctl-raised` |
| `--fb-text` (toast) | `--color-cream` | `--office-text` | `--sys-text` | `--ctl-text` |
| `--fb-muted` (toast) | `--color-text-muted-inverse` | `--office-muted` | `--sys-text-2` | `--ctl-text-2` |
| `--fb-edge` | `--color-hairline-inverse` | `rgb(73 46 33 / 0.08)` (derived, proposed) | `--sys-line` | `--ctl-track` |
| `--fb-shadow` | `--shadow-toast` (proposed below) | `--office-shadow-2` | `--sys-shadow-pop` | none (edge only) |
| `--fb-ok` / `--fb-info` | `--color-gold` / `--color-cream` | `--color-espresso` / `--color-espresso` | `--sys-ok` / `--sys-info` | `--ctl-ok` / `--ctl-accent` |
| `--fb-warn` / `--fb-danger` | `--color-gold` / `--color-danger-inverse` | `--office-gold-text` / `--office-danger` | `--sys-warn` / `--sys-danger` | `--ctl-warn` / `--ctl-danger` |
| `--fb-radius` (toast) | `--radius-md` 12px | `--office-radius` 14px | `--sys-radius-lg` 6px | `--ctl-radius-lg` 12px |
| modal surface / text / muted | `--color-cream-raised` / `--color-espresso` / `--color-text-muted` | `--office-surface` / `--office-text` / `--office-muted` | `--sys-surface` / `--sys-text` / `--sys-text-2` | `--ctl-raised` / `--ctl-text` / `--ctl-text-2` |
| `--fb-modal-radius` | `--radius-md` 12px | `--office-radius-lg` 20px | `--sys-radius-lg` 6px | `--ctl-radius-lg` 12px |
| `--fb-modal-shadow` | `--shadow-raised` | `--office-shadow-3` | `--sys-shadow-pop` | `0 0 0 1px var(--ctl-track)` |
| `--fb-overlay` | `--color-overlay-soft` (proposed) | `--office-overlay` | `--sys-overlay` | `--ctl-overlay` |
| `--fb-primary` / on | `--color-espresso` / `--color-cream` | same | `--sys-accent` / `--sys-surface` | `--ctl-accent` / `--ctl-bg` |
| `--fb-danger-fill` / on | `--color-danger` / `--color-cream` | `--office-danger` / `--color-cream` | `--sys-danger` / `--sys-surface` | `--ctl-danger` / `--ctl-bg` |
| `--fb-line` | `--color-control-line` | `--color-control-line` | `--sys-control` | `--ctl-control` |
| `--fb-btn-radius` | `--radius-sm` 6px | `--office-pill` | `--sys-radius` 4px | `--ctl-radius` 6px |
| `--fb-title-font` | `--font-display` | `--font-display` | `--font-body` (600) | `--ctl-display` |
| `--fb-focus` | `--color-focus-inverse` on toast, `--color-focus` in modal | `--color-espresso` | `--sys-accent` | `--ctl-accent` |
| `--fb-hover` | `--color-hairline-inverse` | `--office-sunken` | `--sys-subtle` | `--ctl-selected` |

System type sizes follow its density: toast `--sys-fs` 13px, modal title `--sys-fs-md` 600, body `--sys-fs`, padding `--sys-5` (24px), buttons `--sys-ctl` 28px with 44px hit area on touch. Everything else as above.

**Proposed additions to BRAND.md section 8** (clearly marked, need sign-off):
```css
--shadow-toast: 0 2px 4px rgb(73 46 33 / 0.12), 0 12px 32px -12px rgb(73 46 33 / 0.45); /* proposed (FEEDBACK): toasts only */
--color-overlay-soft: rgb(73 46 33 / 0.32);  /* proposed (FEEDBACK): modal backdrop, with 4px blur; same value as --office-overlay */
--toast-w: 22.5rem;                          /* proposed (FEEDBACK): toast width from 64em */
--modal-w: 26.25rem;                         /* proposed (FEEDBACK): the one modal */
```
Office: `--office-toast-edge: rgb(73 46 33 / 0.08)` (proposed, decoration only). Contrast: cream on espresso 10.95, danger-inverse on espresso 6.81, gold on espresso 6.17; all other pairs are existing documented host pairs.

## 5. Markup (Django messages and JS use the same)

`common/templates/common/_feedback.html`, included once per host base (replaces `_messages.html` + `_modal.html`, System `_confirm.html` confirm part, Control `_reset_dialog.html` and its `data-dialog`):
```html
<section class="toasts" aria-label="Notifications">
  <ol class="toasts-list" role="status" aria-live="polite" data-toasts-polite></ol>
  <ol class="toasts-list" role="alert" aria-live="assertive" data-toasts-assertive></ol>
</section>
<template data-server-messages>{% for m in messages %}<li data-kind="{{ m.level_tag|toast_kind }}" data-undo="...">{{ m }}</li>{% endfor %}</template>
<dialog class="fb-modal" aria-labelledby="fb-modal-title" aria-describedby="fb-modal-body">...</dialog>
```
One toast: `<li class="toast" data-kind="success"><svg class="toast-icon" aria-hidden="true">..</svg><p class="toast-text"><span class="visually-hidden">Done: </span>Saved.</p>[<button class="toast-action">Undo</button>]<button class="toast-close" aria-label="Dismiss">x</button></li>`. Level map: debug, info to info; success; warning; error. System `extra_tags` undo becomes the action.

## 6. Migrate (every place found)

Browser dialogs (must go first):
- `common/static/common/js/system.js:148` `window.confirm(spec.title)` fallback.
- `common/static/common/js/control/core.js:129` `window.confirm(...)` fallback.
- `common/static/common/js/control/app.js:161-162` reset dialog silently does nothing without `showModal`; `:216-219` its close handler. Replace with `confirmModal({title: 'Reset demo', ..., confirmLabel: 'Reset'})`.

Modal:
- `common/static/common/js/modal.js` (whole file) into `feedback.js`; `common/templates/common/_modal.html`.
- `system/templates/system/_confirm.html:3-15` and `system.js:142-166` (diff + LIVE guard via `details`/`guard`); keep the `sys-keys` dialog (`_confirm.html:17`) but give it the same shell.
- `control/templates/control/base.html:62` `data-dialog`; `control/_reset_dialog.html`; `core.js:123-155` `confirmDialog`/`formDialog`; call sites `library.js:300, 308, 341, 521, 548, 620`, `screens.js:466`, `music.js:491, 510, 541`.
- `data-confirm` triggers (keep working, check copy): `users/templates/users/account_you.html:58`, `office/templates/office/person.html:53`, `office/templates/office/_gold_actions.html:4`.
- CSS: `components.css:264-283` (`.modal`, phone sheet), `office.css:164-168`, `system.css:139-144, 187`, `control.css:776-782, 895-896`.

Toasts:
- `common/templates/common/_messages.html` (whole); includes in `common/templates/base.html:13,17`, `base_bare.html:11,15`, `users/templates/users/member_base.html:23-24`, `office/templates/office/base.html:63-64`, `pages/templates/pages/journey.html:9`, `pages/templates/pages/gold_apply.html:9`. (`400.html`, `403.html`, `_404_public.html` keep their empty `messages` block.)
- `system/templates/system/base.html:62` (`sys-stack` list) and `:68` (`sys-toasts`); `control/templates/control/base.html:45` (`ctl-messages`, inline) and `:59` (`ctl-toasts`).
- JS: `common/static/common/js/messages.js` (whole, into `feedback.js`); `member.js:20-28` (4s timer becomes shared), `member.js:64, 67`; `gold-apply.js:63-65, 341, 343`; `journey.js:108-111, 384`; `office-swap.js:70-73`; `system.js:232-262` (`systemToast`, keep Undo); `control/core.js:81-121` (`toast(text, onUndo, ms)`, keep Undo) and its callers (`lights.js:360`, `library.js` many).
- CSS: `components.css:249-262`, `member.css:48-52, 198, 234`, `office.css:156-163`, `office-signin.css:26`, `scenes.css:31`, `pages.css:193` (print: hide `.toasts`), `system.css:134-138, 185`, `control.css:135-136, 783-788, 826-827, 903-904`. `system.css:88-89` `.sys-note` stays for in-page notes only.

## 7. Check before done
375px and 1440px on each host: toast sits above bars and home indicator, never covers the primary button; three stacked fit; error stays; Undo works; "You're signed out." is one neat line. Modal centred at 375 with 16px gutters; Esc, backdrop, focus return; danger focuses Cancel; works with `showModal` removed (fallback); `grep -rn "window\.\(alert\|confirm\|prompt\)"` returns nothing.

## 8. Form problems modal (2026-10-25)

Moishe's rule, for every form with fields on every host: while typing, a problem shows only under the box, as before. On Save / Register / Submit / Sign in with anything wrong, the shared centred modal lists every problem (field label in bold, then a short message). Closing it (OK, Esc, backdrop) keeps everything filled in and focuses the first problem, then scrolls it to the middle (smooth; instant under reduced motion). Never a page jump alone, never a reset. Same look on every host (the one modal, themed by `--fb-*`); the list is `.fb-problems` in `feedback.css`.

One piece of code: `common/static/common/js/form-problems.js` (started by `app.js`, `office.js`, `control.js`, `system.js`, `system-bare.js`).
- `<form data-problems>`: opt in. A capture listener on the document runs before every other submit handler (so before System's "change this?" confirm), checks the form, and on any problem does `preventDefault` + `stopImmediatePropagation` and opens the dialog; on none it re-submits once. `data-problems="manual"`: the page calls the API itself (Register: its fetch path; Gold apply step 1). Not for GET search/filter forms or single-button action forms.
- Checked: live rules (`form.spaValidation.problems()`), the browser's constraint checks (`required`, `pattern`, `min`, ... the browser's own bubbles are switched off with `noValidate`), and required choices: `data-required-group` on a fieldset / radiogroup (optional `data-label`, `data-required-message`, a `[data-group-error]` line that is shown and hides when he picks). Labels: `data-label`, `<label>`, `<legend>` / `aria-label` of a radio group, a table row's `data-row-label` + `aria-label`.
- Server answers on a normal POST (page re-rendered, values kept by Django, password boxes emptied): on load the same dialog opens once, reading the errors from the DOM: `[data-problem]` (`data-problem-label`, `data-problem-message`, `data-problem-field`, else its text), the shared field lines `[data-error-for][data-state=error]`, System's `.sys-row.invalid .sys-error`. `data-problem-form="<form id>"` ties an element outside the form (System table-row errors) to its form. A problem with no field (wrong password) focuses the password; a named password field focuses that box.
- API: `collectProblems(form)`, `showProblems(scope, problems, { title, opener })` (resolves after close and focus), `focusFirst`, `serverProblems(form)`, `labelOf(control)`, `initFormProblems()`.
- Sign in with a wrong email or password lists one problem, "Email or password is wrong." (`users.forms.SignInForm`, also System), never which part.
- Fetch-based saves (Register, Gold apply) open the dialog from their own error path. System's "Save" bar over several rows checks every dirty row first and lists all problems; a failed single row (400, or 409 "the row changed") re-renders and the dialog lists it on load.
