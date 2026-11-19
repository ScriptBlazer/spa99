"""Team levels (docs/features/user-rules.md, U2-U4). The one place that answers "what level is this person?".

Levels, lowest first: Viewer, Office, Admin, Developer, Superuser. They are Django Groups `Viewer`, `Office`, `Admin`, `Developer` plus the
superuser flag; the highest one wins. Three extra permission groups sit on top of a level: `Approver` (shown to people as "Gold approver";
the group name is kept so live data is untouched), `Membership approver` and `Final approver`. Views call these helpers; they never test
group names themselves.
Team levels need is_staff and is_active; a superuser is is_superuser and is_active.
"""
NONE, VIEWER, OFFICE, ADMIN, DEVELOPER, SUPERUSER = "none", "viewer", "office", "admin", "developer", "superuser"
RANK = {NONE: 0, VIEWER: 1, OFFICE: 2, ADMIN: 3, DEVELOPER: 4, SUPERUSER: 5}
LABELS = {NONE: "No team access", VIEWER: "Viewer", OFFICE: "Office", ADMIN: "Admin", DEVELOPER: "Developer", SUPERUSER: "Superuser"}
GROUP_FOR = {VIEWER: "Viewer", OFFICE: "Office", ADMIN: "Admin", DEVELOPER: "Developer"}
LEVEL_FOR_GROUP = {name: level for level, name in GROUP_FOR.items()}
APPROVER_GROUP = "Approver"  # the Gold approver (the label people see is GOLD_APPROVER_LABEL)
MEMBERSHIP_APPROVER_GROUP = "Membership approver"
FINAL_APPROVER_GROUP = "Final approver"
GOLD_APPROVER_LABEL = "Gold approver"
ROLE_LABELS = {APPROVER_GROUP: GOLD_APPROVER_LABEL, MEMBERSHIP_APPROVER_GROUP: "Membership approver", FINAL_APPROVER_GROUP: "Final approver"}
LEVEL_GROUPS = tuple(GROUP_FOR.values())
ROLE_GROUPS = (APPROVER_GROUP, MEMBERSHIP_APPROVER_GROUP, FINAL_APPROVER_GROUP)
TEAM_GROUPS = LEVEL_GROUPS + ROLE_GROUPS
# Who may hold each role (docs/features/user-rules.md U2). Membership approver is for Office and Admin (2026-11-19): both need the tick to approve memberships;
# Developer and Superuser always can, so the role is refused there, not stored.
APPROVER_MIN_LEVEL, FINAL_APPROVER_MIN_LEVEL, MEMBERSHIP_APPROVER_MIN_LEVEL, MEMBERSHIP_APPROVER_MAX_LEVEL = OFFICE, ADMIN, OFFICE, ADMIN


def rank(level):
    return RANK.get(level, 0)


def _group_names(user):
    return {group.name for group in user.groups.all()}  # uses a prefetch when there is one


def held(user):
    """(level, approver_group) as stored, ignoring is_active and is_staff: what a person holds on the Team screen."""
    if user is None or not getattr(user, "pk", None):
        return NONE, False
    names = _group_names(user)
    level = max((LEVEL_FOR_GROUP[n] for n in names if n in LEVEL_FOR_GROUP), key=rank, default=NONE)
    if user.is_superuser:
        level = SUPERUSER
    return level, APPROVER_GROUP in names


def holds_membership_group(user):
    """The Membership approver group as stored (ignoring level)."""
    return user is not None and bool(getattr(user, "pk", None)) and MEMBERSHIP_APPROVER_GROUP in _group_names(user)


def held_roles(user):
    """(approver_group, final_approver_group) as stored: the extra permissions on the Team and Approval screens.
    The Membership approver group is read with holds_membership_group."""
    if user is None or not getattr(user, "pk", None):
        return False, False
    names = _group_names(user)
    return APPROVER_GROUP in names, FINAL_APPROVER_GROUP in names


def held_level(user):
    return held(user)[0]


def level_of(user):
    """none / office / admin / developer / superuser for a signed-in, active person."""
    if user is None or not user.is_authenticated or not user.is_active:
        return NONE
    if user.is_superuser:
        return SUPERUSER
    if not user.is_staff:
        return NONE
    return held(user)[0]


def at_least(user, level):
    return rank(level_of(user)) >= rank(level)


def is_approver(user):
    """May approve, decline and resend Gold: the Gold approver group (Approver) on top of Office level or higher, or a superuser."""
    level = level_of(user)
    if level == SUPERUSER:
        return True
    return rank(level) >= rank(APPROVER_MIN_LEVEL) and held(user)[1]


def can_approve_memberships(user):
    """May use the Approvals page and approve regular memberships: Developer and up always; Office or Admin only with the Membership approver group. Never Viewer."""
    level = level_of(user)
    if rank(level) >= rank(DEVELOPER):
        return True
    return rank(MEMBERSHIP_APPROVER_MIN_LEVEL) <= rank(level) <= rank(MEMBERSHIP_APPROVER_MAX_LEVEL) and holds_membership_group(user)


def can_hold_approver(user):
    """The one guard for the Gold approver role: Office level or higher (a superuser counts). Not signed-in state: what is stored."""
    return rank(held_level(user)) >= rank(APPROVER_MIN_LEVEL)


def can_hold_membership_approver_level(level):
    """The same rule for a level name (no user yet), e.g. when setting up a team before the accounts exist."""
    return rank(MEMBERSHIP_APPROVER_MIN_LEVEL) <= rank(level) <= rank(MEMBERSHIP_APPROVER_MAX_LEVEL)


def can_hold_membership_approver(user):
    """The one guard for the Membership approver role: Office or Admin level. Viewer cannot; Developer and up already approve memberships."""
    return can_hold_membership_approver_level(held_level(user))


def can_hold_final_approver(user):
    """The one guard for the Final approver role: Admin level or higher (Admin, Developer, Superuser); never Office."""
    return rank(held_level(user)) >= rank(FINAL_APPROVER_MIN_LEVEL)


def is_final_approver(user):
    """May confirm or send back a Gold application awaiting final approval: the Final approver group on top of an Admin
    level or higher, or a superuser (U3: a superuser may act; they only get the emails when they hold the group)."""
    level = level_of(user)
    if level == SUPERUSER:
        return True
    return rank(level) >= rank(FINAL_APPROVER_MIN_LEVEL) and held_roles(user)[1]


def can_assign(actor, level):
    """Levels the actor may hand out: any for a superuser, otherwise only below their own."""
    actor_level = level_of(actor)
    if actor_level == SUPERUSER:
        return level in RANK
    return rank(level) < rank(actor_level)


def can_manage(actor, target):
    """U4: only a developer or superuser manages the team; never yourself; strictly higher rank than the target,
    except that a superuser may manage another superuser."""
    actor_level = level_of(actor)
    if rank(actor_level) < rank(DEVELOPER) or target is None or actor.pk == target.pk:
        return False
    if actor_level == SUPERUSER:
        return True
    return rank(actor_level) > rank(held_level(target))
