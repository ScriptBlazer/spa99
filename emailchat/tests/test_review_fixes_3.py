"""Final review fixes for the email chat. Mocked: nothing real is sent, the queue runs inline."""
import os
import time

from emailchat import services
from emailchat.models import Message
from emailchat.tests.test_emailchat import Base, inbound_post, payload_for


def _fill(unit, size=1_000_000):
    return (unit * (size // len(unit) + 1))[:size]


SHAPES = {
    "div/": _fill("<div/>"), "div <>": _fill("<div <>"), 'div a="<"': _fill('<div a="<">'), "x-a x-b": _fill("<x-a></x-b>"),
    "span div misnest": _fill("<span><div></span></div>"), "deep": "<div>" * 200_000, "wide": _fill("<p>a</p>"), "comments": _fill("<!-- a -->"),
    "entities": _fill("&amp;&lt;&#x41;"), "unclosed": _fill("<a"), "unclosed with a late >": _fill("<a<") + ">",
    "misnest at the budget": "<span><div></span></div>" * 12_000 + "x" * 700_000,
}


class HostileHtmlBudgetTests(Base):
    def test_every_one_megabyte_shape_goes_through_the_webhook_quickly_and_keeps_its_text(self):
        times = {}
        for number, (name, html) in enumerate(SHAPES.items()):
            payload = {**payload_for(self.thread, text="", message_id=f"pm-shape-{number}"), "HtmlBody": html}
            started = time.monotonic()
            self.assertEqual(inbound_post(payload).status_code, 200, name)
            times[name] = time.monotonic() - started
            message = Message.objects.get(provider_id=f"pm-shape-{number}")
            if message.body_html == "":  # refused: the text is kept and the note says so
                self.assertEqual(message.note, services.TOO_COMPLEX, name)
        if os.environ.get("SHOW_TIMES"):
            for name, took in sorted(times.items(), key=lambda item: -item[1]):
                print(f"{took:6.2f}s  {name}")
        self.assertLess(max(times.values()), 2.5, times)

    def test_the_budget_refuses_by_tag_count_and_lets_real_mail_through(self):
        from common import richtext

        self.assertTrue(richtext.too_complex("<div/>" * 500))  # a slash does not close anything
        self.assertTrue(richtext.too_complex("<span><div></span></div>" * 13_000))  # shallow by the depth count, over the budget
        self.assertFalse(richtext.too_complex("<table><tr><td><div><p>x</p></div></td></tr></table>" * 2_000))  # a long newsletter
