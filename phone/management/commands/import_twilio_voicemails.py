"""One-off: bring the voicemails already in Twilio into the Calls list (docs/features/voicemail.md). Not a migration. Safe to run twice.

DRY RUN IS THE DEFAULT: it reads from Twilio (GET only) and prints what it would do, writing nothing. Add --apply to write.
Reads calls TO the Spa 99 number only (PHONE_NUMBER; the account is shared with BML), and for each new call its recordings made by the Record verb.
Creates rows with source "import", copies each MP3 to private storage, NEVER sends an email, NEVER changes or deletes anything in Twilio.
--mark-heard sets heard_at on the imported voicemails (heard_by stays empty) so the badge does not show the whole backlog as new.
Cost safety: GET only (phone.twilio_api refuses anything else), at most --limit calls per run (default 500) and the pages to cover them."""
from email.utils import parsedate_to_datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from phone import services, twilio_api
from phone.models import Call

PAGE_SIZE = 20


def mask(number):
    """Only the last 3 digits are ever printed."""
    digits = "".join(ch for ch in (number or "") if ch.isdigit())
    return "***" + digits[-3:] if digits else "(none)"


def parse_time(text):
    try:
        moment = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    return timezone.make_aware(moment) if timezone.is_naive(moment) else moment



def seconds(value):
    """Twilio's duration as whole seconds, never negative (it reports -1 when a recording has no length)."""
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


class Command(BaseCommand):
    help = "Import old voicemails from Twilio (this number's calls only). Dry run unless --apply."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show what would be done and change nothing (this is already the default).")
        parser.add_argument("--apply", action="store_true", help="Really import: create the rows and copy the audio.")
        parser.add_argument("--mark-heard", action="store_true", help="Mark the imported voicemails as heard (by nobody), so the sidebar badge does not jump to the whole backlog. Off by default.")
        parser.add_argument("--limit", type=int, default=500, help="Most calls to look at in one run (default 500).")

    def handle(self, *args, **options):
        apply = options["apply"] and not options["dry_run"]
        self.mark_heard = options["mark_heard"]
        limit = max(min(options["limit"], 5000), 1)
        if not twilio_api.configured():
            raise CommandError("Set TWILIO_ACCOUNT_SID, TWILIO_API_KEY_SID and TWILIO_API_KEY_SECRET first.")
        number = settings.PHONE_NUMBER
        self.stdout.write(f"{'IMPORTING' if apply else 'DRY RUN (nothing is written; add --apply to import)'}: calls to {number}, at most {limit}.")
        counts = dict.fromkeys(["looked_at", "already_there", "voicemails", "no_message", "other_recordings_skipped", "failed_audio"], 0)
        try:
            for call in self.calls(number, limit):
                counts["looked_at"] += 1
                self.one(call, apply, counts)
        except (twilio_api.TwilioError, twilio_api.Refused, OSError, ValueError) as error:
            # A failed or cut-off page: stop cleanly. What was imported stays; run again to carry on (already imported calls are skipped).
            self.stdout.write("Summary so far: " + ", ".join(f"{name.replace('_', ' ')} {value}" for name, value in counts.items()))
            raise CommandError(f"Stopped: could not read the call list from Twilio ({error}). Run again to carry on.")
        self.stdout.write("Summary: " + ", ".join(f"{name.replace('_', ' ')} {value}" for name, value in counts.items()))
        if counts["looked_at"] >= limit:
            self.stdout.write(f"Stopped at the limit of {limit}: run again (or raise --limit) for older calls; calls already imported are skipped.")

    def calls(self, number, limit):
        """Calls to the number, newest first, paged, never more than `limit`."""
        account = settings.TWILIO_ACCOUNT_SID
        path, params, seen = f"/2010-04-01/Accounts/{account}/Calls.json", {"To": number, "PageSize": PAGE_SIZE}, 0
        for _ in range(-(-limit // PAGE_SIZE) + 1):
            data = twilio_api.get_json(path, params)
            for call in data.get("calls", []):
                if call.get("to") != number:  # belt and braces: never touch a call that is not to this number
                    continue
                if seen >= limit:
                    return
                seen += 1
                yield call
            path, params = data.get("next_page_uri"), None
            if not path:
                return

    def one(self, call, apply, counts):
        sid = call.get("sid", "")
        if Call.objects.filter(call_sid=sid).exists():
            counts["already_there"] += 1
            return
        account = settings.TWILIO_ACCOUNT_SID
        recordings = twilio_api.get_json(f"/2010-04-01/Accounts/{account}/Calls/{sid}/Recordings.json").get("recordings", [])
        wanted = [r for r in recordings if r.get("source") == "RecordVerb" and r.get("status") in (Call.COMPLETED, Call.ABSENT)]
        counts["other_recordings_skipped"] += len(recordings) - len(wanted)
        wanted = [r for r in wanted if not Call.objects.filter(recording_sid=r.get("sid")).exists()][:1]  # one per call; a recording we already hold is not added twice
        received = parse_time(call.get("start_time")) or parse_time(call.get("date_created")) or timezone.now()
        recording = wanted[0] if wanted else None
        counts["voicemails" if recording else "no_message"] += 1
        self.stdout.write(f"  {received:%Y-%m-%d %H:%M} from {mask(call.get('from'))}: {'voicemail, ' + str(seconds(recording.get('duration'))) + ' s' if recording else 'no message'}")
        if not apply:
            return
        row = Call.objects.create(
            call_sid=sid, from_number=(call.get("from") or "")[:32], to_number=(call.get("to") or "")[:32], received_at=received, source=Call.IMPORT,
            kind=Call.VOICEMAIL if recording else Call.MISSED, recording_sid=recording.get("sid") if recording else None,
            recording_status=recording.get("status", "") if recording else "", duration_seconds=seconds(recording.get("duration")) if recording else 0)
        if self.mark_heard and row.kind == Call.VOICEMAIL:
            Call.objects.filter(pk=row.pk).update(heard_at=timezone.now())
        if row.audio_pending:
            services.process(row.pk)  # copies the audio; an import row is never emailed
            row.refresh_from_db()
            if not row.audio:
                counts["failed_audio"] += 1
                self.stdout.write(f"    audio not saved ({row.last_error}); the 5 minute sweep will try again, a few times")
