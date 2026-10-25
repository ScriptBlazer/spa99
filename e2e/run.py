"""Run the walk-throughs: `python -m e2e.run [--only visitor,gold_approved] [--headed] [--list]`.
Normally started by scripts/e2e.sh, which has already made the throwaway workspace and started the server."""
import argparse
import sys
import time
import urllib.request

from . import report
from .kit import PORT, REPORT_DIR, Walk, run_walk, setup_staff
from .walks import WALKS as CORE_WALKS
from .walks_beta import BETA_WALKS

WALKS = CORE_WALKS + BETA_WALKS


def server_is_up():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health/", timeout=5) as response:
            return response.status == 200
    except OSError:
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", default="", help="comma separated walk-through names or numbers, e.g. gold_approved,6")
    parser.add_argument("--headed", action="store_true", help="show the browser window")
    parser.add_argument("--list", action="store_true", help="list the walk-throughs and stop")
    args = parser.parse_args(argv)

    if args.list:
        for number, (key, title, _, _) in enumerate(WALKS, start=1):
            print(f"{number:>2}  {key:22} {title}")
        return 0
    wanted = [item.strip() for item in args.only.split(",") if item.strip()]
    chosen = [(n, w) for n, w in enumerate(WALKS, start=1) if not wanted or w[0] in wanted or str(n) in wanted]
    if not chosen:
        print(f"No walk-through matches '{args.only}'. Use --list.")
        return 2
    if not server_is_up():
        print(f"The test server is not answering on port {PORT}. Start it with scripts/e2e.sh.")
        return 2

    from playwright.sync_api import sync_playwright

    started = time.time()
    setup_staff()
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.headed)
        for number, (key, title, function, allow) in chosen:
            print(f"[{number}/{len(WALKS)}] {title} ...", flush=True)
            walk = Walk(key, title, browser, headed=args.headed, allow_console=allow)
            results.append(run_walk(walk, function))
            print("      " + ("pass" if results[-1]["passed"] else "FAIL"), flush=True)
        browser.close()
    index = report.write(results, started)
    print("\n" + report.summary(results))
    print(f"\nReport: {index}")
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
