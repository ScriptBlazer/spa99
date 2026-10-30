"""System > Emails: the logic behind the pages (views stay short). Overview figures, the automatic emails, mailing and invite pages.

Everything here reads stored rows or cheap counts (EmailLog has an index on created_at; suppressions are a small table)."""
import datetime

from django import forms
from django.core.paginator import Paginator
from django.utils import timezone

from mailings import blocks as mailing_blocks, segments
from mailings.models import ContactList, EmailOptOut, Invite, Mailing
from notifications import emailbody, ses
from notifications.models import EmailBounce, EmailLog, EmailSuppression, NotificationTemplate
from notifications.seed import DEFAULT_SUBJECTS

from . import defaults
from .forms import VersionedForm
from .models import SystemChange

EMAIL_MODEL = "notifications.notificationtemplate"
PAGE = 50
SCHEDULE_FORMATS = ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S")


# ---------- overview ----------

def overview(request=None):
    """Context for /emails/: the SES state and cheap counts."""
    now = timezone.now()
    today = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    week = now - datetime.timedelta(days=7)
    sent = EmailLog.objects.filter(status=EmailLog.SENT)
    d = defaults.get(request)
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
        "recent_mailings": list(Mailing.objects.all()[:d.recent_mailings]),
        "recent_invite_batches": invite_batches()[:d.recent_batches],
    }


# ---------- bounces ----------

def bounces_week():
    """Bounces and complaints logged in the last 7 days (indexed on received_at)."""
    return EmailBounce.objects.filter(received_at__gte=timezone.now() - datetime.timedelta(days=7)).count()


def bounce_rows(kind=""):
    """The latest 500 bounce records (optionally one kind), each with `suppressed` (the address is on the suppression list; one query)."""
    found = EmailBounce.objects.all()
    if kind in dict(EmailBounce.KIND_CHOICES):
        found = found.filter(kind=kind)
    rows = list(found[:500])
    suppressed = set(EmailSuppression.objects.filter(email__in={r.email for r in rows}).values_list("email", flat=True))
    for row in rows:
        row.suppressed = row.email in suppressed
    return rows


# ---------- automatic emails ----------

def spec_info(spec):
    """One email's placeholders and samples, for the edit screen."""
    return {
        "key": spec.key, "title": spec.title, "editable": spec.editable, "has_button": bool(spec.button_label),
        "button_required": spec.button_required, "button_label": emailbody.button_label_for(spec),
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

    block_errors = None  # {"_": [...], "<index>": {field: [...]}} for the parts, when parts were posted

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["body"].required = False

    def clean_kind(self):
        kind = self.cleaned_data["kind"]
        parts, _ = mailing_blocks._parse(self.data.get("blocks")) if "blocks" in self.data else (None, None)
        if kind == Mailing.INVITATION and not (self.instance and self.instance.automatic_key) and not mailing_blocks.has_personal(parts):
            raise forms.ValidationError("Choose News or Service message. An invitation is sent from the Invitation to register email, or from a mailing with a personal-link button.")
        return kind

    def clean(self):
        data = super().clean()
        # Parts (the `blocks` field, JSON) win over the old body. A form without the field is the old plain-body form.
        if "blocks" in self.data:
            cleaned, self.block_errors = mailing_blocks.clean(self.data.get("blocks"))
            if self.block_errors:
                self.add_error(None, "Check the parts of the email: " + " ".join(mailing_blocks.flat_errors(self.block_errors)))
            self.cleaned_blocks = cleaned
            errors = emailbody.validate(emailbody.SPECS["mailing"], subject=data.get("subject"))
        else:
            errors = emailbody.validate(emailbody.SPECS["mailing"], subject=data.get("subject"), body=data.get("body"))
            if not (data.get("body") or "").strip():
                errors.setdefault("body", []).append("Write the message.")
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
        if "blocks" in self.data:
            self.instance.blocks, self.instance.body = self.cleaned_blocks, ""  # the parts replace the old body
        return super().save(commit)

    def errors_json(self):
        """{field: [messages]} for the script, with `blocks` as {"_": [...], "<index>": {field: [...]}}."""
        errors = {name: [str(m) for m in messages] for name, messages in self.errors.items() if name != "__all__"}
        if self.block_errors:
            errors["blocks"] = self.block_errors
        if "__all__" in self.errors and not self.block_errors:
            errors["_"] = [str(m) for m in self.errors["__all__"]]
        return errors


def editor_blocks(form, mailing, template=None):
    """The parts the editor starts with: what was posted (after a failed save), else the saved parts, else an old body turned into
    paragraphs, else the chosen saved template's parts, else nothing."""
    if form is not None and form.is_bound and "blocks" in form.data:
        parts, _ = mailing_blocks._parse(form.data.get("blocks"))
        return parts or []
    if mailing is not None:
        return mailing.blocks or mailing_blocks.from_body(mailing.body)
    return list(template.blocks) if template is not None else []


def mailing_extra(kind, group_key):
    """Footer context for a preview or test of a mailing: the sample unsubscribe link (News) or the 'why you get this' line (Service)."""
    from mailings import tokens
    from mailings.sending import INVITE_NOTICE, NEWS_NOTICE

    if kind in Mailing.MARKETING:
        return {"unsubscribe_url": tokens.unsubscribe_url("james@example.com"), "notice": INVITE_NOTICE if kind == Mailing.INVITATION else NEWS_NOTICE}
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


# ---------- groups and uploaded lists ----------

def lists_table():
    """Every uploaded list with its size, newest changes last (the Groups tab)."""
    from django.db.models import Count

    return ContactList.objects.select_related("created_by").annotate(people=Count("members")).order_by("name")


# ---------- past invite batches (read only) ----------

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
