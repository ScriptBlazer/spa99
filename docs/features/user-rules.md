# User rules (the rule book)

Decided by Moishe 2026-10-23 (PROJECT.md). This replaces the old Owner / Manager / Viewer roles. Every view checks these rules on the server; hiding a button is never the only guard.

## U1. Who exists

| Type | What it is |
|---|---|
| **Visitor** | Not signed in. The public website, the journey, registering interest, the Gold application, the tour |
| **Member** | A person with a membership (registered interest in a tier, later a paid plan). The website plus the member area (`/account/`) |
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

**Approver** is an extra permission, not a level: may approve, decline and resend Gold applications. It can only be given to someone at Office level or higher (e.g. Barry = Office + Approver).

## U3. What "act" means in the Office

| Action | Office | Admin | Developer | Superuser |
|---|---|---|---|---|
| See dashboard, analytics, people, Gold | ✓ | ✓ | ✓ | ✓ |
| Approve / decline / resend Gold | only with Approver | only with Approver | only with Approver | ✓ |
| Export members (CSV, a person's data) | ✗ | ✓ | ✓ | ✓ |
| Delete a member | ✗ | ✓ | ✓ | ✓ |

## U4. Managing the team

- Only **Developers and the superuser** add team members and set levels, in **System > Team** (behind the System unlock, every change in the audit log).
- Adding someone: email, level, Approver yes/no. They get an email to set their own password; nobody types a password for someone else.
- **Nobody can delete or edit someone higher than them**, and below superuser nobody can delete or edit someone at their own level either. A Developer can change Office and Admin people; only a superuser can change a Developer. **Superusers are the exception: a superuser can delete or edit another superuser** (so a lost or departed superuser can always be removed).
- Nobody can remove their own access or deactivate themselves.

## U5. Sign-in

- Members sign in on the website and land in the member area. Team members sign in on their own address (Office, Control, System) and land on its home page.
- Office sign-in lasts 30 days. System locks after the set idle minutes (default 15) and ends after the set hours (default 12). Member sign-in lasts 2 weeks.
- No access = a plain "not found" (staff addresses never admit what is there).
