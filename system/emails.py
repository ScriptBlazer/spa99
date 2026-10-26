"""System > Emails: the logic behind the pages (views stay short). Overview figures, the automatic emails, mailing and invite pages.

Everything here reads stored rows or cheap counts (EmailLog has an index on created_at; suppressions are a small table)."""
import datetime

from django import forms
from django.core.paginator import Paginator
from django.utils import timezone

from mailings import segments
from mailings.models import EmailOptOut, Invite, Mailing
from notifications import emailbody, ses
from notifications.models import EmailLog, EmailSuppression, NotificationTemplate
from notifications.seed import DEFAULT_SUBJECTS

from .forms import VersionedForm
from .models import SystemChange

EMAIL_MODEL = "notifications.notificationtemplate"
PAGE = 50
SCHEDULE_FORMATS = ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S")


# ---------- overview ----------

def overview():
    """Context for /emails/: the SES state and cheap counts."""
    now = timezone.now()
    today = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    week = now - datetime.timedelta(days=7)
    sent = EmailLog.objects.filter(status=EmailLog.SENT)
    return {
        "ses": ses.ses_status(),
        "stats": {
            "sent_today": sent.filter(created_at__gte=today).count(),
            "sent_week": sent.filter(created_at__gte=week).count(),
            "failed_week": EmailLog.objects.filter(status=EmailLog.FAILED, created_at__gte=week).count(),
            "bounces_week": EmailSuppression.objects.filter(reason=EmailSuppression.HARD_BOUNCE, last_seen__gte=week).count(),
            "complaints_week": EmailSuppression.objects.filter(reason=EmailSuppression.COMPLAINT, last_seen__gte=week).count(),
            "suppressed_total": EmailSuppression.objects.count(),
            "unsubscribed_no_account": EmailOptOut.objects.count(),
        },
        "recent_mailings": list(Mailing.objects.all()[:5]),
        "recent_invite_batches": invite_batches()[:5],
    }


# ---------- automatic emails ----------

def spec_info(spec):
    """One email's placeholders and samples, for the edit screen."""
    return {
        "key": spec.key, "title": spec.title, "editable": spec.editable, "has_button": bool(spec.button_label),
        "button_required": spec.button_required, "button_label": spec.button_label,
        "placeholders": [{"name": n, "description": d, "sample": str(emailbody.sample_values(spec).get(n.strip(), ""))[:80]}
                         for n, d in spec.placeholders.items()],
        "subject_placeholders": [{"name": n, "description": d} for n, d in spec.subject_placeholders.items()],
    }


def template_row(key, create=False):
    """The NotificationTemplate row for a key (None when seeding has not made it; `create` makes it, like the seed does: no person, no log entry)."""
    row = NotificationTemplate.objects.filter(key=key).first()
    if row is None and create:
        subject, note = DEFAULT_SUBJECTS[key]
        row = NotificationTemplate.objects.create(key=key, subject=subject, note=note)
    return row


def automatic_list():
    """Every automatic email: when it is sent, subject, whether it was changed, last edit (who and when)."""
    specs = emailbody.listed_specs()
    rows = {r.key: r for r in NotificationTemplate.objects.filter(key__in=[s.key for s in specs])}
    last = {}
    for change in SystemChange.objects.filter(model_label=EMAIL_MODEL, object_pk__in=[str(r.pk) for r in rows.values()]).order_by("-created_at")[:200]:
        last.setdefault(change.object_pk, change)
    result = []
    for spec in specs:
        row = rows.get(spec.key)
        default_subject, note = DEFAULT_SUBJECTS[spec.key]
        change = last.get(str(row.pk)) if row else None
        result.append({
            "key": spec.key, "title": spec.title, "when": (row.note if row and row.note else note), "editable": spec.editable,
            "subject": row.subject if row else default_subject, "default_subject": default_subject,
            "subject_changed": bool(row and row.subject != default_subject), "body_changed": bool(row and row.body.strip()),
            "last_edited_at": change.created_at if change else None, "last_edited_by": change.user_label if change else "",
        })
    return result


class TemplateForm(VersionedForm):
    """Subject and wording of one automatic email. Unknown placeholders and a missing {button} are field errors. A body equal to
    the built-in default is stored blank, so the email keeps following the default."""

    class Meta:
        model = NotificationTemplate
        fields = ["subject", "body"]

    def __init__(self, *args, spec, **kwargs):
        self.spec = spec
        super().__init__(*args, **kwargs)
        if not spec.editable:
            del self.fields["body"]
        else:
            self.fields["body"].required = False
            if not self.is_bound:
                self.initial["body"] = self.instance.body or spec.default_body  # the editor shows what is sent

    def clean_body(self):
        text = (self.cleaned_data.get("body") or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        return "" if text == self.spec.default_body.strip() else text

    def clean(self):
        data = super().clean()
        errors = emailbody.validate(self.spec, subject=data.get("subject"), body=data.get("body") if "body" in self.fields else None)
        for name, messages in errors.items():
            for message in messages:
                self.add_error(name, message)
        return data


def edit_context(spec, form, row):
    default_subject = DEFAULT_SUBJECTS[spec.key][0]
    return {
        "spec": spec_info(spec), "form": form, "row": row, "default_subject": default_subject,
        "default_body": spec.default_body, "is_default": not ((row.subject != default_subject) or row.body.strip()),
        "risky_fields": [],
    }


# ---------- mailings ----------

class MailingForm(forms.ModelForm):
    """A draft mailing. The group's options (plan, dates, status) come in as plain fields named after them."""

    class Meta:
        model = Mailing
        fields = ["name", "subject", "body", "kind", "group"]

    def clean(self):
        data = super().clean()
        errors = emailbody.validate(emailbody.SPECS["mailing"], subject=data.get("subject"), body=data.get("body"))
        for name, messages in errors.items():
            for message in messages:
                self.add_error(name, message)
        if data.get("group"):
            self.params, group_errors = segments.clean_params(data["group"], self.data)
            for name, messages in group_errors.items():
                for message in messages:
                    self.add_error(name if name in self.fields else None, message)
        return data

    def save(self, commit=True):
        self.instance.params = getattr(self, "params", {})
        return super().save(commit)


def mailing_extra(kind, group_key):
    """Footer context for a preview or test of a mailing: the sample unsubscribe link (News) or the 'why you get this' line (Service)."""
    from mailings import tokens
    from mailings.sending import NEWS_NOTICE

    if kind == Mailing.NEWS:
        return {"unsubscribe_url": tokens.unsubscribe_url("james@example.com"), "notice": NEWS_NOTICE}
    group = segments.GROUPS.get(group_key)
    return {"notice": f"You are receiving this message {group.reason if group else segments.REASON_ACCOUNT}."}


def parse_when(text):
    """A local date and time typed in a datetime-local box -> an aware datetime (UK time), or None."""
    text = (text or "").strip()
    for fmt in SCHEDULE_FORMATS:
        try:
            return timezone.make_aware(datetime.datetime.strptime(text, fmt))
        except ValueError:
            continue
    return None


def mailing_recipients(mailing, status="", page=1):
    qs = mailing.recipients.all()
    if status:
        qs = qs.filter(status=status)
    return Paginator(qs.order_by("email"), PAGE).get_page(page)


def mailing_list(page=1):
    return Paginator(Mailing.objects.all(), PAGE).get_page(page)


# ---------- invites ----------

def invite_batches():
    """One line per import: when, who, and how many invites in each state."""
    from django.db.models import Count, Max, Min, Q

    rows = Invite.objects.values("batch_id").annotate(
        created=Min("created_at"), last=Max("updated_at"), total=Count("pk"),
        **{status: Count("pk", filter=Q(status=status)) for status, _ in Invite.STATUS_CHOICES}).order_by("-created")
    rows = list(rows[:200])
    people = {}
    for batch_id, email in Invite.objects.filter(batch_id__in=[r["batch_id"] for r in rows]).values_list("batch_id", "created_by__email"):
        people.setdefault(batch_id, email or "")
    return [{**row, "by": people.get(row["batch_id"], "")} for row in rows]


def invite_page(batch_id, status="", page=1):
    qs = Invite.objects.filter(batch_id=batch_id)
    if status:
        qs = qs.filter(status=status)
    return Paginator(qs.order_by("email"), PAGE).get_page(page)
