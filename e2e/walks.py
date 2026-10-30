"""The nine walk-throughs. Each is a plain function that takes a Walk and acts like a person: every `with w.step(...)` is one
screenshotted step; the first failed step ends that walk-through (the rest depend on it). Selectors use the real templates
(ids, names and the stable data-* hooks), not pixel positions."""
import io
import math
import re
import struct
import wave
from pathlib import Path

from . import mailbox
from .kit import (
    CONTROL, NEW_PASSWORD, OFFICE, PASSWORD, RESET_PASSWORD, SITE, STAFF, SYSTEM, UNLOCK_CODE, WORKSPACE_DIR, answer_journey,
    apply_gold, approve_on_application_page, confirm_office_modal, dbtool, fill_date_of_birth, form_errors, manage, no_horizontal_overflow, register_member,
    problems_modal, sign_in, sign_in_fails, tick, verify_email_link,
)


# ---------- small helpers used by several walk-throughs ----------

def goto_ok(page, url, h1=True):
    """Open a page; it must answer 200 and (normally) show a heading."""
    response = page.goto(url)
    assert response is not None and response.status == 200, f"{url} answered {response.status if response else 'nothing'}"
    page.wait_for_load_state("load")
    if h1:
        assert page.locator("h1").count() > 0, f"{url} has no heading"
    return response


def toast_text(page, words, timeout=3000):
    """Server messages show as toasts a moment after load (feedback.js): wait for one containing `words`."""
    try:
        page.locator(".toasts-list li", has_text=re.compile(re.escape(words), re.I)).first.wait_for(timeout=timeout)
        return True
    except Exception:
        return False


def body_text(page):
    return page.locator("body").text_content() or ""


def sign_out_member(page):
    page.goto(f"{SITE}/account/you/")
    with page.expect_navigation():
        page.locator("form.m-signout button").click()
    page.wait_for_url(f"{SITE}/")  # signing out lands on the home page


def submit_login_form(page, email, password):
    """Fill the sign-in form that is already on screen (Office, Control or the website) and send it."""
    page.locator("input[name=username]").fill(email)
    page.locator("input[name=password]").fill(password)
    with page.expect_navigation():
        page.locator("form[data-live-validate] button[type=submit]").click()


def csrf_token(context):
    for cookie in context.cookies():
        if cookie["name"] == "csrftoken":
            return cookie["value"]
    raise AssertionError("The browser has no CSRF cookie to reuse for a direct request.")


def direct_post(page, base, path):
    """A POST sent straight to the server by the signed-in browser session, with a valid CSRF token and no button involved.
    No redirects are followed, so the answer is exactly what the view said (302 = done, 403 = refused)."""
    return page.context.request.post(base + path, headers={"X-CSRFToken": csrf_token(page.context), "Referer": base + "/"}, max_redirects=0)


def office_gold_detail(page, name):
    """From the Gold list (waiting), open the application of `name`. Returns its id."""
    page.goto(f"{OFFICE}/gold/?status=all")
    row = page.locator("[data-gold-row]", has_text=name).first
    row.wait_for()
    with page.expect_navigation():
        row.locator("a.o-rowlink").click()
    return re.search(r"/gold/([0-9a-f-]{36})/", page.url).group(1)


def wav_bytes(seconds=0.5, rate=8000):
    """A tiny valid mono 16-bit WAV (a quiet 440 Hz tone) made on the spot."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(2 * math.pi * 440 * n / rate))) for n in range(int(seconds * rate))))
    return buffer.getvalue()


# ---------- 1. Visitor ----------

def visitor(w):
    page = w.page()
    for label, path, title_has in (("Home", "/", "Spa 99"), ("The spa", "/the-spa/", "Spa 99")):
        with w.step(f"{label} page opens", page):
            goto_ok(page, SITE + path)
            assert title_has in page.title(), f"Unexpected title: {page.title()}"
    with w.step("Tour page opens", page):
        goto_ok(page, f"{SITE}/tour/", h1=False)
    with w.step("Journey: answer every screen and reach a suggested tier", page):
        tier = answer_journey(page)
        assert tier.strip(), "The result shows no tier"
        assert page.locator("[data-flow-root] a[href*='/register/']").count() > 0, "The result has no register link"
    for label, path in (("Privacy notice", "/privacy/"), ("Terms of use", "/terms/")):
        with w.step(f"{label} opens", page):
            goto_ok(page, SITE + path)
            assert len(body_text(page)) > 800, f"{label} looks empty"


# ---------- 2. Tier membership ----------

def tier(w):
    email, first, last, mobile = "tier@example.com", "Tobias", "Tierney", "07123 456781"
    page = w.page()
    with w.step("Register for Tier 2", page):
        register_member(page, email, first, last, mobile, plan_name="Tier 2")
        assert "email" in body_text(page).lower()
    with w.step("The verification email arrives", page):
        message = mailbox.wait_for(email, "Confirm your email")
        link = mailbox.link(message, "/verify/")
    with w.step("Open the link and confirm the email (lands signed in on /account/)", page):
        verify_email_link(page, link)
        assert page.locator("[data-verify-banner]").count() == 0, "Still asked to confirm the email"
    with w.step("The welcome email is sent after confirming", page):
        mailbox.wait_for(email, "Welcome to Spa 99")
    with w.step("Sign out, then sign in with the password", page):
        sign_out_member(page)
        sign_in(page, SITE, email, PASSWORD, expect_path="/account/")
    with w.step("The dashboard shows the tier", page):
        status = page.locator("[data-status]").first
        assert status.get_attribute("data-status") == "registered", f"Status is {status.get_attribute('data-status')}"
        assert "Tier 2" in status.inner_text(), f"Dashboard says: {status.inner_text()}"
        assert "Tier 2" in page.locator("[data-tile=membership]").inner_text()
        assert dbtool("user", email)["plan"] == "tier-2"
    with w.step("Book a visit opens", page):
        page.locator("[data-member-rail] [data-tab=book]").click()
        page.wait_for_selector("[data-screen=book]")
        assert "Book a visit" in page.title(), f"Title: {page.title()}"
        assert "Booking opens" in body_text(page), "The booking-opening line is missing"


# ---------- 3. Gold approved ----------

def gold_approved(w):
    email, first, last, mobile = "gold1@example.com", "Gideon", "Goldman", "07123 456782"
    barry = STAFF["barry"]
    visitor_page = w.page()
    with w.step("Apply for the Gold Card", visitor_page):
        reference = apply_gold(visitor_page, first, last, email, mobile)
        assert "GC-" in reference, f"Odd reference: {reference}"
        assert dbtool("gold", email)["status"] == "new"
    with w.step("The applicant gets the thank-you email", visitor_page):
        mailbox.wait_for(email, "Gold Card application")
    with w.step("The approver gets the application email with a Review application link", visitor_page):
        message = mailbox.wait_for(barry["email"], f"Gold Card application: {first} {last}")
        approve_url = mailbox.link(message, "?t=")
        assert approve_url.startswith(OFFICE), f"The approve link does not point at the Office: {approve_url}"
    office = w.page()
    with w.step("The approver taps the link: sign in, then the full application page", office):
        office.goto(approve_url)
        office.wait_for_url(re.compile(r"/login/"))
        submit_login_form(office, barry["email"], PASSWORD)
        office.wait_for_selector("[data-gold-decision]")
        assert f"{first} {last}" in office.locator("h1").inner_text()
    with w.step("Approve and invite on the application page", office):
        approve_on_application_page(office)
        assert dbtool("gold", email)["status"] == "approved"
    with w.step("The approval email (invite) arrives", office):
        invite = mailbox.wait_for(email, "Gold Card is approved")
        invite_url = mailbox.link(invite, "/gold/invite/")
    with w.step("The new member opens the invite and sets a password", visitor_page):
        visitor_page.goto(invite_url)
        visitor_page.locator("#id_password").fill(PASSWORD)
        fill_date_of_birth(visitor_page)
        tick(visitor_page, "men_only_accepted")
        tick(visitor_page, "privacy_accepted")
        visitor_page.locator("#register-form button[type=submit]").click()
        try:
            visitor_page.wait_for_url(re.compile(r"/account/"))
        except Exception:  # noqa: BLE001
            raise AssertionError(f"Setting up the account did not reach /account/. The form says: {form_errors(visitor_page)}") from None
    with w.step("The dashboard shows a Gold member", visitor_page):
        status = visitor_page.locator("[data-status]").first
        assert status.get_attribute("data-status") == "gold", f"Status is {status.get_attribute('data-status')}"
        assert "Gold member" in status.inner_text()
        visitor_page.goto(f"{SITE}/account/membership/")
        assert "Gold Card" in visitor_page.locator("h1").first.inner_text()
        assert dbtool("user", email)["plan"] == "gold"


# ---------- 4. Gold declined ----------

def gold_declined(w):
    email, first, last, mobile = "gold2@example.com", "Gareth", "Gilbert", "07123 456783"
    barry = STAFF["barry"]
    visitor_page = w.page()
    with w.step("A second applicant applies for the Gold Card", visitor_page):
        apply_gold(visitor_page, first, last, email, mobile)
        assert dbtool("gold", email)["status"] == "new"
    office = w.page()
    with w.step("The approver finds the application in the Office", office):
        sign_in(office, OFFICE, barry["email"], PASSWORD)
        application_id = office_gold_detail(office, f"{first} {last}")
        assert "Waiting" in office.locator("[data-gold-decision]").inner_text() or office.locator("[data-decline]").count() > 0
    with w.step("Decline needs a reason: an empty form lists the problem and stays open", office):
        office.locator("[data-decline] button:visible").first.click()
        dialog = office.locator('dialog[data-gold-dialog="decline"]')
        dialog.wait_for(state="visible")
        dialog.locator('button[type="submit"]').click()
        office.locator("dialog[data-fb-modal][open] .fb-problems").wait_for()
        assert "Reason" in office.locator("dialog[data-fb-modal][open] .fb-problems").inner_text()
        office.locator("dialog[data-fb-modal][open] button", has_text="OK").click()
        assert dbtool("gold", email)["status"] == "new", "A decline without a reason went through"
    with w.step("Decline with a reason (the applicant is not emailed by default)", office):
        dialog.locator('textarea[name="reason"]').fill("E2E: not a fit for Gold at this time")
        assert not dialog.locator('input[name="email_applicant"]').is_checked(), "Email the applicant must be off by default"
        dialog.locator('button[type="submit"]').click()
        office.wait_for_selector("[data-gold-decision] .o-state")
        assert "Declined" in office.locator("[data-gold-decision]").inner_text()
    with w.step("The History shows the decline with the reason, who and how", office):
        trail = office.locator("[data-gold-timeline]").inner_text()
        assert "Declined" in trail and "E2E: not a fit for Gold at this time" in trail and "Office" in trail, f"History says: {trail}"
    with w.step("The application is declined and the person is not Gold", office):
        status = dbtool("gold", email)
        assert status["status"] == "declined" and not status["has_user"], f"Database says {status}"
        office.goto(f"{OFFICE}/gold/{application_id}/")
        assert office.locator("[data-gold-decision] [data-approve]").count() == 0, "The application page still offers to approve"
        office.goto(f"{OFFICE}/gold/?status=declined")
        assert office.locator("[data-gold-row]", has_text=f"{first} {last}").count() == 1
    with w.step("Emails: the applicant got the thank-you only (this app sends no decline email and no invite)", office):
        assert mailbox.find(email, "Gold Card application") is not None, "No thank-you email was sent"
        assert mailbox.find(email, "approved") is None, "A decline must not send an approval/invite email"
        assert mailbox.count_to(email) == 1, f"Expected exactly 1 email to the applicant, found {mailbox.count_to(email)}"


# ---------- 5. Account: password, reset, delete ----------

def account(w):
    email, first, last, mobile = "account@example.com", "Arthur", "Accountman", "07123 456784"
    page = w.page()
    with w.step("Register and confirm the email", page):
        register_member(page, email, first, last, mobile, plan_name="Tier 1")
        verify_email_link(page, mailbox.link(mailbox.wait_for(email, "Confirm your email"), "/verify/"))
    with w.step("Change the password on the You screen", page):
        page.goto(f"{SITE}/account/you/password/")
        page.locator("#id_old_password").fill(PASSWORD)
        page.locator("#id_new_password1").fill(NEW_PASSWORD)
        page.locator("#id_new_password2").fill(NEW_PASSWORD)
        with page.expect_navigation():
            page.locator("form.m-form button[type=submit]").click()
        page.wait_for_url(re.compile(r"/account/you/$"))
        assert toast_text(page, "password has been changed"), f"No success message. {form_errors(page)}"
    with w.step("Sign out and sign in with the new password", page):
        sign_out_member(page)
        sign_in(page, SITE, email, NEW_PASSWORD, expect_path="/account/")
    other = w.page()
    with w.step("The old password no longer works", other):
        sign_in_fails(other, SITE, email, PASSWORD)
    with w.step("Forgotten password: ask for a reset link", other):
        other.goto(f"{SITE}/forgot-password/")
        other.locator("#id_email").fill(email)
        with other.expect_navigation():
            other.locator("form[data-live-validate] button[type=submit]").click()
        assert "check your email" in body_text(other).lower()
        reset_url = mailbox.link(mailbox.wait_for(email, "Reset your Spa 99 password"), "/reset/")
    with w.step("Choose a new password from the email link", other):
        other.goto(reset_url)
        other.locator("#id_password").fill(RESET_PASSWORD)
        with other.expect_navigation():
            other.locator("form[data-live-validate] button[type=submit]").click()
        assert "password has been changed" in body_text(other).lower(), f"Reset failed. {form_errors(other)}"
    with w.step("Sign in with the reset password", other):
        sign_in(other, SITE, email, RESET_PASSWORD, expect_path="/account/")
    with w.step("Delete the account (asks for the password, then a confirm)", other):
        other.goto(f"{SITE}/account/you/")
        other.locator("[data-delete-open]").click()
        other.locator("#delete-password").fill(RESET_PASSWORD)
        other.locator("#delete-form button[data-confirm]").click()
        confirm_office_modal(other)
        other.wait_for_selector("h1:has-text('Account deleted')")
        assert dbtool("user", email)["exists"] is False, "The account is still in the database"
    again = w.page()
    with w.step("A deleted account cannot sign in", again):
        sign_in_fails(again, SITE, email, RESET_PASSWORD)


# ---------- 6. Office levels, then the figures ----------

def office_levels(w):
    office_user, admin_user, barry = STAFF["office"], STAFF["admin"], STAFF["barry"]
    members = [("levels-delete@example.com", "Dennis", "Deleteme", "07123 456785"), ("levels-keep@example.com", "Kevin", "Keeper", "07123 456786")]
    applicant = ("gold3@example.com", "Gordon", "Gravesend", "07123 456787")
    site = w.page()
    for email, first, last, mobile in members:
        with w.step(f"Set up: {first} registers", site):
            register_member(site, email, first, last, mobile, plan_name="Tier 3")
            site.context.clear_cookies()
    with w.step("Set up: a Gold application is waiting", site):
        apply_gold(site, applicant[1], applicant[2], applicant[0], applicant[3])
        assert dbtool("gold", applicant[0])["status"] == "new"

    # --- Office level: sees everything, can do nothing ---
    page = w.page()
    with w.step("Office level signs in and sees the dashboard", page):
        sign_in(page, OFFICE, office_user["email"], PASSWORD)
        page.wait_for_selector("[data-office-dashboard]")
    with w.step("Office level: Gold list and application show no Approve or Decline buttons", page):
        application_id = office_gold_detail(page, f"{applicant[1]} {applicant[2]}")
        assert page.locator("[data-gold-decision]").count() == 1
        assert page.locator("[data-approve], [data-decline]").count() == 0, "Office level sees decision buttons"
        page.goto(f"{OFFICE}/gold/?status=all")
        assert page.locator("[data-gold-row] [data-approve]").count() == 0, "Office level sees Approve in the list"
    with w.step("Office level: People shows the members but no Export, no Delete", page):
        page.goto(f"{OFFICE}/people/")
        assert page.locator("[data-person-row]", has_text=members[0][0]).count() == 1, "The new member is not in People"
        assert page.locator("[data-export-csv]").count() == 0, "Office level sees Export CSV"
        with page.expect_navigation():
            page.locator("[data-person-row]", has_text=members[0][0]).locator("a.o-rowlink").click()
        person_id = re.search(r"/people/([0-9a-f-]{36})/", page.url).group(1)
        assert page.locator("[data-delete-person], [data-export-person]").count() == 0, "Office level sees Delete/Export on a person"
    with w.step("Office level: direct requests are refused (403) and nothing changes", page):
        refused = {
            "approve": direct_post(page, OFFICE, f"/gold/{application_id}/approve/"),
            "decline": direct_post(page, OFFICE, f"/gold/{application_id}/decline/"),
            "delete a member": direct_post(page, OFFICE, f"/people/{person_id}/delete/"),
            "export CSV": page.context.request.get(f"{OFFICE}/people/export.csv", max_redirects=0),
            "export a person": page.context.request.get(f"{OFFICE}/people/{person_id}/export/", max_redirects=0),
        }
        wrong = {name: r.status for name, r in refused.items() if r.status != 403}
        assert not wrong, f"Expected 403 for every one; got {wrong}"
        assert dbtool("gold", applicant[0])["status"] == "new", "The application changed"
        assert dbtool("user", members[0][0])["exists"], "The member was deleted"

    # --- Admin: export and delete, but not Gold decisions (no Approver) ---
    admin = w.page()
    with w.step("Admin exports the members CSV", admin):
        sign_in(admin, OFFICE, admin_user["email"], PASSWORD)
        admin.goto(f"{OFFICE}/people/")
        with admin.expect_download() as download:
            admin.locator("[data-export-csv]:visible").click()
        content = Path(download.value.path()).read_text()
        assert members[0][0] in content and members[1][0] in content, "The CSV is missing the new members"
        assert content.splitlines()[0].startswith("account_id,"), "Unexpected CSV header"
    with w.step("Admin cannot approve (not an Approver): no buttons, direct request refused", admin):
        office_gold_detail(admin, f"{applicant[1]} {applicant[2]}")
        assert admin.locator("[data-approve], [data-decline]").count() == 0, "Admin without Approver sees decision buttons"
        assert direct_post(admin, OFFICE, f"/gold/{application_id}/approve/").status == 403
        assert dbtool("gold", applicant[0])["status"] == "new"
    with w.step("Admin deletes a member", admin):
        admin.goto(f"{OFFICE}/people/{person_id}/")
        admin.locator("[data-delete-person] button").click()
        confirm_office_modal(admin)
        admin.wait_for_url(re.compile(r"/people/$"))
        assert toast_text(admin, "were deleted"), "No confirmation message after deleting"
        assert dbtool("user", members[0][0])["exists"] is False, "The member is still in the database"

    # --- Approver: can approve (the same direct request that was refused above now works) ---
    approver = w.page()
    with w.step("Approver cannot export, but can approve (direct request accepted)", approver):
        sign_in(approver, OFFICE, barry["email"], PASSWORD)
        approver.goto(f"{OFFICE}/people/")
        assert approver.locator("[data-export-csv]").count() == 0, "Office + Approver sees Export CSV"
        approver.goto(f"{OFFICE}/gold/{application_id}/")
        assert approver.locator("[data-approve]").count() > 0, "The Approver sees no Approve button"
        response = direct_post(approver, OFFICE, f"/gold/{application_id}/approve/")
        assert response.status == 302, f"Approve answered {response.status}"
        assert dbtool("gold", applicant[0])["status"] == "approved"

    # --- the figures reflect all of this ---
    with w.step("Rebuild the stored figures and check nothing differs from the source tables", approver):
        code, output = manage("rebuild_metrics")
        assert code == 0, output[-500:]
        code, output = manage("rebuild_metrics", "--dry-run")
        assert code == 0 and "0 difference(s)" in output, output[-500:]
    with w.step("Dashboard: registrations and waiting Gold match what the run created", approver):
        expected = dbtool("registrations")["count"]
        waiting = dbtool("waiting")["count"]
        assert expected >= 1, "No registrations in the database"
        approver.goto(f"{OFFICE}/")
        approver.wait_for_selector("[data-ring=registrations] [data-ring-value]")
        shown = int(approver.locator("[data-ring=registrations] [data-ring-value]").get_attribute("data-count"))
        assert shown == expected, f"Dashboard shows {shown} registrations; the database has {expected}"
        gold_waiting = int(approver.locator("[data-gold-waiting]").inner_text().replace(",", "").strip())
        assert gold_waiting == waiting, f"Dashboard shows {gold_waiting} Gold waiting; the database has {waiting}"
        latest = approver.locator("[data-office-latest]").inner_text()
        assert members[1][1] in latest, "The latest registrations list does not show the member who stayed"
        assert members[0][1] not in latest, "The deleted member still shows in latest registrations"


# ---------- 7. System ----------

def system(w):
    dev, admin_user = STAFF["dev"], STAFF["admin"]
    page = w.page()
    with w.step("Developer signs in on the System address", page):
        page.goto(f"{SYSTEM}/dev-login/")
        page.locator("input[name=username]").fill(dev["email"])
        page.locator("input[name=password]").fill(PASSWORD)
        with page.expect_navigation():
            page.locator("[data-system-signin] button[type=submit]").click()
        assert "/dev-login/" not in page.url, f"Sign-in failed: {page.locator('[data-system-error]').all_inner_texts()}"
    with w.step("System is locked: unlock with the lock code only", page):
        page.goto(f"{SYSTEM}/plans/")
        page.wait_for_selector("[data-system-unlock]")
        assert page.locator("[data-system-unlock] input[name=password]").count() == 0, "The unlock still asks for a password"
        page.locator("[data-system-unlock] input[name=code]").fill(UNLOCK_CODE)
        with page.expect_navigation():
            page.locator("[data-system-unlock] button[type=submit]").click()
        page.wait_for_selector("[data-system-plans]")
    with w.step("Change one price (Tier 1 to 311) and confirm", page):
        row = page.locator('tr[data-system-plan="tier-1"]')
        field = row.locator('input[aria-label="Price ex VAT"]')
        field.fill("311")
        page.wait_for_selector("[data-system-savebar]:not([hidden])")
        page.locator("[data-system-save]").click()
        page.wait_for_selector("dialog.fb-modal[open]")
        with page.expect_navigation():
            page.locator("dialog.fb-modal[open] [data-fb-ok]").click()
        page.wait_for_selector("[data-system-plans]")
        shown = page.locator('tr[data-system-plan="tier-1"] input[aria-label="Price ex VAT"]').input_value()
        assert float(shown) == 311, f"The page shows {shown}"
        assert float(dbtool("price", "tier-1")["price"]) == 311
    with w.step("The change is in the audit log", page):
        page.goto(f"{SYSTEM}/changes/")
        page.wait_for_selector("[data-system-audit]")
        text = page.locator("[data-system-audit]").text_content() or ""
        assert "311" in text, "The audit log does not mention the new price"
        assert "tier" in text.lower(), "The audit log does not name the plan"
    with w.step("verify_audit_log passes (the chain is intact)", page):
        code, output = manage("verify_audit_log")
        assert code == 0, output[-600:]
    other = w.page()
    with w.step("An Admin cannot use System: sign-in refused, pages answer 404", other):
        other.goto(f"{SYSTEM}/dev-login/")
        other.locator("input[name=username]").fill(admin_user["email"])
        other.locator("input[name=password]").fill(PASSWORD)
        with other.expect_navigation():
            other.locator("[data-system-signin] button[type=submit]").click()
        assert "/dev-login/" in other.url and other.locator("[data-system-error]").count() == 1, "An Admin got past the System sign-in"
        assert any("not recognised" in line.lower() for line in problems_modal(other)), "The refusal is not listed in the problems dialog"
        for path in ("/", "/plans/", "/changes/"):
            status = other.goto(f"{SYSTEM}{path}").status
            assert status == 404, f"{path} answered {status} to an Admin (expected 404)"


# ---------- 8. Control (Admin) ----------

CONTROL_TABS = [("overview", "Overview", "/"), ("rooms", "Rooms", "/rooms/"), ("music", "Music", "/music/"),
                ("screens", "Screens", "/screens/"), ("schedule", "Schedule", "/schedule/"), ("library", "Library", "/library/")]


def _open_tab(page, key):
    page.locator(f".ctl-nav a[data-nav={key}]").click()
    page.wait_for_selector(f".ctl-nav a[data-nav={key}][aria-current=page]")


def _close_panel(page):
    page.keyboard.press("Escape")
    try:
        page.wait_for_selector("[data-panel]", state="hidden", timeout=3000)
    except Exception:  # noqa: BLE001 - Escape did not close it: use the backdrop like a person would
        page.locator("[data-backdrop]").click(position={"x": 5, "y": 300})
        page.wait_for_selector("[data-panel]", state="hidden")


def control(w):
    admin = STAFF["admin"]
    page = w.page()
    with w.step("Admin signs in on the Control address", page):
        sign_in(page, CONTROL, admin["email"], PASSWORD)
        page.wait_for_selector(".ctl-nav")
    for key, label, path in CONTROL_TABS:
        with w.step(f"{label} tab loads", page):
            if key == "overview":
                page.goto(CONTROL + "/")
            else:
                _open_tab(page, key)
            page.wait_for_selector("#ctl-main > *")
            assert page.url.rstrip("/").endswith(path.rstrip("/")), f"URL is {page.url}"
            assert label in page.title() or label.lower() in page.url, f"Title is {page.title()}"
    with w.step("Back after tab switches goes to the previous tab, exactly once", page):
        page.goto(CONTROL + "/")
        page.wait_for_selector(".ctl-nav")
        before = page.evaluate("history.length")
        _open_tab(page, "rooms")
        _open_tab(page, "music")
        assert page.evaluate("history.length") == before + 2, f"Two tab switches added {page.evaluate('history.length') - before} history entries"
        page.go_back()
        page.wait_for_selector(".ctl-nav a[data-nav=rooms][aria-current=page]")
        assert page.url.rstrip("/").endswith("/rooms"), f"Back went to {page.url}"
    with w.step("Rooms: tap every room card; the panel title matches the room", page):
        page.goto(f"{CONTROL}/rooms/")
        page.wait_for_selector(".ctl-rcard")
        rooms = page.eval_on_selector_all("a[data-open-room]", "links => links.map(a => [a.dataset.openRoom, a.textContent.trim()])")
        assert len(rooms) >= 6, f"Only {len(rooms)} rooms found"
        problems = []
        for slug, name in rooms:
            page.locator(f'a[data-open-room="{slug}"]').click()
            page.wait_for_selector("[data-panel]:not([hidden])")
            title = (page.locator("[data-panel] #ctl-panel-title").first.text_content() or "").strip()
            if title != name:
                problems.append(f"{slug}: card says '{name}', panel says '{title}'")
            _close_panel(page)
        assert not problems, "; ".join(problems)
    with w.step("Library: upload a tiny generated WAV", page):
        _open_tab(page, "library")
        page.wait_for_selector("input[data-lib-input]", state="attached")
        page.locator("input[data-lib-input]").set_input_files(files=[{"name": "e2e-tone.wav", "mimeType": "audio/wav", "buffer": wav_bytes()}])
        page.wait_for_selector("a[data-open-item]:has-text('e2e')", timeout=40000)
        assert dbtool("assets")["count"] == 1, "The upload is not in the database"
        stored = [p for p in (WORKSPACE_DIR / "media").rglob("*") if p.is_file()]
        assert stored, "No file landed in the throwaway media folder"
    with w.step("Library: delete the file again", page):
        page.locator("a[data-open-item]:has-text('e2e')").first.click()
        page.wait_for_selector("[data-item-panel]")
        page.locator("[data-item-delete]").click()
        page.wait_for_selector("dialog.fb-modal[open]")
        page.locator("dialog.fb-modal[open] [data-fb-ok]").click()
        page.wait_for_selector("a[data-open-item]:has-text('e2e')", state="detached")
        assert dbtool("assets")["count"] == 0, "The file is still in the database"


# ---------- 9. Phone width ----------

def phone(w):
    admin, office_user = STAFF["admin"], STAFF["office"]
    results = []

    def check(page, label):
        page.wait_for_load_state("load")
        page.wait_for_timeout(800)  # let layout and reveal animations settle
        ok, wide, inner = no_horizontal_overflow(page)
        results.append((label, ok))
        assert ok, f"{label}: the page is {wide}px wide in a {inner}px window (sideways scrolling)"

    page = w.page(375, 812, mobile=True)
    with w.step("Phone: home", page):
        page.goto(SITE + "/")
        check(page, "Home")
    with w.step("Phone: journey start", page):
        page.goto(f"{SITE}/journey/")
        page.wait_for_selector("[data-flow-root] .screen")
        check(page, "Journey start")
    with w.step("Phone: register page", page):
        page.goto(f"{SITE}/register/")
        check(page, "Register")
    email = "phone@example.com"
    with w.step("Phone: register, confirm and open /account/", page):
        register_member(page, email, "Pedro", "Phonesmith", "07123 456788", plan_name="Tier 1")
        verify_email_link(page, mailbox.link(mailbox.wait_for(email, "Confirm your email"), "/verify/"))
        check(page, "Account")
    with w.step("Phone: the other member screens", page):
        for path in ("/account/book/", "/account/membership/", "/account/you/"):
            page.goto(SITE + path)
            check(page, path)
    office = w.page(375, 812, mobile=True)
    with w.step("Phone: Office dashboard", office):
        sign_in(office, OFFICE, office_user["email"], PASSWORD)
        office.wait_for_selector("[data-office-dashboard]")
        check(office, "Office dashboard")
    control_page = w.page(375, 812, mobile=True)
    with w.step("Phone: Control overview", control_page):
        sign_in(control_page, CONTROL, admin["email"], PASSWORD)
        control_page.wait_for_selector("#ctl-main > *")
        check(control_page, "Control overview")


WALKS = [
    ("visitor", "1. Visitor: pages and the journey to a suggested tier", visitor, ()),
    ("tier", "2. Tier membership: register, verify, sign in, dashboard, Book a visit", tier, ()),
    ("gold_approved", "3. Gold approved: apply, approver email, approve on the application page, member is Gold", gold_approved, ()),
    ("gold_declined", "4. Gold declined: decline in the Office, not Gold", gold_declined, ()),
    ("account", "5. Account: change password, reset by email, delete, cannot sign in", account, ()),
    ("office_levels", "6. Office levels, then the figures", office_levels, (r"status of 40[34]",)),
    ("system", "7. System: unlock, change a price, audit log, Admin gets 404", system, (r"status of 40[34]",)),
    ("control", "8. Control: every tab, every room, Back, Library upload and delete", control, ()),
    ("phone", "9. Phone width (375x812): no sideways scrolling", phone, ()),
]
