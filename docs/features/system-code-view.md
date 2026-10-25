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
