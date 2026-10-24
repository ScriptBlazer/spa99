"""Small helper for the end-to-end run: sets up and reads the THROWAWAY database. One JSON line on stdout.

Run as `python -m e2e.dbtool <command> ...` with the e2e environment (scripts/e2e.sh sets it). Playwright's sync API runs
an event loop, where Django refuses database calls, so the run calls this in a child process instead.

  create-staff EMAIL PASSWORD LEVEL [--approver] [--first NAME] [--last NAME]   Office, Admin or Developer team account
  set-approver EMAIL        who receives Gold applications (the same field as System > Emails)
  registrations             number of registered-interest rows
  user EMAIL                {"exists", "plan"}
  gold EMAIL                {"status", "has_user", "count"}
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
    from gold.models import GoldApplication
    from plans.models import Plan, SiteSettings
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
        user = User.objects.filter(email__iexact=args[0]).first()
        interest = getattr(user, "interest", None) if user else None
        return {"exists": user is not None, "plan": interest.plan.slug if interest and interest.plan_id else None}
    if cmd == "gold":
        rows = GoldApplication.objects.filter(email__iexact=args[0]).order_by("-created_at")
        first = rows.first()
        return {"status": first.status if first else None, "has_user": User.objects.filter(email__iexact=args[0]).exists(), "count": rows.count()}
    if cmd == "waiting":
        return {"count": GoldApplication.objects.filter(status__in=[GoldApplication.NEW, GoldApplication.CONTACTED]).count()}
    if cmd == "price":
        return {"price": str(Plan.objects.get(slug=args[0]).price_ex_vat)}
    if cmd == "assets":
        return {"count": MediaAsset.objects.count()}
    raise SystemExit(f"Unknown command: {cmd}")


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1:])))
