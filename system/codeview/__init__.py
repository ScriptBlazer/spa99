"""The System code view: the rule pages as code (docs/features/system-code-view.md). Nothing is executed: the code is parsed as
literals only and saved through the same forms and change log as the pages.

Modules: adapters (one per section), render (rows -> text, version), parse (text -> located values), plan (what would change),
service (preview and apply). `codeview.render.render(section)`, `codeview.parse.parse(section, text)` and `plan_changes` are the
three steps."""
from .adapters import SECTIONS, get as section
from .plan import plan_changes

__all__ = ["SECTIONS", "section", "plan_changes"]
