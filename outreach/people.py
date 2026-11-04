"""Who is "the same person": the addresses a person goes by. The account email, the emails of his Gold applications and the
addresses he left at the journey gate while signed in, or - for a lead - his one address. Notes, the approach list and messages
are found through this set, so they follow him from lead to account (docs/features/office-outreach.md section 2)."""
from users.models import User


def _clean(email):
    return (email or "").strip().lower()


def resolve(user=None, email="", application=None):
    """(main address, set of all his addresses, user or None). `main` = the account email when there is an account, else the
    lead or application email. A verified account takes over an address, as Leads does (an unverified one may carry someone
    else's address, so it is not merged)."""
    email = _clean(email)
    if application is not None:
        email = email or _clean(application.email)
        if user is None and application.user_id and application.user.email_verified_at:  # an unverified account may only look linked (an old link made by address alone)
            user = application.user
    if user is None and email:
        user = User.objects.filter(email__iexact=email, email_verified_at__isnull=False).first()
    addresses = {email} if email else set()
    if application is not None:
        addresses.add(_clean(application.email))
    main = email
    if user is not None:
        main = _clean(user.email)
        addresses.add(main)
        addresses |= {_clean(e) for e in user.gold_applications.values_list("email", flat=True)}
        if user.email_verified_at:  # an unverified account may carry someone else's address: its journeys are not merged
            addresses |= {_clean(e) for e in user.journey_sessions.exclude(lead_email="").values_list("lead_email", flat=True)}
    addresses.discard("")
    return main, addresses, user
