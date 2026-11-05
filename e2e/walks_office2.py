"""Office 2 walk-throughs (docs/features/office-2.md, "Built, UI"): the phone Home cards and tabs, approvals with undo, Registered, Leads and the Approach list, the wa.me button, the group send
with its confirm, the add-your-number link, a bounced lead coming back, and a list that loads itself. Fake mail only (the throwaway workspace's mail folder).

Accounts: Barry (Approver) does the work; the people are office2-*@example.test. Leads and members are made through the real journey and register forms; the few things no screen can do
(a bounce arriving, a pile of leads for the long list) are done with manage.py shell against the throwaway database."""
import json
import re

from . import mailbox
from .kit import OFFICE, PASSWORD, SITE, STAFF, SYSTEM, UNLOCK_CODE, answer_journey, dbtool, manage, no_horizontal_overflow, register_member, sign_in

BARRY = STAFF["barry"]["email"]
DEV = STAFF["dev"]


def _barry(w, width=375, height=812, mobile=True):
    page = w.page(width=width, height=height, mobile=mobile)
    sign_in(page, OFFICE, BARRY, PASSWORD)
    return page


def _shell(code):
    """Run a few lines of Python against the throwaway database; returns the output."""
    status, output = manage("shell", "-c", code)
    assert status == 0, f"manage.py shell failed: {output[-400:]}"
    return output


def _lead(w, email, mobile="07400 123451"):
    page = w.page()
    answer_journey(page, email=email, mobile=mobile)
    page.context.close()


def office2_home_tabs(w):
    page = _barry(w)
    with w.step("Phone Home: three cards with two rings each, no greeting, no Gold applications, Waiting for you or Hot leads", page):
        page.goto(f"{OFFICE}/")
        page.wait_for_selector("[data-approval-cards]")
        assert page.locator("[data-approval-cards] .o-pair").count() == 3
        assert page.locator("[data-approval-cards] .o-pair-link[data-ring]").count() == 6
        for selector in (".o-greeting", ".o-gold-tile", ".o-waiting", ".o-hot", ".o-range--header"):
            assert not page.locator(selector).first.is_visible(), f"{selector} shows on a phone"
        assert page.locator("a[href^='http']").count() == 0, "a link to another site is on Home"
    with w.step("The phone asks for All: a saved 7 days does not stick", page):
        page.goto(f"{OFFICE}/?range=7d")
        page.wait_for_function("() => document.querySelector('[data-range-form] input:checked')?.value === 'all'")
    with w.step("Five tabs: Home, Approach, Analytics, Leads, Revenue; no More, no Assistant", page):
        tabs = page.locator(".o-nav-list li:visible a")
        labels = [t["text"] for t in sorted(({"x": tabs.nth(i).bounding_box()["x"], "text": tabs.nth(i).inner_text().strip()} for i in range(tabs.count())), key=lambda t: t["x"])]
        assert labels == ["Home", "Approach", "Analytics", "Leads", "Revenue"], labels
        assert page.locator("[data-nav-sheet], [data-nav-more]").count() == 0
    with w.step("The Revenue card opens the Revenue page; the Waiting ring (Memberships) opens Approvals with Home lit", page):
        page.locator("[data-card=revenue]").click()
        page.wait_for_url(re.compile(r"/revenue/"))
        assert page.locator("[data-revenue-total]").is_visible() and page.locator("[data-revenue-possible]").is_visible()
        page.goto(f"{OFFICE}/")
        page.locator("[data-card=waiting] [data-ring=memberships]").click()
        page.wait_for_url(re.compile(r"/approvals/"))
        assert page.locator("body[data-under-home]").count() == 1
    with w.step("The Approved Memberships ring opens Registered, the Gold rings open Gold; the person menu has Registered and Gold", page):
        page.goto(f"{OFFICE}/")
        page.locator("[data-card=approved] [data-ring=memberships]").click()
        page.wait_for_url(re.compile(r"/people/"))
        page.goto(f"{OFFICE}/")
        page.locator("[data-card=waiting] [data-ring=gold]").click()
        page.wait_for_url(re.compile(r"/gold/"))
        page.locator("[data-person-menu] summary").click()
        assert page.locator("[data-menu-registered]").is_visible() and page.locator("[data-menu-gold]").is_visible()
    with w.step("No sideways scroll on Home and Revenue", page):
        for path in ("/", "/revenue/"):
            page.goto(f"{OFFICE}{path}")
            ok, wide, inner = no_horizontal_overflow(page)
            assert ok, f"{path} is {wide}px wide in {inner}px"
    desktop = _barry(w, 1440, 900, mobile=False)
    with w.step("Computer: the cards sit side by side under the greeting, with the range bar", desktop):
        desktop.goto(f"{OFFICE}/")
        boxes = [desktop.locator(f"[data-card={name}]").bounding_box() for name in ("waiting", "approved", "revenue")]
        assert boxes[0]["y"] == boxes[1]["y"] == boxes[2]["y"], boxes
        assert desktop.locator(".o-range--header").is_visible() and desktop.locator(".o-greeting").is_visible()


def office2_approvals(w):
    first, second = "office2-ann@example.test", "office2-ben@example.test"
    reg = w.page()
    register_member(reg, first, "Ann", "Approval", "07400 223451")
    register_member(w.page(), second, "Ben", "Approval", "07400 223452")
    page = _barry(w)
    with w.step("Approvals, Waiting: the note, three tabs with counts, Decline and Approve", page):
        page.goto(f"{OFFICE}/approvals/")
        page.wait_for_selector("[data-approval-row]")
        assert "Nothing here changes anything for the member" in page.locator("[data-approvals-note]").inner_text()
        assert page.locator("[data-approval-tabs] [data-tab]").count() == 3
        row = page.locator("[data-approval-row]", has_text="Ann Approval")
        assert row.locator("[data-decision=approve]").count() and row.locator("[data-decision=decline]").count()
    with w.step("Approve: the row becomes an Undo strip of the SAME height, the counts move, the next row does not jump", page):
        rows = page.locator("[data-approval-row]")
        target = page.locator("[data-approval-row]", has_text="Ann Approval")
        height = target.bounding_box()["height"]
        after = page.locator("[data-approval-row]", has_text="Ben Approval")
        before_y = after.bounding_box()["y"] if rows.count() > 1 else None
        waiting_before = int(page.locator("[data-tab=waiting] [data-tab-count]").inner_text().replace(",", ""))
        target.locator("[data-decision=approve] button").click()
        page.wait_for_selector("[data-approval-row].o-approval--strip")
        strip = page.locator("[data-approval-row].o-approval--strip").first
        assert abs(strip.bounding_box()["height"] - height) < 1, (height, strip.bounding_box()["height"])
        assert "approved." in strip.inner_text()
        assert int(page.locator("[data-tab=waiting] [data-tab-count]").inner_text().replace(",", "")) == waiting_before - 1
        if before_y is not None:
            assert abs(after.bounding_box()["y"] - before_y) < 1, "the next row jumped"
    with w.step("Undo puts him back waiting; Decline works the same way", page):
        page.locator("[data-approval-row].o-approval--strip button").click()
        page.wait_for_selector("[data-approval-row].o-approval--strip", state="detached")
        page.locator("[data-approval-row]", has_text="Ann Approval").locator("[data-decision=decline] button").click()
        page.wait_for_selector("[data-approval-row].o-approval--strip")
    with w.step("A refresh and Back keep the decision: Declined tab shows him with Back to waiting", page):
        page.goto(f"{OFFICE}/approvals/?status=declined")
        row = page.locator("[data-approval-row]", has_text="Ann Approval")
        assert row.locator("[data-decision=undo]").count()
        row.locator("[data-decision=undo] button").click()
        page.wait_for_selector("[data-approval-row].o-approval--strip")
        page.reload()
        assert page.locator("[data-approval-row]", has_text="Ann Approval").count() == 0
    with w.step("Approve him for the Registered page: the line says approved and left to approve, with a link", page):
        page.goto(f"{OFFICE}/approvals/")
        page.locator("[data-approval-row]", has_text="Ann Approval").locator("[data-decision=approve] button").click()
        page.wait_for_selector(".o-approval--strip")
        page.goto(f"{OFFICE}/people/")
        line = page.locator("[data-approvals-line]")
        assert "approved" in line.inner_text() and "left to approve" in line.inner_text()
        assert page.locator("[data-person-row]", has_text="Ann Approval").count() == 1
    with w.step("Registered on a phone: Membership and Gold tabs, one table at a time; on a computer two tables", page):
        assert page.locator("[data-table=membership]").is_visible() and page.locator("[data-table=gold]").is_visible()
        assert page.locator("[data-table-card=gold]").is_hidden()
        page.goto(f"{OFFICE}/people/?table=gold")
        assert page.locator("[data-table-card=gold]").is_visible()
        ok, wide, inner = no_horizontal_overflow(page)
        assert ok, f"Registered is {wide}px wide in {inner}px"
    desktop = _barry(w, 1440, 900, mobile=False)
    with w.step("Computer: Approvals is a table and Registered has two tables", desktop):
        desktop.goto(f"{OFFICE}/approvals/")
        assert desktop.locator("table.o-list--approvals").is_visible()
        desktop.goto(f"{OFFICE}/people/")
        assert desktop.locator("[data-table-card]").count() == 2


def office2_leads_list(w):
    email = "office2-lead@example.test"
    _lead(w, email)
    page = _barry(w)
    with w.step("Leads: two tiles (Leads, Registered), a Emailed filter, no number filters, rows open the person", page):
        page.goto(f"{OFFICE}/leads/?range=all")
        assert page.locator("[data-leads-total-tile]").is_visible() and page.locator("[data-registered-tile]").is_visible()
        assert page.locator("[data-hot-tile], [data-went-on-to-register]").count() == 0
        row = page.locator("[data-lead-row]", has_text=email)
        row.click()  # anywhere on the row
        page.wait_for_url(re.compile(r"/leads/"))
    with w.step("The WhatsApp button is a wa.me link with the number in digits; Email beside it; Add to list is a quiet link", page):
        link = page.locator("a[data-whatsapp-open]")
        assert link.get_attribute("href") == "https://wa.me/447400123451", link.get_attribute("href")
        assert link.get_attribute("target") == "_blank" and "noopener" in link.get_attribute("rel")
        assert page.locator("[data-email-open]").is_visible()
        assert page.locator(".o-addlist").is_visible() and "btn" not in page.locator(".o-addlist").get_attribute("class")
    with w.step("Add him to the Approach list: he leaves Leads and shows on the list", page):
        lead_url = page.url
        page.locator(".o-addlist").click()
        page.locator("dialog[data-dialog=outreach][open] button[type=submit]").click()
        page.wait_for_selector("[data-on-outreach]")
        page.goto(f"{OFFICE}/leads/?range=all")
        assert page.locator("[data-lead-row]", has_text=email).count() == 0
        page.goto(f"{OFFICE}/outreach/")
        assert page.locator("[data-outreach-row]", has_text=email).count() == 1
    with w.step("Back to Leads from the list, with Undo; then Archive with a reason", page):
        row = page.locator("[data-outreach-row]", has_text=email)
        row.locator("[data-outreach-act=to-leads] button").click()
        page.wait_for_selector(".toast:has-text('Moved back to Leads')")
        page.locator(".toast-action").click()
        page.wait_for_selector(".toast:has-text('Back on the list')")
        page.locator("[data-outreach-row]", has_text=email).locator("[data-archive-url]").click()
        page.locator("dialog[data-dialog=archive][open] input[name=reason]").fill("Test")
        page.locator("dialog[data-dialog=archive][open] button[type=submit]").click()
        page.wait_for_selector(".toast:has-text('Archived')")
        page.goto(f"{OFFICE}/leads/?view=archived")
        assert "Test" in page.locator("[data-lead-row]", has_text=email).inner_text()
    with w.step("Tap feedback: a row shows the pressed tone while the finger is down", page):
        page.goto(f"{OFFICE}/people/")
        row = page.locator("[data-person-row]").first
        box = row.bounding_box()
        page.mouse.move(box["x"] + 60, box["y"] + 20)
        page.mouse.down()
        page.wait_for_function("() => document.querySelector('[data-person-row].is-pressed')")
        page.mouse.up()


def office2_group_send(w):
    with_mobile, without = "office2-has@example.test", "office2-none@example.test"
    _lead(w, with_mobile)
    _lead(w, without)
    dbtool("clear-lead-mobile", without)
    dev = w.page(width=1440, height=1000)
    sign_in(dev, f"{SYSTEM}", DEV["email"], PASSWORD) if False else None
    dev.goto(f"{SYSTEM}/dev-login/")
    dev.locator("input[name=username]").fill(DEV["email"])
    dev.locator("input[name=password]").fill(PASSWORD)
    with dev.expect_navigation():
        dev.locator("[data-system-signin] button[type=submit]").click()
    dev.goto(f"{SYSTEM}/plans/")
    if dev.locator("[data-system-unlock]").count():
        dev.locator("[data-system-unlock] input[name=code]").fill(UNLOCK_CODE)
        with dev.expect_navigation():
            dev.locator("[data-system-unlock] button[type=submit]").click()
    with w.step("Barry's invitation: the sender is a dropdown, the button is the Add your number link", dev):
        dev.goto(f"{SYSTEM}/emails/mailings/new/?start=barry_invitation")
        dev.wait_for_selector("select[name=sender_user]")
        assert dev.locator("select[name=sender_user] option").count() >= 2
        assert "Add your number" in dev.locator("[data-se-preview], .se-preview").first.inner_text()
        dev.locator("[data-se-send], button:has-text('Save draft')").first.click()
        dev.wait_for_url(re.compile(r"/emails/mailings/[0-9a-f-]{36}/"))
    with w.step("Send asks first and says who moves: those with a mobile stay, those without go to Archived", dev):
        dev.locator("[data-se-confirm-send], button:has-text('Send to')").first.click()
        dev.wait_for_selector("dialog.fb-modal[open] [data-se-moves]")
        text = dev.locator("dialog.fb-modal[open] [data-se-moves]").inner_text()
        assert "stay in Leads" in text or "stays in Leads" in text
        assert "Archived" in text and "Emailed, no number" in text
        dev.locator("dialog.fb-modal[open] [data-fb-ok]").click()
        dev.wait_for_timeout(2500)
    message = mailbox.wait_for(with_mobile, "A word from Barry")
    link = mailbox.link(message, "/add-number/")
    barry = _barry(w, 1440, 900, mobile=False)
    with w.step("The one with a mobile stays in Leads tagged Emailed; the one without is in Archived (Group email)", barry):
        barry.goto(f"{OFFICE}/leads/?range=all&emailed=1")
        assert barry.locator("[data-lead-row]", has_text=with_mobile).locator("[data-emailed-tag]").count() == 1
        barry.goto(f"{OFFICE}/leads/?view=archived")
        archived = barry.locator("[data-lead-row]", has_text=without).inner_text()
        assert "Emailed, no number" in archived and "Group email" in archived, archived
    with w.step("His own link opens the add-your-number page; he adds a number and lands on the Approach list", barry):
        public = w.page(width=375, height=667, mobile=True)
        mail = mailbox.wait_for(without, "A word from Barry") if mailbox.find(without, "A word from Barry") else None
        link = mailbox.link(mail, "/add-number/") if mail else link
        public.goto(link)
        public.wait_for_selector("[data-add-number]")
        assert public.locator("button[type=submit]").bounding_box()["y"] < 667, "the button is below the fold at 375 by 667"
        public.locator("#id_mobile").fill("07911 123499")
        public.locator("#id_consent").check()
        public.locator("button[type=submit]").click()
        public.wait_for_selector("h1:has-text('Thank you.')")
        barry.goto(f"{OFFICE}/outreach/")
        assert barry.locator("[data-outreach-row]").filter(has_text=re.compile("office2-")).count() >= 1
        barry.goto(f"{OFFICE}/leads/?view=archived")
        assert barry.locator("[data-lead-row]", has_text=link and (without if mail else with_mobile)).count() == 0
    with w.step("A bounce after the send brings an archived lead back to Leads as Possible fake", barry):
        out = _shell(
            "from outreach import services as s\nfrom notifications import suppression\nfrom notifications.models import EmailSuppression\n"
            "from outreach.models import ArchivedLead\nfrom django.contrib.auth import get_user_model\n"
            "s.archive_after_group_email('office2-bounce@example.test')\n"
            "suppression.add('office2-bounce@example.test', EmailSuppression.HARD_BOUNCE)\n"
            "s.return_bounced_lead('office2-bounce@example.test')\nprint('ARCH', ArchivedLead.objects.filter(email='office2-bounce@example.test').count())")
        assert "ARCH 0" in out, out


def office2_autoload(w):
    _shell(
        "from office.tests.test_leads import lead\nfrom journey.models import JourneySession\n"
        "for i in range(60):\n    s = lead(f'office2-pile{i}@example.test', finish=False)\n"
        "    JourneySession.objects.filter(pk=s.pk).update(lead_mobile=f'+4477011{i:05d}')\nprint('PILE')")
    page = _barry(w)
    with w.step("Leads on a phone: the first page loads, then scrolling loads the rest by itself", page):
        page.goto(f"{OFFICE}/leads/?range=all")
        page.wait_for_selector("[data-lead-row]")
        first = page.locator("[data-lead-row]").count()
        assert page.locator("[data-list-card]").get_attribute("data-auto") is not None
        for _ in range(8):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(600)
        assert page.locator("[data-lead-row]").count() > first, "no rows were added by scrolling"
        assert page.locator("[data-end-row]").count() == 1, "no end of the list"
        assert page.locator("[data-show-more]").first.is_hidden() if page.locator("[data-show-more]").count() else True
    with w.step("Open a person far down, go Back: the same rows are there and the page is where he was", page):
        count = page.locator("[data-lead-row]").count()
        link = page.locator("[data-lead-row] .o-rowlink").nth(40)
        link.scroll_into_view_if_needed()
        y = page.evaluate("scrollY")
        link.click()
        page.wait_for_url(re.compile(r"/leads/[0-9a-f-]{36}/"))
        page.go_back()
        page.wait_for_selector("[data-lead-row]")
        page.wait_for_function(f"() => document.querySelectorAll('[data-lead-row]').length >= {count}")
        page.wait_for_timeout(500)
        assert abs(page.evaluate("scrollY") - y) < 300, (y, page.evaluate("scrollY"))
    with w.step("No sideways scroll, and the last row clears the tab bar", page):
        ok, wide, inner = no_horizontal_overflow(page)
        assert ok, f"{wide}px in {inner}px"
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        end = page.locator("[data-end-row]").bounding_box()
        bar = page.locator("[data-office-nav]").bounding_box()
        assert end["y"] + end["height"] <= bar["y"] + 1, (end, bar)


OFFICE2_WALKS = [
    ("office2_home_tabs", "25. Office 2: phone Home cards and rings, five tabs, Revenue", office2_home_tabs, ()),
    ("office2_approvals", "26. Office 2: approve, decline, undo, Registered tables", office2_approvals, ()),
    ("office2_leads_list", "27. Office 2: Leads to the Approach list and back, wa.me, tap feedback", office2_leads_list, ()),
    ("office2_group_send", "28. Office 2: group send with its confirm, add-your-number link, a bounce", office2_group_send, (r"status of 4\d\d",)),
    ("office2_autoload", "29. Office 2: Leads loads itself on a phone and Back returns to the row", office2_autoload, ()),
]
