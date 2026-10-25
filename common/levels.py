"""Team levels (docs/features/user-rules.md, U2-U4). The one place that answers "what level is this person?".

Levels are Django Groups `Office`, `Admin`, `Developer` plus the superuser flag; the highest one wins. `Approver` is an
extra permission group, valid only on top of a level. Views call these helpers; they never test group names themselves.
Team levels need is_staff and is_active; a superuser is is_superuser and is_active.
"""
NONE, OFFICE, ADMIN, DEVELOPER, SUPERUSER = "none", "office", "admin", "developer", "superuser"
RANK = {NONE: 0, OFFICE: 1, ADMIN: 2, DEVELOPER: 3, SUPERUSER: 4}
LABELS = {NONE: "No team access", OFFICE: "Office", ADMIN: "Admin", DEVELOPER: "Developer", SUPERUSER: "Superuser"}
GROUP_FOR = {OFFICE: "Office", ADMIN: "Admin", DEVELOPER: "Developer"}
LEVEL_FOR_GROUP = {name: level for level, name in GROUP_FOR.items()}
APPROVER_GROUP = "Approver"
FINAL_APPROVER_GROUP = "Final approver"
LEVEL_GROUPS = tuple(GROUP_FOR.values())
TEAM_GROUPS = LEVEL_GROUPS + (APPROVER_GROUP, FINAL_APPROVER_GROUP)
APPROVER_MIN_LEVEL, FINAL_APPROVER_MIN_LEVEL = OFFICE, ADMIN  # who may hold each role (docs/features/user-rules.md U2)


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


def held_roles(user):
    """(approver_group, final_approver_group) as stored: the extra permissions on the Team and Approval screens."""
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
    """May approve, decline and resend Gold: the Approver group on top of a level, or a superuser."""
    level = level_of(user)
    if level == SUPERUSER:
        return True
    return level != NONE and held(user)[1]


def can_hold_approver(user):
    """The one guard for the Approver role: Office level or higher (a superuser counts). Not signed-in state: what is stored."""
    return rank(held_level(user)) >= rank(APPROVER_MIN_LEVEL)


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
