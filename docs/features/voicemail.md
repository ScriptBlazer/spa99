# Voicemail emails (020 4538 4999)

Status: **server side built on `feature/voicemail-email`, not released** (2026-11-19). Frontend styling and a live Twilio test come next. Moishe chose A (our site + Postmark). Main want: listen in the Office. Branch `feature/voicemail-email`.

**2026-11-23:** Moishe moves the number to our site (`/phone/voice/`), with Sam's function as the fallback. Live and tested the same day. See PROJECT.md.

## The request (from Sam, 2026-11-19)

When someone leaves a voicemail, email it with the recording attached as an MP3, plus the caller's number and the time. No transcription. Every voicemail gets an email, however short.

## How it works today (checked in Twilio, account "BML Empire")

- The number +442045384999 ("Spa 99 Official") is a voice-only number. Incoming calls go to the Twilio Function `https://spa99-call-forward-1292-prod.twil.io/voice` (service "Spa 99 call forward", `ZS4c81f7bda275a996aa341d189aa570bd`). There is no backup webhook and no call status callback.
- `/voice`: Polly.Amy (en-GB) says the greeting, then `<Record maxLength=120 playBeep transcribe>` with `transcribeCallback` set to `https://twimlets.com/voicemail?Email=hello%40spa99.uk`, then "Thank you. Goodbye."
- The greeting says: "Hello, and thank you for calling Spa 99. The quickest way to reach us is on WhatsApp, on this same number. Or leave your name and phone number after the tone, and we will get back to you as soon as we can."
- `/forward` (calls 07530 117902 with a `/whisper` "Incoming call from Spa 99.") and `/whisper` exist, but the number does not use them. Nobody's phone rings.
- The service was created through the API, so it is **read-only** in the Console. Changing it means a CLI or API redeploy.
- The service has no environment variables.
- The emails come from **Twimlets** (an old public Twilio helper), not from SES or Postmark.

## Why it fails

1. **The link gives 401.** The account requires HTTP auth on recording URLs ("Enforce HTTP Auth on Media URLs"), so the plain recording link in the Twimlets email cannot be opened. This setting covers the whole BML account. It stays on, and we don't touch it.
2. **Emails go missing.** Twimlets only emails after the transcription finishes, and Twilio does not transcribe very short recordings. The Recording logs show voicemails of 1, 1, 3 and 6 seconds.
3. **Silence trimming.** Twilio's default `trim-silence` can leave a very short or silent message with no file at all (status `absent`).

## Ways to fix it (not chosen)

**A. Our site + Postmark.**
- Twilio tells the site when a recording is ready (`recordingStatusCallback`, including `absent`, with `trim="do-not-trim"`).
- The site checks Twilio's signature, downloads the MP3 with a Spa 99 API key, and emails it through Postmark (spa99.co.uk is set up there).
- No AWS keys anywhere. A row per voicemail allows a retry and a later Office list.
- Needs Twilio credentials back in the server `.env`.
- If the site is down, the email waits or is missed, but the recording stays in Twilio.

**B. Twilio Function + SES (Sam's suggestion).**
- A new Twilio Function emails the MP3 through SES.
- It works even if the site is down.
- Needs an AWS key stored in Twilio, and a CLI redeploy for every change. The code lives outside our repo.

## Decided (2026-11-19, Moishe)

- **Our site + Postmark.** No AWS keys anywhere. Twimlets is removed.
- **Storage:** each MP3 is copied to our private S3 (about 1 MB for 2 minutes, so 1,000 voicemails is about 1 GB, pennies a month). Twilio keeps its copy too.
- **Office tab "Calls"** (renamed from "Voicemails"): two views on one page. "Voicemails" (default) lists calls that have a recording, with caller number, time, length and a player; "All calls" is the call log, and a hang-up before the beep shows as "No message". Anyone above Viewer (Office, Admin, Developer, Superuser) can see it. Sidebar badge = unheard voicemails.
- **Email:** sent From hello@spa99.co.uk through Postmark. It says there is a new voicemail, with a link to it in the Office. **No MP3 attached.**
- **Old voicemails:** a one-off import script (separate from migrations, dry run first) brings in the existing recordings. It reads only calls to +442045384999, never BML's. It copies the MP3s to S3 and sends no emails. Safe to run twice.
- **Recipients:** an editable list in System → Emails, starting with hello@spa99.co.uk.
- **Greeting:** stays exactly as it is, with the WhatsApp line (Moishe, superseding the tech lead call).
- **Office tab "Calls":** two views. **Voicemails** (default) and **All calls** (call log). A hang-up before the beep shows only in All calls as "No message", with no email. The badge counts unheard voicemails.

## Open points (older, some answered above)

- The greeting still mentions WhatsApp on this number. The WhatsApp chat was removed on 2026-11-05. Is anyone reading WhatsApp messages there?
- Who should get the email: hello@spa99.co.uk, or someone else?
- Should the greeting be served from our site, with Sam's function kept as the backup?
- Should a caller who hangs up before the beep get a "missed call" email too?
- Keep recordings in Twilio, or delete them once the email is sent?

Sources: Twilio `<Record>` docs (twilio.com/docs/voice/twiml/record), Twilio error 17553, the Twilio changelog on enforcing HTTP auth for media.


## Built (2026-11-19, app `phone`)

**Model** `phone.Call` (one row per call to the number; `kind` voicemail or missed, shown as "No message"; `source` live or import). Audio is a file on the private media storage (S3 `prod/` on live) at `voicemails/YYYY/MM/YYYY-MM-DD_HH-MM_<caller>.mp3`, London time, caller = national digits of a UK number (`07368912320`), `00` + digits for a foreign number, `unknown` when withheld or masked; a clash gets `_2`, `_3`. No SIDs or random text in the name (`phone/naming.py`). Processing fields: `audio_saved_at`, `emailed_at`, `email_skipped`, `last_error`, `attempts`, `next_attempt_at`, `claimed_until`; `heard_at`/`heard_by` for the first staff play. Read-only in the Django admin.

**Public host, Twilio webhooks** (POST only, CSRF exempt, `X-Twilio-Signature` checked against `SITE_URL` + path, our own account only, 300 a minute rate limit; 503 when Twilio is not configured, so Twilio uses the fallback):
- `/phone/voice/`: makes the Call row (once per CallSid), answers TwiML: Polly.Amy greeting (one constant, `phone/twiml.py`), `<Record maxLength="120" playBeep trim="do-not-trim">` with `action` = `/phone/after-record/` and `recordingStatusCallback` = `/phone/recording/` (events `completed absent`). No transcription.
- `/phone/after-record/`: "Thank you. Goodbye." then `<Hangup/>`.
- `/phone/recording/`: sets the recording, duration, kind = voicemail (so a late callback is never "No message" for ever); `absent` = a voicemail with no sound (0 seconds, so it counts as a short one below: hidden and not emailed). Queues `phone.tasks.process` once, answers 204.

**Processing** (`phone/services.py`, `phone.tasks.process`): download `Recordings/<sid>.mp3` with the API key, save to storage, then email once. Schedule `voicemail-sweep` (every 5 minutes, `register_schedules`) retries rows still waiting.

**Email** (`voicemail_new`, editable under System > Emails > Automatic): From the site address, no attachment, subject "New voicemail from 07368 912320", body with caller, London time, length and a button to `<OFFICE_URL>/calls/<id>/`. Goes to the new list **System > Emails > Voicemail email to** (`SiteSettings.voicemail_email_to`; new installs get the address inside `DEFAULT_FROM_EMAIL`; the column has `db_default=""` for safe rollback, so an existing database starts blank until `python manage.py set_voicemail_recipients` (dry run first, fills only a blank, a script not a migration) is run on deploy; audited in System changes). Empty list = skipped and recorded in `last_error`. Suppressed addresses are skipped by the normal send path. Calls with no message, imported rows and voicemails under 3 seconds are never emailed (a short one records "Shorter than 3 seconds: no email sent." in `last_error`).

**Office** (`config.urls_office`, any level above Viewer, a Viewer gets 403): `/calls/` (Voicemails) and `/calls/?view=all` (All calls), `/calls/<id>/`, `/calls/<id>/audio/` (on S3 a redirect to a 5 minute signed link; locally the bytes, with Range), `POST /calls/<id>/heard/` (first real play only; the player sends it on `playing`). Caller number is matched to a lead (journey email step), Gold applicant or registered person by stored mobile (three reads per page, the strongest match wins). Voicemails with no sound are never "New" and never in the badge; opening one marks it heard. **Short voicemails** (under 3 seconds, `services.SHORT_SECONDS`, no-sound ones included) are left out of the Voicemails view and its count. A small link on top, "N short voicemails (under 3 seconds) →", opens their own page (`/calls/?view=short`, with only "← Back to real voicemails"; a refresh stays on that page). They are left out of the badge. All calls still lists every call. **Phone card**: always a fixed 2x2 grid: number (and matched person) top left, New top right, date and time under it on the left, length on the right, then the player full width. The badge and the list counts are capped reads (no COUNT on a source table).

**Env vars** (all optional; blank = off, startup line shows `phone=off`): `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` (signature check only), `TWILIO_API_KEY_SID`, `TWILIO_API_KEY_SECRET` (download and import, GET only), `PHONE_NUMBER` (default +442045384999).

**Import** `python manage.py import_twilio_voicemails` (not a migration). Dry run is the default (reads from Twilio, prints, writes nothing; numbers shown as `***` + last 3 digits). `--apply` writes. `--limit N` (default 500), `--mark-heard` (off by default: marks the imported voicemails heard, by nobody, so the badge does not jump to the whole backlog) caps the calls looked at. Only calls TO the number, only recordings with Source RecordVerb, new rows are `source=import`, audio copied to storage, no emails ever, calls already imported are skipped (safe to run twice), calls with no recording come in as "No message".

**The Twilio URL must match `SITE_URL` exactly.** Twilio signs the URL it called; we check the signature against `SITE_URL` + `/phone/voice/`. If the site's domain changes (the move from spa99.uk to spa99.co.uk on Saturday 21 November 2026), change the number's "A call comes in" URL in Twilio at the same moment `SITE_URL` changes. If they differ, every call fails the signature check (logged at error level, so Sentry sees it) and Twilio quietly uses the fallback function, so voicemails stop arriving in the site until the URL is fixed.

**What Moishe sets in Twilio** (this number only, Console > Phone Numbers > Manage > Active numbers > the Spa 99 number > Voice Configuration): "A call comes in" = Webhook, `https://<site>/phone/voice/`, HTTP POST. "Primary handler fails" (fallback) = Webhook `https://spa99-call-forward-1292-prod.twil.io/voice` (Sam's function, kept as the backup). Twimlets is no longer used. Cloudflare Bot Fight Mode must stay off (it blocks Twilio).

**Privacy (UK GDPR).** A call row holds a phone number and a recording of someone's voice. Rows are matched to a person only by number at view time, so the person erasure/export code does not touch them and nothing is wired automatically. The Django admin lets Moishe see and search calls but is read-only, so to erase a caller's voicemail a Developer deletes the row in the shell (`Call.objects.filter(from_number=...)`) and the audio file with it. Twilio keeps its own copy (recordings are never deleted by us); delete those in the Twilio Console. Decision still needed from Moishe whether to wire erasure and add a retention period.

## Listen locally (import on a Mac)

The import and the player work with the local media storage too. Put the four `TWILIO_*` keys in the private `.env` (the auth token is not needed: it is only for the webhooks, which stay off, `phone=off`). Then:

```bash
python manage.py migrate
python manage.py import_twilio_voicemails            # dry run, prints counts
python manage.py import_twilio_voicemails --apply    # writes rows and copies the MP3s (add --mark-heard to keep the badge at 0)
python manage.py runserver                           # sign in on http://office.localhost:8000/calls/
```

The files land in the private media folder (`media/` in the private folder, or `.private/media/` as the fallback) at the same tidy path, `voicemails/YYYY/MM/YYYY-MM-DD_HH-MM_<caller>.mp3`; the player streams them from disk. Run the import again whenever you like: it reads newest calls first and skips any it already has, so only new calls are added. (A local copy is its own database: it does not share rows with live.) If `TWILIO_AUTH_TOKEN` is also in the local `.env`, the startup line shows `phone=on`; that is fine, Twilio cannot reach the Mac so no webhook ever arrives.

## Cost safety (Moishe's rule: nothing here can run up the Twilio bill)

- **GET only.** All Twilio HTTP is in `phone/twilio_api.py`. `_send` refuses every method except GET, and `get` refuses any path outside this account's call list, one call's recordings list and one recording's MP3. Nothing can create a call, message or transcription. Tests prove it.
- **No transcription**, and no `<Redirect>`, `<Dial>` or second `<Record>` in any TwiML. The Record has an explicit `action` that says goodbye and hangs up, `maxLength` 120. A test checks the shapes.
- **Every retry is capped.** Each processing run counts an attempt; at 8 it stops for good and `last_error` shows why. Backoff between tries: 5, 10, 20, 40, 80, 160, 320 minutes. The sweep handles at most 10 rows a run, takes no new row after 90 seconds (django-q stops a task at 120), and skips rows that are backing off, claimed or out of attempts. Nothing re-queues itself: the task never raises and never calls `async_task`.
- **django-q** `Q_CLUSTER` has `max_attempts` 3 and `retry` above `timeout`; our task returns a status instead of raising, so django-q has nothing to retry.
- **Webhooks are signed, rate limited (300 a minute) and idempotent.** A retry storm from Twilio makes no second row, no second queued job and no second email (`emailed_at` is claimed with one conditional update before sending, and given back only if the send failed).
- **Import**: GET only, only calls `To` the number, at most `--limit` calls (default 500, ceiling 5000) and the pages to cover them, dry run by default.
- Redirects when downloading are followed at most 3 times, https only, and the API key is sent to api.twilio.com only. Downloads have a 20 second timeout and a 30 MB cap.
