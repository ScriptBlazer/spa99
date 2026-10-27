# Email layout (2026-10-27)

Build brief for the shared email layout: `notifications/templates/notifications/emails/_base.html`, `_body.html`, `_body.txt`, the inline styles in `notifications/emailbody.py`, and the three Gold staff templates. Moishe: "the emails look ugly". Goal: every email looks like a quiet note from the spa, the same in Gmail, Outlook, Apple Mail and in dark mode.

Design read: transactional and service email for guests and staff. Calm, warm, one idea per email. An espresso band with the gold swan, a soft cream page, a light card with big Signika heading and comfortable Figtree body, one espresso button, a quiet footer.

Brand rules (`docs/BRAND.md`) win. No new hues. Derived tints are marked **derived (email)**.

---

## 1. Structure

Top to bottom, centred, one column, max width **600px**:

1. **Preheader**: hidden preview text (section 6).
2. **Header**: espresso band, the swan + "SPA 99" logo centred.
3. **Card** (light): heading, short gold rule, paragraphs, primary button, button fallback line, small notes. Gold staff emails add summary sections (section 9).
4. **Footer** (on the page colour, outside the card, centred): "Beyond Luxury", address, contact line, then the "why you get this" line slot, then the unsubscribe slot.

Header and card read as one surface: header has 12px top corners, card 12px bottom corners (`--radius-md`). Outlook desktop shows square corners; that is fine.

```
 page  #F5F2D8 ───────────────────────────────────────
 │  [ 32px ]                                          │
 │  ┌──────────── header #492E21 ───────────────┐     │
 │  │                 (swan logo 120 x 89)      │     │
 │  ├──────────── card #FBF9EC ─────────────────┤     │
 │  │  Heading (Signika 28/34)                  │     │
 │  │  ──  (32px caramel rule)                  │     │
 │  │  Paragraphs (Figtree 16/26)               │     │
 │  │  [ Primary button ]                       │     │
 │  │  If the button does not work... (13/20)   │     │
 │  └───────────────────────────────────────────┘     │
 │          Beyond Luxury                             │
 │          address · contact · why · unsubscribe     │
 └────────────────────────────────────────────────────┘
```

## 2. Tokens

### Light (default)

| Role | Hex | Source | Contrast |
|---|---|---|---|
| Page (canvas) | `#F5F2D8` | Spa Cream | |
| Header band | `#492E21` | Espresso | |
| Card | `#FBF9EC` | **derived (email)**: lighter cream for cards (BRAND 3 allows it). Replaces today's pure white | |
| Text, headings, links | `#492E21` | Espresso | 11.71 on card, 10.95 on page |
| Muted text (notes, footer, table labels) | `#7B675A` | **derived (email)**: espresso 72% over card, as a solid hex (opacity is unreliable in mail) | 5.05 on card, 4.73 on page (AA) |
| Hairline divider | `#E2DDD0` | **derived (email)**: espresso 14% over card. Decoration only | |
| Heading rule | `#BB8855` | Caramel. Decoration only, never text | |
| Button | `#492E21` fill, `#F5F2D8` text | Espresso / Cream | 10.95 |
| Panel (repeat notice, note) | `#F5F2D8` on the card | Spa Cream | espresso 10.95 |
| Logo | gold swan + cream "SPA 99" on espresso | PNG, section 4 | |

### Dark (only where `prefers-color-scheme` is honoured: Apple Mail macOS / iOS, Outlook for Mac, some others)

| Role | Hex | Source | Contrast |
|---|---|---|---|
| Page | `#2B1B13` | **derived (email)**: deep espresso | |
| Header band | `#492E21` | Espresso (unchanged, logo unchanged) | |
| Card | `#3A261C` | **derived (email)**: espresso, one step darker | |
| Text, headings | `#F5F2D8` | Cream | 12.6 on card |
| Links | `#E5AC6E` | Gold | 7.1 on card |
| Muted text | `#C1B9A3` | **derived (email)**: cream 72% over dark card | 7.28 on card, 8.46 on page |
| Hairline | `#58473A` | **derived (email)**: cream 16% over dark card | |
| Heading rule | `#BB8855` | Caramel (unchanged) | |
| Button | `#E5AC6E` fill, `#492E21` text | Gold / Espresso | 6.17 |
| Panel | `#492E21` on the dark card | Espresso | cream 10.95 |

No pure `#FFFFFF` or `#000000` anywhere: inverting clients handle off-colours more gently.

### Type

| Role | Stack | Size / line height | Weight | Tracking |
|---|---|---|---|---|
| Heading (h1) | `'Signika', 'Trebuchet MS', 'Segoe UI', Helvetica, Arial, sans-serif` | 28px / 34px (24px / 30px under 480px) | 500 | `-0.7px` (-0.025em) |
| Section heading (Gold summaries, h2) | Signika stack | 18px / 24px | 500 | `-0.45px` |
| Body | `'Figtree', 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Helvetica, Arial, sans-serif` | 16px / 26px | 400 | `-0.16px` |
| Button label | Figtree stack | 16px / 20px | 600 | `0` |
| Small note, button fallback | Figtree stack | 13px / 20px, muted | 400 | `0` |
| Footer | Figtree stack | 13px / 20px, muted | 400 | `0` |
| Footer brand line "Beyond Luxury" | Signika stack | 15px / 20px, text colour | 500 | `-0.2px` |

Web fonts: in `<head>`, `@font-face` for Signika (300 600) and Figtree (400 600) with **absolute** URLs `{{ site_url }}/static/common/fonts/signika-latin.woff2` and `.../figtree-latin.woff2` (the unhashed names; WhiteNoise serves them). Apple Mail and iOS Mail use them. Gmail and Outlook strip them and fall back down the stack: Trebuchet / Segoe UI keep the humanist feel, never Times. Outlook desktop gets an MSO block forcing Arial (it otherwise falls back to Times New Roman when the first font is unknown).

### Spacing

| Where | Desktop | Under 480px |
|---|---|---|
| Page padding above header / below footer | 32px / 48px | 16px / 32px |
| Header padding | 32px top and bottom | 28px |
| Card padding | 48px 48px 40px | 32px 24px 28px |
| Heading to rule | 16px | same |
| Rule (32px wide, 1px caramel) to first paragraph | 24px | same |
| Between paragraphs | 16px | same |
| Above button / below button | 8px / 16px (paragraph margin + button) | same |
| Button to fallback line | 16px | same |
| Footer padding | 32px 24px 0 | 24px 16px 0 |
| Footer: brand line to address | 12px | same |
| Footer: lines | 4px between blocks, notice and unsubscribe 16px above | same |

Paragraph measure is the card itself (504px of text at 600). No extra max-width.

## 3. Header and footer

**Header**: one cell, `align="center"`, `bgcolor="#492E21"`, plus the Gmail guard `background-image:linear-gradient(#492E21,#492E21)` (section 5). Logo links to `{{ site_url }}/`.

**Footer**, centred, in this order. Copy is exact:

```
Beyond Luxury
Spa 99, {{ address }}
Questions? Reply to this email or write to {{ contact_email }}.

{{ notice }}                         (only when set: the "why you get this" line, service and group mail)
Unsubscribe from these emails.       (only when unsubscribe_url: News and invites; "Unsubscribe" is the link)
```

Footer links: muted colour, underlined. The contact address is a `mailto:` link.

## 4. Logo asset

Made: `common/static/common/img/email/logo-on-dark-2x.png` (240 x 179 px, transparent background, rendered from `logo-on-dark.svg`: gold swan, cream "SPA 99"). SVG is not used in email (Gmail drops it).

```html
<img src="{{ logo_url }}" width="120" height="89" alt="Spa 99"
     style="display:block;width:120px;height:auto;border:0;outline:none;text-decoration:none;
            font-family:'Signika','Trebuchet MS',Helvetica,Arial,sans-serif;font-size:22px;line-height:89px;
            color:#E5AC6E;text-align:center;">
```

- Add `logo_url` to `notifications.services.base_context()`: `f"{settings.SITE_URL}/static/common/img/email/logo-on-dark-2x.png"`. Use the **unhashed** path, not `{% static %}`: hashed names change on every logo edit and would break images in emails already sent.
- The styled alt text matters: Outlook blocks images by default and Gmail cannot fetch `http://localhost:8000` in development. With the styles above the broken image shows "Spa 99" in gold Signika on espresso, centred in the same 89px band, so the email still looks deliberate.
- Transparent PNG on purpose: the header colour shows through, so a client that shifts the band colour does not reveal a box.

## 5. Dark mode

What each client does, and the answer:

| Client | Behaviour | What we do |
|---|---|---|
| Apple Mail (macOS, iOS) | Honours `color-scheme` and `@media (prefers-color-scheme: dark)`; without them it auto-inverts | Declare both schemes; ship the dark palette above. No auto-inversion happens |
| Outlook for Mac, Outlook iOS | Honour the media query (mostly) | Same dark palette |
| Gmail app iOS | Full inversion: light backgrounds go dark, dark backgrounds go light, text flips. Ignores our CSS | Light parts invert acceptably (card dark, espresso text cream). The espresso header and button are protected with `background-image: linear-gradient(#492E21,#492E21)` on their cells: Gmail does not touch background images, so the band stays espresso and the gold logo stays readable. Images are never inverted |
| Gmail app Android, Outlook.com, Outlook app Android | Partial inversion: only light backgrounds and dark text change | Fine as is: header and button already dark |
| Gmail web | No dark mode for message bodies | Light design |
| Outlook Windows desktop (dark) | Partial inversion, may lighten text | Accept; check in acceptance |

In `<head>`:

```html
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
<style>
  :root { color-scheme: light dark; supported-color-schemes: light dark; }
  @media (prefers-color-scheme: dark) {
    .e-canvas { background:#2B1B13 !important; }
    .e-card   { background:#3A261C !important; }
    .e-card, .e-card p, .e-card td, .e-card h1, .e-card h2 { color:#F5F2D8 !important; }
    .e-card a, .e-foot a.e-link { color:#E5AC6E !important; }
    .e-muted, .e-muted a, .e-foot, .e-foot p { color:#C1B9A3 !important; }
    .e-foot .e-brand { color:#F5F2D8 !important; }
    .e-hair   { border-color:#58473A !important; }
    .e-panel  { background:#492E21 !important; }
    .e-btn    { background:#E5AC6E !important; background-image:linear-gradient(#E5AC6E,#E5AC6E) !important; }
    .e-btn a  { color:#492E21 !important; }
  }
</style>
```

## 6. Preheader

First thing inside `<body>`:

```html
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;font-size:1px;line-height:1px;color:#F5F2D8;opacity:0;">
  {{ preheader }}&#847;&zwnj;&nbsp;&#847;&zwnj;&nbsp; (repeat the filler about 40 times)
</div>
```

The filler stops clients pulling body text into the preview after our sentence.

Source of `preheader`, in this order:
1. `preheader` in the context (Gold templates set it in a `{% block preheader %}`, section 9).
2. For `_body.html`: the first paragraph of `body_text` that is not a greeting (skip a paragraph that starts with "Hello", "Hi" or "Dear" and is under 40 characters), cut at 100 characters on a word boundary with "…". Compute it in Python next to `render` (e.g. `emailbody.preview_text(text)`), not in the template.

Example: verify gives "Please confirm your email address to finish setting up your Spa 99 account. The link works for 24…".

## 7. The shared layout (`_base.html`)

Tables for layout, `role="presentation"` on every layout table, all critical styles inline, the `<style>` block only for dark mode, mobile tweaks and resets. No JS, no forms, no background images that carry meaning (the gradients only repeat the solid colour). Every link absolute (`http(s)://` or `mailto:`).

```html
<!doctype html>
<html lang="en-GB" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="x-apple-disable-message-reformatting">
<meta name="format-detection" content="telephone=no, date=no, address=no, email=no">
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
<title>{% block title %}{{ site_name }}{% endblock %}</title>
<!--[if mso]><noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml></noscript>
<style>body,table,td,p,a,h1,h2{font-family:Arial,Helvetica,sans-serif !important;}</style><![endif]-->
<style>
  @font-face { font-family:'Signika'; src:url('{{ site_url }}/static/common/fonts/signika-latin.woff2') format('woff2'); font-weight:300 600; font-style:normal; }
  @font-face { font-family:'Figtree'; src:url('{{ site_url }}/static/common/fonts/figtree-latin.woff2') format('woff2'); font-weight:400 600; font-style:normal; }
  body { margin:0 !important; padding:0 !important; width:100% !important; -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%; }
  table { border-collapse:collapse; mso-table-lspace:0; mso-table-rspace:0; }
  img { -ms-interpolation-mode:bicubic; }
  a[x-apple-data-detectors] { color:inherit !important; text-decoration:none !important; }
  @media (max-width:480px) {
    .e-outer { padding:16px 12px 32px !important; }
    .e-head  { padding:28px 24px !important; }
    .e-body  { padding:32px 24px 28px !important; }
    .e-h1    { font-size:24px !important; line-height:30px !important; }
    .e-row td { display:block !important; width:100% !important; padding:0 !important; }
    .e-row td.e-label { padding-top:10px !important; }
  }
  /* dark mode block from section 5 */
</style>
</head>
<body class="e-canvas" style="margin:0;padding:0;background:#F5F2D8;">
  {% block preheader_html %}{# section 6 #}{% endblock %}
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" class="e-canvas" bgcolor="#F5F2D8" style="background:#F5F2D8;">
    <tr><td align="center" class="e-outer" style="padding:32px 16px 48px;">
      <!--[if mso]><table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0"><tr><td><![endif]-->
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;margin:0 auto;">
        <tr><td align="center" class="e-head" bgcolor="#492E21"
                style="background:#492E21;background-image:linear-gradient(#492E21,#492E21);padding:32px;border-radius:12px 12px 0 0;">
          <a href="{{ site_url }}/" style="text-decoration:none;">{# logo img, section 4 #}</a>
        </td></tr>
        <tr><td class="e-card e-body" bgcolor="#FBF9EC"
                style="background:#FBF9EC;padding:48px 48px 40px;border-radius:0 0 12px 12px;color:#492E21;
                       font-family:'Figtree','Segoe UI',-apple-system,BlinkMacSystemFont,'Helvetica Neue',Helvetica,Arial,sans-serif;
                       font-size:16px;line-height:26px;letter-spacing:-0.16px;">
          {% block heading %}{% endblock %}
          {% block content %}{% endblock %}
        </td></tr>
        <tr><td align="center" class="e-foot" style="padding:32px 24px 0;font-family:(Figtree stack);font-size:13px;line-height:20px;color:#7B675A;">
          <p class="e-brand" style="margin:0 0 12px;font-family:(Signika stack);font-size:15px;line-height:20px;font-weight:500;letter-spacing:-0.2px;color:#492E21;">Beyond Luxury</p>
          <p style="margin:0 0 4px;">{{ site_name }}, {{ address }}</p>
          <p style="margin:0;">Questions? Reply to this email or write to <a class="e-link" href="mailto:{{ contact_email }}" style="color:#7B675A;text-decoration:underline;">{{ contact_email }}</a>.</p>
          {% block footer_extra %}{% endblock %}
        </td></tr>
      </table>
      <!--[if mso]></td></tr></table><![endif]-->
    </td></tr>
  </table>
</body>
</html>
```

`tagline` stays in the context but is no longer printed in the header (the logo is the header; "Beyond Luxury" lives in the footer).

### Heading block (shared snippet, used by `_body.html` and the Gold templates)

```html
<h1 class="e-h1" style="margin:0 0 16px;font-family:'Signika','Trebuchet MS','Segoe UI',Helvetica,Arial,sans-serif;font-size:28px;line-height:34px;font-weight:500;letter-spacing:-0.7px;color:#492E21;">{{ heading }}</h1>
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 24px;"><tr>
  <td width="32" height="1" bgcolor="#BB8855" style="width:32px;height:1px;font-size:0;line-height:0;background:#BB8855;">&nbsp;</td>
</tr></table>
```

`heading` for `_body.html` = the subject without a "[Test] " prefix (pass it from `render_email` as `heading`). A News mailing therefore shows its subject as the heading. This is intentional: the email reads like a titled note.

## 8. The body (`_body.html` and `emailbody.py`)

`_body.html` keeps its role: heading block, then `{{ body_html }}`; `footer_extra` renders the notice and unsubscribe lines (section 3) as `<p class="e-muted" style="margin:16px 0 0;">`.

Change these in `notifications/emailbody.py` (they are the inline styles every editable email gets):

- **`P_STYLE`** → `margin:0 0 16px;font-size:16px;line-height:26px;color:#492E21;` (colour inline because Outlook.com ignores inheritance through tables).
- **Inline links** (`_html_value` for `*_url`, the WhatsApp `Rich` line) → `color:#492E21;text-decoration:underline;word-break:break-word;`. Long URLs must wrap on 375px.
- **`_button_html`** → the bulletproof button below, wrapped in a 8px top / 0 bottom spacer. No VML: the cell carries the colour and padding in Outlook, the link carries it everywhere else.

```html
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:8px 0 16px;">
  <tr><td class="e-btn" bgcolor="#492E21" align="center"
          style="background:#492E21;background-image:linear-gradient(#492E21,#492E21);border-radius:6px;mso-padding-alt:15px 32px;">
    <a href="{url}" target="_blank"
       style="display:inline-block;padding:15px 32px;font-family:'Figtree','Segoe UI',-apple-system,BlinkMacSystemFont,'Helvetica Neue',Helvetica,Arial,sans-serif;
              font-size:16px;line-height:20px;font-weight:600;color:#F5F2D8;text-decoration:none;border-radius:6px;">{label}</a>
  </td></tr>
</table>
```

  Radius 6px = `--radius-sm`, the site's control radius. Labels are already short ("Confirm my email", "Choose a new password"): they never wrap at 375.
- **Fallback line** (when `button_fallback`):

```html
<p class="e-muted" style="margin:0 0 16px;font-size:13px;line-height:20px;color:#7B675A;">
  If the button does not work, paste this link into your browser:<br>
  <a href="{url}" style="color:#7B675A;text-decoration:underline;word-break:break-all;">{url}</a></p>
```

- **Plain-text button**: `pieces_text.append(f"{label}:\n{button_url}")` instead of the bare URL, so the text version says what the link does.
- `render_plain` uses the same `P_STYLE`, nothing else changes.

The "small notes" style (13/20 muted) is the `e-muted` paragraph above; templates use it for any secondary line.

## 9. Gold staff emails (approver, final, sent back)

Same `_base.html`, same heading block, same button. They set their own `heading` and `preheader` blocks:

| Template | Heading | Preheader |
|---|---|---|
| `gold_approver` | `Gold Card application: {{ name }}` | `{{ potential_label }} potential. Review it in the Office.` |
| `gold_final` | `Final approval: {{ name }}` | `Approved by an approver, potential Low. Your final approval is needed.` |
| `gold_sent_back` | `{{ name }}: sent back for review` | `The final approver asks whether you are sure. The applicant has not been told.` |

(`gold_sent_back`'s current question "was approved, but the potential is Low. Are you sure?" moves into the first paragraph.)

Layout inside the card, in order:

1. **Repeat notice** (approver, when `is_repeat`) and **Note from the final approver** (sent back): a panel, `class="e-panel"`, `bgcolor="#F5F2D8"`, `padding:14px 16px;border-radius:6px;margin:0 0 24px;`, 15px / 24px text. Label in 600 weight, no `<strong>` colour change.
2. **Potential line**: `e-muted` 13/20 paragraph directly under the rule: `{{ potential_label }} potential`.
3. **Intro paragraph(s)**: body style.
4. **One primary button**: "Review application" (approver, sent back) or "Confirm approval" (final).
5. **Secondary actions as text links**, one line under the button, 15px, underlined, espresso, 20px apart (`padding-right:20px` on inline `<a>`; they wrap naturally on a phone): approver and sent back `Decline`, `Respond`, `View application`; final `Send back`, `View application`. Replaces today's three side-by-side buttons, which overflow at 375px.
6. **Small note** (`e-muted` 13/20): the existing "opens in the Office, you may need to sign in" sentence.
7. **Summary sections**, for each section:
   - Divider: `border-top:1px solid #E2DDD0` (`class="e-hair"`) on a full-width cell, 32px above, 16px below.
   - Section heading h2: Signika 18/24, 500, `margin:0 0 12px`. Keep the number: `1. Contact`.
   - Rows: a 2-column table, `class="e-row"` on each `<tr>`. Label cell `class="e-label e-muted"`, 40% wide, 14px / 22px muted, `padding:6px 16px 6px 0;vertical-align:top`. Value cell 15px / 22px text colour, `padding:6px 0;vertical-align:top;word-break:break-word`. No row lines. Under 480px the two cells stack (label above value) via the media query in section 7.
   - Remove `opacity:0.8` on labels (unreliable, and it is now the solid muted colour).

Plain-text versions of these three keep their current structure, with the section 10 header and footer.

## 10. Plain text (`_body.txt` and the Gold `.txt`)

Unwrapped paragraphs (no hard line breaks: clients reflow), one blank line between blocks, link labels on their own line followed by the URL. Exact shape:

```
SPA 99

Hello James,

Please confirm your email address to finish setting up your Spa 99 account. The link works for 24 hours.

Confirm my email:
https://spa99.uk/...

If you did not ask for this, you can ignore this email.

-- 
Spa 99, BML House, 99c Vale Road, London N4 1PR
Questions? Reply to this email or write to hello@spa99.uk.
Beyond Luxury

You are receiving this because you opted in to news from Spa 99.
Unsubscribe from these emails: https://spa99.uk/unsubscribe/...
```

`-- ` is the standard signature separator (two hyphens and a space). The notice and unsubscribe lines appear only when set. Gold `.txt` files start with `SPA 99` and a blank line and end with the same footer.

## 11. Copy tone

- Short, calm, a host writing to a guest. One idea per email. No exclamation marks, no hype words, no "Dear valued customer".
- Headings are the subject: plain and specific ("Confirm your email for Spa 99", not "Almost there").
- Buttons say what happens, two to four words, sentence case: "Confirm my email", "Set up your account".
- Staff emails are plainer still: facts first, then the action.
- Fixed strings changed by this brief: the fallback line ("If the button does not work, paste this link into your browser:"), the `gold_sent_back` heading, the footer adds "Beyond Luxury". Editable bodies in System are not touched.

## 12. Weight

Keep a rendered email well under Gmail's 102 KB clip limit: target **under 40 KB** for a service email and **under 80 KB** for a full Gold approver email. The `<style>` block stays under 3 KB; no repeated inline font stacks beyond what is listed; no comments in the output (Django `{# #}` only).

## 13. Acceptance checks (reviewer)

Send a test of `verify`, `welcome`, `gold_invite`, a News mailing (with unsubscribe), `gold_approver` (repeat, with long answers) and `gold_sent_back` (with a note) from a staging host with a public `SITE_URL`.

1. **Gmail web** (Chrome): logo loads, fonts fall back to Trebuchet / Segoe / Helvetica (never Times), card and header corners round, button espresso with cream text, no "[Message clipped]".
2. **Gmail iOS app, light and dark**: in dark, header band stays espresso with the gold swan readable; button stays espresso with cream text; body text readable.
3. **Gmail Android, dark**: same.
4. **Apple Mail macOS and iOS, light and dark**: Signika heading and Figtree body render; dark mode shows the dark palette from section 2 (deep espresso page, gold links, gold button with espresso text), not an automatic inversion.
5. **Outlook web (Outlook.com), light and dark**; **Outlook Windows desktop**: 600px column, button visible with padding (square corners fine), Arial body, nothing in Times.
6. **375px** (iPhone view in any client): no horizontal scroll, card padding 24px, heading 24px, long URLs wrap, Gold summary rows stack label over value, secondary links wrap cleanly.
7. **Images off** (Outlook default, and the localhost case): the header still reads "Spa 99" in gold on espresso, same height.
8. Every `href` is absolute (`https://` or `mailto:`); the logo `src` is absolute and unhashed.
9. The logo `<img>` has `alt="Spa 99"`, width and height set.
10. Preview text in the inbox list is the preheader, not "Hello James," and not footer text.
11. Plain-text part matches section 10.
12. HTML size of the largest Gold approver email under 80 KB (`len(html.encode())` in a test).
13. No exclamation marks in any fixed string; contrast pairs as listed in section 2.
14. The System Emails preview (desktop 640 and phone 375 frames) shows the new layout.
