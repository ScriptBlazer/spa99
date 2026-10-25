"""Toasts and the one modal (docs/design/FEEDBACK.md): the shared markup is on every host, Django messages become toasts."""
from django.contrib.messages import constants
from django.contrib.messages.storage.base import Message
from django.template import Context, Template
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from common.templatetags.feedback_tags import toast_kind, undo_url


class FeedbackTagTests(SimpleTestCase):
    def test_levels_map_to_toast_kinds(self):
        self.assertEqual([toast_kind(t) for t in ("debug", "info", "success", "warning", "error", "", None, "custom")],
                         ["info", "info", "success", "warning", "error", "info", "info", "info"])

    def test_undo_link_is_read_from_the_extra_tags(self):
        self.assertEqual(undo_url("x undo:/changes/4/undo/"), "/changes/4/undo/")
        self.assertEqual(undo_url(""), "")
        self.assertEqual(undo_url(None), "")


class FeedbackMarkupTests(TestCase):
    def render(self, messages):
        items = [Message(level, text, extra_tags=extra) for level, text, extra in messages]
        return Template('{% include "common/_feedback.html" %}').render(Context({"messages": items}))

    def test_regions_and_one_modal_are_always_there(self):
        html = self.render([])
        self.assertIn("data-toasts-polite", html)
        self.assertIn("data-toasts-assertive", html)
        self.assertIn('class="fb-modal"', html)
        self.assertNotIn("data-server-messages", html)

    def test_server_messages_wait_in_a_template_with_kind_and_undo(self):
        html = self.render([(constants.SUCCESS, "Saved.", "undo:/changes/1/undo/"), (constants.ERROR, "Nope.", "")])
        self.assertIn('data-kind="success" data-undo="/changes/1/undo/">Saved.', html)
        self.assertIn('data-kind="error" data-undo="">Nope.', html)

    def test_public_page_has_the_shared_feedback_and_no_browser_dialogs(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('class="toasts"', html)
        self.assertIn("data-fb-modal", html)
