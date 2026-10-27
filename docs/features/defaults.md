# Defaults page (System) — inventory, waiting for Moishe

Decided 2026-10-27: every default visible in System on one tidy **Defaults** page, grouped by area. This is the inventory (170 defaults found). Not built yet. Moishe marks what should be editable before the build.

Key: **E** editable · **RO** shown read-only (security, infra, abuse protection) · **Code** too technical, stays in code (not shown).
28 defaults are already editable on other System pages (Settings, Hours, Plans, Gold rules, Journey, Emails, Approval). The Defaults page links to them instead of copying them.

## Proposed editable (new) — 33

### Office
| Default | Now |
|---|---|
| Leads: last seen range | 30 days |
| Leads: show | All |
| Leads: sort | Last seen |
| Leads: rows per page | 25 |
| People and Gold lists: rows per page | 50 |
| Gold list: default status | Waiting |
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
| "Booking is open" email | Off (no System switch yet) |
| Spa address | BML House, 99c Vale Road, London N4 1PR (no System field yet) |
| New visit counted after | 30 minutes away |
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
| Group send speed | 10 a second (never above the provider limit) |
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

### Control (parked)
| Default | Now |
|---|---|
| Picture time on screen | 8 seconds |

## Proposed read-only (shown, not editable) — 73
Grouped on the page with a one-line reason each. Main ones:
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
