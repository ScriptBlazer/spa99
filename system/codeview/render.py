"""Rows -> code text. Deterministic Python-literal text: 4-space indents, one key per line, `# read only` beside the keys that
cannot change, money as text, times "HH:MM", dates ISO, JSON fields as nested literals. The version is a sha256 over the
fingerprints (services.row_fingerprint) of every row shown, so any change in the database since opening is detected."""
import copy
import datetime
import decimal
import hashlib
import json
import uuid
from dataclasses import dataclass, field

from django.db import models
from django.utils import timezone

from .. import services
from . import adapters

INDENT = "    "
COMMENT_COLUMN = 34  # the "# read only" comments line up here
HEADER_1 = "# spa99 / rules / {filename}"
HEADER_2 = "# Generated from the database at {stamp} by System. Edit and Apply."


@dataclass
class Row:
    entity: adapters.Entity
    obj: object
    children: dict = field(default_factory=dict)  # key -> [Row]


def load_rows(entity, parent=None):
    """The rows of one entity as Row objects, children included (the database is read here and only here)."""
    return [Row(entity, obj, {key: load_rows(child, obj) for key, child in entity.children.items()}) for obj in entity.queryset(parent)]


def load(section):
    """[(Variable, [Row] or Row)] for the section."""
    out = []
    for variable in section.variables:
        rows = load_rows(variable.entity)
        out.append((variable, rows if variable.many else rows[0]))
    return out


# ---------- values ----------

def to_code(model_field, value):
    """One stored value as a plain literal for the code (text for money, times, dates and ids)."""
    if value is None:
        return None
    if isinstance(model_field, models.DateTimeField) and isinstance(value, datetime.datetime):
        value = timezone.localtime(value) if timezone.is_aware(value) else value
        return value.strftime("%Y-%m-%dT%H:%M:%S" if value.second else "%Y-%m-%dT%H:%M")
    if isinstance(value, datetime.time):
        return value.strftime("%H:%M:%S" if value.second else "%H:%M")
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, (decimal.Decimal, uuid.UUID)):
        return str(value)
    if isinstance(value, (list, dict)):
        return json.loads(json.dumps(value))
    return value


def row_values(row):
    """{key: literal} for the scalar keys of a row, in code order (id, read only keys, then the page's fields)."""
    entity, obj = row.entity, row.obj
    values = {"id": str(obj.pk)} if entity.has_id else {}
    for name in (*entity.fixed, *entity.editable):
        values[name] = to_code(obj._meta.get_field(name), getattr(obj, obj._meta.get_field(name).attname))
    return values


def version_fields(entity):
    return [*entity.fixed, *entity.editable]


def _fingerprints(path, rows, parts):
    for row in rows:
        parts.append([path, str(row.obj.pk), services.row_fingerprint(row.obj, version_fields(row.entity))])
        for key, kids in row.children.items():
            _fingerprints(f"{path}.{key}", kids, parts)


def version_of(loaded):
    parts = []
    for variable, rows in loaded:
        _fingerprints(variable.name, rows if variable.many else [rows], parts)
    return hashlib.sha256(json.dumps(parts, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ---------- text ----------

def _ind(level):
    return INDENT * level


def _scalar(value):
    if value is True or value is False or value is None:
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)  # a valid Python string literal
    return repr(value)


def fmt(value, level):
    """A literal as text; lines after the first are indented from `level`. Short lists of plain values stay on one line."""
    if isinstance(value, dict):
        if not value:
            return "{}"
        lines = [f"{_ind(level + 1)}{json.dumps(str(k), ensure_ascii=False)}: {fmt(v, level + 1)}," for k, v in value.items()]
        return "{\n" + "\n".join(lines) + f"\n{_ind(level)}}}"
    if isinstance(value, (list, tuple)):
        if not value:
            return "[]"
        if all(not isinstance(v, (dict, list, tuple)) for v in value):
            inline = "[" + ", ".join(_scalar(v) for v in value) + "]"
            if len(inline) <= 72:
                return inline
        lines = [f"{_ind(level + 1)}{fmt(v, level + 1)}," for v in value]
        return "[\n" + "\n".join(lines) + f"\n{_ind(level)}]"
    return _scalar(value)


def _commented(line, comment):
    """The line with `# comment` after it, at column 34 when there is room (else two spaces after the code)."""
    return (line.ljust(COMMENT_COLUMN - 1) if len(line) < COMMENT_COLUMN - 2 else line + "  ") + f"# {comment}"


def fmt_row(row, level):
    lines = ["{"]
    fixed = {"id", *row.entity.fixed}
    for key, value in row_values(row).items():
        line = f"{_ind(level + 1)}{json.dumps(key)}: {fmt(value, level + 1)},"
        lines.append(_commented(line, "read only") if key in fixed else line)
    for key, kids in row.children.items():
        lines.append(f"{_ind(level + 1)}{json.dumps(key)}: {fmt_rows(kids, level + 1)},")
    lines.append(f"{_ind(level)}}}")
    return "\n".join(lines)


def fmt_rows(rows, level):
    if not rows:
        return "[]"
    return "[\n" + "".join(f"{_ind(level + 1)}{fmt_row(r, level + 1)},\n" for r in rows) + f"{_ind(level)}]"


def header(section, now=None):
    stamp = timezone.localtime(now or timezone.now()).strftime("%Y-%m-%d %H:%M")
    return [HEADER_1.format(filename=section.filename), HEADER_2.format(stamp=stamp)]


def render_loaded(section, loaded, now=None):
    blocks = [f"{variable.name} = {fmt_rows(rows, 0) if variable.many else fmt_row(rows, 0)}\n" for variable, rows in loaded]
    return "\n".join(header(section, now)) + "\n" + "\n".join(blocks)


def render(section, now=None):
    """(code text, version hash) of the section as the database holds it now."""
    section = adapters.get(section) if isinstance(section, str) else section
    loaded = load(section)
    return render_loaded(section, loaded, now), version_of(loaded)


def swap_header(text, section, now):
    """`text` with its two header lines replaced by the current ones, so a diff shows only what was really edited."""
    lines = text.splitlines()
    fresh = header(section, now)
    for i, start in ((0, "# spa99 / rules /"), (1, "# Generated from the database at")):
        if len(lines) > i and lines[i].startswith(start):
            lines[i] = fresh[i]
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
