"""Parsed code -> what would change. Rows are matched by id; every row goes through the page's own form (the same instance,
the same validation, the same changed-field logic), so the code view cannot accept what the page would refuse. Nothing is
saved here: the result holds the validated forms for `apply`, the review lists, and the errors with their line and column."""
import json
from dataclasses import dataclass, field

from django import forms

from .. import changes as change_log
from .. import sentences
from ..forms import TOKEN
from ..templatetags.system_ui import human
from . import adapters, render
from .parse import CodeError, LDict, LList, error, nearest


@dataclass
class Plan:
    section: adapters.Section
    errors: list = field(default_factory=list)
    changes: list = field(default_factory=list)   # [{row_label, field, label, old_display, new_display, risky, line}]
    creates: list = field(default_factory=list)   # [{row_label, noun, fields: [{field, label, display}], line}]
    deletes: list = field(default_factory=list)   # [{row_label, noun, line, risky}]
    forms: list = field(default_factory=list)     # [(valid form, (line, col) of its row)] in code order (saved by apply)
    removals: list = field(default_factory=list)  # model rows to delete
    stale: bool = False                           # a row changed while this was being checked

    @property
    def empty(self):
        return not (self.changes or self.creates or self.deletes)

    @property
    def risky(self):
        return any(c["risky"] for c in self.changes) or bool(self.deletes)

    @property
    def total(self):
        return len(self.changes) + len(self.creates) + len(self.deletes)

    def raise_if_errors(self):
        if self.errors:
            raise CodeError(sorted(self.errors, key=lambda e: (e["line"], e["col"])))


def to_input(form_field, value):
    """A value from the code as the page's form expects it in POST data (text, with True/False for switches and JSON as text).
    Raises ValueError with the message to show when the value is the wrong kind."""
    if isinstance(form_field, forms.BooleanField):
        if isinstance(value, bool):
            return value
        raise ValueError("Use True or False.")
    if isinstance(form_field, forms.JSONField):
        try:
            return json.dumps(value, allow_nan=False)
        except (TypeError, ValueError):
            raise ValueError("Use a list or dict of plain values here.") from None
    if value is None:
        return ""
    if isinstance(form_field, forms.IntegerField):  # Decimal and float fields too
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise ValueError('Use a number, like 8 or "299.00".')
        return repr(value) if isinstance(value, float) else str(value)
    if not isinstance(value, str):
        raise ValueError('Use text in quotes, like "abc".')
    return value


class Planner:
    def __init__(self, section, parsed):
        self.section, self.parsed, self.plan = section, parsed, Plan(section)

    def err(self, at, message):
        self.plan.errors.append(error(at[0], at[1], message))

    def run(self):
        for variable in self.section.variables:
            value, at = self.parsed[variable.name], self.parsed.name_at[variable.name]
            if variable.many:
                self.rows(variable.entity, value, at, None)
            elif isinstance(value, LDict):
                self.row(variable.entity, value, {}, set(), None, set())
            else:
                self.err(at, f"{variable.name} must be a {{ ... }} dict.")
        return self.plan

    # ----- a list of rows -----

    def rows(self, entity, value, at, parent):
        if not isinstance(value, LList):
            return self.err(getattr(value, "at", at), "This must be a list [ ... ].")
        existing = {str(obj.pk): obj for obj in entity.queryset(parent)}
        seen, new_keys, unmatched = set(), set(), False
        for index, item in enumerate(value):
            if isinstance(item, LDict):
                unmatched = self.row(entity, item, existing, seen, parent, new_keys) is False or unmatched
            else:
                self.err(value.item_at[index], "Each row must be a { ... } dict.")
                unmatched = True
        for pk, obj in existing.items():
            if pk in seen or unmatched:  # a row that could not be matched explains the gap: no second error for it
                continue
            label = entity.label(obj)
            if entity.removable:
                self.plan.removals.append(obj)
                self.plan.deletes.append({"row_label": label, "noun": entity.noun, "line": value.at[0], "risky": True})
            else:
                self.err(value.at, f'The {entity.noun} "{label}" is missing. It cannot be removed here{entity.hint}.')

    # ----- one row -----

    def row(self, entity, item, existing, seen, parent, new_keys):
        """Check one row. Returns False when it could not be matched to a database row (a bad id or no right to add)."""
        bad = False
        for key in item:
            if key not in entity.row_keys:
                hint = nearest(key, entity.row_keys)
                self.err(item.key_at[key], f'Unknown key "{key}".' + (f' Did you mean "{hint}"?' if hint else ""))
                bad = True
        obj = None
        if not entity.has_id:
            obj = entity.queryset(parent)[0]
        elif "id" in item:
            row_id = item["id"]
            if not isinstance(row_id, str):
                self.err(item.key_at["id"], 'The id must be the text shown in the code, like "3f2a...".')
                bad = True
            elif row_id in seen:
                self.err(item.key_at["id"], f'The id "{row_id}" is used twice.')
                bad = True
            elif row_id not in existing:
                self.err(item.key_at["id"], f'No {entity.noun} has the id "{row_id}". To add one, leave the id out.' if entity.add_form
                         else f'No {entity.noun} has the id "{row_id}". Rows cannot be added here.')
                bad = True
            else:
                obj = existing[row_id]
                seen.add(row_id)
        elif not entity.add_form:
            self.err(item.at, f"New {entity.noun}s cannot be added here. Every row needs its id.")
            return False
        if bad:
            return False if "id" in item else None
        if obj is None:
            return self.new_row(entity, item, parent, new_keys)
        bad = self.check_fixed(entity, item, obj)
        for name in entity.editable:
            if name not in item:
                self.err(item.at, f'Missing key "{name}". Every row needs all its keys.')
                bad = True
        for key, child in entity.children.items():
            if key not in item:
                self.err(item.at, f'Missing key "{key}". Every row needs all its keys.')
                bad = True
            else:
                self.rows(child, item[key], item.key_at[key], obj)
        if not bad:
            self.validate(entity, item, obj, new=False)

    def check_fixed(self, entity, item, obj):
        bad = False
        for name in entity.fixed:
            current = render.to_code(obj._meta.get_field(name), getattr(obj, obj._meta.get_field(name).attname))
            if name not in item:
                self.err(item.at, f'Missing key "{name}" (read only).')
                bad = True
            elif item[name] != current or type(item[name]) is not type(current):
                self.err(item.key_at[name], f'"{name}" is read only. It is {json.dumps(current)}.')
                bad = True
        return bad

    def new_row(self, entity, item, parent, new_keys):
        for key in entity.children:
            if key in item:
                self.err(item.key_at[key], f'A new {entity.noun} cannot have "{key}" yet. Add it after saving.')
                return
        if entity.fixed:
            key = tuple(json.dumps(item.get(name)) for name in entity.fixed)
            if key in new_keys:
                self.err(item.at, f"Two new rows have the same {' and '.join(entity.fixed)}.")
                return
            new_keys.add(key)
        self.validate(entity, item, entity.model(**entity.new_kwargs(parent)), new=True)

    # ----- the page's form -----

    def validate(self, entity, item, obj, new):
        form_class = entity.add_form if new else entity.form
        names = [*entity.fixed, *entity.editable] if new else entity.editable
        data, bad = {}, False
        for name in names:
            model_field = obj._meta.get_field(name)
            if name in item:
                value = item[name]
            elif new:  # a new row may leave out a key: it gets the model's default
                value = render.to_code(model_field, getattr(obj, model_field.attname))
            else:
                continue
            try:
                data[name] = to_input(form_class.base_fields[name], value)
            except ValueError as exc:
                self.err(item.key_at.get(name, item.at), str(exc))
                bad = True
        if bad:
            return
        old = {name: change_log.to_json(getattr(obj, obj._meta.get_field(name).attname)) for name in entity.editable}
        if not new:
            base = form_class(instance=obj)
            data[TOKEN] = base.initial[TOKEN]
            for name, form_field in base.fields.items():  # JSON fields with a callable default carry their old value in a hidden input
                if form_field.show_hidden_initial:
                    data[base.add_initial_prefix(name)] = form_field.prepare_value(base.initial.get(name))
        form = form_class(data, instance=obj)
        if not form.is_valid():
            if form.stale:
                self.plan.stale = True
            for name, messages in form.errors.items():
                if name == TOKEN or (form.stale and name == "__all__"):
                    continue
                at = item.at if name == "__all__" else item.key_at.get(name, item.at)
                for message in messages:
                    self.err(at, message)
            return
        self.plan.forms.append((form, item.at))
        label = entity.label(form.instance) if new else entity.label(obj)
        if new:
            fields = [{"field": n, "label": human(n), "display": sentences.show(obj._meta.get_field(n), change_log.to_json(form.cleaned_data.get(n)))} for n in names]
            self.plan.creates.append({"row_label": label, "noun": entity.noun, "fields": fields, "line": item.at[0]})
            return
        for name in form.changed_data:
            model_field = obj._meta.get_field(name)
            self.plan.changes.append({
                "row_label": label, "field": name, "label": human(name),
                "old_display": sentences.show(model_field, old[name]),
                "new_display": sentences.show(model_field, change_log.to_json(form.cleaned_data[name])),
                "risky": name in self.section.risky, "line": item.key_at.get(name, item.at)[0]})


def plan_changes(section, parsed):
    """Match the parsed rows to the database and validate each through the page's form. Returns a Plan (see its fields);
    check `plan.errors`, `plan.stale` first. Saves nothing."""
    section = adapters.get(section) if isinstance(section, str) else section
    return Planner(section, parsed).run()
