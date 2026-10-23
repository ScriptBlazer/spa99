"""Stored figures (docs/features/office.md, "The rule: stored figures only"). Pages read these rows; events and the
hourly roll-up write them. No personal data in any of them.

Keys are plain strings (see insights.metrics.K). `dimension` is "" for a total, or a slug / bucket for a breakdown
(plan slug, page group, referrer host, "question:option"). Rates are stored in basis points (1234 = 12.34%)."""
from django.db import models


class MetricCounter(models.Model):
    """A running total (or current state, e.g. applications by status), updated in the same transaction as the event."""

    key = models.CharField(max_length=60)
    dimension = models.CharField(max_length=100, blank=True, default="")
    value = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["key", "dimension"], name="metric_counter_unique")]

    def __str__(self):
        return f"{self.key}[{self.dimension}] = {self.value}"


class DailyMetric(models.Model):
    """One figure for one London calendar day. Written as events happen; the roll-up adds the derived rates."""

    date = models.DateField()
    key = models.CharField(max_length=60)
    dimension = models.CharField(max_length=100, blank=True, default="")
    value = models.BigIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["date", "key", "dimension"], name="daily_metric_unique")]
        indexes = [models.Index(fields=["key", "date"])]

    def __str__(self):
        return f"{self.date} {self.key}[{self.dimension}] = {self.value}"


class PeriodMetric(models.Model):
    """Weekly (Monday start) and monthly rows, summed from the daily rows by the roll-up so charts read a ready series."""

    WEEK, MONTH = "week", "month"
    PERIOD_CHOICES = [(WEEK, "Week"), (MONTH, "Month")]

    period = models.CharField(max_length=5, choices=PERIOD_CHOICES)
    start = models.DateField(help_text="First day of the week or month.")
    key = models.CharField(max_length=60)
    dimension = models.CharField(max_length=100, blank=True, default="")
    value = models.BigIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["period", "start", "key", "dimension"], name="period_metric_unique")]
        indexes = [models.Index(fields=["period", "key", "start"])]

    def __str__(self):
        return f"{self.period} {self.start} {self.key}[{self.dimension}] = {self.value}"


class VisitorSalt(models.Model):
    """The day's random salt for visitor hashes. Only today's row is kept: the roll-up deletes older ones, which makes
    yesterday's hashes impossible to recompute even with an IP and user agent in hand."""

    date = models.DateField(unique=True)
    salt = models.CharField(max_length=64)


class VisitorHash(models.Model):
    """Today's anonymous visitors, only so one visitor counts once a day. hash = sha256(salt of the day, IP, user agent);
    neither the IP nor the user agent is stored. Wiped by the roll-up once the day is over."""

    date = models.DateField()
    hash = models.CharField(max_length=64)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["date", "hash"], name="visitor_hash_unique")]


class Insight(models.Model):
    """One stored "what people want" fact, written by the roll-up from the daily rows (nothing is worked out when a page
    loads). Per range and key, rank 1 is the top answer and rank 2 the runner-up (and so on, to rank 6).
    value of of_total: e.g. Gym, 5 of 7. The sentence is written on rank 1 only."""

    range = models.CharField(max_length=5, help_text="today, 7d, 30d, 90d or all.")
    key = models.CharField(max_length=30)
    rank = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=60)
    label = models.CharField(max_length=120)
    value = models.PositiveIntegerField()
    of_total = models.PositiveIntegerField()
    sentence = models.CharField(max_length=300, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["range", "key", "rank"], name="insight_unique")]

    def __str__(self):
        return f"{self.key}[{self.range}] #{self.rank} {self.label}"


class OfficeSnapshot(models.Model):
    """The finished payload of one Office data view (page: dashboard, analytics or pages) for one range, written by the
    roll-up and by the debounced refresh after each event. Views read this one row; nothing is summed on page load."""

    DASHBOARD, ANALYTICS, PAGES = "dashboard", "analytics", "pages"

    page = models.CharField(max_length=12)
    range = models.CharField(max_length=5)
    payload = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["page", "range"], name="office_snapshot_unique")]

    def __str__(self):
        return f"{self.page}[{self.range}]"


class SnapshotRefresh(models.Model):
    """One row that debounces the background refresh: queued_at is set when a refresh job is queued and cleared when the
    job starts, so a burst of events queues one job. A stale value (the queue is off) expires and the hourly roll-up
    covers the gap."""

    key = models.CharField(max_length=20, unique=True, default="snapshots")
    queued_at = models.DateTimeField(null=True, blank=True)


class OfficeGoal(models.Model):
    """A goal or target for a dashboard ring, edited in the Django admin. No row = the ring shows "No goal set".
    All three are counts for the range."""

    REGISTRATIONS, JOURNEYS_STARTED, JOURNEYS_FINISHED = "registrations", "journeys_started", "journeys_finished"
    KEY_CHOICES = [
        (JOURNEYS_STARTED, "People who started the journey (count in the range)"),
        (JOURNEYS_FINISHED, "People who finished the journey (count in the range)"),
        (REGISTRATIONS, "Registrations (count in the range)"),
    ]
    TODAY, WEEK, MONTH, ALL = "today", "7d", "30d", "all"
    RANGE_CHOICES = [(TODAY, "Today"), (WEEK, "7 days"), (MONTH, "30 days"), (ALL, "Any range (used when the range has no row)")]

    key = models.CharField(max_length=30, choices=KEY_CHOICES)
    range = models.CharField(max_length=5, choices=RANGE_CHOICES, default=ALL)
    target = models.PositiveIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["key", "range"], name="office_goal_unique")]

    def __str__(self):
        return f"{self.key} {self.range} = {self.target}"


class MetricText(models.Model):
    """A sentence written by the roll-up (the dashboard's "what changed" line, each chart's summary), so no page
    composes text at request time."""

    key = models.CharField(max_length=60)
    scope = models.CharField(max_length=10, blank=True, default="", help_text="The range: today, 7d, 30d, 90d or all.")
    text = models.CharField(max_length=300)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["key", "scope"], name="metric_text_unique")]

    def __str__(self):
        return f"{self.key}[{self.scope}]"
