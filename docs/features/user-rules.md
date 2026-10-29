# User rules (the rule book)

Decided by Moishe 2026-10-23 (PROJECT.md). This replaces the old Owner / Manager / Viewer roles. Every view checks these rules on the server; hiding a button is never the only guard.

## U1. Who exists

| Type | What it is |
|---|---|
| **Visitor** | Not signed in. The public website, the journey, registering, the Gold application, the tour |
| **Member** | A person with a membership (registered for a tier, later a paid plan). The website plus the member area (`/account/`) |
| **Gold member** | A member whose membership is Gold (approved application). Same member area; Gold cannot be changed there |
| **Team** | People who work on Spa 99, at one of four levels (U2). Being on the team never makes you a member |

One login per person (the email address). The same login can be a team member and a member at once: member access comes only from holding a membership. If someone already has two accounts, a Developer merges them in System (logged).

## U2. Team levels (each level includes everything of the levels below it)

| Level | Office | Control (building) | System | Hidden Django admin | Member area |
|---|---|---|---|---|---|
| **Office** | View only | ✗ | ✗ | ✗ | only with a membership |
| **Admin** | View and act | ✓ | ✗ | ✗ | only with a membership |
| **Developer** | View and act | ✓ | ✓ (password + code) | ✗ | only with a membership |
| **Superuser** | Everything | ✓ | ✓ (password + code) | ✓ | ✓ always (an empty membership if none) |

Two extra permissions sit on top of a level (set in **System > Approval**, shown read only on Team; 2026-10-25):

- **Approver**: may approve, decline and resend Gold applications, and gets the email for each one. Office level or higher (e.g. Barry = Office + Approver).
- **Final approver**: may confirm or send back a Gold application that an approver approved with Low potential (it cannot decline). **Admin level or higher only** (Admin, Developer, Superuser), never Office. Guard: `common.levels.can_hold_final_approver`.

Each person's approval emails go to their account email, or to another address chosen in System > Approval.

## U3. What "act" means in the Office

| Action | Office | Admin | Developer | Superuser |
|---|---|---|---|---|
| See dashboard, analytics, people, Gold | ✓ | ✓ | ✓ | ✓ |
| Approve / decline / resend Gold | only with Approver | only with Approver | only with Approver | ✓ |
| Confirm / send back a Low potential approval (final approval; cannot decline) | ✗ (never) | only with Final approver | only with Final approver | ✓ (emailed only if they hold the role) |
| Export members (CSV, a person's data) | ✗ | ✓ | ✓ | ✓ |
| Delete a member | ✗ | ✓ | ✓ | ✓ |

## U4. Managing the team

- Only **Developers and the superuser** add team members and set levels, in **System > Team** (behind the System unlock, every change in the audit log).
- Adding someone: email and level (Approver and Final approver are not asked here; they are set in **System > Approval**, and Team shows them as read-only labels). They get an email to set their own password; nobody types a password for someone else.
- **System > Approval** (Developer level, behind the unlock) adds and removes Approvers and Final approvers and sets where their emails go. It follows the same `can_manage` guard as Team (never yourself, strictly below you, a superuser may change another superuser), with one addition: a superuser may set their own approval roles (it adds no power; it only decides who is emailed). Changing a level in Team keeps these roles, except that a level below Admin drops Final approver and removing someone from the team drops both. Every change is in the audit log (`role_changed`).
- **Nobody can delete or edit someone higher than them**, and below superuser nobody can delete or edit someone at their own level either. A Developer can change Office and Admin people; only a superuser can change a Developer. **Superusers are the exception: a superuser can delete or edit another superuser** (so a lost or departed superuser can always be removed).
- Nobody can remove their own access or deactivate themselves.

## U5. Sign-in

- Members sign in on the website and land in the member area. Team members sign in on their own address (Office, Control, System) and land on its home page. System sign-in is at `/dev-login/` (the old `/login/` is a plain 404), and System then asks only for the lock code. Wrong tries on the System sign-in and unlock show the tries left; 6 wrong in a row wait 1 minute, then each further wrong try adds a minute (cap 60), with a live countdown.
- Office sign-in lasts 30 days. System locks after the set idle minutes (default 15) and ends after the set hours (default 12). Member sign-in lasts 2 weeks.
- No access = a plain "not found" (staff addresses never admit what is there).

## Payment window actions (2026-10-29)
Admin and above (Office person page, audited): set up a membership manually (edit, cancel), restore a lapsed sale price (reason required). Developer (System, unlocked): open, schedule, cancel the schedule and close payments; Defaults. Office level can see the sale and payment state, not change it.
