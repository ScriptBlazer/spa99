# Feature: System code view (hidden "rules as code")

Decided by Moishe 2026-10-25 (PROJECT.md). Branch `feature/system-code-view`. System look stays as it is (docs/design/SYSTEM.md).

## What it is

A quiet `</>` icon in the page header of each rule page in System. Click: the page's rules appear as code, generated from the database, read only, syntax highlighted, with line numbers. **Edit** turns it into an editor. **Review** shows what will change. **Apply** saves. It is a different way to edit the same rows the page already edits, nothing more.

Never real program files. Nothing is executed.

## Pages

| Page | Code covers | Can add rows | Can remove rows |
|---|---|---|---|
| Plans | every plan (all editable page fields) | yes | no (hide with `visible: False`) |
| Hours | capacity and slots, opening rules, closures | rules, closures | closures only |
| Gold rules | every rule | yes | no (`active: False`) |
| Journey | questions, their options, suggestion rules | options | no (`active: False`) |
| Settings | the page's fields (opening date and text, stage switches, wording, VAT, discount link, security limits) | n/a | n/a |
| Emails | the three recipient fields | n/a | n/a |

Not covered: Team, Email suppressions, Change log, Dashboard (people and security stay on their own screens).

## The code

Python-style literals with a header comment, e.g.

```python
# spa99 / rules / plans.py
# Generated from the database at 2026-10-25 20:14 by System. Edit and Apply.
PLANS = [
    {
        "id": 3,                 # read only
        "slug": "tier-1",        # read only
        "name": "Tier 1",
        "price_ex_vat": "299.00",
        "visits_per_month": 8,
        "visible": True,
    },
]
```

- Money and decimals as strings ("299.00"), times "07:00", dates "2027-01-15", booleans True/False, None, lists, dicts. Same field names as the model.
- Parsed with `ast.literal_eval` only (no eval, no imports, no calls). Input capped at 128 KB and nesting depth; parse errors come back with the line and column.
- `id` (and slugs where they are keys) are read only: changing one is an error. A dict without `id` is a new row (only where adding is allowed). A missing row is a removal (only closures); elsewhere it is an error.

## Saving

- Preview (`POST .../code/preview/`): parse, match rows, run every row through the page's own form validation, return the field changes (old → new) and any errors. Nothing saved.
- Apply (`POST .../code/apply/`): the same, then saves everything in one transaction through the normal logged path (`save_logged`), so each field is a normal change-log entry sharing one batch id: "Saved together (N)" with **Undo all**. Any error saves nothing.
- Stale check: the client sends the hash of the code it opened; if the rows changed since, 409 "Changed since you opened it" and the fresh code.
- Risky fields still go through the confirm modal (old → new) before Apply.
- One extra audit event `code_edit` (section, before/after sha256, the unified diff of the code text, capped) so the log shows exactly what was typed, line by line, next to the field changes.
- Same access as the page: Developer level, behind the unlock, CSRF.

## Built (2026-10-25)

Backend only (the frontend adds the `</>` icon, editor and review). Package `system/codeview/`: `adapters.py` (one `Section` per page, built from the page's own forms: edit fields = `Form.Meta.fields`, read only keys = what the add form asks for beyond that, plus `id`), `render.py`, `parse.py`, `plan.py`, `service.py`. Views `system/views_code.py`. Migration `system.0008` (choices only). Tests `system/tests/test_codeview.py`.

**Variables.** `PLANS = [..]`; `HOURS = {"capacity", "slot_length_minutes", "slot_step_minutes", "booking_notice_minutes", "rules": [..], "closures": [..]}`; `GOLD_RULES = [..]`; `JOURNEY = [question + "options": [..]]` and `SUGGESTIONS = [..]`; `SETTINGS = {..}`; `EMAILS = {..}`. Ids are UUID text. Read only per row: `id` plus plans `slug`, `kind`; rules `key`, `kind`; Gold `group`, `match_value`; questions `key`, `type`; options `value`. New row = no `id` (plans, opening rules, closures, Gold rules, options); the read only keys are then required, other keys left out get the model default. Removal = a missing row, closures only. Every key of an existing row must be present (an omitted switch would otherwise read as off). Values must be the right kind (`"no"` for a switch is an error, not on).

**Endpoints** (System host, `unlocked`, Developer level, CSRF header, 60 per person per minute, JSON). `<section>` is plans, hours, gold, journey, settings or emails (else 404). Page views now put `code_url` (= `/code/<section>/`) in the template context (`system.views.page`).

| Call | Answer |
|---|---|
| `GET /code/<section>/` (`system_code`) | `{code, version, section, title}` |
| `POST /code/<section>/preview/` `{code, version}` (`system_code_preview`) | 200 `{ok, section, count, risky, changes: [{row_label, field, label, old_display, new_display, risky, line}], creates: [{row_label, noun, line, fields: [{field, label, display}]}], deletes: [{row_label, noun, line, risky: true}], diff, diff_lines: [{type: add/del/ctx/hunk, text, old, new}]}` |
| `POST /code/<section>/apply/` `{code, version, confirm_risky}` (`system_code_apply`) | 200 `{ok, message: "Saved N changes.", changed, undo_url, code, version}`; nothing to change: 200 `{ok, message: "Nothing to change.", changed: 0, code, version}`, no event |

Errors: 400 `{ok: false, message, errors: [{line, col, message}]}` (syntax, not a plain literal, unknown key with "Did you mean", read only changed, unknown or duplicate id, missing row or key, wrong kind of value, and every page-form field error, each on the line of its key; `col` is 1-based); 413 same shape (over 128 KB); 409 `{ok: false, message: "Changed since you opened it. Reload to see the latest.", code, version}` (fresh); 400 `{ok: false, needs_confirm: true, message, risky: true, changes, creates, deletes}` when apply has risky changes (or a removal) without `confirm_risky: true`; 429 `{ok: false, message}` with `Retry-After`; 500 `{ok: false, message}` when the audit event could not be written (nothing saved).

**Version.** sha256 over `row_fingerprint` of every row shown (read only and editable fields, with the row ids and their place), so any change, addition or removal since opening gives 409. Each row's form also carries the page's `row_token`, checked again under a row lock in `save_form`.

**Apply** is one transaction: stale check, every form saved with `services.save_form` (each field a normal change-log entry, all sharing the request's batch id: "Saved together (N)", `undo_url` is Undo all, or the single undo), closure removals with `services.delete_logged` (not undoable), then one `code_edit` event. If the event cannot be written the whole save rolls back. Detail: `{section, title, before_sha256, after_sha256, diff, diff_truncated, changed_fields, changes, added, removed}`; `diff` is the unified diff of rendered-before vs rendered-after (header timestamp excluded, capped at 20 KB with a `... diff truncated (20 KB limit)` line). Sentence: "<email> edited Plans as code (N changes)". Section = the page's section; category `change` (so the Changes chip shows it); icon `code`.

**Audit feed.** Event groups carry `icon: "code"` and `changed_fields`; the drawer (`feed.entry_detail`) adds `diff_lines` (same row shape as the preview), `diff_truncated`, `changed_fields`.

**Limits.** 128 KB text; nesting 12 levels; 20 errors returned; literals only (text, whole and decimal numbers, True, False, None, lists, dicts, tuples, a minus sign); duplicate keys refused. Rows are validated against the database as it is now, one row at a time, so a cross-row rule that is only true after two rows change together (Gold High and Medium thresholds moved in one edit) can be refused; change them in two steps.
