"""The next-morning email to new leads, from a person (docs/features/office-outreach.md R7).

Who: every address given at the journey gate (JourneySession.lead_email, which carries the tick "Spa 99 may email me about opening"),
once per address, ever (NextMorningEmail.email is unique).
When: the next send time (System, default 10:00 Europe/London) at least N hours (System, default 8) after the address was first given
(`due_time`, zoneinfo, DST-safe). A timing change in System applies to unsent rows: each run recomputes their due_at (`refresh_due`).
Skipped at send time, logged and never retried: a verified account exists, archived, unsubscribed, hard bounce, switch off, no sender.

How leads are found: the 15-minute job DISCOVERS them from the journey sessions rather than a hook in the journey code. Reasons:
every path that stores `lead_email` is covered (the gate, a restart that copies it, a shell or admin edit), the visitor's request pays
nothing and cannot fail because of this, a worker that was down simply catches up on the next run, and the unique row makes a repeat
harmless. The cost is a small query every 15 minutes over the sessions of the last few days.
Only addresses first given AFTER the switch was turned on (`SiteSettings.lead_next_morning_since`) get a row, so leads from before are
never mass-emailed. A row more than a day overdue (the worker was down for long) is skipped as "too late": a "next morning" email must
not arrive days later.

Once-only with two workers: rows are claimed with select_for_update(skip_locked=True) where the database has it (Postgres), and every
claim is also a conditional UPDATE of `claimed_at` that only one worker can win (SQLite, and Postgres too)."""
import logging
from datetime import datetime, time, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.db import connection, transaction
from django.db.models import Min
from django.db.models.functions import Lower
from django.utils import timezone

from common.emaildefaults import SENDER_PERSON
from common.jobs import tracked
from journey.models import JourneySession
from plans.models import SiteSettings

from .models import ArchivedLead, NextMorningEmail

logger = logging.getLogger("spa99.outreach")

LONDON = ZoneInfo("Europe/London")
SEND_AT = time(10, 0)
TOO_LATE = timedelta(hours=24)  # overdue by more than this at send time: skipped, not sent
DISCOVER_DAYS = 3  # look back this far for new addresses (a longer outage than the TOO_LATE rule could use anyway)
BATCH = 50
TAG = "lead-next-morning"
TEMPLATE = "lead_next_morning"
NOTICE = "You are receiving this because you gave us your email to hear about Spa 99 opening."

SKIP_OFF, SKIP_NO_SENDER, SKIP_ACCOUNT, SKIP_ARCHIVED, SKIP_UNSUBSCRIBED = "switch off", "no sender address", "has an account", "archived", "unsubscribed"
SKIP_BOUNCE, SKIP_LATE, SKIP_SUPPRESSED, SKIP_FAILED = "hard bounce", "too late", "suppressed", "send failed"


def due_time(lead_at, send_at=SEND_AT, min_hours=8):
    """The next `send_at` (London wall-clock time, default 10:00) at least `min_hours` (default 8) after `lead_at` (an aware datetime), as
    an aware UTC datetime. With the defaults, 2:00 gives 10:00 the same day; 9:30 gives 10:00 the next day; 23:00 gives 10:00 the next day.
    The wall-clock time is built from the London date, not by adding hours, so a clock-change day still lands on it (a send time inside
    the skipped spring hour moves forward, one in the repeated autumn hour takes its first occurrence: zoneinfo's rule)."""
    earliest = lead_at.astimezone(dt_timezone.utc) + timedelta(hours=min_hours)  # absolute hours: an aware London datetime would add wall-clock time across a clock change
    day = earliest.astimezone(LONDON).date()
    candidate = datetime.combine(day, send_at, tzinfo=LONDON)
    if candidate < earliest:
        candidate = datetime.combine(day + timedelta(days=1), send_at, tzinfo=LONDON)
    return candidate.astimezone(dt_timezone.utc)


def timing(site):
    """(send_at, min_hours) from System."""
    return site.lead_next_morning_at or SEND_AT, site.lead_next_morning_min_hours if site.lead_next_morning_min_hours is not None else 8


def refresh_due(site, now):
    """System timing changes apply to leads not yet sent: recompute due_at of the recent unsent rows (the only ones that can still be
    due; older ones are skipped as too late). Returns how many changed."""
    send_at, hours = timing(site)
    changed = 0
    for row in NextMorningEmail.objects.filter(sent_at__isnull=True, skipped_at__isnull=True, claimed_at__isnull=True, lead_at__gte=now - timedelta(days=DISCOVER_DAYS + 2)):
        due = due_time(row.lead_at, send_at, hours)
        if due != row.due_at:
            NextMorningEmail.objects.filter(pk=row.pk, claimed_at__isnull=True).update(due_at=due)
            changed += 1
    return changed


# ---------- finding new leads ----------

def discover(site, now=None):
    """Create a row for each address first given since the switch was turned on. Returns how many rows were created."""
    now = now or timezone.now()
    since = site.lead_next_morning_since
    if since is None:
        return 0
    cutoff = max(since, now - timedelta(days=DISCOVER_DAYS))
    recent = (JourneySession.objects.filter(is_bot=False, lead_at__gte=cutoff).exclude(lead_email="").annotate(k=Lower("lead_email"))
              .order_by().values_list("k", flat=True).distinct())
    wanted = set(recent)
    if not wanted:
        return 0
    wanted -= set(NextMorningEmail.objects.filter(email__in=wanted).values_list("email", flat=True))
    if not wanted:
        return 0
    firsts = (JourneySession.objects.filter(is_bot=False, lead_at__isnull=False).annotate(k=Lower("lead_email")).filter(k__in=wanted)
              .values("k").annotate(first=Min("lead_at")).order_by())  # the FIRST time he gave it, over all his journeys
    rows = [NextMorningEmail(email=found["k"], lead_at=found["first"], due_at=due_time(found["first"], *timing(site)))
            for found in firsts if found["first"] >= cutoff]  # an address first given before the switch is not a new lead
    NextMorningEmail.objects.bulk_create(rows, ignore_conflicts=True)  # unique email: a second worker's duplicate is dropped
    return len(rows)


# ---------- sending ----------

def skip_reason(email, site, now):
    """Why this address must not be emailed now ('' = go ahead). Checked at send time."""
    from mailings.models import EmailOptOut
    from notifications.models import EmailBounce
    from users.models import User

    if User.objects.filter(email__iexact=email, email_verified_at__isnull=False).exists():
        return SKIP_ACCOUNT
    if ArchivedLead.objects.filter(email=email).exists():
        return SKIP_ARCHIVED
    if EmailOptOut.objects.filter(email=email).exists() or User.objects.filter(email__iexact=email, marketing_consent=False).exists():
        return SKIP_UNSUBSCRIBED
    if EmailBounce.objects.filter(email=email, kind=EmailBounce.HARD).exists():
        return SKIP_BOUNCE
    return ""


def _finish(row, **fields):
    NextMorningEmail.objects.filter(pk=row.pk).update(**fields)


def _skip(row, reason, now):
    _finish(row, skipped_at=now, skip_reason=reason)
    logger.info("Next-morning email skipped for a lead (%s)", reason)  # never the address in the log
    return reason


def _first_name(email):
    """The first name he gave at the email step (or staff typed), else his Gold application's, else ''."""
    from gold.models import GoldApplication
    from journey.models import JourneySession

    lead = JourneySession.objects.filter(lead_email__iexact=email, is_bot=False).exclude(lead_first_name="").order_by("-created_at").first()
    if lead is not None:
        return lead.lead_first_name

    application = GoldApplication.objects.filter(email__iexact=email).exclude(first_name="").order_by("created_at").first()
    return application.first_name if application else ""


def send_one(row, site, now, force=False):
    """Send (or skip) one claimed row. Returns 'sent' or the skip reason. Never raises. `force` is staff pressing Resend follow-up on a corrected
    address: it ignores the automatic switch and the "too late" rule (everything else, a bounce, an unsubscribe, the sender address, still counts)."""
    from mailings import tokens
    from notifications import emailsettings
    from notifications.models import EmailLog
    from notifications.services import send_templated, subject_for

    if not site.lead_next_morning_on and not force:
        return _skip(row, SKIP_OFF, now)
    if emailsettings.options_for(TEMPLATE).sender == SENDER_PERSON and not site.auto_sender:  # the email's own sender setting (Person by default)
        return _skip(row, SKIP_NO_SENDER, now)
    if row.due_at < now - TOO_LATE and not force:
        return _skip(row, SKIP_LATE, now)
    reason = skip_reason(row.email, site, now)
    if reason:
        return _skip(row, reason, now)
    try:
        first_name = _first_name(row.email)
        url = tokens.unsubscribe_url(row.email)
        headers = {**tokens.list_unsubscribe_headers(url), "X-PM-Tag": TAG}
        log = send_templated(TEMPLATE, [row.email], subject_for(TEMPLATE, first_name=first_name),
                             {"first_name": first_name, "sender_name": (site.auto_email_from_name or "").strip() or "Spa 99", "unsubscribe_url": url, "notice": NOTICE},
                             subject_email=row.email, headers=headers)  # From, Reply-To and the footer come from the email's own settings (System > Emails)
    except Exception as error:  # noqa: BLE001 - one bad row must not stop the others; the row is not retried (it may have gone out)
        logger.error("Next-morning email failed (%s)", type(error).__name__)
        return _skip(row, SKIP_FAILED, now)
    if log.status == EmailLog.SENT:
        _finish(row, sent_at=timezone.now())
        return "sent"
    return _skip(row, SKIP_SUPPRESSED if log.status == EmailLog.SUPPRESSED else SKIP_FAILED, now)


def claim_due(now, limit=BATCH):
    """Rows due now that nobody has picked up, claimed for this worker. select_for_update(skip_locked) where the database has it
    (Postgres; SQLite ignores it), and a conditional UPDATE per row either way: only one worker can win a row."""
    mine = []
    with transaction.atomic():
        due = NextMorningEmail.objects.filter(due_at__lte=now, sent_at__isnull=True, skipped_at__isnull=True, claimed_at__isnull=True).order_by("due_at", "pk")
        if connection.features.has_select_for_update_skip_locked:
            due = due.select_for_update(skip_locked=True)
        for row in list(due[:limit]):
            if NextMorningEmail.objects.filter(pk=row.pk, claimed_at__isnull=True).update(claimed_at=now):
                mine.append(row)
    return mine


def run(now=None):
    """The job body: find new leads (only while the switch is on), then send or skip what is due. Returns a short summary."""
    now = now or timezone.now()
    site = SiteSettings.load()
    created = discover(site, now) if site.lead_next_morning_on else 0
    refresh_due(site, now)
    counts = {}
    for row in claim_due(now):
        outcome = send_one(row, site, now)
        counts[outcome] = counts.get(outcome, 0) + 1
    return f"{created} new, " + (", ".join(f"{n} {what}" for what, n in sorted(counts.items())) or "nothing due")


@tracked("lead_next_morning")
def scheduled():
    return run()
