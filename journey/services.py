"""Journey logic: sessions, saving answers, screens and steps. Views stay thin and call these."""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import F, Prefetch
from django.utils import timezone

from common.useragent import device_type

from .conditions import matches
from .models import Answer, JourneySession, Option, Question

COOKIE_NAME = "spa99_journey"
NEW_VISIT_AFTER = timedelta(minutes=30)
MAX_TEXT_LENGTH = 500
UTM_FIELDS = ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content")


class AnswerError(ValueError):
    """The answer cannot be saved. The message is safe to show."""


# ---------- sessions ----------

def create_session(user_agent="", referrer="", utm=None, user=None):
    utm = utm or {}
    kind = device_type(user_agent)
    return JourneySession.objects.create(
        device_type=kind,
        is_bot=kind == "bot",
        referrer=(referrer or "")[:500],
        user=user if user is not None and user.is_authenticated else None,
        **{name: (utm.get(name) or "")[:100] for name in UTM_FIELDS},
    )


def touch(session):
    """Mark the session as seen now. A return after 30 minutes counts as a new visit. Queryset update: no history row."""
    now = timezone.now()
    changes = {"last_seen_at": now}
    if now - session.last_seen_at > NEW_VISIT_AFTER:
        changes["visit_count"] = F("visit_count") + 1
    JourneySession.objects.filter(pk=session.pk).update(**changes)
    session.refresh_from_db(fields=["last_seen_at", "visit_count"])


def get_or_create_session(key, user_agent="", referrer="", utm=None, user=None):
    """The session for a cookie value, or a new one. Returns (session, created)."""
    if key:
        session = JourneySession.objects.filter(key=key).first()
        if session is not None:
            touch(session)
            return session, False
    return create_session(user_agent, referrer, utm, user), True


def session_from_cookies(cookies):
    """The existing session for a request's cookies, or None. Never creates one (used by sign-up and Gold)."""
    key = cookies.get(COOKIE_NAME)
    return JourneySession.objects.filter(key=key).first() if key else None


def link_user(session, user):
    """Tie a session to a person once known (sign-up, login). Keeps an existing link."""
    if session is not None and session.user_id is None:
        session.user = user
        session.save(update_fields=["user", "updated_at"])
    return session


# ---------- questions, visibility, screens ----------

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
        raise AnswerError("Choose at least one option, or skip.")
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
        target = min(target, last)
    else:
        raise AnswerError("Choose a step.")
    session.current_step = target
    session.furthest_step = max(session.furthest_step, target)
    session.save(update_fields=["current_step", "furthest_step", "updated_at"])
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
        "skippable": True,
        "options": [{"value": o.value, "label": o.label} for o in question.active_options],
        "answer": None if answer is None else {
            "options": [o.value for o in answer.options.all()],
            "text": answer.text_value,
            "skipped": answer.skipped,
        },
    }


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
            "current_step": session.current_step,
            "furthest_step": session.furthest_step,
            "completed": session.completed,
            "result_step": result_step(session, visible),
            "total_screens": len(numbers),
        },
        "screens": [{"number": n, "questions": screens[n]} for n in sorted(screens)],
    }
