"""The small framework the walk-throughs share: steps with screenshots, console and server error collection, test accounts,
and the helpers a person's actions are built from (sign in, register, answer the journey, apply for Gold)."""
import json
import os
import re
import subprocess
import sys
import time
import traceback
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = int(os.environ.get("E2E_PORT", "8765"))
SITE = f"http://localhost:{PORT}"
OFFICE = f"http://office.localhost:{PORT}"
CONTROL = f"http://control.localhost:{PORT}"
SYSTEM = f"http://system.localhost:{PORT}"
# The second ("strict") server: same database and mail folder, but real rate limits and tiny upload limits (e2e/settings_strict.py).
# 0 = scripts/e2e.sh did not start one; the walk-throughs that need it say so and skip.
STRICT_PORT = int(os.environ.get("E2E_STRICT_PORT", "0") or 0)
STRICT_SITE = f"http://localhost:{STRICT_PORT}"
STRICT_CONTROL = f"http://control.localhost:{STRICT_PORT}"
WORKSPACE_DIR = Path(os.environ.get("E2E_WORKSPACE", ROOT / ".private" / "e2e"))
REPORT_DIR = Path(os.environ.get("E2E_REPORT_DIR", ROOT / ".private" / "e2e-report"))
UNLOCK_CODE = os.environ.get("SYSTEM_UNLOCK_CODE", "482916")
PASSWORD = "Sauna-Steam-2026!"
NEW_PASSWORD = "Plunge-Pool-2027!"
RESET_PASSWORD = "Eucalyptus-Mist-88"
TIMEOUT = 20000

# The staff accounts (made by the run itself: team people are never self-service).
STAFF = {
    "office": {"email": "office@example.com", "level": "office", "approver": False, "first": "Olive", "last": "Office"},
    "admin": {"email": "admin@example.com", "level": "admin", "approver": False, "first": "Adam", "last": "Admin"},
    "barry": {"email": "barry@example.com", "level": "office", "approver": True, "first": "Barry", "last": "Approver"},
    "dev": {"email": "dev@example.com", "level": "developer", "approver": False, "first": "Dana", "last": "Developer"},
}

# Console noise that is not the site's fault (the headless browser's own graphics messages).
# Chrome's own messages, not our scripts. The last one: the robot clicks faster than a page-to-page fade can run,
# so Chrome skips the fade and reports it; a person never sees anything.
IGNORED_CONSOLE = [r"GPU stall", r"GL Driver", r"WebGL", r"swiftshader", r"GroupMarker",
                   r"Transition was aborted because of invalid state",
                   r"status of (400|429) .*/register/"]  # the register form is sent with fetch: Chrome logs its answered 4xx (the dialog shows them)


class StepFailed(Exception):
    pass


def strict_server_up():
    """True when the strict server (rate limits on, tiny upload limits) is answering."""
    if not STRICT_PORT:
        return False
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{STRICT_PORT}/health/", timeout=5) as response:
            return response.status == 200
    except OSError:
        return False


# ---------- the throwaway database and manage.py ----------

def dbtool(*args):
    """Run e2e.dbtool in a child process; returns its JSON answer."""
    result = subprocess.run([sys.executable, "-m", "e2e.dbtool", *args], cwd=ROOT, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"dbtool {' '.join(args)} failed: {result.stderr.strip()[-600:]}")
    return json.loads(result.stdout.strip().splitlines()[-1])


def manage(*args):
    """Run a manage.py command against the throwaway database. Returns (exit code, output)."""
    result = subprocess.run([sys.executable, "manage.py", *args], cwd=ROOT, capture_output=True, text=True, timeout=300)
    return result.returncode, (result.stdout + result.stderr)


def setup_staff():
    for person in STAFF.values():
        extra = ["--approver"] if person["approver"] else []
        dbtool("create-staff", person["email"], PASSWORD, person["level"], "--first", person["first"], "--last", person["last"], *extra)
    dbtool("set-approver", STAFF["barry"]["email"])


# ---------- a walk-through: steps, screenshots, errors ----------

def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "step"


class Walk:
    def __init__(self, key, title, browser, headed=False, allow_console=()):
        self.key, self.title, self.browser = key, title, browser
        self.allow_console = [re.compile(p) for p in (*IGNORED_CONSOLE, *allow_console)]
        self.steps = []
        self.console_errors, self.server_errors = [], []
        self.dialogs = []             # alert / confirm / prompt boxes the pages tried to open (always dismissed)
        self.watch_dialogs = False    # a walk-through that sets this gets a last check: no dialog opened
        self.contexts, self.last_page = [], None
        self.started = time.time()
        self.shots = REPORT_DIR / "shots"
        self.shots.mkdir(parents=True, exist_ok=True)

    # --- browser contexts: one per person / host (cookies are per host anyway) ---
    def page(self, width=1280, height=800, mobile=False, user_agent=None):
        options = {"user_agent": user_agent} if user_agent else {}
        context = self.browser.new_context(
            viewport={"width": width, "height": height}, locale="en-GB", timezone_id="Europe/London", accept_downloads=True,
            is_mobile=mobile, has_touch=mobile, device_scale_factor=2 if mobile else 1, **options)
        context.set_default_timeout(TIMEOUT)
        context.on("page", self._hook)
        page = context.new_page()
        self.contexts.append(context)
        self.last_page = page
        return page

    def _hook(self, page):
        page.on("console", lambda message: self._console(message))
        page.on("pageerror", lambda error: self._script_error(f"Script error: {error} ({page.url})"))
        page.on("dialog", lambda dialog: self._dialog(dialog, page))
        page.on("response", lambda response: self.server_errors.append(f"{response.status} {response.request.method} {response.url}") if response.status >= 500 else None)

    def _dialog(self, dialog, page):
        if dialog.type != "beforeunload":  # the browser's own "leave this page?" box is not the site opening a message
            self.dialogs.append(f"{dialog.type} box: '{dialog.message[:80]}' on {page.url}")
        try:
            dialog.dismiss()
        except Exception:  # noqa: BLE001 - already closed
            pass

    def _script_error(self, text):
        if not any(pattern.search(text) for pattern in self.allow_console):
            self.console_errors.append(text)

    def _console(self, message):
        if message.type != "error":
            return
        text = f"{message.text} ({message.location.get('url', '')})"
        if not any(pattern.search(text) for pattern in self.allow_console):
            self.console_errors.append(text)

    # --- steps ---
    def _shoot(self, page, label, failed=False):
        name = f"{self.key}-{len(self.steps):02d}-{slug(label)}{'-FAILED' if failed else ''}.png"
        try:
            page.screenshot(path=str(self.shots / name))
            return f"shots/{name}"
        except Exception:  # noqa: BLE001 - a page that is gone cannot be photographed; the step result still counts
            return ""

    @contextmanager
    def step(self, name, page=None):
        page = page or self.last_page
        record = {"name": name, "status": "pass", "error": "", "shot": ""}
        self.steps.append(record)
        try:
            yield
        except Exception as error:  # noqa: BLE001 - any failure ends this walk-through, with the reason and a photo
            record["status"] = "fail"
            record["error"] = f"{type(error).__name__}: {error}"[:1800]
            record["shot"] = self._shoot(page, name, failed=True) if page else ""
            raise StepFailed(name) from error
        record["shot"] = self._shoot(page, name) if page else ""

    def info(self, text):
        """A passing line in the report that records a fact (used for open questions: what the app did, not a verdict)."""
        self.steps.append({"name": text, "status": "pass", "error": "", "shot": ""})

    def check_errors(self):
        """The last checks of every walk-through: no server errors, no console errors (and, if asked, no dialog boxes)."""
        checks = [("No server errors (HTTP 5xx)", self.server_errors), ("No console errors", self.console_errors)]
        if self.watch_dialogs:
            checks.append(("No JavaScript dialog (alert, confirm, prompt) opened", self.dialogs))
        for label, found in checks:
            unique = list(dict.fromkeys(found))
            self.steps.append({"name": label, "status": "fail" if unique else "pass", "error": "\n".join(unique[:8]), "shot": ""})

    def close(self):
        for context in self.contexts:
            try:
                context.close()
            except Exception:  # noqa: BLE001
                pass

    def result(self):
        return {"key": self.key, "title": self.title, "steps": self.steps, "seconds": round(time.time() - self.started, 1),
                "passed": all(s["status"] == "pass" for s in self.steps)}


def run_walk(walk, function):
    """Run one walk-through function; whatever happens the result is complete (a crash becomes a failed step)."""
    try:
        function(walk)
    except StepFailed:
        pass
    except Exception as error:  # noqa: BLE001
        walk.steps.append({"name": "Unexpected error in the walk-through", "status": "fail",
                           "error": f"{type(error).__name__}: {error}\n{traceback.format_exc()[-1200:]}", "shot": ""})
    walk.check_errors()
    walk.close()
    return walk.result()


# ---------- what a person does ----------

def sign_in(page, base, email, password, expect_path=None):
    """Sign in on a host's own /login/ page (public site, Office or Control). Waits for the page after sign-in."""
    page.goto(f"{base}/login/")
    page.locator("input[name=username]").fill(email)
    page.locator("input[name=password]").fill(password)
    with page.expect_navigation():
        page.locator("form[data-live-validate] button[type=submit]").click()
    if expect_path:
        page.wait_for_url(re.compile(re.escape(expect_path)))


def sign_in_fails(page, base, email, password):
    """A sign-in that must be refused: stays on /login/ with an error."""
    page.goto(f"{base}/login/")
    page.locator("input[name=username]").fill(email)
    page.locator("input[name=password]").fill(password)
    with page.expect_navigation():
        page.locator("form[data-live-validate] button[type=submit]").click()
    assert "/login/" in page.url, f"Expected to stay on the sign-in page, but landed on {page.url}"
    page.locator(".form-error").first.wait_for()
    lines = problems_modal(page)
    assert any("email or password is wrong" in line.lower() for line in lines), f"The problems dialog says: {lines}"
    close_problems(page)


def problems_modal(page, timeout=5000):
    """The shared problems dialog (form-problems.js): waits for it and returns its lines (label and message, one per problem)."""
    page.wait_for_selector("dialog.fb-modal[open] .fb-problems", timeout=timeout)
    return page.locator("dialog.fb-modal[open] .fb-problems li").all_inner_texts()


def close_problems(page):
    """OK on the problems dialog. Everything typed stays; focus goes to the first problem."""
    page.locator("dialog.fb-modal[open] .fb-modal-custom .fb-btn").click()
    page.wait_for_function("!document.querySelector('dialog.fb-modal[open]')")


def form_errors(page):
    """The error lines currently shown on a form (live feedback and server errors)."""
    return page.locator(".feedback[data-state=error], .form-error").all_inner_texts()


def tick(page, name):
    """Tick a consent box (the real input; the row around it is styled, so click the input itself)."""
    box = page.locator(f"input[name={name}]").first
    if not box.is_checked():
        box.evaluate("element => element.click()")


def fill_date_of_birth(page, day="14", month="03", year="1985"):
    page.locator("#dob-day").fill(day)
    page.locator("#dob-month").fill(month)
    page.locator("#dob-year").fill(year)


def register_member(page, email, first, last, mobile, plan_name="Tier 2", password=PASSWORD):
    """Register for a tier through the real form, then wait for the 'check your email' screen."""
    page.goto(f"{SITE}/register/")
    page.locator("label.plan-chip", has_text=plan_name).first.click()
    page.locator("#id_first_name").fill(first)
    page.locator("#id_last_name").fill(last)
    page.locator("#id_email").fill(email)
    page.locator("#id_mobile").fill(mobile)
    page.locator("#id_password").fill(password)
    fill_date_of_birth(page)
    tick(page, "men_only_accepted")
    tick(page, "privacy_accepted")
    page.locator("#register-form button[type=submit]").click()
    try:
        page.wait_for_url(re.compile(r"/register/sent/"))
    except Exception:  # noqa: BLE001 - say what the form complained about instead of just timing out
        raise AssertionError(f"Registering did not reach 'check your email'. The form says: {form_errors(page) or 'nothing visible'}") from None


def verify_email_link(page, url):
    """Open the verification link, tap 'Confirm my email'; lands signed in on the member dashboard."""
    page.goto(url)
    with page.expect_navigation():
        page.get_by_role("button", name="Confirm my email").click()
    page.wait_for_url(re.compile(r"/account/"))


def answer_journey(page, stop_before_result=False, email="journey-walker@example.test"):
    """Walk the guided journey: pick the first choice of every question on every screen until the suggested tier shows.
    Returns the suggested tier text (for example 'Tier 2.')."""
    page.goto(f"{SITE}/journey/")
    for _ in range(10):
        page.wait_for_selector("[data-flow-root] .screen, [data-flow-root] .result")
        if page.locator("[data-flow-root] .result").count():
            break
        if page.locator("[data-flow-root] .lead-gate").count():  # the email gate before the result (2026-10-26)
            page.locator("#lead-email").fill(email)
            tick(page, "consent")
            page.locator("[data-gate-primary]").click()
            # The gate stays in the page until the server has taken the address: wait for the result itself, or the next
            # pass would fill and click the old gate while it is being replaced (a click on a detached button times out).
            page.wait_for_selector("[data-flow-root] .result")
            break
        heading = page.locator("[data-flow-root] h1").first.inner_text()
        for _ in range(5):  # follow-up questions appear after an answer, so look again
            unanswered = page.locator("fieldset[data-question]:not([hidden])").filter(has_not=page.locator("input:checked"))
            if not unanswered.count():
                break
            unanswered.first.locator("label.tile, label.seg").first.click()
        page.locator("[data-primary]").click()
        page.wait_for_function(
            "old => { const h = document.querySelector('[data-flow-root] h1'); return h && h.textContent !== old; }", arg=heading)
    page.wait_for_selector("[data-flow-root] .result-tier")
    return page.locator("[data-flow-root] .result-tier").inner_text()


def gold_open_about(page):
    """Open the Gold application and choose Finance (the first screen, 'about you'). Company and role are not filled."""
    page.goto(f"{SITE}/gold-card/apply/")
    page.wait_for_selector("[data-flow-root] .screen")
    # Industry is multi-select: a tile is a checkbox, and answers from an earlier journey or application can already be ticked
    # (clicking a ticked one would untick it and block Continue), so tick it only when it is not.
    page.locator("input[name=industry][value=finance]").wait_for(state="attached")
    if not page.locator("input[name=industry][value=finance]").is_checked():
        page.locator("label.tile:has(input[name=industry][value=finance])").click()


def gold_to_last_screen(page):
    """Open the Gold application, choose Finance, fill company and role (always required, 2026-10-29), pass 'your visits',
    and wait on the last screen ('you')."""
    gold_open_about(page)
    page.locator("#g-company").fill("E2E Holdings")
    page.locator("#g-role").fill("Director")
    page.locator("[data-primary]").click()           # screen 2: your visits (from the journey, or asked now)
    page.wait_for_selector("[data-flow-root] .screen-title")
    page.locator("[data-primary]").click()           # screen 3: you
    page.locator("#g-first_name").wait_for()


def gold_fill_you(page, first, last, email, mobile, note="", privacy=True):
    """Fill the last Gold screen. Values go in exactly as given (no trimming), so bad input can be tried."""
    page.locator("#g-first_name").fill(first)
    page.locator("#g-last_name").fill(last)
    page.locator("#g-email").fill(email)
    page.locator("#g-mobile").fill(mobile)
    if note:
        page.locator("#g-note").fill(note)
    if privacy:
        tick(page, "privacy_accepted")


def apply_gold(page, first, last, email, mobile, note=""):
    """Fill in the Gold Card application (about you, your visits, you) and send it. Returns the reference (GC-XXXXXX)."""
    gold_to_last_screen(page)
    gold_fill_you(page, first, last, email, mobile, note)
    page.locator("[data-primary]").click()
    page.wait_for_selector(".gold-sent")
    return page.locator(".gold-sent .reference").inner_text()


def confirm_office_modal(page):
    """Confirm the Office/website confirm dialog (Approve, Decline, Delete ...)."""
    page.locator("dialog.fb-modal[open] [data-fb-ok]").click()


def approve_on_application_page(page):
    """On the Office application page: tap Approve and invite, confirm, wait for the rail to say Approved."""
    page.locator("[data-gold-decision] [data-approve] button").first.click()
    confirm_office_modal(page)
    page.wait_for_selector("[data-gold-decision]:has-text('Approved')")

def no_horizontal_overflow(page):
    """(ok, scrollWidth, innerWidth): nothing sticks out sideways."""
    width = page.evaluate("() => [document.documentElement.scrollWidth, document.body ? document.body.scrollWidth : 0, window.innerWidth]")
    return max(width[0], width[1]) <= width[2], max(width[0], width[1]), width[2]
