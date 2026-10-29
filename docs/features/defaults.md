# Defaults page (System) — agreed list (Moishe, 2026-10-27)

Decided 2026-10-27: every default visible in System on one tidy **Defaults** page, grouped by area. This is the inventory (170 defaults found). **Built 2026-10-27** (branch `feature/defaults`).

Only editable defaults are shown (Moishe, 2026-10-27). A range default is the choice pre-selected when a page opens; the list of choices stays fixed.
28 defaults are already editable on other System pages (Settings, Hours, Plans, Gold rules, Journey, Emails, Approval). The Defaults page links to them instead of copying them.

## Built (2026-10-27)

**Model.** `system.SiteDefaults` (singleton, `load()`, django-simple-history, section "Defaults" in the change log). A separate model from `plans.SiteSettings` so Settings stays the small page of switches; this one is plain numbers and pre-selected choices. The row is made on first read (no data migration); until then, and for every field, the value is today's code value (the field default, shown as the "Default: ..." hint and restored by "Reset to default"). Migrations `system.0011` and `mailings.0003` (help text only). Read with `system.defaults.get(request)` (one read per request, kept on the request) or `get()` without a request. Range, show and sort choices are checked in `SiteDefaults.clean()` against the constants of `office.leads` / `office.selectors` (never copied); numbers carry min and max validators.

**Page.** System > Defaults (`/defaults/`, `POST /defaults/reset/`; Developer level behind the unlock, `system/views_defaults.py`, `forms_defaults.py`). One form, groups Office, Website and journey, Gold, Emails, Sign-in, System, Notifications; each row shows the value, a one-line "Default: ..." hint and a per-row "Reset to default" (a logged change). Saves and resets go through `services.save_form` / `save_logged`: change log, audit, undo as on Settings. The five link and sign-in lengths ask for confirmation (risky). No per-group reset and no "Rules as code" view for this page.

**Where each is read.**
| Default | Read in |
|---|---|
| Leads range / show / sort | `office.leads.filters_from` and `is_filtered` (same values; `data-default` of the filter controls in `leads.html`) |
| Leads rows | `office.leads.page` (view passes it) |
| People and Gold rows | `office.lists.cut` (`people_page`, `gold_page`) |
| Dashboard / Analytics range | `office.views` (`_remembered_range`, JSON endpoints), `office.selectors` fallbacks |
| Hot leads, activity, Gold waiting, latest registrations | `office.selectors.dashboard` (LIMIT reads) |
| Options per question, top pages | `office.selectors.build_analytics` / `build_pages`: stored in the snapshots, so a change shows at the next refresh (saving either one asks for a refresh) |
| Timeline events, emails shown | `office.leads.timeline_page`, `office.profile.timeline` |
| Result reasons, Gold nudge | `journey.engine._reasons`, `gold_presentation` |
| Opener lines | `pages.services.opener_lines`; `spa.html` now loops over the lines |
| Gold invite days | `gold.invites` (stamped on the `GoldInvite` row when made; the signed token only has an outer cap of 91 days, so the row decides) |
| Approve / final approval days | `gold.approval` (signed links with no stored date: read when checked) |
| Register invite days | `mailings.models.Invite.save` and `mailings.invites.create_batch` (stamped on the row) |
| Recent mailings / batches | `system.emails.overview` |
| Office sign-in | `users.views.LoginView.form_valid` (at sign-in) |
| Email confirmation | `users.tokens.read_verify_token` (read when checked) |
| Change log / audit feed rows, dashboard recent changes | `system.services.change_list`, `system.feed.audit_feed` / `page_of`, `system.views.dashboard` |
| Notifications | `{% toast_times %}` in `common/_messages.html` puts `data-toast-ms` and `data-toast-long-ms` on the toast region (every host); `feedback.js` reads them; errors still stay |

**Link validity.** Gold invite and register invite lengths are stamped on each row when it is made, so a new value applies to links made from now on and never cuts off a link already sent. Approve, final approval and email confirmation links carry no stored date, so a new value applies to links already sent too. Removed: `settings.OFFICE_SESSION_AGE`, `settings.EMAIL_VERIFY_MAX_AGE`. Email wording follows the Defaults: the placeholder `{valid_for}` (plain words: "24 hours", "1 day", "14 days") is in the Confirm your email, Gold approved and Invitation to register emails, filled at send time and in previews and test sends. Confirmation uses the current hours; Gold invite and register invite use the length stamped on the link's row (a link already sent keeps its words), falling back to the Defaults value. The older `{valid_days}` (number only) still works in edited wording. Default bodies are blank in the database (they follow the built-in text), so no backfill is needed; a body edited by hand keeps its own words. Password reset and team invite stay fixed at one hour. The invalid-link page shows the real number of days.

Referrers on the Analytics pages stay fixed at 10 (only Top pages is a default). Office sign-in is capped at 1 to 30 days so the privacy notice ("up to 30 days") stays true. The privacy notice's Gold invite length and the Register page's "It works for ..." line fill from the Defaults through `{gold_invite_days}` and `{confirm_for}` in new seeds; rows already stored (edited in Control or seeded before) keep their old words until edited. If `SiteDefaults` cannot be read (table missing before migrate, database blip) `load()` logs once and returns the code defaults.

## Editable (agreed 2026-10-27)

### Office
| Default | Now |
|---|---|
| Leads: last seen range | 30 days |
| Leads: show | All |
| Leads: sort | Last seen |
| Leads: rows per page | 25 |
| People and Gold lists: rows per page | 50 |
| Dashboard: default range | 7 days |
| Analytics: default range | 30 days |
| Dashboard: hot leads shown | 5 |
| Dashboard: activity shown | 10 |
| Dashboard: Gold waiting shown | 5 |
| Dashboard: latest registrations shown | 5 |
| Analytics: options shown per question | 6 |
| Top pages shown | 10 |
| Person page: timeline events per page | 20 |
| Person page: emails shown | 50 |

### Website and journey
| Default | Now |
|---|---|
| Result: reasons shown | 3 |
| Gold nudge by potential | High: panel · Medium: line · Low: none |
| Home opener: lines shown | 1 |

### Gold
| Default | Now |
|---|---|
| Gold invite link valid | 14 days |
| Approve / final approval email link valid | 14 days |

### Emails
| Default | Now |
|---|---|
| Register invite link valid | 30 days |
| Invitation link goes to (`invite_landing`; hint "Where the button in 'Invitation to register' takes people.") | The questionnaire (or Register). Also picks the invitation button text: "Find my membership" / "Register for Spa 99" |
| Recent mailings / invite batches shown | 5 / 5 |

### Sign-in
| Default | Now |
|---|---|
| Office sign-in lasts | 30 days |
| Email confirmation link valid | 24 hours |

### System
| Default | Now |
|---|---|
| Change log rows per page | 50 |
| Audit feed rows per page | 25 |
| Dashboard recent changes | 10 |

### Notifications (all staff sites)
| Default | Now |
|---|---|
| On-screen notification stays | 4 seconds (6 with a button; errors stay until closed) |

## Not shown (Moishe, 2026-10-27: no read-only section) — 73
These stay in code and are not on the page:
- **Abuse protection:** every rate limit (sign-in 10 per 5 min, registrations 20 an hour, Gold 10 an hour, journey and email limits, System code tries).
- **Security:** password rules (min 10), reset link 1 hour, public sign-in 2 weeks, HTTPS/CSRF/HSTS, secret key, System code, hidden admin path (values never shown, only "set" / "not set").
- **Legal and rules:** minimum age 18, UK mobiles only, journey cookie 1 year, privacy notice version, hot-lead definition, spa day 5am to 3am, audit retention.
- **Infrastructure:** domains and hosts, database, media storage, email provider, workers, timeouts, time zone, Sentry, upload sizes, job schedules.
- **Health thresholds:** snapshot "stale" after 15 min, failed tasks window 24 h.

## Stays in code (not shown) — 36
Validation lengths, duplicate-submit windows, queue and retry internals, UI timings (toasts, debounce), parser limits, demo values.

## Notes for the build
- The Leads defaults appear twice in `office/leads.py` (filters and "is filtered"); both must read the same setting.
- Lock idle minutes and longest System sign-in already live in Settings, with env fallbacks.
- `notify_booking_open`, the address fields and `privacy_version` have no System form today (admin only).
- Only the audit log has a retention setting; other data has none (see the clean-up jobs item in PROJECT.md).

## Payments group (2026-10-29)
`payment_window_days` (14, 3 to 60), `payment_reminder_days_before` (3, 1 to 30), `payment_staff_alert_days_before` (7, 1 to 60), `staff_alert_emails` (comma separated, up to 5, empty in code; `seed_phase1` fills it once while empty; empty shows "No alert email set" here and on System > Payments). Reset to default restores the code values.

`payment_staff_alert_hour` (9, 0 to 23; added 2026-10-29): the earliest London hour the daily staff warning goes out (was a code constant `ALERT_HOUR`).
