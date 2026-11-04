"""The chat walk-throughs (25 onwards): the two reach out buttons (WhatsApp and Email), WhatsApp, and the mobile at the end of the journey.
Same rules as walks.py: each is a plain function that takes a Walk, every `with w.step(...)` is one screenshotted step, the first failed step ends that walk-through.

Twilio is faked in e2e/fakes.py (a send is recorded, never made; his messages and the ticks are posted to the real webhooks, signed); email goes to the file backend. Nothing here can reach a real service, and no fake-mode switch exists outside e2e/settings.py."""
import re
import time

from . import mailbox
from .chatkit import twilio_calls, whatsapp_from_him
from .kit import OFFICE, PASSWORD, STAFF, answer_journey, dbtool, no_horizontal_overflow, open_register, problems_modal, sign_in, tick
from .walks import body_text

ADMIN = STAFF["admin"]
WANDA = "chat-wanda@example.com"
WANDA_PHONE_TYPED, WANDA_PHONE = "07400 123462", "+447400123462"
EDDIE = "chat-eddie@example.com"
FRANK = "chat-frank@example.com"
FRANK_PHONE_TYPED, FRANK_PHONE = "07400 123464", "+447400123464"
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


# ---------- 25: the two buttons, and sending the email ----------

def chat_buttons(w):
    with w.step("A visitor finishes the journey and leaves a mobile"):
        lead = ensure_lead(w, WANDA, WANDA_PHONE_TYPED, "Wanda")
        assert lead["mobile"] == WANDA_PHONE, f"The mobile was stored as {lead['mobile']!r}"
    with w.step("An older lead, from before the number was required, has no mobile"):
        ensure_lead(w, EDDIE, "07400 123465", "Eddie")
        dbtool("clear-lead-mobile", EDDIE)
        other = dbtool("lead", EDDIE)
        assert other["exists"] and other["mobile"] == "", f"Stored: {other}"
    office = office_page(w)
    with w.step("His page with a mobile and no chat: Start WhatsApp chat is the one primary, Email is secondary", office):
        office.goto(f"{OFFICE}/leads/{dbtool('lead', WANDA)['id']}/")
        card = office.locator("[data-person-reach]")
        wa, em = card.locator("[data-whatsapp-open]"), card.locator("[data-email-open]")
        assert wa.inner_text().strip() == "Start WhatsApp chat", wa.inner_text()
        assert em.inner_text().strip() == "Email", em.inner_text()
        assert "btn-primary" in wa.get_attribute("class") and "btn-secondary" in em.get_attribute("class")
        # Start can make a chat, so it is a small form POST (with its CSRF token), never a link; Open (below, walk 26) is a link
        assert card.locator("form[data-whatsapp-start][method=post] input[name=csrfmiddlewaretoken]").count() == 1, "Start WhatsApp chat is not a CSRF form"
        assert card.locator("a[data-whatsapp-open]").count() == 0, "Start WhatsApp chat is a link: a GET would write"
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
    with w.step("Email: the pop-up (one text box) sends from him with his address as Reply-To, and the timeline shows it", office):
        office.goto(f"{OFFICE}/leads/{dbtool('lead', WANDA)['id']}/")
        office.locator("[data-email-open]").click()
        dialog = office.locator("dialog[data-dialog=email][open]")
        dialog.wait_for()
        assert f"From Adam, Spa 99 <{ADMIN['email']}>" in dialog.inner_text(), dialog.inner_text()  # UNRUN: written with the two-button change
        dialog.locator("textarea[name=message]").fill("Hello Wanda, welcome to Spa 99.")
        dialog.locator("button[type=submit]").click()
        office.locator("text=Your email is on its way").wait_for()
        message = mailbox.wait_for(WANDA, "A message from Spa 99")
        assert ADMIN["email"] in str(message["From"]) and "Spa 99" in str(message["From"]), message["From"]
        assert ADMIN["email"] in str(message["Reply-To"]), message["Reply-To"]
        assert "Hello Wanda, welcome to Spa 99." in mailbox.text_body(message) and "Kind regards" in mailbox.text_body(message)
        office.reload()
        assert "Email sent by" in office.locator("[data-person-timeline], .o-timeline").first.inner_text(), "The email is not in the timeline"
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
    wanda_chat = office.url  # the Frank steps leave this page, so the later steps come back to it
    ensure_lead(w, FRANK, FRANK_PHONE_TYPED, "Frank")
    with w.step("He wrote first and nobody linked the chat: Open WhatsApp chat is a link, it reads only, and the thread offers Link it after the chat is on screen", office):
        assert whatsapp_from_him(FRANK_PHONE, "Hi, I'm Frank", "SMe2e0020") == 200
        office.goto(f"{OFFICE}/leads/{dbtool('lead', FRANK)['id']}/")
        button = office.locator("[data-person-reach] a[data-whatsapp-open]")
        assert button.locator("span").first.inner_text().strip() == "Open WhatsApp chat", button.inner_text()  # the button also carries his unread count, so read the label span only
        button.click()
        office.wait_for_url(re.compile(r"/whatsapp/[0-9a-f-]{36}/"))
        office.locator("[data-link-offer]").wait_for()
        text = body_text(office)
        assert "Hi, I'm Frank" in text and FRANK_PHONE in text, "The chat was not on screen with the offer"
        assert "This number isn't linked to Frank. Link it?" in text, text[:300]
    with w.step("Link it links the chat to him (a POST), and the offer goes", office):
        office.locator("[data-link-offer] button[type=submit]").click()
        office.wait_for_load_state()
        office.locator("[data-link-offer]").wait_for(state="detached")
        office.get_by_text("Linked to Frank.").first.wait_for()  # a toast: it appears just after the page loads
    with w.step("He writes first (a signed Twilio webhook): the window opens and the composer shows", office):
        assert whatsapp_from_him(WANDA_PHONE, "Hello, is Tier 2 available this month?", "SMe2e0001") == 200
        office.goto(wanda_chat)
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


# ---------- 27: the mobile is required at the end of the journey, Register unchanged ----------

def journey_mobile_required(w):
    site = w.page(375, 667, mobile=True, user_agent=HUMAN_PHONE)
    with w.step("The email step asks for first name, email and mobile plainly, with the owner's tick wording, and fits one screen", site):
        answer_journey(site, stop_before_result=True)
        site.wait_for_timeout(1500)  # the screen's own reveal has to finish before its height means anything
        text = site.locator(".lead-gate").inner_text()
        assert "optional" not in text.lower() and "good offers" not in text, text
        assert "Yes, Spa 99 may email and WhatsApp me about opening and offers. I can stop at any time." in text
        ok, tall, inner = no_horizontal_overflow(site)
        assert ok
        height = site.evaluate("document.documentElement.scrollHeight")
        assert height <= 667, f"The email step runs past one screen at 375 by 667 ({height}px)"
    with w.step("A blank mobile is refused", site):
        site.locator("#lead-first-name").fill("Opal")
        site.locator("#lead-email").fill("chat-required@example.com")
        tick(site, "consent")
        site.locator("[data-gate-primary]").click()
        site.locator("#lead-mobile-msg[data-state=error]").wait_for()
        assert not dbtool("lead", "chat-required@example.com")["exists"], "A lead was stored with no mobile"
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
    ("journey_mobile_required", "27. Journey mobile is required; Register still requires one", journey_mobile_required, (r"status of 40\d",)),
]
