"""Who owns a WhatsApp chat: the one rule, in one place. `whatsapp` asks here, for the page, the timeline, the export, the erasure
and the merge. Nothing else decides ownership (docs/features/whatsapp.md, "Ownership").

A person's chats are exactly:
  1. those with an explicit owner link (`user`), set by a staff action or by a proven step;
  2. those on his address (`email`, `lead_email`), only when his account email is verified (a person with no account, a lead or an applicant, is found by the address staff opened);
  3. those through his Gold application, only when that application's link is proven: the account is verified, or the application is being handled by staff on its own page.

THE LINK RULE (who may set a chat's links `user`, `lead_email`, `application`; this is the root of every ownership bug found in review):
  1. A chat's links are set only by: a) a staff POST by an editor after seeing the chat (`link`, the "This number isn't linked to X. Link it?" button in the thread), b) creating a NEW
     chat from a staff start action (a POST, `link` right after the create), or c) a proven email address joining up on verify, only when the chat already has that lead address
     set by a) or b) (`resolve_links` on verify). A staff correction of a lead's address moves the lead address it already holds (`whatsapp.move_address`).
  2. A number typed on a public form (the journey gate, Register, Gold apply) never sets or replaces any link on an existing chat, nor a chat's name. It may be stored on its own form record.
  3. No GET ever writes a link or creates ownership: viewing is viewing. Opening a chat is a link; starting one is a POST.
A mobile number is never proof of anything, and verifying an email proves the email only. Nothing is linked by number: a chat is linked by staff (`link`, `claim`) or, once its lead address
is a verified account's own, by that account verifying. A chat nobody holds stays unlinked until staff link it from the thread or delete it; the person's page still shows that it exists
(`visible_from_page`).

Existing `GoldApplication.user` rows on live may link an application to an account that was never verified (the old code linked by address alone): nothing here trusts such a
link, and nothing rewrites it. Plain Django, no database features beyond `iexact`, so it works the same on SQLite and Postgres."""
from django.db.models import Q


def clean(address):
    return (address or "").strip().lower()


def is_verified(user):
    return user is not None and getattr(user, "email_verified_at", None) is not None


def trusted_addresses(user, addresses):
    """The addresses a lookup may use: all of them for a person with no account (staff opened that address) or a verified account, none for an unverified account
    (anyone can register with any address, so its address proves nothing)."""
    if user is not None and not is_verified(user):
        return set()
    return {clean(a) for a in addresses or () if clean(a)}


def applications(user=None, addresses=(), application=None):
    """Q on GoldApplication: the applications that count as his. His own link only for a verified account; applications made with a trusted address; and the one application
    staff opened (its own page)."""
    from gold.models import GoldApplication

    query = Q(pk__in=[])
    if is_verified(user):
        query |= Q(user=user)
    for address in trusted_addresses(user, addresses):
        query |= Q(email__iexact=address)
    if application is not None:
        query |= Q(pk=application.pk)
    return GoldApplication.objects.filter(query)


def person_q(user=None, addresses=(), application=None):
    """Q for a Contact: owner link, trusted lead addresses, proven applications."""
    query = Q(pk__in=[])
    if user is not None:
        query |= Q(user=user)  # the explicit link counts even for an unverified account
    trusted = trusted_addresses(user, addresses)
    if trusted:
        query |= Q(lead_email__in=trusted)
    query |= Q(application__in=applications(user, addresses, application).values("pk"))
    return query


def owned(model, user=None, addresses=(), application=None):
    """Every row of `model` (the WhatsApp Contact) held for this person. The only lookup the page, timeline, export, erasure and merge use."""
    return model.objects.filter(person_q(user, addresses, application))


def claim(chat, user):
    """Staff opened this person's page and started the chat: link an ownerless chat to him (their explicit choice). A chat that already has an owner is never
    taken, and neither is a lead's chat (it has a lead address) unless that is his own verified address. Returns True when it was linked."""
    if user is None or chat.user_id is not None:
        return False
    lead = clean(chat.lead_email)
    if lead and not (is_verified(user) and lead == clean(user.email)):
        return False
    chat.user = user
    chat.save(update_fields=["user"])
    return True


def visible_from_page(chat, user=None, addresses=(), application=None):
    """Does the person's page show this chat as its own? Held for him by the rule, or nobody's yet (no owner, lead address or application: staff can still open and claim it).
    A chat that is someone else's is not shown as his."""
    if chat.user_id is None and not clean(chat.lead_email) and chat.application_id is None:
        return True
    return type(chat).objects.filter(pk=chat.pk).filter(person_q(user, addresses, application)).exists()


def is_unlinked(chat):
    """A chat nobody holds yet: no owner, no lead address, no application."""
    return chat.user_id is None and not clean(chat.lead_email) and chat.application_id is None


def link(chat, user=None, lead_email="", application=None):
    """Rule 1a and 1b: staff chose to link this chat to the person whose page they came from (a POST by an editor, or a chat just created by a start POST). Give exactly one of `user`
    (a person's page: `claim`), `lead_email` (a lead's page) or `application` (a Gold page; it also takes the applicant's address as the lead address). Only an unlinked chat is linked
    (a person's page may also claim a chat that holds his own verified address): a chat somebody holds is never taken. Returns True when it was linked."""
    if user is not None:
        return claim(chat, user)
    if not is_unlinked(chat):
        return False
    fields = []
    if application is not None:
        chat.application = application
        chat.lead_email = clean(application.email)
        fields = ["application", "lead_email"]
    elif clean(lead_email):
        chat.lead_email = clean(lead_email)
        fields = ["lead_email"]
    if fields:
        chat.save(update_fields=fields)
    return bool(fields)
