# Defaults page (System) — agreed list (Moishe, 2026-10-27)

Decided 2026-10-27: every default visible in System on one tidy **Defaults** page, grouped by area. This is the inventory (170 defaults found). Not built yet. Moishe marks what should be editable before the build.

Only editable defaults are shown (Moishe, 2026-10-27). A range default is the choice pre-selected when a page opens; the list of choices stays fixed.
28 defaults are already editable on other System pages (Settings, Hours, Plans, Gold rules, Journey, Emails, Approval). The Defaults page links to them instead of copying them.

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
