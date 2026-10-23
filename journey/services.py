"""Journey logic: sessions, saving answers, screens and steps. Views stay thin and call these."""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import F, Prefetch
from django.utils import timezone

from common.useragent import device_type
from insights import metrics

from .conditions import matches
from .models import Answer, JourneySession, Option, Question, new_session_key

COOKIE_NAME = "spa99_journey"
NEW_VISIT_AFTER = timedelta(minutes=30)
MAX_TEXT_LENGTH = 500
UTM_FIELDS = ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content")


class AnswerError(ValueError):
    """The answer cannot be saved. The message is safe to show. `missing` lists question keys still to answer."""

    def __init__(self, message, missing=None):
        super().__init__(message)
        self.missing = missing or []


# ---------- sessions ----------

def create_session(user_agent="", referrer="", utm=None, user=None, previous=None):
    """A new journey session. `previous` (a restart in the same browser) hands over its person_key, so the person stays one
    person; otherwise the session's own key becomes its person_key."""
    utm = utm or {}
    kind = device_type(user_agent)
    key = new_session_key()
    with transaction.atomic():
        session = JourneySession.objects.create(
            key=key,
            person_key=(previous.person_key or previous.key) if previous is not None else key,
            device_type=kind,
            is_bot=kind == "bot",
            referrer=(referrer or "")[:500],
            user=user if user is not None and user.is_authenticated else None,
            **{name: (utm.get(name) or "")[:100] for name in UTM_FIELDS},
        )
        if not session.is_bot:  # bots are never counted
            metrics.journey_started(session.created_at, screens_between(0, session.furthest_step))
    return session


def touch(session):
    """Mark the session as seen now. A return after 30 minutes counts as a new visit. Queryset update: no history row."""
    now = timezone.now()
    changes = {"last_seen_at": now}
    if now - session.last_seen_at > NEW_VISIT_AFTER:
        changes["visit_count"] = F("visit_count") + 1
    JourneySession.objects.filter(pk=session.pk).update(**changes)
    session.refresh_from_db(fields=["last_seen_at", "visit_count"])


def _usable_by(session, user):
    """A session belongs to one browser until a person is tied to it. Anyone may continue an unowned session; an
    owned one only by that person. (On a shared device the next person must never inherit the last one's answers.)"""
    owner = session.user_id
    return owner is None or (user is not None and user.is_authenticated and owner == user.pk)


def get_or_create_session(key, user_agent="", referrer="", utm=None, user=None):
    """The session for a cookie value if this person may use it, or a new one. Returns (session, created)."""
    if key:
        session = JourneySession.objects.filter(key=key).first()
        if session is not None and _usable_by(session, user):
            touch(session)
            return session, False
    return create_session(user_agent, referrer, utm, user), True


def session_from_cookies(cookies, user=None):
    """The existing session for a request's cookies if `user` may use it, else None. Never creates one (used by
    sign-up and Gold)."""
    key = cookies.get(COOKIE_NAME)
    session = JourneySession.objects.filter(key=key).first() if key else None
    return session if session is not None and _usable_by(session, user) else None


def cookie_belongs_to_someone_else(cookies, user):
    """True when the journey cookie holds a session owned by a different person than `user` (shared device)."""
    key = cookies.get(COOKIE_NAME)
    session = JourneySession.objects.filter(key=key).first() if key else None
    return session is not None and not _usable_by(session, user)


def link_user(session, user):
    """Tie a session to a person once known (sign-up, login). Keeps an existing link."""
    if session is not None and session.user_id is None:
        session.user = user
        session.save(update_fields=["user", "updated_at"])
    return session


# ---------- questions, visibility, screens ----------

def screens_between(old_step, new_step):
    """Screen numbers (of all active questions) newly reached when the furthest step goes from old to new. The stored
    per-screen reach figures use this same definition, and so does `rebuild_metrics`."""
    if new_step <= old_step:
        return []
    numbers = Question.objects.filter(active=True, screen__gt=old_step, screen__lte=new_step).values_list("screen", flat=True)
    return sorted(set(numbers))


def _active_questions():
    options = Option.objects.filter(active=True).order_by("order", "value")
    return list(Question.objects.filter(active=True).prefetch_related(Prefetch("options", options, to_attr="active_options")))


def answers_by_key(session):
    answers = session.answers.select_related("question").prefetch_related("options")
    return {answer.question.key: answer for answer in answers}


def visible_questions(session, answers=None):
    """(visible questions in order, {question key: [option values]} for the visible, answered ones).
    A question is visible when its condition holds given the answers to the questions before it."""
    answers = answers if answers is not None else answers_by_key(session)
    values, visible = {}, []
    for question in _active_questions():
        if not matches(question.condition, values):
            continue
        visible.append(question)
        answer = answers.get(question.key)
        if answer is not None and not answer.skipped:
            values[question.key] = [o.value for o in answer.options.all()]
    return visible, values


def effective_answers(session):
    """{question key: Answer} for answered (not skipped) questions that are visible right now."""
    answers = answers_by_key(session)
    visible, _ = visible_questions(session, answers)
    keys = {q.key for q in visible}
    return {key: a for key, a in answers.items() if key in keys and not a.skipped}


def screen_numbers(session, visible=None):
    visible = visible if visible is not None else visible_questions(session)[0]
    return sorted({q.screen for q in visible})


def result_step(session, visible=None):
    numbers = screen_numbers(session, visible)
    return (numbers[-1] if numbers else 0) + 1


# ---------- saving ----------

def _clean_values(question, options, active_values):
    values = []
    for value in options or []:
        if not isinstance(value, str):
            raise AnswerError("That choice is not valid.")
        if value not in values:
            values.append(value)
    if question.type == Question.TEXT:
        raise AnswerError("This question takes typed text.")
    if question.type in (Question.SINGLE, Question.SCALE) and len(values) != 1:
        raise AnswerError("Choose one option, or skip.")
    if question.type == Question.MULTI and not values:
        raise AnswerError("Choose at least one option." if question.min_choices else "Choose at least one option, or skip.")
    if len(values) < question.min_choices:
        raise AnswerError(f"Choose at least {question.min_choices}.")
    if any(v not in active_values for v in values):
        raise AnswerError("That choice is not available.")
    return values


def save_answer(session, question_key, options=None, text="", skipped=False):
    """Save (or change) the answer to one question. Safe to repeat: the same answer twice changes nothing.
    Returns (answer, changed). Raises AnswerError for anything invalid."""
    visible, _ = visible_questions(session)
    question = next((q for q in visible if q.key == question_key), None)
    if question is None:
        raise AnswerError("That question is not part of this journey.")
    active = {o.value: o for o in question.active_options}

    chosen, text = [], (text or "")
    if skipped and question.min_choices:
        raise AnswerError("Choose at least one option.")
    if skipped:
        text = ""
    elif question.type == Question.TEXT:
        text = " ".join(str(text).split())
        if not text:
            raise AnswerError("Type an answer, or skip.")
        if len(text) > MAX_TEXT_LENGTH:
            raise AnswerError("That answer is too long.")
        if options:
            raise AnswerError("This question takes typed text.")
    else:
        text = ""
        chosen = _clean_values(question, options, active)

    new_options = [active[v] for v in chosen]
    try:
        with transaction.atomic():
            answer, changed = _store(session, question, new_options, text, bool(skipped))
    except IntegrityError:  # two taps raced to create the same row: the other one won, so repeat as an update
        with transaction.atomic():
            answer, changed = _store(session, question, new_options, text, bool(skipped))
    touch(session)
    return answer, changed


def _store(session, question, new_options, text, skipped):
    answer = Answer.objects.filter(session=session, question=question).first()
    if answer is None:
        answer = Answer.objects.create(session=session, question=question, text_value=text, skipped=skipped)
        answer.options.set(new_options)
        return answer, True
    same = (
        answer.skipped == skipped
        and answer.text_value == text
        and {o.pk for o in answer.options.all()} == {o.pk for o in new_options}
    )
    if same:
        return answer, False
    answer.skipped, answer.text_value, answer.answered_at = skipped, text, timezone.now()
    answer.save()
    answer.options.set(new_options)
    return answer, True


# ---------- required questions ----------

def missing_required(session, before_step=None):
    """Keys of visible questions that need choices (min_choices) and do not have enough yet, on screens before
    `before_step` (all screens when None). A skipped or unanswered question counts as missing."""
    answers = answers_by_key(session)
    visible, _ = visible_questions(session, answers)
    missing = []
    for question in visible:
        if not question.min_choices or (before_step is not None and question.screen >= before_step):
            continue
        answer = answers.get(question.key)
        chosen = 0 if answer is None or answer.skipped else len({o.value for o in answer.options.all() if o.active})
        if chosen < question.min_choices:
            missing.append(question.key)
    return missing


def require_answers(session, before_step=None):
    missing = missing_required(session, before_step)
    if missing:
        raise AnswerError("Choose at least one option to continue.", missing)


# ---------- steps ----------

def next_screen(session, current=None):
    """The screen after `current` that has visible questions, or the result step."""
    visible, _ = visible_questions(session)
    current = session.current_step if current is None else current
    later = [n for n in screen_numbers(session, visible) if n > current]
    return later[0] if later else result_step(session, visible)


def previous_screen(session, current=None):
    visible, _ = visible_questions(session)
    current = session.current_step if current is None else current
    earlier = [n for n in screen_numbers(session, visible) if n < current]
    return earlier[-1] if earlier else (screen_numbers(session, visible) or [1])[0]


def set_step(session, step=None, direction=None):
    """Move to an exact step (snapped to a screen that exists) or `direction` 'next' / 'back'. Returns the step."""
    visible, _ = visible_questions(session)
    numbers = screen_numbers(session, visible)
    last = result_step(session, visible)
    if direction == "next":
        target = next_screen(session)
    elif direction == "back":
        target = previous_screen(session)
    elif isinstance(step, int) and not isinstance(step, bool) and step >= 1:
        target = step if step in numbers or step >= last else next((n for n in numbers if n > step), last)
        # Never further than the screen after the furthest one reached: the funnel statistics cannot be inflated by
        # posting a big number.
        target = min(target, last, next_screen(session, session.furthest_step))
    else:
        raise AnswerError("Choose a step.")
    if target > session.current_step:  # moving forward: the screens he leaves must be complete
        require_answers(session, before_step=target)
    old_furthest = session.furthest_step
    session.current_step = target
    session.furthest_step = max(session.furthest_step, target)
    with transaction.atomic():
        session.save(update_fields=["current_step", "furthest_step", "updated_at"])
        if not session.is_bot:
            metrics.journey_screens_reached(session.created_at, screens_between(old_furthest, session.furthest_step))
    return target


# ---------- state for the page ----------

def _question_data(question, visible_keys, answers):
    answer = answers.get(question.key)
    return {
        "key": question.key,
        "text": question.text,
        "help": question.help_text,
        "type": question.type,
        "screen": question.screen,
        "visible": question.key in visible_keys,
        "condition": question.condition,
        "min_choices": question.min_choices,
        "required": question.min_choices > 0,
        "skippable": question.min_choices == 0,
        "options": [{"value": o.value, "label": o.label} for o in question.active_options],
        "answer": None if answer is None else {
            "options": [o.value for o in answer.options.all()],
            "text": answer.text_value,
            "skipped": answer.skipped,
        },
    }


def last_suggestion(session):
    """The stored suggestion of a finished journey, for the 'See my last suggestion' link. None when there is none.
    `url` is the result page (a view of the stored answers; nothing is computed until he opens it)."""
    plan = session.suggested_plan if session.suggested_plan_id else None
    if plan is None:
        return None
    return {"plan_name": plan.name, "plan_slug": plan.slug, "url": result_url()}


def result_url():
    from django.urls import reverse  # local: pages.views holds the slug constants
    from pages.views import JOURNEY_RESULT_SLUG
    return reverse("journey_page", args=[JOURNEY_RESULT_SLUG])


def build_state(session):
    """Everything the journey page needs to draw itself and resume. JSON friendly."""
    answers = answers_by_key(session)
    visible, _ = visible_questions(session, answers)
    visible_keys = {q.key for q in visible}
    screens = {}
    for question in _active_questions():
        screens.setdefault(question.screen, []).append(_question_data(question, visible_keys, answers))
    numbers = screen_numbers(session, visible)
    return {
        "session": {
            "id": str(session.pk),
            "max_text_length": MAX_TEXT_LENGTH,
            "current_step": session.current_step,
            "furthest_step": session.furthest_step,
            "completed": session.completed,
            "result_step": result_step(session, visible),
            "total_screens": len(numbers),
            "resume_step": numbers[0] if numbers else 1,  # reopening always starts at screen 1, answers ticked
        },
        "last_suggestion": last_suggestion(session),
        "screens": [{"number": n, "questions": screens[n]} for n in sorted(screens)],
    }
