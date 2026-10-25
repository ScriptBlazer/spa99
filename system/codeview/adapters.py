"""One adapter per System rule section: what the code shows, which model and form each row uses, what is read only, and
where rows may be added or removed. The code view edits the same rows as the page, through the page's own forms, so the
fields here are read from the forms (never listed twice).

Entity = one kind of row (a plan, a closure, a question with its options inside). A section has one or more variables:
a list of entities (PLANS = [...]) or a single record (SETTINGS = {...}, the site settings row)."""
from dataclasses import dataclass, field
from typing import Callable

from gold.models import GoldRule
from journey.models import Option, Question, SuggestionRule
from plans.models import Closure, OpeningRule, Plan, SiteSettings

from .. import forms_rules as f
from ..forms import EmailsForm, SettingsForm


@dataclass(frozen=True)
class Entity:
    model: type
    form: type                                   # validates an existing row (the page's form)
    label: Callable                              # obj -> text shown in the review ("Tier 1")
    queryset: Callable = lambda parent: None     # parent object (or None) -> the rows shown
    add_form: type = None                        # validates a new row; None = rows cannot be added here
    readonly: tuple = ()                         # extra read only keys besides id (slug, kind ...)
    removable: bool = False                      # a row missing from the code is a removal (closures only)
    children: dict = field(default_factory=dict) # key -> Entity: lists nested inside each row (a question's options)
    noun: str = "row"                            # for messages and the review ("plan", "closure")
    hint: str = ""                               # said when a removal is refused ("set visible to False")
    new_kwargs: Callable = lambda parent: {}     # model kwargs of a new row (an option needs its question)
    has_id: bool = True                          # a single record (the site settings row) has no id key

    @property
    def editable(self):
        return list(self.form._meta.fields)

    @property
    def fixed(self):
        """Read only keys after id: the explicit ones, plus what the add form asks for beyond the edit form (slug, kind)."""
        extra = [n for n in (self.add_form._meta.fields if self.add_form else ()) if n not in self.form._meta.fields]
        return tuple(dict.fromkeys([*self.readonly, *extra]))

    @property
    def row_keys(self):
        return [*(["id"] if self.has_id else []), *self.fixed, *self.editable, *self.children]


@dataclass(frozen=True)
class Variable:
    name: str
    entity: Entity
    many: bool = True        # a list of rows; False = one dict (the site settings row)


@dataclass(frozen=True)
class Section:
    key: str
    title: str               # "Plans" (the audit sentence: Edited Plans as code)
    filename: str
    variables: tuple
    risky: tuple             # fields that need the confirm step (forms_rules.RISKY)

    @property
    def names(self):
        return [v.name for v in self.variables]


def _site(_parent):
    return [SiteSettings.load()]


PLAN = Entity(Plan, f.PlanForm, label=lambda o: o.name, queryset=lambda p: Plan.objects.all(), add_form=f.PlanAddForm,
              noun="plan", hint=" (hide it with \"visible\": False)")
RULE = Entity(OpeningRule, f.OpeningRuleForm, label=lambda o: o.label, queryset=lambda p: OpeningRule.objects.all(),
              add_form=f.OpeningRuleAddForm, noun="opening rule", hint=" (switch it off with \"active\": False)")
CLOSURE = Entity(Closure, f.ClosureForm, label=lambda o: o.name, queryset=lambda p: Closure.objects.all(), add_form=f.ClosureForm,
                 removable=True, noun="closure")
CAPACITY = Entity(SiteSettings, f.CapacityForm, label=lambda o: "Capacity and slots", queryset=_site, has_id=False,
                  children={"rules": RULE, "closures": CLOSURE}, noun="capacity")
GOLD = Entity(GoldRule, f.GoldRuleForm, label=lambda o: o.label or f"{o.group}:{o.match_value}", queryset=lambda p: GoldRule.objects.all(),
              add_form=f.GoldRuleAddForm, noun="Gold rule", hint=" (switch it off with \"active\": False)")
OPTION = Entity(Option, f.OptionForm, label=lambda o: f"{o.question.key} · {o.label}", queryset=lambda q: q.options.all(), add_form=f.OptionAddForm,
                noun="option", hint=" (switch it off with \"active\": False)", new_kwargs=lambda q: {"question": q})
QUESTION = Entity(Question, f.QuestionForm, label=lambda o: o.key, queryset=lambda p: Question.objects.all(), readonly=("key", "type"),
                  children={"options": OPTION}, noun="question", hint=" (switch it off with \"active\": False)")
SUGGESTION = Entity(SuggestionRule, f.SuggestionRuleForm, label=lambda o: o.name, queryset=lambda p: SuggestionRule.objects.all(),
                    noun="suggestion rule", hint=" (switch it off with \"active\": False)")
SETTINGS = Entity(SiteSettings, SettingsForm, label=lambda o: "Settings", queryset=_site, has_id=False, noun="settings")
EMAILS = Entity(SiteSettings, EmailsForm, label=lambda o: "Emails", queryset=_site, has_id=False, noun="emails")

SECTIONS = {s.key: s for s in (
    Section("plans", "Plans", "plans.py", (Variable("PLANS", PLAN),), tuple(f.RISKY["plans"])),
    Section("hours", "Hours", "hours.py", (Variable("HOURS", CAPACITY, many=False),), tuple(f.RISKY["hours"])),
    Section("gold", "Gold rules", "gold.py", (Variable("GOLD_RULES", GOLD),), tuple(f.RISKY["gold"])),
    Section("journey", "Journey", "journey.py", (Variable("JOURNEY", QUESTION), Variable("SUGGESTIONS", SUGGESTION)), tuple(f.RISKY["journey"])),
    Section("settings", "Settings", "settings.py", (Variable("SETTINGS", SETTINGS, many=False),), tuple(f.RISKY["settings"])),
    Section("emails", "Emails", "emails.py", (Variable("EMAILS", EMAILS, many=False),), tuple(f.RISKY["emails"])),
)}


def get(key):
    """The section, or None for a name that has no code view."""
    return SECTIONS.get(key)
