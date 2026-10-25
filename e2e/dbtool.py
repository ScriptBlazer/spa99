"""Small helper for the end-to-end run: sets up and reads the THROWAWAY database. One JSON line on stdout.

Run as `python -m e2e.dbtool <command> ...` with the e2e environment (scripts/e2e.sh sets it). Playwright's sync API runs
an event loop, where Django refuses database calls, so the run calls this in a child process instead.

  create-staff EMAIL PASSWORD LEVEL [--approver] [--first NAME] [--last NAME]   Office, Admin or Developer team account
  set-approver EMAIL        who receives Gold applications (the same field as System > Emails)
  registrations             number of registered-interest rows
  user EMAIL                {"exists", "count", "plan", "verified", "active"}
  gold EMAIL                {"status" (newest), "statuses", "waiting", "has_user", "count", "invites", "invites_used"}
  gold-total                number of Gold applications of any email
  age-gold EMAIL            make this email's applications a day old (so a re-apply is not inside the two-minute double-click window)
  events KIND               System audit events of one kind (for example unlock_failed)
  waiting                   Gold applications waiting for a decision
  price SLUG                plan price ex VAT
  assets                    Control Library files
"""
import argparse
import json
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "e2e.settings")

import django  # noqa: E402

django.setup()


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("args", nargs="*")
    parser.add_argument("--approver", action="store_true")
    parser.add_argument("--first", default="")
    parser.add_argument("--last", default="")
    options = parser.parse_args(argv)
    cmd, args = options.command, options.args

    from django.contrib.auth import get_user_model

    from control.models import MediaAsset
    from gold.models import GoldApplication, GoldInvite
    from plans.models import Plan, SiteSettings
    from system.models import SystemEvent
    from users.models import InterestRegistration

    User = get_user_model()
    if cmd == "create-staff":
        from system.team import apply_level

        email, password, level = args
        user = User.objects.filter(email__iexact=email).first() or User.objects.create_user(
            email, password, first_name=options.first, last_name=options.last)
        apply_level(user, level, options.approver, actor=None)
        return {"created": email, "level": level, "approver": options.approver}
    if cmd == "set-approver":
        site = SiteSettings.load()
        site.gold_approver_emails = args[0]
        site.save()
        return {"approver": args[0]}
    if cmd == "registrations":
        return {"count": InterestRegistration.objects.count()}
    if cmd == "user":
        matches = User.objects.filter(email__iexact=args[0])
        user = matches.first()
        interest = getattr(user, "interest", None) if user else None
        return {"exists": user is not None, "count": matches.count(), "plan": interest.plan.slug if interest and interest.plan_id else None,
                "verified": bool(user and user.email_verified_at), "active": bool(user and user.is_active)}
    if cmd == "gold":
        rows = GoldApplication.objects.filter(email__iexact=args[0]).order_by("-created_at")
        first = rows.first()
        invites = GoldInvite.objects.filter(application__email__iexact=args[0])
        return {"status": first.status if first else None, "statuses": [r.status for r in rows],
                "waiting": rows.filter(status__in=[GoldApplication.NEW, GoldApplication.CONTACTED]).count(),
                "has_user": User.objects.filter(email__iexact=args[0]).exists(), "count": rows.count(),
                "invites": invites.count(), "invites_used": invites.filter(used_at__isnull=False).count()}
    if cmd == "gold-total":
        return {"count": GoldApplication.objects.count()}
    if cmd == "age-gold":
        from datetime import timedelta

        from django.utils import timezone

        n = GoldApplication.objects.filter(email__iexact=args[0]).update(created_at=timezone.now() - timedelta(days=1))
        return {"aged": n}
    if cmd == "events":
        return {"count": SystemEvent.objects.filter(kind=args[0]).count()}
    if cmd == "waiting":
        return {"count": GoldApplication.objects.filter(status__in=[GoldApplication.NEW, GoldApplication.CONTACTED]).count()}
    if cmd == "price":
        return {"price": str(Plan.objects.get(slug=args[0]).price_ex_vat)}
    if cmd == "assets":
        return {"count": MediaAsset.objects.count()}
    raise SystemExit(f"Unknown command: {cmd}")


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1:])))
