"""The chat walk-throughs (25 onwards): the two reach out buttons, WhatsApp, email chat, and the optional mobile at the end of the journey.
Same rules as walks.py: each is a plain function that takes a Walk, every `with w.step(...)` is one screenshotted step, the first failed step ends that walk-through.

Twilio and Postmark are faked: Twilio in e2e/fakes.py (a send is recorded, never made; his messages and the ticks are posted to the real webhooks, signed), Postmark as the
file email backend plus real posts to the inbound webhook (e2e/chatkit.py). Nothing here can reach a real service, and no fake-mode switch exists outside e2e/settings.py."""
import re
import time

from . import mailbox
from .chatkit import postmark_inbound, twilio_calls, whatsapp_from_him
from .kit import OFFICE, PASSWORD, STAFF, answer_journey, dbtool, no_horizontal_overflow, open_register, problems_modal, sign_in, tick
from .walks import body_text

ADMIN = STAFF["admin"]
WANDA = "chat-wanda@example.com"
WANDA_PHONE_TYPED, WANDA_PHONE = "07400 123462", "+447400123462"
EDDIE = "chat-eddie@example.com"
FRAME_FLAGS = "allow-same-origin allow-popups allow-popups-to-escape-sandbox"
# A visitor the site counts as a person: the headless browser's own user agent is treated as a bot, and a bot's journey is never a lead.
HUMAN = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
HUMAN_PHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"


def ensure_lead(w, email, mobile, first):
    """A lead made the real way (the journey's email step). Made once per run: later walk-throughs find it."""
    if not dbtool("lead", email)["exists"]:
        answer_journey(w.page(user_agent=HUMAN), email=email, mobile=mobile, first_name=first)
    return dbtool("lead", email)


def office_page(w, width=1280, height=900, mobile=False):
    page = w.page(width, height, mobile=mobile)
    sign_in(page, OFFICE, ADMIN["email"], PASSWORD)
    return page


def wait_for_calls(count, timeout=15):
    """The site sends inline in this run, so the call is normally there already."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        calls = twilio_calls()
        if len(calls) >= count:
            return calls
        time.sleep(0.3)
    raise AssertionError(f"Expected {count} sends to Twilio, saw {len(twilio_calls())}.")


# ---------- 25: the two buttons ----------

def chat_buttons(w):
    with w.step("A visitor finishes the journey and leaves a mobile"):
        lead = ensure_lead(w, WANDA, WANDA_PHONE_TYPED, "Wanda")
        assert lead["mobile"] == WANDA_PHONE, f"The mobile was stored as {lead['mobile']!r}"
    with w.step("Another visitor finishes it with no mobile at all: the step does not insist"):
        other = ensure_lead(w, EDDIE, None, "Eddie")
        assert other["exists"] and other["mobile"] == "", f"Stored: {other}"
    office = office_page(w)
    with w.step("His page with a mobile and no chat: Start WhatsApp chat is the one primary, Start email is secondary", office):
        office.goto(f"{OFFICE}/leads/{dbtool('lead', WANDA)['id']}/")
        card = office.locator("[data-person-reach]")
        wa, em = card.locator("[data-whatsapp-open]"), card.locator("[data-email-open]")
        assert wa.inner_text().strip() == "Start WhatsApp chat", wa.inner_text()
        assert em.inner_text().strip() == "Start email", em.inner_text()
        assert "btn-primary" in wa.get_attribute("class") and "btn-secondary" in em.get_attribute("class")
    with w.step("A lead with no mobile: only the email button, and a grey line that opens Add a mobile", office):
        office.goto(f"{OFFICE}/leads/{dbtool('lead', EDDIE)['id']}/")
        card = office.locator("[data-person-reach]")
        assert card.locator("[data-whatsapp-open]").count() == 0, "A WhatsApp button shows for a man with no number"
        assert "btn-primary" in card.locator("[data-email-open]").get_attribute("class"), "With no WhatsApp, Email should be the primary"
        add = card.locator("button[data-add-mobile]")
        assert "Add a number to enable WhatsApp" in add.inner_text()
        add.click()
        office.locator("dialog[data-dialog=mobile][open]").wait_for()
    with w.step("Saving a number swaps the card: Start WhatsApp chat appears, primary, with focus; Email drops to secondary", office):
        dialog = office.locator("dialog[data-dialog=mobile][open]")
        dialog.locator("input[name=mobile]").fill("07400 123463")
        dialog.locator("button[type=submit]").click()
        office.locator("[data-person-reach] [data-whatsapp-open]").wait_for()
        office.wait_for_function("document.activeElement && document.activeElement.hasAttribute('data-whatsapp-open')")
        card = office.locator("[data-person-reach]")
        assert card.locator("[data-whatsapp-open]").inner_text().strip() == "Start WhatsApp chat"
        assert "btn-primary" in card.locator("[data-whatsapp-open]").get_attribute("class")
        assert "btn-secondary" in card.locator("[data-email-open]").get_attribute("class")
    phone = office_page(w, 375, 667, mobile=True)
    with w.step("Phone width: the card fits with no sideways scroll", phone):
        phone.goto(f"{OFFICE}/leads/{dbtool('lead', WANDA)['id']}/")
        ok, wide, inner = no_horizontal_overflow(phone)
        assert ok, f"Sideways scroll: {wide} > {inner}"


# ---------- 26: WhatsApp ----------

def whatsapp_chat(w):
    ensure_lead(w, WANDA, WANDA_PHONE_TYPED, "Wanda")
    office = office_page(w)
    with w.step("Start WhatsApp chat opens the chat with the template picker (nothing has been sent)", office):
        office.goto(f"{OFFICE}/leads/{dbtool('lead', WANDA)['id']}/")
        office.locator("[data-person-reach] [data-whatsapp-open]").click()
        office.wait_for_url(re.compile(r"/whatsapp/[0-9a-f-]{36}/"))
        office.locator("dialog[data-tpl][open]").wait_for()
        office.keyboard.press("Escape")
        assert "Start with a template" in body_text(office)
    with w.step("He writes first (a signed Twilio webhook): the window opens and the composer shows", office):
        assert whatsapp_from_him(WANDA_PHONE, "Hello, is Tier 2 available this month?", "SMe2e0001") == 200
        office.reload()
        office.locator("[data-composer]").wait_for(state="visible")
    with w.step("Staff send a message: it reaches Twilio exactly as typed", office):
        before = len(twilio_calls())
        office.locator("[data-input]").fill("Yes, there is room.")
        office.keyboard.press("Enter")
        calls = wait_for_calls(before + 1)
        sent = calls[-1]
        assert sent["Body"] == "Yes, there is room." and sent["To"] == f"whatsapp:{WANDA_PHONE}", sent
        office.locator(".o-wa-line--out .o-wa-text", has_text="Yes, there is room.").first.wait_for()
    with w.step("His reply to that message arrives with its quote (the Office links the two)", office):
        assert whatsapp_from_him(WANDA_PHONE, "Great, see you then", "SMe2e0002", OriginalRepliedMessageSid=sent["sid"]) == 200
        office.locator(".o-wa-line--in .o-wa-reply").first.wait_for(timeout=20000)  # the chat polls every 4 seconds
        assert "Yes, there is room." in office.locator(".o-wa-line--in .o-wa-reply").first.inner_text()
    with w.step("Reply on his bubble: the quote bar, the honest note, and a quoted line goes to Twilio", office):
        line = office.locator(".o-wa-line--in", has_text="Great, see you then").last
        line.hover()
        line.locator('[data-act="reply"]').click()
        quote = office.locator("[data-quote]")
        quote.wait_for(state="visible")
        assert "On his phone this shows as a quoted line." in quote.inner_text()
        before = len(twilio_calls())
        office.locator("[data-input]").fill("Looking forward to it.")
        office.keyboard.press("Enter")
        body = wait_for_calls(before + 1)[-1]["Body"]
        assert body == "> Great, see you then\n\nLooking forward to it.", repr(body)
        assert not quote.is_visible(), "The quote bar stayed after sending"
        office.locator(".o-wa-line--out .o-wa-reply", has_text="Great, see you then").first.wait_for()
    with w.step("Quick emoji: one tap sends a normal message, with no quote, and the screen says so", office):
        line = office.locator(".o-wa-line--in", has_text="Great, see you then").last
        line.hover()
        line.locator('[data-act="emoji"]').click()
        assert "Goes as a normal message, not a reaction." in line.inner_text()
        before = len(twilio_calls())
        line.locator('[data-act="send-emoji"]').first.click()
        body = wait_for_calls(before + 1)[-1]["Body"]
        assert body == "\U0001F44D", repr(body)
    with w.step("An MP4 is accepted and goes out as a file; an iPhone .mov is refused in words", office):
        mp4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + b"\x00" * 2000
        office.locator("[data-file]").set_input_files({"name": "clip.mov", "mimeType": "video/quicktime", "buffer": mp4})
        assert "Photos, PDFs or MP4 videos only." in office.locator("[data-tray-error]").inner_text()
        before = len(twilio_calls())
        office.locator("[data-file]").set_input_files({"name": "clip.mp4", "mimeType": "video/mp4", "buffer": mp4})
        office.locator("[data-send]").click()
        call = wait_for_calls(before + 1)[-1]
        assert call.get("MediaUrl", "").startswith("http") and "/twilio/whatsapp/media/" in call["MediaUrl"], call
    with w.step("A message the Office cannot show gets a plain neutral bubble", office):
        assert whatsapp_from_him(WANDA_PHONE, "", "SMe2e0003", MessageType="reaction") == 200
        office.locator(".o-wa-other").first.wait_for(timeout=20000)
        assert office.locator(".o-wa-other").first.inner_text().startswith("This message cannot be shown here.")


# ---------- 27: email chat ----------

def email_chat(w):
    ensure_lead(w, WANDA, WANDA_PHONE_TYPED, "Wanda")
    office = office_page(w)
    subject = "Welcome to Spa 99"
    with w.step("Email tab, New email: find him by name, write a subject and a bold word, send", office):
        office.goto(f"{OFFICE}/email/")
        office.locator("[data-em-new]").first.click()
        office.locator("[data-em-new-root]").wait_for()
        office.locator("[data-to-input]").fill("chat-wanda")
        office.locator("li.o-em-option").first.wait_for()
        office.locator("li.o-em-option").first.click()
        office.locator("[data-subject-input]").fill(subject)
        editor = office.locator("[data-ed-editable]")
        editor.click()
        editor.type("Hello Wanda, ")
        office.locator('[data-cmd="bold"]').click()
        editor.type("welcome")
        office.locator(".o-em-send--tools").click()
        office.locator("[data-em-thread-root]").wait_for()
        assert re.search(r"/email/[0-9a-f-]{36}/", office.url), office.url
    with w.step("The email went out from hello@ with a Reply-To that carries the thread's token, and the bold survived", office):
        message = mailbox.wait_for(WANDA, subject)
        token = dbtool("thread-token", WANDA)["token"]
        assert token and f"reply+{token}@reply.e2e.example" in str(message["Reply-To"]), message["Reply-To"]
        html = message.get_body(preferencelist=("html",)).get_content()
        assert "<strong>welcome</strong>" in html or "<b>welcome</b>" in html, "The bold word is not bold in the email"
    with w.step("His formatted reply arrives (a signed-in Postmark post, found by the poll) and shows in the sandboxed frame", office):
        html_body = ('<p>Thanks, that is <b>great</b>.</p><script>window.__pwned = 1</script><img src="https://tracker.example/pixel.gif" width="1" height="1">'
                     '<p>Regards, Wanda</p><blockquote>Hello Wanda, welcome</blockquote>')
        status = postmark_inbound(token, "pm-e2e-0001", Subject=f"Re: {subject}", FromFull={"Email": WANDA, "Name": "Wanda Walker"},
                                  StrippedTextReply="Thanks, that is great.", TextBody="Thanks, that is great.\n\n> Hello Wanda, welcome", HtmlBody=html_body)
        assert status == 200, f"The inbound webhook answered {status}"
        office.locator(".o-em-msg--in").first.wait_for(timeout=40000)  # the thread polls every 15 seconds
        frame_el = office.locator("iframe.o-em-frame").first
        frame_el.wait_for()
        assert frame_el.get_attribute("sandbox") == FRAME_FLAGS, f"The frame's flags are {frame_el.get_attribute('sandbox')!r}"
        assert "allow-scripts" not in (frame_el.get_attribute("sandbox") or "")
        frame = frame_el.element_handle().content_frame()
        frame.wait_for_selector("p")
        assert frame.locator("script").count() == 0, "A script reached the frame"
        assert frame.evaluate("window.__pwned") is None, "His script ran"
        assert "Thanks, that is" in frame.locator("body").inner_text()
        assert office.locator("[data-em-thread-root] script:not([type='application/json'])").count() == 0, "A script is in the Office page"
        assert "Outside pictures are hidden." in office.locator("[data-em-thread-root]").inner_text()
        assert office.locator(".o-em-toggle", has_text="Show earlier text").count() == 1, "The quoted history is not folded"
    with w.step("Reply from the thread: the editor, bold, send; a second email goes out with Re:", office):
        office.locator("[data-reply-open]").click()
        editor = office.locator("[data-composer] [data-ed-editable]")
        editor.click()
        editor.type("Glad to hear it.")
        office.locator("[data-composer] .o-em-send--tools").click()
        mailbox.wait_for(WANDA, f"Re: {subject}")
        office.locator(".o-em-msg--out").nth(1).wait_for()
    phone = office_page(w, 375, 667, mobile=True)
    with w.step("Phone width: the list and the thread fit with no sideways scroll", phone):
        phone.goto(f"{OFFICE}/email/")
        ok, wide, inner = no_horizontal_overflow(phone)
        assert ok, f"List: {wide} > {inner}"
        phone.locator("a.o-em-row").first.click()
        phone.locator("[data-em-thread-root]").wait_for()
        phone.wait_for_timeout(800)
        ok, wide, inner = no_horizontal_overflow(phone)
        assert ok, f"Thread: {wide} > {inner}"


# ---------- 28: mobile optional at the end of the journey, Register unchanged ----------

def journey_optional_mobile(w):
    email = "chat-optional@example.com"
    site = w.page(375, 667, mobile=True, user_agent=HUMAN_PHONE)
    with w.step("The email step says the mobile is optional, gives one reason, and uses the owner's tick wording", site):
        answer_journey(site, stop_before_result=True)
        site.wait_for_timeout(1500)  # the screen's own reveal has to finish before its height means anything
        gate = site.locator(".lead-gate")
        text = gate.inner_text()
        assert "Mobile (optional)" in text, text
        assert "Add it and the team can reach out with good offers." in text
        assert "Yes, Spa 99 may email me, and WhatsApp me if I add a number, about opening and offers. I can stop at any time." in text
        ok, tall, inner = no_horizontal_overflow(site)
        assert ok
        height = site.evaluate("document.documentElement.scrollHeight")
        assert height <= 667, f"The email step runs past one screen at 375 by 667 ({height}px)"
    with w.step("A typed number that is wrong is told, in words; clearing it makes it fine", site):
        site.locator("#lead-mobile").fill("123")
        site.locator("#lead-first-name").click()
        site.locator("#lead-mobile-msg[data-state=error]").wait_for()
        assert "Check it, or leave it blank." in site.locator("#lead-mobile-msg").inner_text()
        site.locator("#lead-mobile").fill("")
        site.locator("#lead-first-name").click()
        site.wait_for_function("document.querySelector('#lead-mobile-msg').dataset.state === 'hint'")
        assert site.locator("#lead-mobile-hint").is_visible(), "The hint did not come back"
        assert site.locator("#lead-mobile").get_attribute("aria-invalid") is None
    with w.step("Name, email and the tick are enough: the result shows, the mobile is stored blank, the consent version is today's", site):
        site.locator("#lead-first-name").fill("Opal")
        site.locator("#lead-email").fill(email)
        tick(site, "consent")
        site.locator("[data-gate-primary]").click()
        site.wait_for_selector("[data-flow-root] .result")
        stored = dbtool("lead", email)
        assert stored["exists"] and stored["mobile"] == "" and stored["first_name"] == "Opal", stored
        assert stored["consent_version"] == "2026-11-04", stored
    register = w.page()
    with w.step("Register still refuses a blank mobile (unchanged)", register):
        open_register(register, "chat-register@example.com")
        register.locator("label.plan-chip", has_text="Tier 2").first.click()
        register.locator("#id_first_name").fill("Rex")
        register.locator("#id_last_name").fill("Register")
        register.locator("#id_email").fill("chat-register@example.com")
        register.locator("#id_password").fill(PASSWORD)
        register.locator("#id_mobile").fill("")  # the page prefills the number the journey took: a blank one is what is tested
        register.locator("#dob-day").fill("14")
        register.locator("#dob-month").fill("03")
        register.locator("#dob-year").fill("1985")
        tick(register, "men_only_accepted")
        tick(register, "privacy_accepted")
        register.locator("#register-form button[type=submit]").click()
        lines = problems_modal(register)
        assert any("mobile" in line.lower() for line in lines), f"The form says: {lines}"
        assert "/register/" in register.url and "/sent/" not in register.url
        assert not dbtool("user", "chat-register@example.com")["exists"], "An account was made with no mobile"


CHAT_WALKS = [
    ("chat_buttons", "25. Reach out buttons: Start or Open, the grey line, adding a number", chat_buttons, ()),
    ("whatsapp_chat", "26. WhatsApp: send, his reply, reply with a quote, emoji, MP4, a message it cannot show", whatsapp_chat, ()),
    ("email_chat", "27. Email chat: new email, his reply in the frame (no scripts), reply", email_chat, ()),
    ("journey_optional_mobile", "28. Journey mobile is optional; Register still requires one", journey_optional_mobile, (r"status of 40\d",)),
]
