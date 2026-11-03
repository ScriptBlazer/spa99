"""Click-a-header sorting for the Office lists (docs/features/office-outreach.md R1). One place for the rules, so every list does the
same thing: a whitelist of keys per list (an unknown `sort` falls back to the list default), `dir=asc|desc`, empty values last in
both directions (F().asc(nulls_last=True) works on SQLite and Postgres alike: no collations, no Postgres-only syntax), and a stable
tie-break so paging never repeats or skips a row.

A list declares its columns once:

    COLUMNS = [Column("name", "Name", Lower("sort_name")), Column("registered", "Registered", "interest__created_at", first="desc"),
               Column("summary", "Wants")]            # no sort expression = a column that cannot be sorted

and calls `resolve(COLUMNS, request.GET, default_key, default_dir)` for the order and `header_columns(...)` for the template.

The `columns` context list (one dict per column, in declared order, hidden ones left out):
    key        the column key (also the `sort` value)
    label      the header text
    css        extra classes for the th (e.g. "num o-wide-xl"), '' for none
    sortable   False for columns built from several values (summary, answers, badges): draw a plain header
    active     True for the column the list is sorted by now (the default counts: the arrow shows before any click)
    dir        "asc" or "desc" when active, else ""
    aria_sort  "ascending", "descending" or "none" for the th's aria-sort
    url        the link a click follows: same page and filters, this column, the direction a click should give (reverses the
               active one; a new column starts at its natural direction), page reset to the first
"""
from dataclasses import dataclass
from urllib.parse import urlencode

from django.db.models import F

ASC, DESC = "asc", "desc"


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    sort: object = None      # a field name / expression, or a tuple of them (ordered as written); None = not sortable
    first: str = ASC         # the direction a first click gives (text ascending, dates and numbers descending)
    hidden: bool = False     # a valid `sort` key with no header of its own (the list may still be sorted by it)
    css: str = ""            # classes the th already carried (num, o-wide-xl ...), passed through to the template

    @property
    def sortable(self):
        return self.sort is not None


def _expression(value):
    return F(value) if isinstance(value, str) else value


def _direction(value, fallback):
    return value if value in (ASC, DESC) else fallback


def resolve(columns, get, default_key, default_dir=DESC):
    """(key, dir, explicit): what the list is sorted by. `get` is request.GET. Unknown or unsortable keys, and a missing key, give the
    default; a bad `dir` gives the column's natural direction. `explicit` is True when the request asked for a valid sort."""
    wanted = get.get("sort", "") if hasattr(get, "get") else ""
    by_key = {c.key: c for c in columns if c.sortable}
    if wanted in by_key:
        return wanted, _direction(get.get("dir", ""), by_key[wanted].first), True
    return default_key, _direction(get.get("dir", "") if not wanted else "", default_dir), False


def order_by(columns, key, direction, tiebreak=("pk",)):
    """The order_by() expressions for a resolved sort: the column's expressions in `direction`, empty values last, then `tiebreak`
    (field names, '-' prefix for descending) so the order is total and stable."""
    column = next(c for c in columns if c.key == key and c.sortable)
    parts = column.sort if isinstance(column.sort, (tuple, list)) else (column.sort,)
    ordering = []
    for part in parts:
        expression = _expression(part)
        ordering.append(expression.desc(nulls_last=True) if direction == DESC else expression.asc(nulls_last=True))
    return [*ordering, *tiebreak]


def header_columns(columns, key, direction, path, params):
    """The `columns` context for the template (see the module docstring). `params` is request.GET (a QueryDict) or a plain dict of
    the filters to keep; `sort`, `dir` and `page` are replaced."""
    pairs = params.lists() if hasattr(params, "lists") else ((k, [v]) for k, v in params.items())
    kept = [(k, v) for k, values in pairs if k not in ("sort", "dir", "page") for v in values if v != ""]
    out = []
    for column in columns:
        if column.hidden:
            continue
        active = column.sortable and column.key == key
        if not column.sortable:
            out.append({"key": column.key, "label": column.label, "css": column.css, "sortable": False, "active": False, "dir": "", "aria_sort": "none", "url": ""})
            continue
        click = (ASC if direction == DESC else DESC) if active else column.first
        out.append({"key": column.key, "label": column.label, "css": column.css, "sortable": True, "active": active, "dir": direction if active else "",
                    "aria_sort": ("ascending" if direction == ASC else "descending") if active else "none",
                    "url": f"{path}?{urlencode([*kept, ('sort', column.key), ('dir', click)])}"})
    return out


def ordering_from(columns, filters, default_key, tiebreak=("pk",), default_dir=DESC):
    """order_by() expressions from a list's `filters` dict (its `sort` and `dir`), the default when they are missing or not on the
    whitelist. Used by the querysets, so a hand-made filters dict (a test, the CSV export) can never inject a field name."""
    by_key = {c.key: c for c in columns if c.sortable}
    key = filters.get("sort")
    if key not in by_key:
        return order_by(columns, default_key, default_dir, tiebreak)
    return order_by(columns, key, _direction(filters.get("dir", ""), by_key[key].first), tiebreak)
