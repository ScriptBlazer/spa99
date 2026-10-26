"""People and registrations worked out from the source tables, by the background job only (docs/features/office-counting-rules.md,
C1 to C4). Never called while a page loads: the job turns this into stored snapshots and insights.

A person is the account if the journey is linked to one (also when the same browser's earlier journeys were not linked
themselves: the browser's `person_key` maps to the account), otherwise the browser (`person_key`). Bots and staff
accounts are never counted. A person who finishes in a range also counts as started in it, so started >= finished."""
import logging
from collections import Counter, defaultdict

from . import metrics

logger = logging.getLogger("spa99.people")

# Keys of the figures laid over the stored daily sums when the sentences are written (not stored metric keys).
STARTED, FINISHED, REGISTERED, VOTERS = "people_started", "people_finished", "people_registered", "people_voters"


def _in(day, start, end):
    return day <= end and (start is None or day >= start)


class Figures:
    def __init__(self, started, finished, registrations, votes, leads=None, lead_votes=None, registered_emails=None):
        self.started_days = started          # {day: {person}} (includes people who finished that day)
        self.finished_days = finished        # {day: {person}}
        self.registrations = registrations   # [(day, plan slug or "none", source)]
        self.votes = votes                   # [(person, day, completed_at, [answers], suggested slug or "")]
        self.leads = leads or {}             # {lower email: day the address was first given}  (bots and staff left out)
        self.lead_votes = lead_votes or []   # [(lower email, day, completed_at, [answers])] finished journeys that left an email
        self.registered_emails = registered_emails or set()  # lower emails that have an account (not staff)

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

    # ----- leads (an email given at the journey gate; one lead = one lower-cased address) -----
    def new_leads(self, start, end):
        return {email for email, day in self.leads.items() if _in(day, start, end)}

    def new_lead_count(self, start, end):
        return len(self.new_leads(start, end))

    def converted_leads(self, start, end):
        """New leads in the range whose address has an account now (when they registered does not matter)."""
        return len(self.new_leads(start, end) & self.registered_emails)

    def new_leads_series(self, buckets):
        return [self.new_lead_count(a, b) for a, b in buckets]

    def lead_answer_counts(self, start, end):
        """(number of leads voting, {"question:option": n}): one vote per lead address that has not registered, from its latest
        finished journey in the range."""
        latest = {}
        for email, day, completed_at, answers in self.lead_votes:
            if email not in self.registered_emails and _in(day, start, end) and (email not in latest or completed_at > latest[email][0]):
                latest[email] = (completed_at, answers)
        counts = Counter()
        for _, answers in latest.values():
            counts.update(set(answers))
        return len(latest), dict(counts)

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
    """Read the source tables once (journey sessions and registrations) into a Figures. Job only. Sessions are streamed in
    chunks with only the fields needed, so memory holds the small result (people per day, votes), not the sessions."""
    from journey.models import JourneySession
    from users.models import InterestRegistration, User

    staff = set(User.objects.filter(is_staff=True).values_list("pk", flat=True))
    real = JourneySession.objects.filter(is_bot=False)
    account_of = {}  # browser person_key -> account; oldest first, so when a browser was linked to two accounts the latest link wins
    for key, person_key, user_id in real.filter(user__isnull=False).order_by("created_at").values_list("key", "person_key", "user_id").iterator(chunk_size=2000):
        account_of[person_key or key] = user_id

    started, finished, votes, uncounted = defaultdict(set), defaultdict(set), [], 0
    staff_emails = {e.lower() for e in User.objects.filter(is_staff=True).values_list("email", flat=True)}
    leads, lead_votes = {}, []
    fields = ("key", "person_key", "user_id", "created_at", "completed", "completed_at", "updated_at", "suggested_plan__slug", "suggestion_detail",
              "lead_email", "lead_at")
    for key, person_key, user_id, created_at, completed, completed_at, updated_at, plan, detail, lead_email, lead_at in real.values_list(*fields).iterator(chunk_size=2000):
        account = user_id or account_of.get(person_key or key)
        who = ("account", account) if account else ("browser", person_key or key)
        if account in staff:
            continue
        email = (lead_email or "").strip().lower()
        if email and email not in staff_emails:
            given = metrics.day(lead_at or created_at)
            leads[email] = min(given, leads.get(email, given))
        started[metrics.day(created_at)].add(who)
        if not completed:
            continue
        done = completed_at or updated_at
        day = metrics.day(done)
        started[day].add(who)
        finished[day].add(who)
        counted = (detail or {}).get("counted_answers")
        if counted is None:  # finished before answers were recorded on the session: no vote on answers (counted below)
            uncounted += 1
        votes.append((who, day, done, list(counted or []), plan or ""))
        if email and email not in staff_emails and counted is not None:
            lead_votes.append((email, day, done, list(counted)))
    if uncounted:
        logger.info("%s finished journeys have no stored answers and give no answer vote", uncounted)

    registrations = [
        (metrics.day(created), slug or "none", source)
        for created, slug, source in InterestRegistration.objects.filter(user__is_staff=False).values_list("created_at", "plan__slug", "source")
    ]
    registered_emails = {e.lower() for e in User.objects.filter(is_staff=False).values_list("email", flat=True)}
    return Figures(dict(started), dict(finished), registrations, votes, leads, lead_votes, registered_emails)
