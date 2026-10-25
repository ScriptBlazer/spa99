"""The beta-tester scenarios (walk-throughs 10 onwards): the things a careful or careless person does that the happy-path
walk-throughs do not. Same rules as walks.py: each is a plain function that takes a Walk, every `with w.step(...)` is one
screenshotted step, the first failed step ends that walk-through.

These tests expose bugs, they do not adapt to them: where the docs say what must happen, that is the assertion; where the docs
are silent the assertion is the sensible behaviour, and the comment says "judgement". A failed step here is a finding.

Accounts are few and named by what they test (beta-*@example.com); everything lives in the throwaway workspace."""
import html as htmllib
import http.client
import io
import re
import wave
from urllib.parse import urlsplit

from . import mailbox
from .kit import (
    CONTROL, OFFICE, PASSWORD, PORT, RESET_PASSWORD, SITE, STAFF, STRICT_CONTROL, STRICT_SITE, SYSTEM, UNLOCK_CODE,
    NEW_PASSWORD, apply_gold, answer_journey, dbtool, fill_date_of_birth, form_errors, gold_fill_you, gold_to_last_screen, manage,
    close_problems, problems_modal, register_member, sign_in, sign_in_fails, strict_server_up, tick, verify_email_link,
)
from .walks import body_text, confirm_office_modal, wav_bytes

BARRY = STAFF["barry"]["email"]
OLIVE = STAFF["office"]  # Office level, no Approver
ADMIN = STAFF["admin"]
DEV = STAFF["dev"]
SCRIPT = "<script>alert(1)</script>"
HTTP_4XX = (r"status of 4\d\d",)  # these walk-throughs make the site refuse things on purpose; Chrome logs each refusal


def mobile(n):
    """A valid, unused UK mobile: 07123 46xxxx (each walk-through has its own range)."""
    return f"07123 46{n:04d}"


# ---------- helpers ----------

def csrf_for(page, base):
    """The CSRF token the browser holds for THIS host (cookies are per host)."""
    for cookie in page.context.cookies(base):
        if cookie["name"] == "csrftoken":
            return cookie["value"]
    raise AssertionError(f"The browser has no CSRF cookie for {base}.")


def post_direct(page, base, path, form=None, json_body=None, multipart=None, accept=None):
    """A POST sent straight to the server by this browser session with a valid CSRF token and no page involved.
    Redirects are not followed, so the answer is exactly what the view said."""
    headers = {"X-CSRFToken": csrf_for(page, base), "Referer": base + "/"}
    if accept:
        headers["Accept"] = accept
    options = {"headers": headers, "max_redirects": 0}
    if json_body is not None:
        options["data"] = json_body
    elif multipart is not None:
        options["multipart"] = multipart
    else:
        options["form"] = form or {}
    return page.context.request.post(base + path, **options)


def application_id(url):
    return re.search(r"/gold/([0-9a-f-]{36})/", url).group(1)


def approve_link(first, last):
    """The one-tap approve link in the approver's email about this applicant."""
    return mailbox.link(mailbox.wait_for(BARRY, f"Gold Card application: {first} {last}"), "/approve/confirm/")


def barry_page(w):
    page = w.page()
    sign_in(page, OFFICE, BARRY, PASSWORD)
    page.wait_for_selector("[data-office-dashboard]")
    return page


def approve_in_office(page, url):
    """Barry opens the approve link and taps Approve."""
    page.goto(url)
    page.wait_for_selector("[data-gold-confirm]")
    with page.expect_navigation():
        page.locator(".o-confirm-go").click()
    page.wait_for_selector("[data-gold-decision]")
    assert "Approved" in page.locator("[data-gold-decision]").inner_text()


def accept_invite(page, url, password=PASSWORD):
    """The new member opens the invite email's link and sets a password."""
    page.goto(url)
    page.locator("#id_password").fill(password)
    fill_date_of_birth(page)
    tick(page, "men_only_accepted")
    tick(page, "privacy_accepted")
    page.locator("#register-form button[type=submit]").click()
    try:
        page.wait_for_url(re.compile(r"/account/"))
    except Exception:  # noqa: BLE001
        raise AssertionError(f"Setting up the account did not reach /account/. The form says: {form_errors(page)}") from None


def register_and_verify(w, email, first, last, mob, plan="Tier 1", password=PASSWORD):
    """Register through the real form, confirm the email, and return the page (signed in on /account/)."""
    page = w.page()
    register_member(page, email, first, last, mob, plan_name=plan, password=password)
    verify_email_link(page, mailbox.link(mailbox.wait_for(email, "Confirm your email"), "/verify/"))
    return page


GOLD_MEMBER = {}  # one Gold member made by whichever walk-through needs it first (B or H), reused by the others in this run


def ensure_gold_member(w):
    """A signed-in Gold member (applied, approved by the approver, set a password from the invite). Returns (page, email)."""
    if not GOLD_MEMBER:
        email, first, last, mob = "beta-gold-member@example.com", "Gilbert", "Goldmember", mobile(801)
        apply_gold(w.page(), first, last, email, mob)
        approve_in_office(barry_page(w), approve_link(first, last))
        page = w.page()
        accept_invite(page, mailbox.link(mailbox.wait_for(email, "Gold Card is approved"), "/gold/invite/"))
        GOLD_MEMBER.update(email=email)
        return page, email
    page = w.page()
    sign_in(page, SITE, GOLD_MEMBER["email"], PASSWORD, expect_path="/account/")
    return page, GOLD_MEMBER["email"]


def big_wav(megabytes, rate=8000):
    """A valid mono 16-bit WAV of silence of about this many MB."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(bytes(int(megabytes * 1024 * 1024)))
    return buffer.getvalue()


def raw_html(page, url=None):
    """What the server really sent for this address (not the browser's tidied-up DOM)."""
    return page.context.request.get(url or page.url).text()


def assert_text_not_script(page, where, needle=SCRIPT):
    """Hostile text must come out as plain text: escaped in the source, never a live element, never a dialog."""
    source = raw_html(page)
    assert needle not in source, f"{where}: the server sent the text as live HTML ({needle[:30]}... is in the page source)"
    assert page.locator("body script", has_text="alert(1)").count() == 0, f"{where}: a script element with alert(1) is on the page"


# ---------- A. Gold declined, deeper ----------

def beta_gold_declined(w):
    email, first, last, mob = "beta-declined@example.com", "Declan", "Declinedson", mobile(101)
    visitor = w.page()
    barry = None
    with w.step("Apply for the Gold Card, then the approver declines", visitor):
        apply_gold(visitor, first, last, email, mob)
        link = approve_link(first, last)
        barry = barry_page(w)
        assert post_direct(barry, OFFICE, f"/gold/{application_id(link)}/decline/").status == 302
        assert dbtool("gold", email)["status"] == "declined"
    other = w.page()
    with w.step("Signing in with that email gets nothing: no account", other):
        sign_in_fails(other, SITE, email, PASSWORD)
        assert dbtool("user", email)["exists"] is False
    tier_page = w.page()
    with w.step("Registering a tier with the same email works and gives the tier, not Gold", tier_page):
        register_member(tier_page, email, first, last, mob, plan_name="Tier 2")
        verify_email_link(tier_page, mailbox.link(mailbox.wait_for(email, "Confirm your email"), "/verify/"))
        status = tier_page.locator("[data-status]").first
        assert status.get_attribute("data-status") == "registered", f"Dashboard status is {status.get_attribute('data-status')}"
        assert "Tier 2" in status.inner_text(), f"Dashboard says: {status.inner_text()}"
        tier_page.goto(f"{SITE}/account/membership/")
        assert "Gold Card" not in tier_page.locator("h1").first.inner_text(), "A declined applicant sees the Gold Card"
        assert dbtool("user", email)["plan"] == "tier-2"
    with w.step("The declined application stays declined, in the Office and in the database", barry):
        assert dbtool("gold", email)["status"] == "declined"
        barry.goto(f"{OFFICE}/gold/?status=declined")
        assert barry.locator("[data-gold-row]", has_text=f"{first} {last}").count() == 1
        barry.goto(link)
        assert "declined" in barry.locator("[data-confirm-state]").inner_text().lower(), "The approve page offers to approve a declined application"
    again = w.page()
    with w.step("Applying again later: one waiting application, the old one stays declined, no crash", again):
        dbtool("age-gold", email)  # a real re-apply comes days later; this keeps it outside the two-minute double-click window
        apply_gold(again, first, last, email, mob)
        found = dbtool("gold", email)
        assert found["count"] == 2 and found["waiting"] == 1 and "declined" in found["statuses"], f"Database says {found}"
    with w.step("No approval or invite email was ever sent to this person", again):
        subjects = mailbox.subjects_to(email)
        assert not [s for s in subjects if "approved" in s.lower()], f"An approval email was sent: {subjects}"
        leaked = [m["Subject"] for m in mailbox.messages() if email in mailbox.recipients(m) and "/gold/invite/" in mailbox.body(m)]
        assert not leaked, f"An invite link was emailed to a declined applicant: {leaked}"
        w.info(f"Open question (decline email): emails sent to this declined applicant over the whole scenario: {subjects}")


# ---------- B. Gold links ----------

def beta_gold_links(w):
    email, first, last = "beta-links1@example.com", "Linus", "Linkman"
    email2, first2, last2 = "beta-links2@example.com", "Lars", "Linkdeclined"
    site = w.page()
    with w.step("Set up: a Gold application is waiting", site):
        apply_gold(site, first, last, email, mobile(201))
        url = approve_link(first, last)
        pk = application_id(url)
        assert dbtool("gold", email)["status"] == "new"
    signed_out = w.page()
    with w.step("Signed out: the approve link asks for sign-in and approves nothing", signed_out):
        signed_out.goto(url)
        assert "/login/" in signed_out.url, f"Landed on {signed_out.url}"
        assert dbtool("gold", email)["status"] == "new"
    olive = w.page()
    with w.step("Office level without Approver opens the link: refused (403), nothing approved", olive):
        sign_in(olive, OFFICE, OLIVE["email"], PASSWORD)
        status = olive.goto(url).status
        assert status == 403, f"The approve link answered {status} to someone who is not an Approver (expected 403)"
        assert dbtool("gold", email)["status"] == "new"
    barry = barry_page(w)
    with w.step("The approver taps the link: approved, one invite email", barry):
        approve_in_office(barry, url)
        assert dbtool("gold", email)["status"] == "approved"
        mailbox.wait_for(email, "Gold Card is approved")
    with w.step("The same link a second time, and a second approve request: nothing harmful, still one approval, one invite", barry):
        barry.goto(url)
        barry.wait_for_selector("[data-gold-confirm]")
        assert barry.locator(".o-confirm-go").count() == 0, "The approve page still offers a button after approval"
        assert "already approved" in barry.locator("[data-confirm-state]").inner_text().lower()
        again = post_direct(barry, OFFICE, f"/gold/{pk}/approve/")
        assert again.status in (302, 200), f"A second approve request answered {again.status}"
        found = dbtool("gold", email)
        assert found["statuses"] == ["approved"] and found["invites"] == 1, f"Database says {found}"
        assert mailbox.count_subject(email, "Gold Card is approved") == 1, "More than one invite email was sent"
    invite_url = mailbox.link(mailbox.wait_for(email, "Gold Card is approved"), "/gold/invite/")
    member = w.page()
    with w.step("The invite (set-password) link works once", member):
        accept_invite(member, invite_url)
        assert member.locator("[data-status]").first.get_attribute("data-status") == "gold"
        GOLD_MEMBER.update(email=email)
        assert dbtool("gold", email)["invites_used"] == 1
    with w.step("The same invite link a second time is refused, in the same browser and in a fresh one", member):
        status = member.goto(invite_url).status
        assert status == 410 and member.locator("#id_password").count() == 0, f"Second use of the invite answered {status}"
        fresh = w.page()
        status = fresh.goto(invite_url).status
        assert status == 410 and fresh.locator("#id_password").count() == 0, f"Second use (fresh browser) answered {status}"
        assert dbtool("user", email)["count"] == 1
    other = w.page()
    with w.step("Set up: a second application, declined by the approver", other):
        apply_gold(other, first2, last2, email2, mobile(202))
        url2 = approve_link(first2, last2)
        pk2 = application_id(url2)
        assert post_direct(barry, OFFICE, f"/gold/{pk2}/decline/").status == 302
        assert dbtool("gold", email2)["status"] == "declined"
    with w.step("The approve link after a decline is refused and the application stays declined, with no invite", barry):
        barry.goto(url2)
        barry.wait_for_selector("[data-gold-confirm]")
        assert barry.locator(".o-confirm-go").count() == 0, "A declined application can still be approved from its link"
        assert "declined" in barry.locator("[data-confirm-state]").inner_text().lower()
        forced = post_direct(barry, OFFICE, f"/gold/{pk2}/approve/")
        assert forced.status in (302, 200, 403, 400), f"Forced approve answered {forced.status}"
        found = dbtool("gold", email2)
        assert found["statuses"] == ["declined"] and found["invites"] == 0 and not found["has_user"], f"Database says {found}"
        assert mailbox.find(email2, "approved") is None, "An approval email went to a declined applicant"


# ---------- C. Gold duplicates ----------

def beta_gold_duplicates(w):
    email, first, last, mob = "beta-dupe@example.com", "Duncan", "Duplicate", mobile(301)
    page = w.page()
    with w.step("Apply once", page):
        reference = apply_gold(page, first, last, email, mob)
    for label, typed in (("in CAPITALS", email.upper()), ("with spaces around it", f"  {email}  "), ("exactly the same", email)):
        with w.step(f"Apply again with the same email {label}: still one application", page):
            apply_gold(w.page(), first, last, typed, mob)
            found = dbtool("gold", email)
            assert found["count"] == 1, f"{found['count']} applications exist for one person (typed '{typed}')"
    with w.step("One application means one email to the approver and one thank-you to the applicant", page):
        assert mailbox.count_subject(BARRY, f"Gold Card application: {first} {last}") == 1, "The approver was emailed more than once"
        assert mailbox.count_subject(email, "Gold Card application") == 1, "The applicant was thanked more than once"
        assert "GC-" in reference, f"Odd reference: {reference}"


# ---------- D. Sign-up ----------

def beta_signup(w):
    email, first, last, mob = "beta-signup@example.com", "Sidney", "Signup", mobile(401)
    page = w.page()
    with w.step("Register once", page):
        register_member(page, email, first, last, mob, plan_name="Tier 1")
        verify_url = mailbox.link(mailbox.wait_for(email, "Confirm your email"), "/verify/")
    with w.step("Register the same email again (same details, a double submit): still one account", page):
        register_member(w.page(), email, first, last, mob, plan_name="Tier 1")
        assert dbtool("user", email)["count"] == 1
    with w.step("Register the same email in other capitals with other details: refused clearly, still one account", page):
        second = w.page()
        second.goto(f"{SITE}/register/")
        second.locator("label.plan-chip", has_text="Tier 2").first.click()
        second.locator("#id_first_name").fill("Other")
        second.locator("#id_last_name").fill("Person")
        second.locator("#id_email").fill(email.upper())
        second.locator("#id_mobile").fill(mobile(403))
        second.locator("#id_password").fill(NEW_PASSWORD)
        fill_date_of_birth(second)
        tick(second, "men_only_accepted")
        tick(second, "privacy_accepted")
        second.locator("#register-form button[type=submit]").click()
        lines = problems_modal(second)
        assert any("already registered" in line.lower() for line in lines), f"The problems dialog says: {lines}"
        close_problems(second)
        second.wait_for_selector(".feedback[data-state=error]")
        assert "register/sent" not in second.url
        assert any("already registered" in text.lower() for text in form_errors(second)), f"The form says: {form_errors(second)}"
        assert dbtool("user", email)["count"] == 1
    with w.step("Open the verify link (confirm), then open it again: fine, no error", page):
        verify_email_link(page, verify_url)
        again = w.page()
        status = again.goto(verify_url).status
        assert status == 200, f"A second visit to the verify link answered {status}"
        assert "already confirmed" in body_text(again).lower(), "The replayed link does not say it is already confirmed"
        assert dbtool("user", email)["verified"] is True
    unverified_email = "beta-unverified@example.com"
    with w.step("A tampered verify link is refused clearly and verifies nobody", page):
        stranger = w.page()
        register_member(stranger, unverified_email, "Ulrich", "Unverified", mobile(402), plan_name="Tier 1")
        link = mailbox.link(mailbox.wait_for(unverified_email, "Confirm your email"), "/verify/")
        head, token = link.rstrip("/").rsplit("/", 1)
        tampered = f"{head}/{token[:-3]}{'AAA' if token[-3:] != 'AAA' else 'BBB'}/"  # the signature is the end of the token
        response = stranger.goto(tampered)
        assert response.status == 400, f"A tampered link answered {response.status} (expected 400)"
        assert "not valid" in body_text(stranger).lower(), "The tampered link does not say it is not valid"
        assert dbtool("user", unverified_email)["verified"] is False
    with w.step("Sign in before verifying: allowed (docs), but with the confirm banner", stranger):
        sign_in(stranger, SITE, unverified_email, PASSWORD, expect_path="/account/")
        assert stranger.locator("[data-verify-banner]").count() == 1, "No 'confirm your email' banner for an unverified member"
        assert "Tier 1" in stranger.locator("[data-status]").first.inner_text()
    with w.step("Positive control: a tier member sees the choice tiles on Membership", stranger):
        stranger.goto(f"{SITE}/account/membership/")
        assert stranger.locator("[data-plan-tile]").count() >= 3, "A tier member does not see the plan tiles"


# ---------- E. Passwords ----------

def beta_passwords(w):
    email, first, last = "beta-passwords@example.com", "Percy", "Passwords"
    page = register_and_verify(w, email, first, last, mobile(501))
    unknown = "beta-nobody@example.com"
    asker = w.page()
    texts = {}
    for label, address in (("a known email", email), ("an unknown email", unknown)):
        with w.step(f"Forgot password with {label}", asker):
            asker.goto(f"{SITE}/forgot-password/")
            asker.locator("#id_email").fill(address)
            with asker.expect_navigation():
                asker.locator("form[data-live-validate] button[type=submit]").click()
            texts[label] = " ".join(body_text(asker).split())
            assert "check your email" in texts[label].lower()
    with w.step("The answer is word for word the same, and an unknown email gets no email", asker):
        known, unknown_text = texts["a known email"], texts["an unknown email"]
        assert known == unknown_text, f"The two answers differ:\n  known:   {known[:200]}\n  unknown: {unknown_text[:200]}"
        assert mailbox.count_to(unknown) == 0, "An email was sent to an address with no account"
        mailbox.wait_for(email, "Reset your Spa 99 password")
    reset_url = mailbox.link(mailbox.wait_for(email, "Reset your Spa 99 password"), "/reset/")
    with w.step("Use the reset link once: password changed", asker):
        asker.goto(reset_url)
        asker.locator("#id_password").fill(RESET_PASSWORD)
        with asker.expect_navigation():
            asker.locator("form[data-live-validate] button[type=submit]").click()
        assert "password has been changed" in body_text(asker).lower(), f"Reset failed. {form_errors(asker)}"
    with w.step("Use the same reset link a second time: refused", asker):
        status = asker.goto(reset_url).status
        assert status == 400, f"The used reset link answered {status} (expected 400)"
        assert "expired or was already used" in body_text(asker).lower()
        assert asker.locator("#id_password").count() == 0, "A used reset link still shows the password form"
    with w.step("Only the new password works", asker):
        sign_in_fails(w.page(), SITE, email, PASSWORD)
        sign_in(w.page(), SITE, email, RESET_PASSWORD, expect_path="/account/")
    if not strict_server_up():
        w.info("SKIPPED the rate-limit steps: the strict server (real rate limits) is not running. Start the run with scripts/e2e.sh.")
        return
    thrower = w.page()
    with w.step("Wrong passwords again and again: the 11th attempt is throttled with a message, and the right password is refused too", thrower):
        statuses = []
        for _ in range(11):
            thrower.goto(f"{STRICT_SITE}/login/")
            thrower.locator("input[name=username]").fill(email)
            thrower.locator("input[name=password]").fill("Wrong-Password-1!")
            with thrower.expect_navigation() as nav:
                thrower.locator("form[data-live-validate] button[type=submit]").click()
            statuses.append(nav.value.status)
        assert statuses[:10] == [200] * 10, f"The first ten wrong attempts answered {statuses[:10]}"
        assert statuses[10] == 429, f"The 11th wrong attempt answered {statuses[10]} (expected 429)"
        assert "too many attempts" in body_text(thrower).lower()
        thrower.goto(f"{STRICT_SITE}/login/")
        thrower.locator("input[name=username]").fill(email)
        thrower.locator("input[name=password]").fill(RESET_PASSWORD)
        with thrower.expect_navigation() as nav:
            thrower.locator("form[data-live-validate] button[type=submit]").click()
        assert nav.value.status == 429 and "/login/" in thrower.url, "The right password got in while throttled"
    with w.step("Forgot password asked six times in a row: the sixth is throttled", thrower):
        answers = []
        for _ in range(6):
            thrower.goto(f"{STRICT_SITE}/forgot-password/")
            thrower.locator("#id_email").fill(unknown)
            with thrower.expect_navigation() as nav:
                thrower.locator("form[data-live-validate] button[type=submit]").click()
            answers.append(nav.value.status)
        assert answers == [200] * 5 + [429], f"Answers were {answers}"
        assert mailbox.count_to(unknown) == 0


# ---------- F. Delete, then register again ----------

def beta_delete_reregister(w):
    email, first, last, mob = "beta-again@example.com", "Alfie", "Again", mobile(601)
    page = register_and_verify(w, email, first, last, mob, plan="Tier 3")
    with w.step("The same person applies for Gold and is approved: Gold is added to the existing account", page):
        apply_gold(w.page(), first, last, email, mob)
        approve_in_office(barry_page(w), approve_link(first, last))
        page.goto(f"{SITE}/account/")
        assert page.locator("[data-status]").first.get_attribute("data-status") == "gold"
        assert dbtool("user", email)["plan"] == "gold" and dbtool("gold", email)["status"] == "approved"
    with w.step("Delete the account (password, then confirm)", page):
        page.goto(f"{SITE}/account/you/")
        page.locator("[data-delete-open]").click()
        page.locator("#delete-password").fill(PASSWORD)
        page.locator("#delete-form button[data-confirm]").click()
        confirm_office_modal(page)
        page.wait_for_selector("h1:has-text('Account deleted')")
        assert dbtool("user", email)["exists"] is False
        assert dbtool("gold", email)["count"] == 0, "The Gold application survived the deletion"
    fresh = w.page()
    with w.step("Register the same email again with another password: a clean new account", fresh):
        register_member(fresh, email, first, last, mob, plan_name="Tier 1", password=NEW_PASSWORD)
        verify_email_link(fresh, mailbox.link(mailbox.wait_for(email, "Confirm your email"), "/verify/"))
    with w.step("The new account has no old membership and no Gold", fresh):
        status = fresh.locator("[data-status]").first
        assert status.get_attribute("data-status") == "registered", f"Status is {status.get_attribute('data-status')}"
        assert "Tier 1" in status.inner_text() and "Tier 3" not in status.inner_text()
        info = dbtool("user", email)
        assert info["plan"] == "tier-1" and info["count"] == 1, f"Database says {info}"
        found = dbtool("gold", email)
        assert found["count"] == 0 and found["invites"] == 0, f"Old Gold data is back: {found}"
    with w.step("The old password no longer works; the new one does", fresh):
        sign_in_fails(w.page(), SITE, email, PASSWORD)
        sign_in(w.page(), SITE, email, NEW_PASSWORD, expect_path="/account/")


# ---------- G. Who may open what ----------

def beta_access(w):
    email, first, last = "beta-member@example.com", "Marcus", "Memberman"
    member = register_and_verify(w, email, first, last, mobile(701), plan="Tier 1")
    with w.step("Positive control: the member's own Membership screen shows the plan tiles", member):
        member.goto(f"{SITE}/account/membership/")
        assert member.locator("[data-plan-tile]").count() >= 3
    with w.step("A member signed in on the website is not signed in on the Office address (no session carries over)", member):
        member.goto(f"{OFFICE}/")
        assert "/login/" in member.url, f"Office answered a website session with {member.url}"
    for label, base, paths in (("Office", OFFICE, ("/", "/people/", "/gold/", "/analytics/")),
                               ("Control", CONTROL, ("/", "/rooms/", "/library/"))):
        page = w.page()
        with w.step(f"A member who signs in on the {label} address gets a plain 404 on every page", page):
            sign_in(page, base, email, PASSWORD)
            wrong = {path: page.goto(base + path).status for path in paths}
            assert all(code == 404 for code in wrong.values()), f"Expected 404 everywhere; got {wrong}"
    system = w.page()
    with w.step("A member cannot sign in on System, and its pages answer 404", system):
        system.goto(f"{SYSTEM}/login/")
        system.locator("input[name=username]").fill(email)
        system.locator("input[name=password]").fill(PASSWORD)
        with system.expect_navigation():
            system.locator("[data-system-signin] button[type=submit]").click()
        assert "/login/" in system.url and system.locator("[data-system-error]").count() == 1
        wrong = {path: system.goto(SYSTEM + path).status for path in ("/", "/plans/", "/team/")}
        assert all(code == 404 for code in wrong.values()), f"Expected 404 everywhere; got {wrong}"
    office_level = w.page()
    with w.step("Office level (view only) opens Control: plain 404 (Control needs Admin)", office_level):
        sign_in(office_level, CONTROL, OLIVE["email"], PASSWORD)
        wrong = {path: office_level.goto(CONTROL + path).status for path in ("/", "/rooms/", "/library/")}
        assert all(code == 404 for code in wrong.values()), f"Expected 404 everywhere; got {wrong}"
    with w.step("Office level cannot use System either: sign-in refused, 404 pages", office_level):
        office_level.goto(f"{SYSTEM}/login/")
        office_level.locator("input[name=username]").fill(OLIVE["email"])
        office_level.locator("input[name=password]").fill(PASSWORD)
        with office_level.expect_navigation():
            office_level.locator("[data-system-signin] button[type=submit]").click()
        assert "/login/" in office_level.url and office_level.locator("[data-system-error]").count() == 1
        assert office_level.goto(f"{SYSTEM}/plans/").status == 404
    signed_out = w.page()
    with w.step("Signed out: /account/ shows the sign-in page, Office and Control ask to sign in, System answers 404", signed_out):
        signed_out.goto(f"{SITE}/account/")
        assert "/login/" in signed_out.url and signed_out.locator("input[name=username]").count() == 1, f"Landed on {signed_out.url}"
        for base, path in ((OFFICE, "/"), (OFFICE, "/people/"), (CONTROL, "/"), (CONTROL, "/library/")):
            signed_out.goto(base + path)
            assert "/login/" in signed_out.url, f"{base}{path} signed out landed on {signed_out.url}"
        wrong = {path: signed_out.goto(SYSTEM + path).status for path in ("/", "/plans/", "/changes/")}
        assert all(code == 404 for code in wrong.values()), f"System signed out: expected 404 everywhere; got {wrong}"


# ---------- H. A Gold member cannot change tier ----------

def beta_gold_lock(w):
    page, email = ensure_gold_member(w)
    with w.step("The dashboard shows a Gold member", page):
        assert page.locator("[data-status]").first.get_attribute("data-status") == "gold"
        assert dbtool("user", email)["plan"] == "gold"
    with w.step("No way to change tier in the screens: no plan tiles, no interest form, no plan radios", page):
        for path in ("/account/", "/account/membership/", "/account/book/", "/account/you/"):
            page.goto(SITE + path)
            found = page.locator("[data-interest], [data-plan-tile], input[name=plan]").count()
            assert found == 0, f"{path} has {found} tier-choice control(s) for a Gold member"
        page.goto(f"{SITE}/account/membership/")
        assert "Gold Card" in page.locator("h1").first.inner_text()
    with w.step("A tampered form post (a tier chosen anyway) changes nothing", page):
        for slug in ("tier-1", "tier-2", "tier-3"):
            response = post_direct(page, SITE, "/account/interest/", form={"plan": slug})
            assert response.status in (302, 400, 403, 405), f"Choosing {slug} answered {response.status}"
            assert dbtool("user", email)["plan"] == "gold", f"A Gold member was moved to {slug}"
    with w.step("The same through the browser: a tier form injected into the page and submitted", page):
        page.goto(f"{SITE}/account/membership/")
        token = csrf_for(page, SITE)
        with page.expect_navigation():
            page.evaluate(
                """token => { const f = document.createElement('form'); f.method = 'post'; f.action = '/account/interest/';
                   f.innerHTML = '<input name="csrfmiddlewaretoken"><input name="plan" value="tier-1">';
                   f.elements.csrfmiddlewaretoken.value = token; document.body.append(f); f.submit(); }""", token)
        page.goto(f"{SITE}/account/membership/")
        assert "Gold Card" in page.locator("h1").first.inner_text(), "The membership screen no longer shows Gold"
        assert dbtool("user", email)["plan"] == "gold"


# ---------- I. The journey: refresh, Back, restart, jumping ahead ----------

def _pick_all(page):
    """On a journey screen: choose the first option of every question that has no answer yet (each tap is saved, so wait for it)."""
    for _ in range(5):
        unanswered = page.locator("fieldset[data-question]:not([hidden])").filter(has_not=page.locator("input:checked"))
        if not unanswered.count():
            return
        with page.expect_response(lambda r: "/journey/answer/" in r.url):
            unanswered.first.locator("label.tile, label.seg").first.click()


def _journey_heading(page):
    page.wait_for_selector("[data-flow-root] .screen, [data-flow-root] .result")
    return page.locator("[data-flow-root] h1").first.inner_text()


def _checked(page, key):
    return page.locator(f"fieldset[data-question={key}] input:checked").count()


def beta_journey(w):
    page = w.page()
    with w.step("Answer the first screen and continue to the second", page):
        page.goto(f"{SITE}/journey/")
        first_heading = _journey_heading(page)
        _pick_all(page)
        page.locator("[data-primary]").click()
        page.wait_for_url(re.compile(r"/journey/what-draws-you/"))
        page.wait_for_function("old => document.querySelector('[data-flow-root] h1')?.textContent !== old", arg=first_heading)
        second_heading = _journey_heading(page)
        _pick_all(page)
        assert _checked(page, "facilities") >= 1
    with w.step("Refresh in the middle: same screen, answers still shown", page):
        page.wait_for_timeout(500)  # let the last tap finish saving, like a person pausing
        page.reload()
        assert _journey_heading(page) == second_heading, "A refresh moved the person to another screen"
        assert "/journey/what-draws-you/" in page.url
        assert _checked(page, "facilities") >= 1, "The facility answer was lost on refresh"
    with w.step("Browser Back returns to the first screen with its answers; Forward returns to the second", page):
        page.go_back()
        page.wait_for_url(re.compile(r"/journey/your-time/"))
        assert _journey_heading(page) == first_heading
        assert _checked(page, "time") >= 1, "The 'when' answer is gone after Back"
        assert page.locator("[data-flow-root] .flow-loading").count() == 0, "A loading screen is stuck after Back"
        page.go_forward()
        page.wait_for_url(re.compile(r"/journey/what-draws-you/"))
        assert _journey_heading(page) == second_heading
        assert _checked(page, "facilities") >= 1
    with w.step("Start again: the first screen, no answers, no 'Start again' link", page):
        page.go_back()
        page.wait_for_url(re.compile(r"/journey/your-time/"))
        _journey_heading(page)
        page.locator("[data-restart]").click()
        page.wait_for_function("document.querySelectorAll('fieldset[data-question] input:checked').length === 0")
        assert "/journey/your-time/" in page.url
        assert page.locator("[data-restart]").count() == 0, "'Start again' is still offered on an empty journey"
        page.reload()
        _journey_heading(page)
        assert _checked(page, "time") == 0, "The old answers came back after a restart and a refresh"
    fresh = w.page()
    with w.step("Jumping straight to the result by address, with no answers: sent back to the first screen, no result shown", fresh):
        fresh.goto(f"{SITE}/journey/your-membership/")
        fresh.wait_for_url(re.compile(r"/journey/your-time/"))
        assert _journey_heading(fresh)
        assert fresh.locator(".result-tier").count() == 0, "A result was shown without the required answers"
    with w.step("Jumping to the last question screen and pressing on: required answers still cannot be skipped", fresh):
        fresh.goto(f"{SITE}/journey/about-you/")
        _journey_heading(fresh)
        fresh.wait_for_timeout(1000)  # the app may already send him back to the first screen (it does), which is right
        if "/journey/your-time/" not in fresh.url:
            fresh.locator("[data-primary]").click()
            fresh.wait_for_url(re.compile(r"/journey/your-time/"))
        assert fresh.locator(".result-tier").count() == 0, "The result was reached by skipping required answers"
        assert fresh.locator("[data-primary][aria-disabled=true]").count() == 1, "The first screen does not show that an answer is still needed"


# ---------- J. Bad input and hostile text ----------

def _fill_register(page, email, first, last, mob, plan="Tier 1", password=PASSWORD):
    page.goto(f"{SITE}/register/")
    page.locator("label.plan-chip", has_text=plan).first.click()
    page.locator("#id_first_name").fill(first)
    page.locator("#id_last_name").fill(last)
    page.locator("#id_email").fill(email)
    page.locator("#id_mobile").fill(mob)
    page.locator("#id_password").fill(password)
    fill_date_of_birth(page)
    tick(page, "men_only_accepted")
    tick(page, "privacy_accepted")


def beta_bad_input(w):
    w.watch_dialogs = True
    page = w.page()
    baseline = {}
    with w.step("Register: empty form is refused with several clear messages and creates nothing", page):
        baseline["registrations"] = dbtool("registrations")["count"]
        page.goto(f"{SITE}/register/")
        page.locator("#register-form button[type=submit]").click()
        lines = problems_modal(page)
        assert len(lines) >= 4 and "register/sent" not in page.url, f"The problems dialog says: {lines}"
        close_problems(page)
        errors = form_errors(page)
        assert len(errors) >= 4, f"The form says: {errors}"
        assert dbtool("registrations")["count"] == baseline["registrations"]
    for label, overrides, expected in (
        ("a bad email", {"email": "not-an-email"}, "valid email"),
        ("a bad UK mobile", {"mob": "12345"}, "valid uk mobile"),
        ("a 300 character first name", {"first": "A" * 300}, "too long"),
    ):
        with w.step(f"Register: {label} is refused with a clear message", page):
            values = {"email": "beta-bad@example.com", "first": "Barnaby", "last": "Badinput", "mob": mobile(901), **overrides}
            _fill_register(page, values["email"], values["first"], values["last"], values["mob"])
            page.locator("#register-form button[type=submit]").click()
            lines = problems_modal(page)
            assert expected in " ".join(lines).lower(), f"Expected a message with '{expected}', the dialog says {lines}"
            close_problems(page)
            assert expected in " ".join(form_errors(page)).lower(), f"Expected a message with '{expected}', the form says {form_errors(page)}"
            assert "register/sent" not in page.url
            assert dbtool("registrations")["count"] == baseline["registrations"]
    with w.step("Register: straight to the server with nothing valid (no page): 400, not a crash, nothing created", page):
        page.goto(f"{SITE}/register/")
        response = post_direct(page, SITE, "/register/", form={"email": "x", "first_name": "", "mobile": "1", "password": "a"})
        assert response.status == 400, f"A bad direct sign-up answered {response.status} (expected 400)"
        assert dbtool("registrations")["count"] == baseline["registrations"]
    with w.step("Register: emoji and accents in the names are accepted safely", page):
        register_member(page, "beta-emoji@example.com", "Zoë 🧔", "Müller-Ö 🧖", mobile(902), plan_name="Tier 1")
    with w.step("Register: a name that is a script tag is accepted as plain text (no dialog), the verify email escapes it", page):
        email = "beta-script@example.com"
        register_member(page, email, SCRIPT, "Scripty", mobile(903), plan_name="Tier 1")
        message = mailbox.wait_for(email, "Confirm your email")
        assert SCRIPT not in mailbox.html_body(message), "The verify email's HTML carries the script tag as live HTML"
        assert "&lt;script&gt;" in mailbox.html_body(message), "The script text is not shown (escaped) in the email"
        verify_email_link(page, mailbox.link(message, "/verify/"))
        assert_text_not_script(page, "The member dashboard")
        page.wait_for_timeout(300)
    office = w.page()
    with w.step("Office: the person page shows the names as plain text and nothing runs", office):
        sign_in(office, OFFICE, OLIVE["email"], PASSWORD)
        office.goto(f"{OFFICE}/people/")
        row = office.locator("[data-person-row]", has_text="beta-script@example.com").first
        row.wait_for()
        with office.expect_navigation():
            row.locator("a.o-rowlink").click()
        assert SCRIPT in office.locator("h1").inner_text(), f"The page heading is: {office.locator('h1').inner_text()}"
        assert_text_not_script(office, "The Office person page")
        office.goto(f"{OFFICE}/people/")
        assert_text_not_script(office, "The Office People list")
    gold = w.page()
    with w.step("Gold apply: empty, bad email, bad mobile and a 300 character name are refused with clear messages", gold):
        total = dbtool("gold-total")["count"]
        gold_to_last_screen(gold)
        gold.locator("[data-primary]").click()
        lines = problems_modal(gold)
        assert len(lines) >= 3, f"The empty form's dialog says: {lines}"
        close_problems(gold)
        assert len(form_errors(gold)) >= 3, f"The empty form says: {form_errors(gold)}"
        gold_fill_you(gold, "Gus", "Goldbad", "nope", "123")
        gold.locator("[data-primary]").click()
        lines = problems_modal(gold)
        assert any("valid email" in line.lower() for line in lines), f"The dialog says: {lines}"
        close_problems(gold)
        gold.wait_for_selector("[data-error-for=email][data-state=error]")
        text = " ".join(form_errors(gold)).lower()
        assert "valid email" in text and "valid uk mobile" in text, f"The form says: {form_errors(gold)}"
        gold_fill_you(gold, "A" * 300, "Goldbad", "beta-goldbad@example.com", mobile(904))
        gold.locator("[data-primary]").click()
        assert any("too long" in line.lower() for line in problems_modal(gold))
        close_problems(gold)
        gold.wait_for_selector("[data-error-for=first_name][data-state=error]")
        assert "too long" in " ".join(form_errors(gold)).lower()
        assert dbtool("gold-total")["count"] == total, "A refused application was saved"
        assert gold.locator(".gold-sent").count() == 0, "A refused application shows the 'sent' screen"
    with w.step("Gold apply: straight to the server with bad data (no page): 400 with field errors, never a crash", gold):
        bad = post_direct(gold, SITE, "/gold/apply/", json_body={"first_name": "", "last_name": "x", "email": "bad", "mobile": "1", "privacy_accepted": False})
        assert bad.status == 400 and {"first_name", "email", "mobile", "industry"} <= set(bad.json()["errors"]), f"{bad.status} {bad.text()[:200]}"
        assert post_direct(gold, SITE, "/gold/apply/", json_body=[1, 2, 3]).status == 400
        assert dbtool("gold-total")["count"] == total
    with w.step("Gold apply: a script tag as the last name and in the note is accepted as plain text", gold):
        email = "beta-goldscript@example.com"
        apply_gold(w.page(), "Sam", SCRIPT, email, mobile(905), note="<img src=x onerror=alert(1)> and <b>bold</b>")
        message = mailbox.wait_for(BARRY, "Gold Card application: Sam")
        html_part = mailbox.html_body(message)
        assert SCRIPT not in html_part and "<img src=x" not in html_part, "The approver's email carries hostile text as live HTML"
        assert "&lt;script&gt;" in html_part, "The name is not shown (escaped) in the approver's email"
        approver = barry_page(w)
        link = mailbox.link(message, "/approve/confirm/")
        for url in (link, f"{OFFICE}/gold/{application_id(link)}/"):
            approver.goto(url)
            assert_text_not_script(approver, f"Office page {url.split('/')[-2]}")
            assert_text_not_script(approver, f"Office page {url.split('/')[-2]}", needle="<img src=x")
        assert SCRIPT in approver.locator("body").inner_text(), "The name does not show as plain text in the Office"


# ---------- K. Double submit ----------

def beta_double_submit(w):
    w.watch_dialogs = True
    page = w.page()
    email = "beta-double@example.com"
    with w.step("Register: double-click the button: exactly one account, one verification email", page):
        _fill_register(page, email, "Dexter", "Doubleclick", mobile(1001))
        page.locator("#register-form button[type=submit]").dblclick()
        page.wait_for_url(re.compile(r"/register/sent/"))
        page.wait_for_timeout(800)
        assert dbtool("user", email)["count"] == 1
        assert mailbox.count_subject(email, "Confirm your email") == 1, f"{mailbox.count_subject(email, 'Confirm your email')} verification emails"
    with w.step("Register: two requests sent at the same instant (another email): still one account", page):
        email2 = "beta-double2@example.com"
        _fill_register(page, email2, "Dexter", "Twice", mobile(1002))
        results = page.evaluate(
            """async () => { const body = () => new URLSearchParams(new FormData(document.getElementById('register-form')));
               const send = () => fetch('/register/', {method: 'POST', body: body(), redirect: 'manual', credentials: 'same-origin'});
               const out = await Promise.all([send(), send(), send()]); return out.map(r => r.status || r.type); }""")
        assert not [r for r in results if isinstance(r, int) and r >= 500], f"A request crashed: {results}"
        assert dbtool("user", email2)["count"] == 1, f"{dbtool('user', email2)['count']} accounts from one sign-up sent three times"
    gold_page = w.page()
    gold_email = "beta-golddouble@example.com"
    with w.step("Gold apply: double-click Send: exactly one application", gold_page):
        gold_to_last_screen(gold_page)
        gold_fill_you(gold_page, "Dexter", "Goldclick", gold_email, mobile(1003))
        gold_page.locator("[data-primary]").dblclick()
        gold_page.wait_for_selector(".gold-sent")
        gold_page.wait_for_timeout(800)
        assert dbtool("gold", gold_email)["count"] == 1, f"{dbtool('gold', gold_email)['count']} applications"
    with w.step("Gold apply: three requests at the same instant (another email): still one application", gold_page):
        racer = "beta-goldrace@example.com"
        gold_to_last_screen(gold_page)
        token = csrf_for(gold_page, SITE)
        body = {"first_name": "Rory", "last_name": "Racer", "email": racer, "mobile": mobile(1004), "industry": "finance", "privacy_accepted": True}
        results = gold_page.evaluate(
            """async ([token, body]) => { const send = () => fetch('/gold/apply/', {method: 'POST', credentials: 'same-origin',
                 headers: {'Content-Type': 'application/json', 'X-CSRFToken': token}, body: JSON.stringify(body)});
               const out = await Promise.all([send(), send(), send()]); return out.map(r => r.status); }""", [token, body])
        assert all(code == 201 for code in results), f"Statuses: {results}"
        assert dbtool("gold", racer)["count"] == 1, f"{dbtool('gold', racer)['count']} applications from one application sent three times at once"
        assert mailbox.count_subject(BARRY, "Gold Card application: Rory") == 1, "The approver was emailed more than once"


# ---------- L. Office counting: staff and bots are not counted ----------

def _dashboard_figures(office):
    office.goto(f"{OFFICE}/")
    office.wait_for_selector("[data-ring=journeys_started] [data-ring-value]")
    read = lambda key: int(office.locator(f"[data-ring={key}] [data-ring-value]").get_attribute("data-count"))  # noqa: E731
    return read("journeys_started"), read("journeys_completed")


def _rebuild():
    code, output = manage("rebuild_metrics")
    assert code == 0, output[-500:]


def beta_counting(w):
    # Playwright's headless browser says "HeadlessChrome" in its user agent, which the site (rightly) counts as a bot: use a normal one.
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    office = w.page()
    with w.step("Baseline: rebuild the stored figures and read the Dashboard", office):
        sign_in(office, OFFICE, OLIVE["email"], PASSWORD)
        _rebuild()
        started, finished = _dashboard_figures(office)
    staff = w.page(user_agent=ua)
    with w.step("A staff account (Office level) does the whole journey", staff):
        sign_in(staff, SITE, OLIVE["email"], PASSWORD)
        assert answer_journey(staff).strip()
    bot = w.page(user_agent="Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)")
    with w.step("Googlebot visits and does the whole journey", bot):
        assert answer_journey(bot).strip()
    with w.step("After a rebuild the Dashboard figures are exactly the same: neither was counted", office):
        _rebuild()
        now = _dashboard_figures(office)
        assert now == (started, finished), f"Started/finished were {(started, finished)}, now {now}: a staff or bot journey was counted"
    visitor = w.page(user_agent=ua)
    with w.step("Control: a normal visitor does the journey and counts as one started, one finished", visitor):
        assert answer_journey(visitor).strip()
        _rebuild()
        now = _dashboard_figures(office)
        assert now == (started + 1, finished + 1), f"Expected {(started + 1, finished + 1)} after one real visitor, got {now}"


# ---------- M. System refusals ----------

def beta_system_refusals(w):
    page = w.page()
    with w.step("Developer signs in on System (still locked)", page):
        page.goto(f"{SYSTEM}/login/")
        page.locator("input[name=username]").fill(DEV["email"])
        page.locator("input[name=password]").fill(PASSWORD)
        with page.expect_navigation():
            page.locator("[data-system-signin] button[type=submit]").click()
        assert "/login/" not in page.url
    failed_before = dbtool("events", "unlock_failed")["count"]
    with w.step("Wrong lock code and wrong password, several times: always the same refusal, still locked", page):
        page.goto(f"{SYSTEM}/plans/")
        page.wait_for_selector("[data-system-unlock]")
        for password, code in ((PASSWORD, "000000"), (PASSWORD, "111111"), (PASSWORD, "123456"), ("Wrong-Password-1!", UNLOCK_CODE), ("Wrong-Password-1!", "000000")):
            page.locator("[data-system-unlock] input[name=password]").fill(password)
            page.locator("[data-system-unlock] input[name=code]").fill(code)
            with page.expect_navigation():
                page.locator("[data-system-unlock] button[type=submit]").click()
            assert "wrong" in page.locator("[data-system-error]").inner_text().lower(), f"No refusal for {password!r} / {code!r}"
            lines = problems_modal(page)  # the same refusal, listed in the shared dialog; closing it keeps the form
            assert any("wrong" in line.lower() for line in lines), f"The problems dialog says: {lines}"
            close_problems(page)
            assert page.locator("[data-system-unlock]").count() == 1
        page.goto(f"{SYSTEM}/plans/")
        assert page.locator("[data-system-plans]").count() == 0, "System opened after wrong codes"
    with w.step("Every failure is in the audit events (unlock_failed), and the audit chain is still intact", page):
        assert dbtool("events", "unlock_failed")["count"] - failed_before == 5, "Not every failed unlock was logged"
        code, output = manage("verify_audit_log")
        assert code == 0, output[-400:]
    with w.step("Unlock with the right password and code", page):
        page.goto(f"{SYSTEM}/plans/")
        page.locator("[data-system-unlock] input[name=password]").fill(PASSWORD)
        page.locator("[data-system-unlock] input[name=code]").fill(UNLOCK_CODE)
        with page.expect_navigation():
            page.locator("[data-system-unlock] button[type=submit]").click()
        page.wait_for_selector("[data-system-plans]")
    before = dbtool("price", "tier-2")["price"]
    for label, typed in (("a negative price", "-5"), ("letters as a price", "abc"), ("a price with too many digits", "99999999")):
        with w.step(f"Save {label}: refused with a message, the price is unchanged", page):
            page.goto(f"{SYSTEM}/plans/")
            page.wait_for_selector("[data-system-plans]")
            page.locator('tr[data-system-plan="tier-2"] input[aria-label="Price ex VAT"]').fill(typed)
            page.wait_for_selector("[data-system-savebar]:not([hidden])")
            page.locator("[data-system-save]").click()
            page.wait_for_selector("dialog.fb-modal[open]")
            with page.expect_navigation() as nav:
                page.locator("dialog.fb-modal[open] [data-fb-ok]").click()
            assert nav.value.status == 400, f"Saving '{typed}' answered {nav.value.status} (expected 400)"
            assert page.locator(".sys-rowerr").count() >= 1 and page.locator(".sys-rowerr").first.inner_text().strip(), "No error message is shown"
            lines = problems_modal(page)  # the failed row is listed in the shared dialog too
            assert any("price ex vat" in line.lower() for line in lines), f"The problems dialog says: {lines}"
            close_problems(page)
            assert dbtool("price", "tier-2")["price"] == before, f"The price changed to {dbtool('price', 'tier-2')['price']}"


# ---------- N. Control Library refusals (strict server) ----------

def beta_library_refusals(w):
    if not strict_server_up():
        w.info("SKIPPED: the strict server (1 MB audio limit, tiny Library) is not running. Start the run with scripts/e2e.sh.")
        return
    page = w.page()
    with w.step("Admin signs in on the strict Control address and opens the Library", page):
        sign_in(page, CONTROL, ADMIN["email"], PASSWORD)  # the strict server's own sign-in is already throttled by walk 14; the session cookie is shared (same host name, same database)
        page.goto(f"{STRICT_CONTROL}/library/")
        page.wait_for_selector("input[data-lib-input]", state="attached")
        page.wait_for_function("!document.body.textContent.includes('Loading the Library')")  # sizes and limits are known to the page
        assets = dbtool("assets")["count"]

    def upload(name, mime, data):
        page.locator("input[data-lib-input]").set_input_files(files=[{"name": name, "mimeType": mime, "buffer": data}])

    with w.step("A text file renamed .mp3 is refused (the server reads the bytes, not the name)", page):
        upload("not-music.mp3", "audio/mpeg", b"This is plain text, not music.\n" * 20)
        page.wait_for_selector(".ctl-up-error:has-text(\"can't be used\")")
        refused = post_direct(page, STRICT_CONTROL, "/library/assets/upload/", multipart={"file": {"name": "not-music.mp3", "mimeType": "audio/mpeg", "buffer": b"plain text\n" * 20}}, accept="application/json")
        assert refused.status == 415, f"The server answered {refused.status} to a text file named .mp3 (expected 415)"
        assert dbtool("assets")["count"] == assets
    with w.step("A 1.5 MB WAV over the 1 MB limit is refused with a clear message, in the page and by the server", page):
        data = big_wav(1.5)
        upload("too-big.wav", "audio/wav", data)
        page.wait_for_selector(".ctl-up-error:has-text('up to 1 MB')")
        refused = post_direct(page, STRICT_CONTROL, "/library/assets/upload/", multipart={"file": {"name": "too-big.wav", "mimeType": "audio/wav", "buffer": data}}, accept="application/json")
        assert refused.status == 413 and "1 MB" in refused.json()["error"], f"{refused.status} {refused.text()[:200]}"
        assert dbtool("assets")["count"] == assets
    with w.step("A small valid WAV is refused because the Library is full", page):
        upload("small.wav", "audio/wav", wav_bytes())
        page.wait_for_selector(".ctl-up-error:has-text('Library is full')")
        refused = post_direct(page, STRICT_CONTROL, "/library/assets/upload/", multipart={"file": {"name": "small.wav", "mimeType": "audio/wav", "buffer": wav_bytes()}}, accept="application/json")
        assert refused.status == 413 and "full" in refused.json()["error"].lower(), f"{refused.status} {refused.text()[:200]}"
        assert dbtool("assets")["count"] == assets


# ---------- O. Every email in the whole run ----------

FORBIDDEN = [(r"\{\{", "{{"), (r"\{%", "{%"), (r"\{[a-z_]+\}", "{placeholder}"), (r"\bNone\b", "None"), (r"\[", "["), (r"TODO", "TODO"), (r"\bundefined\b", "undefined")]
GREETING = re.compile(r"^\s*(hello|hi|dear)\s*[,!.]", re.I | re.M)
ONE_TIME = ("/verify/", "/reset/", "/gold/invite/")


def _visible_text(html_part):
    """The words a person reads in the HTML part (no comments, styles or tags)."""
    cleaned = re.sub(r"<!--.*?-->", " ", html_part, flags=re.S)
    cleaned = re.sub(r"<(style|head|script)\b.*?</\1>", " ", cleaned, flags=re.S | re.I)
    return htmllib.unescape(re.sub(r"<[^>]+>", " ", cleaned))


def _links(message):
    html_part, text_part = mailbox.html_body(message), mailbox.text_body(message)
    hrefs = [htmllib.unescape(h) for h in re.findall(r"""href=["']([^"']*)["']""", html_part)]
    in_text = [u.rstrip(".,);") for u in mailbox.URL.findall(text_part)]
    return hrefs, in_text


def _expected_host(path, subject):
    if re.match(r"^/gold/[0-9a-f-]{36}/", path) or ("added to the Spa 99 team" in subject and path in ("", "/")):
        return f"office.localhost:{PORT}"
    return f"localhost:{PORT}"


def _get(url):
    """GET an address without following redirects (connecting to this Mac, with the address's own Host header)."""
    parts = urlsplit(url)
    connection = http.client.HTTPConnection("127.0.0.1", parts.port or 80, timeout=20)
    try:
        connection.request("GET", (parts.path or "/") + (f"?{parts.query}" if parts.query else ""), headers={"Host": parts.netloc, "Accept": "text/html"})
        response = connection.getresponse()
        response.read()
        return response.status, response.getheader("Location", "")
    finally:
        connection.close()


def beta_emails(w):
    messages = mailbox.messages()
    page = w.page()
    page.goto("about:blank")
    with w.step(f"Collect every email sent in this run ({len(messages)} so far)", page):
        if not messages:
            w.info("No emails exist yet: run the whole suite (scripts/e2e.sh) so this walk-through has something to check.")
            return
    problems = []
    with w.step("Every email has a subject, both a text and an HTML part, a Reply-To, and no broken placeholder", page):
        for message in messages:
            subject, to = str(message["Subject"] or ""), mailbox.recipients(message).strip()
            label = f"'{subject[:60]}' to {to}"
            text_part, html_part = mailbox.text_body(message), mailbox.html_body(message)
            if not subject.strip() or not text_part.strip() or not html_part.strip():
                problems.append(f"{label}: missing subject, text part or HTML part")
            if not message["Reply-To"]:
                problems.append(f"{label}: no Reply-To")
            for source, text in (("subject", subject), ("text", text_part), ("html", _visible_text(html_part))):
                for pattern, name in FORBIDDEN:
                    if re.search(pattern, text):
                        problems.append(f"{label}: '{name}' in the {source}")
            for source, text in (("text", text_part), ("html", _visible_text(html_part))):
                if GREETING.search(text):
                    problems.append(f"{label}: the greeting has no name in the {source}")
        assert not problems, "\n".join(dict.fromkeys(problems))
    with w.step("Every link is absolute (or mailto:) and on the right host for its purpose", page):
        for message in messages:
            subject = str(message["Subject"] or "")
            hrefs, in_text = _links(message)
            for url in [*hrefs, *in_text]:
                if url.startswith("mailto:"):
                    continue
                parts = urlsplit(url)
                if parts.scheme not in ("http", "https") or not parts.netloc:
                    problems.append(f"'{subject[:50]}': not an absolute link: {url[:80]}")
                    continue
                want = _expected_host(parts.path, subject)
                if parts.netloc != want:
                    problems.append(f"'{subject[:50]}': {url[:90]} is on {parts.netloc}, expected {want}")
        assert not problems, "\n".join(dict.fromkeys(problems))
    with w.step("The key links (verify, reset, invite, approve) are the same in the text and in the HTML part", page):
        for message in messages:
            hrefs, in_text = _links(message)
            key = lambda urls: sorted({u for u in urls if any(k in u for k in (*ONE_TIME, "/approve/confirm/"))})  # noqa: E731
            if key(hrefs) != key(in_text) and key(in_text):
                problems.append(f"'{message['Subject']}': text links {key(in_text)} differ from HTML links {key(hrefs)}")
        assert not problems, "\n".join(dict.fromkeys(problems))
    with w.step("Every link opens: 200 or a redirect (one-time links already used or replaced may say so with 400/410)", page):
        seen, used = {}, 0
        for message in messages:
            hrefs, in_text = _links(message)
            for url in dict.fromkeys([*hrefs, *in_text]):
                if url.startswith("mailto:") or url in seen:
                    continue
                status, location = _get(url)
                seen[url] = status
                path = urlsplit(url).path
                if status in (400, 410) and any(k in path for k in ONE_TIME):
                    used += 1  # a spent or superseded one-time link: refused cleanly, which is right (structure was checked above)
                elif not (status == 200 or status in (301, 302, 303, 307, 308) and location):
                    problems.append(f"{url[:100]} answered {status}")
        assert not problems, "\n".join(dict.fromkeys(problems))
        w.info(f"{len(seen)} distinct links opened; {used} were one-time links already used or replaced (refused cleanly)")


BETA_WALKS = [
    ("beta_gold_declined", "10. Gold declined, deeper: no sign-in, tier not Gold, re-apply, no approval email", beta_gold_declined, ()),
    ("beta_gold_links", "11. Gold links: approve twice, after decline, wrong person, signed out; invite used twice", beta_gold_links, HTTP_4XX),
    ("beta_gold_duplicates", "12. Gold duplicates: same email, capitals, spaces: one application", beta_gold_duplicates, ()),
    ("beta_signup", "13. Sign-up: same email twice, verify twice, tampered link, sign in before verifying", beta_signup, HTTP_4XX),
    ("beta_passwords", "14. Passwords: reset answers, link used twice, 11 wrong attempts throttled", beta_passwords, HTTP_4XX),
    ("beta_delete_reregister", "15. Delete, then register the same email: clean new account", beta_delete_reregister, ()),
    ("beta_access", "16. Access: member, Office level and signed-out people on Office, Control, System", beta_access, HTTP_4XX),
    ("beta_gold_lock", "17. A Gold member cannot change tier (screens and direct post)", beta_gold_lock, ()),
    ("beta_journey", "18. Journey: refresh, Back, Forward, restart, jumping ahead", beta_journey, HTTP_4XX),
    ("beta_bad_input", "19. Bad input and hostile text: errors are clear, scripts stay plain text", beta_bad_input, HTTP_4XX),
    ("beta_double_submit", "20. Double submit: register and Gold apply create one record", beta_double_submit, HTTP_4XX),
    ("beta_counting", "21. Office counting: staff and bot journeys are not counted", beta_counting, ()),
    ("beta_system_refusals", "22. System: wrong unlock codes logged, bad prices refused", beta_system_refusals, HTTP_4XX),
    ("beta_library_refusals", "23. Control Library: fake mp3, too big, library full (strict server)", beta_library_refusals, HTTP_4XX),
    ("beta_emails", "24. Every email of the run: no broken text, absolute links on the right host, links open", beta_emails, ()),
]
