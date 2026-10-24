"""The report: .private/e2e-report/index.html (a table: walk-through, steps, pass/fail, error text, screenshot links) and a short
summary for the terminal."""
import html
import json
from datetime import datetime

from .kit import REPORT_DIR

STYLE = """
body{font:15px/1.45 -apple-system,system-ui,sans-serif;margin:2rem;color:#222;background:#faf8f5}
h1{margin:0 0 .25rem} .sub{color:#666;margin-bottom:1.5rem}
table{border-collapse:collapse;width:100%;background:#fff;margin-bottom:2rem}
th,td{border:1px solid #ddd;padding:.45rem .6rem;text-align:left;vertical-align:top}
th{background:#f0ece6} tr.walk td{background:#2b211b;color:#fff;font-weight:600}
.pass{color:#0a7a35;font-weight:600} .fail{color:#b3261e;font-weight:700}
pre{white-space:pre-wrap;margin:0;font:12px/1.4 ui-monospace,monospace;color:#b3261e}
img{max-width:180px;border:1px solid #ccc;display:block} a{color:#0a58ca}
"""


def write(results, started):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "results.json").write_text(json.dumps(results, indent=2))
    total = sum(len(r["steps"]) for r in results)
    failed = sum(1 for r in results for s in r["steps"] if s["status"] != "pass")
    rows = []
    for r in results:
        verdict = "pass" if r["passed"] else "fail"
        rows.append(f'<tr class="walk"><td colspan="4">{html.escape(r["title"])} &nbsp; <span class="{verdict}" style="color:{"#7be3a0" if r["passed"] else "#ff9d96"}">'
                    f'{"PASS" if r["passed"] else "FAIL"}</span> &nbsp; {r["seconds"]}s</td></tr>')
        for step in r["steps"]:
            shot = f'<a href="{step["shot"]}"><img src="{step["shot"]}" alt="screenshot" loading="lazy"></a>' if step["shot"] else ""
            error = f"<pre>{html.escape(step['error'])}</pre>" if step["error"] else ""
            rows.append(f'<tr><td>{html.escape(step["name"])}</td><td class="{step["status"]}">{step["status"].upper()}</td><td>{error}</td><td>{shot}</td></tr>')
    page = (f"<!doctype html><meta charset=utf-8><title>Spa 99 end-to-end report</title><style>{STYLE}</style>"
            f"<h1>Spa 99 end-to-end report</h1><p class=sub>{datetime.now():%A %d %B %Y, %H:%M} &middot; {len(results)} walk-throughs, {total} steps, "
            f'<span class="{"fail" if failed else "pass"}">{failed} failed</span></p>'
            f"<table><tr><th>Step</th><th>Result</th><th>Error</th><th>Screenshot</th></tr>{''.join(rows)}</table>")
    (REPORT_DIR / "index.html").write_text(page)
    return REPORT_DIR / "index.html"


def summary(results):
    lines = []
    for r in results:
        bad = [s for s in r["steps"] if s["status"] != "pass"]
        mark = "PASS" if r["passed"] else "FAIL"
        lines.append(f"  {mark}  {r['title']}  ({len(r['steps'])} steps, {r['seconds']}s)")
        for step in bad[:4]:
            first = step["error"].strip().splitlines()[0][:170] if step["error"] else ""
            lines.append(f"        - {step['name']}: {first}")
    failed = [r for r in results if not r["passed"]]
    lines.append("")
    lines.append(f"{len(results) - len(failed)} of {len(results)} walk-throughs passed." + (" Everything works." if not failed else ""))
    return "\n".join(lines)
