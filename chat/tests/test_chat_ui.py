"""The Ask us button and panel markup (docs/design/ASK-US-CHAT.md). The behaviour lives in common/static/common/js/chat.js."""
from django.test import Client, TestCase, override_settings
from django.template.loader import render_to_string

from chat.models import FaqItem
from journey.copy import GATE
from plans.management.commands.seed_phase1 import seed_all

KEY = override_settings(ANTHROPIC_API_KEY="test-key-not-real")


class ChatButtonTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    @KEY
    def test_pill_and_panel_on_public_pages(self):
        for path in ("/", "/the-spa/", "/privacy/"):
            html = Client().get(path).content.decode()
            self.assertIn("data-chat-open", html, path)
            self.assertIn('aria-controls="ask-us"', html, path)
            self.assertIn('aria-haspopup="dialog"', html, path)
            self.assertIn('<dialog id="ask-us"', html, path)
            self.assertIn('aria-labelledby="ask-us-title"', html, path)
            self.assertIn("common/js/chat", html, path)

    @KEY
    def test_pill_starts_hidden_so_there_is_never_a_dead_button(self):
        html = Client().get("/").content.decode()
        pill = html[html.index("data-chat-open"):]
        self.assertIn("hidden>", pill[:300])

    @KEY
    def test_absent_where_the_backend_says_no(self):
        for path in ("/journey/", "/gold-card/apply/", "/account/", "/login/", "/register/", "/tour/"):
            response = Client().get(path, follow=True)
            self.assertNotContains(response, "data-chat-open", msg_prefix=path)
            self.assertNotContains(response, 'id="ask-us"', msg_prefix=path)

    @override_settings(ANTHROPIC_API_KEY="")
    def test_absent_when_the_key_is_unset(self):
        for path in ("/", "/the-spa/", "/privacy/"):
            response = Client().get(path)
            self.assertNotContains(response, "data-chat-open", msg_prefix=path)
            self.assertNotContains(response, "ask-us", msg_prefix=path)

    @KEY
    def test_panel_markup(self):
        html = Client().get("/").content.decode()
        for needle in ('data-state-url="/chat/state/"', 'data-message-url="/chat/message/"', 'data-email-url="/chat/email/"',
                       'role="log"', 'aria-live="off"', 'aria-live="polite" data-chat-live', 'maxlength="500"', 'for="ask-us-input"',
                       "Your question", "Ask a question", "Ask us anything.", "Prefer a person?", "Message our team",
                       "AI assistant. Chats are kept for 90 days.", 'data-chat-tpl="handoff"', 'data-chat-tpl="email"',
                       "WhatsApp us", "Email us", "Show prices", "Not now", GATE["consent"], GATE["privacy_label"], 'name="website"'):
            self.assertIn(needle, html)
        self.assertNotIn("value=\"on\"", html[html.index('data-chat-tpl="email"'):][:2500].split("consent")[1][:80])  # not pre-ticked

    @KEY
    def test_cream_card_with_assistant_name_and_fallbacks(self):
        html = Client().get("/").content.decode()
        self.assertIn('class="chat on-light"', html)
        self.assertNotIn("on-dark\" aria-labelledby=\"ask-us-title", html)
        self.assertIn("Spa 99 Assistant", html)  # the fallback until System > Assistant sets a name
        self.assertIn("Ask us anything.", html)

    def test_assistant_words_from_context(self):
        html = render_to_string("chat/_chat.html", {"chat_gate": GATE, "chat_handoff": {"email": "h@x.test", "mailto": "", "whatsapp_url": ""}, "chat_suggested": [],
                                                    "chat_assistant": {"name": "Ask Spa 99", "welcome_heading": "Hello.", "welcome_line": "Anything about the spa."}})
        for words in ("Ask Spa 99", "Hello.", "Anything about the spa."):
            self.assertIn(words, html)

    @KEY
    def test_fallback_chips_until_faq_questions_are_suggested(self):
        html = Client().get("/").content.decode()
        for question in ("When do you open?", "What is included in a membership?", "What is the Gold Card?", "Where are you?"):
            self.assertIn(question, html)

    @KEY
    def test_suggested_faq_questions_replace_the_fallback(self):
        FaqItem.objects.all().delete()
        FaqItem.objects.create(question="Is there parking nearby?", answer="Yes.", visible=True, suggested=True, order=1)
        html = Client().get("/").content.decode()
        self.assertIn("Is there parking nearby?", html)
        self.assertNotIn("Where are you?", html)

    @KEY
    def test_no_inline_script_and_no_json_blob(self):
        html = render_to_string("chat/_chat.html", {"chat_gate": GATE, "chat_handoff": {"email": "hello@spa99.test", "mailto": "mailto:hello@spa99.test", "whatsapp_url": ""}, "chat_suggested": []})
        self.assertEqual(html.count("<script"), 1)
        self.assertIn('type="module" src="', html)
        self.assertNotIn("onclick", html)

    def test_files_exist_and_use_tokens(self):
        from django.contrib.staticfiles import finders

        css = open(finders.find("common/css/chat.css")).read()
        tokens = open(finders.find("common/css/tokens.css")).read()
        self.assertIn("--chat-w: 23.75rem", tokens)
        self.assertIn("--z-chat-entry: 30", tokens)
        self.assertIn('@import "chat.css"', open(finders.find("common/css/app.css")).read())
        self.assertNotRegex(css, r"#[0-9a-fA-F]{3,8}\b")  # no ad-hoc colours
        import re

        script = open(finders.find("common/js/chat.js")).read()
        uses = re.findall(r"(\w+)\.innerHTML", script)
        self.assertEqual(set(uses), {"chips"})  # only the welcome chips, restored from our own template; never model text
