# WhatsApp in the Office: replaced (2026-11-05)

The in-Office WhatsApp chat (Twilio, templates, media, voice notes, push, System > WhatsApp) was **removed in Office 2** and is kept only on the branch `archive/whatsapp-chat`. Spec of what replaced it: `docs/features/office-2.md` ("Built").

What the Office does now:
- **The WhatsApp button is a plain link** to `https://wa.me/<digits>` on lead, person and Gold pages. With no mobile there is no button: Email fills the row, a muted line says "Add a number to WhatsApp him." (or "No mobile on file." for a reader), and the Details row has the one Add.
- **Barry WhatsApps from his own phone.** The site's WhatsApp number (System > Settings) is the old number; nothing answers the 020 number any more (Moishe accepts this).
- **A wa.me click proves nothing**, so it never marks a Gold application Contacted. An email sent from the pop-up still does, and there is a "Mark contacted" button.
- **Kept:** the Office as an installable app (manifest and a service worker with no push, in `office`), `common/phone.py`, the mobile on leads, people and Gold with its Details row and `PersonEdit` audit, the site's counted WhatsApp short link (`/whatsapp/`) and its System dashboard figures, and the consent tick "Spa 99 may email and WhatsApp me" (still true: Barry WhatsApps people from his phone).
- **Gone:** the chat, templates, media, voice notes and ffmpeg, web push and VAPID, the Twilio webhooks and settings, the Office WhatsApp tab and badge, the Notifications row of the person menu, `common/ownership.py` and `common/polling.py`, the Office `Permissions-Policy: microphone=(self)` (every host now says `microphone=()`), and the Office upload limit (Caddy now allows 6 MB, down from 20 MB: the Office pages take no files, only the Django admin does, up to 5 MB).
- **Database:** `common 0003_drop_whatsapp_tables` drops the six `whatsapp_*` tables (and the app's `django_migrations` rows) on live, and does nothing on a fresh database. Not reversible: the chats come back only from the RDS snapshot (see `docs/GO-LIVE.md`, "Office 2").

`whatsapp-design.md` is superseded for the chat parts; its Details rows and reach out buttons sections describe what was kept, with the button now a link.
