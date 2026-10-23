"""People and registrations worked out from the source tables, by the background job only (docs/features/office-counting-rules.md,
C1 to C4). Never called while a page loads: the job turns this into stored snapshots and insights.

A person is the account if the journey is linked to one (also when the same browser's earlier journeys were not linked
themselves: the browser's `person_key` maps to the account), otherwise the browser (`person_key`). Bots and staff
accounts are never counted. A person who finishes in a range also counts as started in it, so started >= finished."""
from collections import Counter, defaultdict

from . import metrics

# Keys of the figures laid over the stored daily sums when the sentences are written (not stored metric keys).
STARTED, FINISHED, REGISTERED, VOTERS = "people_started", "people_finished", "people_registered", "people_voters"


def _in(day, start, end):
    return day <= end and (start is None or day >= start)


class Figures:
    def __init__(self, started, finished, registrations, votes):
        self.started_days = started          # {day: {person}} (includes people who finished that day)
        self.finished_days = finished        # {day: {person}}
        self.registrations = registrations   # [(day, plan slug or "none", source)]
        self.votes = votes                   # [(person, day, completed_at, [answers], suggested slug or "")]

    # ----- people -----
    @staticmethod
    def _distinct(days, start, end):
        out = set()
        for day, people in days.items():
            if _in(day, start, end):
                out |= people
        return len(out)

    def started(self, start, end):
        return self._distinct(self.started_days, start, end)

    def finished(self, start, end):
        return self._distinct(self.finished_days, start, end)

    def started_series(self, buckets):
        return [self.started(a, b) for a, b in buckets]

    def finished_series(self, buckets):
        return [self.finished(a, b) for a, b in buckets]

    # ----- registrations -----
    def registered(self, start, end):
        return sum(1 for day, _, _ in self.registrations if _in(day, start, end))

    def registered_series(self, buckets):
        return [self.registered(a, b) for a, b in buckets]

    def registered_by(self, start, end, index):
        """{plan slug | source: n} for registrations in the range; index 1 = plan, 2 = source."""
        out = Counter()
        for row in self.registrations:
            if _in(row[0], start, end):
                out[row[index]] += 1
        return dict(out)

    # ----- votes: each person's latest finished journey in the range -----
    def latest_votes(self, start, end):
        latest = {}
        for person, day, completed_at, answers, plan in self.votes:
            if _in(day, start, end) and (person not in latest or completed_at > latest[person][0]):
                latest[person] = (completed_at, answers, plan)
        return list(latest.values())

    def vote_counts(self, start, end):
        """(number of voters, {"question:option": n}, {plan slug: n}) with one vote per person."""
        votes = self.latest_votes(start, end)
        answers, plans = Counter(), Counter()
        for _, items, plan in votes:
            answers.update(set(items))
            if plan:
                plans[plan] += 1
        return len(votes), dict(answers), dict(plans)

    def overlay(self, sums, start, end):
        """`sums` (stored daily totals for the range) with every person-based figure replaced by this range's."""
        out = {k: v for k, v in sums.items() if k[0] not in (metrics.K.JOURNEY_ANSWER, metrics.K.SUGGESTED_PLAN,
                                                             metrics.K.REGISTRATIONS_BY_PLAN, metrics.K.REGISTRATIONS)}
        voters, answers, plans = self.vote_counts(start, end)
        out[(STARTED, "")], out[(FINISHED, "")], out[(VOTERS, "")] = self.started(start, end), self.finished(start, end), voters
        out[(REGISTERED, "")] = out[(metrics.K.REGISTRATIONS, "")] = self.registered(start, end)
        out.update({(metrics.K.JOURNEY_ANSWER, d): n for d, n in answers.items()})
        out.update({(metrics.K.SUGGESTED_PLAN, d): n for d, n in plans.items()})
        out.update({(metrics.K.REGISTRATIONS_BY_PLAN, d): n for d, n in self.registered_by(start, end, 1).items()})
        return out


def load():
    """Read the source tables once (journey sessions and registrations) into a Figures. Job only."""
    from journey import engine
    from journey.models import JourneySession
    from users.models import InterestRegistration, User

    staff = set(User.objects.filter(is_staff=True).values_list("pk", flat=True))
    sessions = list(JourneySession.objects.filter(is_bot=False).select_related("suggested_plan"))
    account_of = {}  # browser person_key -> account, from any of its linked journeys
    for s in sessions:
        if s.user_id:
            account_of.setdefault(s.person_key or s.key, s.user_id)

    def person(s):
        account = s.user_id or account_of.get(s.person_key or s.key)
        return ("account", account) if account else ("browser", s.person_key or s.key)

    started, finished, votes = defaultdict(set), defaultdict(set), []
    for s in sessions:
        who = person(s)
        if who[0] == "account" and who[1] in staff:
            continue
        started[metrics.day(s.created_at)].add(who)
        if not s.completed:
            continue
        done = s.completed_at or s.updated_at
        day = metrics.day(done)
        started[day].add(who)
        finished[day].add(who)
        counted = s.suggestion_detail.get("counted_answers")
        answers = counted if counted is not None else engine.counted_answers(s)
        votes.append((who, day, done, list(answers), s.suggested_plan.slug if s.suggested_plan_id else ""))

    registrations = [
        (metrics.day(created), slug or "none", source)
        for created, slug, source in InterestRegistration.objects.filter(user__is_staff=False).values_list("created_at", "plan__slug", "source")
    ]
    return Figures(dict(started), dict(finished), registrations, votes)
