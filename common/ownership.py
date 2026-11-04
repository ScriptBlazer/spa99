"""Who owns an email thread or a WhatsApp chat: the one rule, in one place. `emailchat` and `whatsapp` both ask here, for the page, the timeline, the export, the erasure
and the merge. Nothing else decides ownership (docs/features/office-email-chat.md, "Ownership").

A person's chats and threads are exactly:
  1. those with an explicit owner link (`user`), set by a staff action or by a proven step;
  2. those on his address (`email`, `lead_email`), only when his account email is verified (a person with no account, a lead or an applicant, is found by the address staff opened);
  3. those through his Gold application, only when that application's link is proven: the account is verified, or the application is being handled by staff on its own page.
A mobile number is never proof of anything, and verifying an email proves the email only. A chat is linked to an account by its mobile only when the chat's lead address, if it
has one, is the verified account's address (`mobile_link_ok`). Self-service stays stricter: the verified account address only (emailchat.threads_for_member).

`Thread` and `Contact` both have `user`, `lead_email` and `application`, so one query serves both; the address columns differ (`address_fields`).
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


def person_q(user=None, addresses=(), application=None, address_fields=("lead_email",)):
    """Q for a Thread or Contact: owner link, trusted address columns, proven applications."""
    query = Q(pk__in=[])
    if user is not None:
        query |= Q(user=user)  # the explicit link counts even for an unverified account
    trusted = trusted_addresses(user, addresses)
    if trusted:
        for field in address_fields:
            query |= Q(**{f"{field}__in": trusted})
    query |= Q(application__in=applications(user, addresses, application).values("pk"))
    return query


def owned(model, user=None, addresses=(), application=None, address_fields=("lead_email",)):
    """Every row of `model` (Thread or Contact) held for this person. The only lookup the page, timeline, export, erasure and merge use."""
    return model.objects.filter(person_q(user, addresses, application, address_fields))


def mobile_link_ok(lead_email, user):
    """May a chat whose lead address is `lead_email` (blank when it has none) be linked to this account because the mobiles match? Only a verified account, and only when the
    chat has no lead address or it is the account's own address: a lead's chat is his, whoever types his number at sign-up."""
    if not is_verified(user):
        return False
    lead = clean(lead_email)
    return not lead or lead == clean(user.email)


def claim(chat, user):
    """Staff opened this person's page and started the chat: link an ownerless chat to him (their explicit choice, as an email thread is). A chat that already has an owner is never
    taken, and neither is a lead's chat (it has a lead address) unless that is his own verified address. Returns True when it was linked."""
    if user is None or chat.user_id is not None:
        return False
    lead = clean(chat.lead_email)
    if lead and not (is_verified(user) and lead == clean(user.email)):
        return False
    chat.user = user
    chat.save(update_fields=["user"])
    return True


def visible_from_page(chat, user=None, addresses=(), application=None, address_fields=("lead_email",)):
    """Does the person's page show this chat as its own? Held for him by the rule, or nobody's yet (no owner, lead address or application: staff can still open and claim it).
    A chat that is someone else's is not shown as his."""
    if chat.user_id is None and not clean(chat.lead_email) and chat.application_id is None:
        return True
    return type(chat).objects.filter(pk=chat.pk).filter(person_q(user, addresses, application, address_fields)).exists()
