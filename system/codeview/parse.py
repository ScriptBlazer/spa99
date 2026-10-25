"""Code text -> plain values with their line and column. Nothing is executed: the text is parsed with `ast.parse`, the tree is
checked to hold only `NAME = <literal>` lines (text, numbers, True, False, None, lists, dicts, tuples, minus signs), and each
value is read with `ast.literal_eval`. Anything else is refused with its line and column."""
import ast
import difflib
import math

from . import adapters

MAX_BYTES = 128 * 1024
MAX_DEPTH = 12  # real rules nest about 5 deep (journey > options > plan points)
MAX_ERRORS = 20
SIZE_MESSAGE = "Over 128 KB. Shorten it to review."

NOT_ALLOWED = {
    "Call": "Function calls are not allowed. Only plain values: text, numbers, True, False, None, lists and dicts.",
    "Attribute": "Attribute access is not allowed. Only plain values.",
    "Lambda": "Lambdas are not allowed. Only plain values.",
    "JoinedStr": "f-strings are not allowed. Use plain text in quotes.",
    "FormattedValue": "f-strings are not allowed. Use plain text in quotes.",
    "ListComp": "Comprehensions are not allowed. Write the values out.",
    "SetComp": "Comprehensions are not allowed. Write the values out.",
    "DictComp": "Comprehensions are not allowed. Write the values out.",
    "GeneratorExp": "Comprehensions are not allowed. Write the values out.",
    "BinOp": "Calculations are not allowed. Write the number out.",
    "Name": "Names are not allowed here. Use text in quotes, True, False or None.",
    "Set": "Sets are not allowed. Use a list.",
    "Subscript": "Indexing is not allowed. Only plain values.",
    "Starred": "Unpacking is not allowed. Only plain values.",
    "IfExp": "Conditions are not allowed. Only plain values.",
    "Compare": "Comparisons are not allowed. Only plain values.",
    "BoolOp": "Conditions are not allowed. Only plain values.",
}


class CodeError(Exception):
    """One or more errors, each {line, col, message} (col is 1-based). `status` 413 for a text that is too large, else 400."""

    def __init__(self, errors, status=400):
        super().__init__(errors[0]["message"] if errors else "Error")
        self.errors = errors
        self.status = status


def error(line, col, message):
    return {"line": int(line or 1), "col": int(col or 1), "message": message}


class Parsed(dict):
    """{variable name: located value}; `name_at` has where each name was written (for errors about the whole value)."""

    def __init__(self):
        super().__init__()
        self.name_at = {}


class LDict(dict):
    """A dict from the code that remembers where each key (`key_at`) and the dict itself (`at`) started: (line, column)."""

    at = (1, 1)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.key_at = {}


class LList(list):
    at = (1, 1)

    def __init__(self, *args):
        super().__init__(*args)
        self.item_at = []


def _pos(node):
    return node.lineno, node.col_offset + 1


def nearest(name, options):
    """The closest of `options` to a mistyped `name`, or None."""
    match = difflib.get_close_matches(str(name), [str(o) for o in options], n=1, cutoff=0.6)
    return match[0] if match else None


def _check(node, errors):
    """Collect what is not a plain literal under `node` (iterative: a deep text cannot overflow the stack)."""
    stack = [(node, 1)]
    while stack and len(errors) < MAX_ERRORS:
        current, level = stack.pop()
        kind = type(current).__name__
        if level > MAX_DEPTH:
            errors.append(error(*_pos(current), f"Nested too deeply (more than {MAX_DEPTH} levels)."))
            continue
        if isinstance(current, ast.Constant):
            value = current.value
            if isinstance(value, (bytes, complex)) or value is Ellipsis:
                errors.append(error(*_pos(current), "Only text, whole or decimal numbers, True, False and None are allowed."))
            elif isinstance(value, float) and not math.isfinite(value):
                errors.append(error(*_pos(current), "That number is too large."))
        elif isinstance(current, (ast.List, ast.Tuple)):
            stack.extend((child, level + 1) for child in reversed(current.elts))
        elif isinstance(current, ast.Dict):
            for key, value in reversed(list(zip(current.keys, current.values))):
                if key is None:
                    errors.append(error(*_pos(value), "Unpacking (**) is not allowed."))
                elif not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                    errors.append(error(*_pos(key), 'Keys must be text in quotes, like "name".'))
                else:
                    stack.append((value, level + 1))
        elif isinstance(current, ast.UnaryOp):
            operand = current.operand
            if (isinstance(current.op, (ast.USub, ast.UAdd)) and isinstance(operand, ast.Constant)
                    and isinstance(operand.value, (int, float)) and not isinstance(operand.value, bool) and math.isfinite(operand.value)):
                continue
            errors.append(error(*_pos(current), "Only a minus sign directly before a number is allowed."))
        else:
            errors.append(error(*_pos(current), NOT_ALLOWED.get(kind, f"{kind} is not allowed. Only plain values.")))


def _build(node):
    """The located value of a checked node (depth is already capped, so plain recursion is safe)."""
    if isinstance(node, ast.Dict):
        out = LDict()
        out.at = _pos(node)
        for key, value in zip(node.keys, node.values):
            name = key.value
            out[name] = _build(value)
            out.key_at.setdefault(name, _pos(key))
        return out
    if isinstance(node, (ast.List, ast.Tuple)):
        out = LList(_build(child) for child in node.elts)
        out.at = _pos(node)
        out.item_at = [_pos(child) for child in node.elts]
        return out
    return ast.literal_eval(node)


def _duplicate_keys(node, errors):
    for child in ast.walk(node):
        if isinstance(child, ast.Dict):
            seen = set()
            for key in child.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    if key.value in seen:
                        errors.append(error(*_pos(key), f'The key "{key.value}" appears twice.'))
                    seen.add(key.value)


def check_size(text):
    """Raise CodeError (413) for a text over 128 KB, or that is not text at all."""
    if not isinstance(text, str):
        raise CodeError([error(1, 1, "The code must be text.")])
    if len(text.encode("utf-8", "surrogatepass")) > MAX_BYTES:
        raise CodeError([error(1, 1, SIZE_MESSAGE)], status=413)


def parse(section, text):
    """{variable name: located value} for the section's code. Raises CodeError (all problems found, with line and column)."""
    section = adapters.get(section) if isinstance(section, str) else section
    check_size(text)
    try:
        tree = ast.parse(text, filename="<spa99-code>", mode="exec")
    except SyntaxError as exc:
        raise CodeError([error(exc.lineno, exc.offset, f"Syntax error: {exc.msg}.")]) from None
    except (RecursionError, MemoryError):
        raise CodeError([error(1, 1, "Too deeply nested or too large to read.")]) from None
    except (ValueError, OverflowError) as exc:
        raise CodeError([error(1, 1, f"Cannot read this text: {str(exc)[:120]}")]) from None
    errors, found = [], {}
    for statement in tree.body:
        if not isinstance(statement, ast.Assign):
            errors.append(error(*_pos(statement), f"Only lines like {section.names[0]} = [...] are allowed (no {type(statement).__name__.lower()})."))
            continue
        target = statement.targets[0] if len(statement.targets) == 1 else None
        if not isinstance(target, ast.Name):
            errors.append(error(*_pos(statement), f"Write one name on the left, like {section.names[0]} = [...]."))
        elif target.id not in section.names:
            hint = nearest(target.id, section.names)
            errors.append(error(*_pos(target), f"Unknown name {target.id}." + (f" Did you mean {hint}?" if hint else f" Expected {', '.join(section.names)}.")))
        elif target.id in found:
            errors.append(error(*_pos(target), f"{target.id} is set twice."))
        else:
            before = len(errors)
            _check(statement.value, errors)
            if len(errors) == before:
                _duplicate_keys(statement.value, errors)
            found[target.id] = (statement.value, _pos(target))
    for name in section.names:
        if name not in found:
            errors.append(error(1, 1, f"{name} is missing. The code must set {', '.join(section.names)}."))
    if errors:
        raise CodeError(sorted(errors, key=lambda e: (e["line"], e["col"]))[:MAX_ERRORS])
    values = Parsed()
    for name, (node, at) in found.items():
        try:
            values[name] = _build(node)
        except (RecursionError, MemoryError, ValueError, SyntaxError, TypeError) as exc:
            raise CodeError([error(at[0], at[1], f"Cannot read this value: {str(exc)[:120]}")]) from None
        values.name_at[name] = at
    return values
