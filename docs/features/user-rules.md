# User rules (the rule book)

Decided by Moishe 2026-10-23 (PROJECT.md). This replaces the old Owner / Manager / Viewer roles. Every view checks these rules on the server; hiding a button is never the only guard.

## U1. Who exists

| Type | What it is |
|---|---|
| **Visitor** | Not signed in. The public website, the journey, registering, the Gold application, the tour |
| **Member** | A person with a membership (registered for a tier, later a paid plan). The website plus the member area (`/account/`) |
| **Gold member** | A member whose membership is Gold (approved application). Same member area; Gold cannot be changed there |
| **Team** | People who work on Spa 99, at one of five levels (U2). Being on the team never makes you a member |

One login per person (the email address). The same login can be a team member and a member at once: member access comes only from holding a membership. If someone already has two accounts, a Developer merges them in System (logged).

## U2. Team levels (each level includes everything of the levels below it)

| Level | Office | Control (building) | System | Hidden Django admin | Member area |
|---|---|---|---|---|---|
| **Viewer** (new, 2026-11-16) | Sees leads, people and Gold only. No action works | ✗ | ✗ | ✗ | only with a membership |
| **Office** | Viewer plus the everyday actions (U3) | ✗ | ✗ | ✗ | only with a membership |
| **Admin** | Office plus Revenue, Assistant chats, export, delete, payment setup | ✓ | ✗ | ✗ | only with a membership |
| **Developer** | Admin plus Activity | ✓ | ✓ (password + code) | ✗ | only with a membership |
| **Superuser** | Everything | ✓ | ✓ (password + code) | ✓ | ✓ always (an empty membership if none) |

Three extra permissions sit on top of a level (set in **System > Approval**, shown read only on Team; 2026-10-25, reshaped 2026-11-16). A **Viewer cannot hold any of them**:

- **Gold approver**: may approve, decline and resend Gold applications, and gets the email for each one. Office level or higher (e.g. Barry = Admin + Gold approver). This is the old "Approver"; the group is still named `Approver` in the database so live data is untouched, only the label people see changed.
- **Membership approver**: may use the Approvals page and approve or decline regular memberships. **Office and Admin levels** (2026-11-19): both need the tick. Developer and Superuser always can, so the permission is refused for them (and dropped when someone is promoted to Developer) rather than shown as implied. Moving between Office and Admin keeps it. Guard: `common.levels.can_hold_membership_approver`. No email goes with this role.
- **Final approver**: may confirm or send back a Gold application that an approver approved with Low potential (it cannot decline). **Admin level or higher only** (Admin, Developer, Superuser), never Office. Guard: `common.levels.can_hold_final_approver`.

Each person's Gold approval emails go to their account email, or to another address chosen in System > Approval.

## U3. What "act" means in the Office

| Action | Viewer | Office | Admin | Developer | Superuser |
|---|---|---|---|---|---|
| See dashboard, analytics, people, leads, Gold | ✓ | ✓ | ✓ | ✓ | ✓ |
| Email (Message), WhatsApp button, Send guide, Add a mobile, Mark contacted, sticky notes, the Approach list (add, done, remove, back to Leads, archive from the list), fix a lead's email, resend the follow-up, mark a lead genuine, archive / unarchive leads | ✗ | ✓ | ✓ | ✓ | ✓ |
| Approve / decline / resend Gold | ✗ | only with Gold approver | only with Gold approver | only with Gold approver | ✓ |
| Approvals page: approve / decline memberships | ✗ | only with Membership approver | only with Membership approver | ✓ (always) | ✓ |
| Confirm / send back a Low potential approval (final approval; cannot decline) | ✗ | ✗ (never) | only with Final approver | only with Final approver | ✓ (emailed only if they hold the role) |
| Revenue (page, tab, Home cards, Analytics cards) | ✗ | ✗ | ✓ | ✓ | ✓ |
| Assistant chats (list, a chat, the card on a person's page) | ✗ | ✗ | ✓ | ✓ | ✓ |
| Export members (CSV, a person's data) | ✗ | ✗ | ✓ | ✓ | ✓ |
| Delete a member, set up payments, restore a sale | ✗ | ✗ | ✓ | ✓ | ✓ |
| Activity | ✗ | ✗ | ✗ | ✓ | ✓ |

A Viewer sees Home and Analytics with no money figures, plus Leads, People and Gold (decided 2026-11-16). A Viewer's page has no action buttons (no WhatsApp or Email buttons, no notes, no Approach list tab); every action URL answers 403 on the server. Revenue was open to approvers below Admin before 2026-11-16; it is now Admin and up only.

## U4. Managing the team

- Only **Developers and the superuser** add team members and set levels, in **System > Team** (behind the System unlock, every change in the audit log).
- Adding someone: email and level (Gold approver, Membership approver and Final approver are not asked here; they are set in **System > Approval**, and Team shows them as read-only labels). They get an email to set their own password.
- **System > Approval** (Developer level, behind the unlock) adds and removes Gold approvers, Membership approvers and Final approvers and sets where the Gold emails go. It follows the same `can_manage` guard as Team (never yourself, strictly below you, a superuser may change another superuser), with one addition: a superuser may set their own approval roles (it adds no power; it only decides who is emailed). Changing a level in Team keeps these roles, except that a level below Admin drops Final approver, any level other than Office or Admin drops Membership approver, Viewer drops Gold approver too, and removing someone from the team drops all three. Every change is in the audit log (`role_changed`).
- **Nobody can delete or edit someone higher than them**, and below superuser nobody can delete or edit someone at their own level either. A Developer can change Viewer, Office and Admin people; only a superuser can change a Developer. **Superusers are the exception: a superuser can delete or edit another superuser** (so a lost or departed superuser can always be removed).
- Nobody can remove their own access or deactivate themselves.
- **A page per team member** (System > Team > click a person, 2026-11-16) holds the level, the three approval ticks (the same rules as System > Approval; both places work), the Office email, the login email and the password. Every action there uses the same `can_manage` guard and is in the audit log.
- **Change email** (login): the same account, so all data stays; refused if another account has the address (use Merge); the person is signed out everywhere and the old and new address are both told. Nobody changes their own here.
- **Password: two options (replaces the old U4 rule "nobody types a password for someone else", 2026-11-16).** (1) *Send password reset link*: the person chooses their own (one hour). (2) *Set password*: a Developer or superuser types a new one twice for someone they can manage. Safeguards: never yourself (you have Change password), Django's password validators, the password is never logged, stored in plain text or shown again, the audit log says who set it (not what), the person is signed out everywhere and emailed that it was changed and by whom.

## U5. Sign-in

- Members sign in on the website and land in the member area. Team members sign in on their own address (Office, Control, System) and land on its home page. System sign-in is at `/dev-login/` (the old `/login/` is a plain 404), and System then asks only for the lock code. Wrong tries on the System sign-in and unlock show the tries left; 6 wrong in a row wait 1 minute, then each further wrong try adds a minute (cap 60), with a live countdown.
- Office sign-in lasts 30 days. System locks after the set idle minutes (default 15) and ends after the set hours (default 12). Member sign-in lasts 2 weeks.
- No access = a plain "not found" (staff addresses never admit what is there).

## Payment window actions (2026-10-29)
Admin and above (Office person page, audited): set up a membership manually (edit, cancel), restore a lapsed sale price (reason required). Developer (System, unlocked): open, schedule, cancel the schedule and close payments; Defaults. Office level and below can see the sale and payment state (Viewer and Office), not change it.
