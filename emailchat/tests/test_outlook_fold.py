"""Outlook's quoted mail folds (docs/features/office-email-chat.md, "Outlook quoted history"). The HTML below is what each client really writes for a reply (trimmed): Outlook on the web,
Outlook for Mac (new and the older OLK_SRC_BODY_SECTION), Outlook for Windows (Word HTML), and Gmail and Apple Mail, which mark their quotes themselves. The marker is an empty div with
the class em-fold-from; the page script folds it and everything after it. His new words are never hidden: no marker is the answer when nothing is found, or nothing comes before it."""
import time

from django.test import SimpleTestCase, override_settings

from common import richtext
from emailchat import services
from emailchat.models import Message
from emailchat.tests.test_emailchat import Base, inbound_post, payload_for

OUTLOOK_WEB = ('<html><head><meta http-equiv="Content-Type" content="text/html; charset=utf-8"><style type="text/css" style="display:none;"> P {margin-top:0;margin-bottom:0;} </style></head>'
               '<body dir="ltr"><div class="elementToProof" style="font-family: Aptos, Calibri, Helvetica, sans-serif; font-size: 12pt; color: rgb(0, 0, 0);">Friday at 3 works for me.</div>'
               '<div id="appendonsend"></div><hr style="display:inline-block;width:98%" tabindex="-1"><div id="divRplyFwdMsg" dir="ltr"><font face="Calibri, sans-serif" style="font-size:11pt" color="#000000">'
               '<b>From:</b> Spa 99 &lt;barry@spa99.uk&gt;<br><b>Sent:</b> Tuesday, 3 November 2026 10:12<br><b>To:</b> Dan &lt;dan@example.com&gt;<br><b>Subject:</b> Your visit</font>'
               '<div>&nbsp;</div></div><div class="BodyFragment"><font size="2"><span style="font-size:11pt;"><div class="PlainText">Hello Dan, would Friday suit?</div></span></font></div></body></html>')
OUTLOOK_MAC = ('<html><head><meta http-equiv="Content-Type" content="text/html; charset=utf-8"></head><body style="word-wrap:break-word;"><div>Friday at 3 works for me.</div><div><br></div>'
               '<div id="mail-editor-reference-message-container"><div><div style="border:none; border-top:solid #B5C4DF 1.0pt; padding:3.0pt 0in 0in 0in"><div><b>From: </b>Spa 99 &lt;barry@spa99.uk&gt;<br>'
               '<b>Date: </b>Tuesday, 3 November 2026 at 10:12<br><b>To: </b>Dan &lt;dan@example.com&gt;<br><b>Subject: </b>Your visit</div></div><div><br></div><div>Hello Dan, would Friday suit?</div></div></div></body></html>')
OUTLOOK_MAC_OLD = ('<html><head></head><body style="word-wrap: break-word;"><div>Friday at 3 works for me.</div><div><br></div><span id="OLK_SRC_BODY_SECTION">'
                   '<div style="font-family:Calibri; font-size:11pt; text-align:left; color:black; BORDER-BOTTOM: medium none; BORDER-TOP: #b5c4df 1pt solid; PADDING-TOP: 3pt">'
                   '<span style="font-weight:bold">From: </span>Spa 99 &lt;barry@spa99.uk&gt;<br><span style="font-weight:bold">Date: </span>Tue, 3 Nov 2026<br><span style="font-weight:bold">To: </span>Dan<br>'
                   '<span style="font-weight:bold">Subject: </span>Your visit</div><div><br></div><div>Hello Dan, would Friday suit?</div></span></body></html>')
OUTLOOK_WORD = ('<html xmlns:o="urn:schemas-microsoft-com:office:office"><head><style><!-- p.MsoNormal {margin:0cm;} --></style></head><body lang=EN-GB><div class=WordSection1>'
                '<p class=MsoNormal>Friday at 3 works for me.<o:p></o:p></p><p class=MsoNormal><o:p>&nbsp;</o:p></p><div><div style="border:none;border-top:solid #E1E1E1 1.0pt;padding:3.0pt 0cm 0cm 0cm">'
                '<p class=MsoNormal><b><span lang=EN-US>From:</span></b><span lang=EN-US> Spa 99 &lt;barry@spa99.uk&gt; <br><b>Sent:</b> 03 November 2026 10:12<br><b>To:</b> Dan<br>'
                '<b>Subject:</b> Your visit<o:p></o:p></span></p></div></div><p class=MsoNormal>Hello Dan, would Friday suit?</p></div></body></html>')
GMAIL = ('<div dir="ltr">Friday at 3 works for me.<br><br><div class="gmail_quote"><div dir="ltr" class="gmail_attr">On Tue, 3 Nov 2026 at 10:12, Spa 99 &lt;<a href="mailto:barry@spa99.uk">barry@spa99.uk</a>&gt; wrote:<br></div>'
         '<blockquote class="gmail_quote" style="margin:0px 0px 0px 0.8ex;border-left:1px solid rgb(204,204,204);padding-left:1ex">Hello Dan, would Friday suit?</blockquote></div></div>')
APPLE = ('<html><head><meta http-equiv="content-type" content="text/html; charset=utf-8"></head><body style="overflow-wrap: break-word;"><div>Friday at 3 works for me.</div><div><br>'
         '<blockquote type="cite"><div>On 3 Nov 2026, at 10:12, Spa 99 &lt;barry@spa99.uk&gt; wrote:</div><br class="Apple-interchange-newline"><div><div>Hello Dan, would Friday suit?</div></div></blockquote></div></body></html>')
MARK = "em-fold-from"


class OutlookHtmlTests(SimpleTestCase):
    def check(self, html):
        clean = richtext.clean_incoming(html)
        self.assertEqual(clean.count(MARK), 1)
        before, after = clean.split(MARK, 1)
        self.assertIn("Friday at 3 works for me.", before)  # his words stay in front of the marker
        self.assertNotIn("Hello Dan", before)
        self.assertIn("Hello Dan", after)  # the quote, and the header block with it, come after it
        self.assertIn("Subject:", after)
        self.assertNotIn("Subject:", before)
        return clean

    def test_each_outlook_marks_where_its_quote_begins(self):
        for name, html in (("Outlook web", OUTLOOK_WEB), ("Outlook for Mac", OUTLOOK_MAC), ("Outlook for Mac (older)", OUTLOOK_MAC_OLD), ("Outlook for Windows", OUTLOOK_WORD)):
            with self.subTest(client=name):
                self.check(html)

    def test_gmail_and_apple_mail_keep_their_own_marks_and_get_no_fold_marker(self):
        for html in (GMAIL, APPLE):
            clean = richtext.clean_incoming(html)
            self.assertNotIn(MARK, clean)
            self.assertIn("Friday at 3 works for me.", clean)
        self.assertIn('class="quoted"', richtext.clean_incoming(GMAIL))
        self.assertIn("<blockquote", richtext.clean_incoming(APPLE))

    def test_the_header_block_is_found_without_any_outlook_id_too(self):
        bare = "<div>Thanks, see below.</div><div><b>From:</b> A<br><b>Sent:</b> B<br><b>To:</b> C<br><b>Subject:</b> D</div><div>older</div>"
        clean = richtext.clean_incoming(bare)
        self.assertEqual(clean.index("Thanks, see below.") < clean.index(MARK) < clean.index("older"), True)

    def test_nothing_is_hidden_when_nothing_is_found_or_nothing_comes_before(self):
        for html in ("<p>Just a note. From: me, Sent: soon.</p>", "<p>From: the team</p><p>To: you</p>",  # not a header block
                     "<div><b>From:</b> A<br><b>Sent:</b> B<br><b>To:</b> C<br><b>Subject:</b> D</div><div>a forward with no words of his own</div>",  # nothing before it
                     '<style>.x{color:red}</style><div id="appendonsend"></div><div id="divRplyFwdMsg">quoted</div>',  # only a style sheet before it
                     "<table><tr><td>words</td><td><b>From:</b> A<br><b>Sent:</b> B<br><b>To:</b> C<br><b>Subject:</b> D</td></tr></table>"):  # inside a table: a marker could not stay put
            self.assertNotIn(MARK, richtext.clean_incoming(html), html)

    def test_a_sender_cannot_hide_his_own_text_with_the_marker_class_and_the_token_is_one_off(self):
        clean = richtext.clean_incoming('<div class="em-fold-from">hidden?</div><div class="em-fold-from-x">more</div><p>visible</p>')
        self.assertNotIn(MARK, clean)  # his class is dropped like any other
        self.assertNotEqual(richtext.mark_outlook_fold(OUTLOOK_WEB, "tok1"), richtext.mark_outlook_fold(OUTLOOK_WEB, "tok2"))
        self.assertEqual(richtext.mark_outlook_fold("<p>no quote</p>", "tok"), "<p>no quote</p>")

    def test_hostile_markup_stays_fast(self):
        started = time.monotonic()
        for html in ("<" * 40_000 + "x", "<div " * 20_000, ("<b>From:</b> x<br>" * 12_000), "<div id=" * 20_000, "<!--" * 30_000, "<p>words</p>" + "<br>From: a" * 20_000):
            richtext.outlook_fold_position(html[:290_000])
        self.assertLess(time.monotonic() - started, 5)


class OutlookTextTests(SimpleTestCase):
    WEB = "Friday at 3 works for me.\n\n________________________________\nFrom: Spa 99 <barry@spa99.uk>\nSent: Tuesday, 3 November 2026 10:12\nTo: Dan <dan@example.com>\nSubject: Your visit\n\nHello Dan, would Friday suit?"
    MAC = "Friday at 3 works for me.\n\nFrom: Spa 99 <barry@spa99.uk>\nDate: Tuesday, 3 November 2026 at 10:12\nTo: Dan <dan@example.com>\nSubject: Your visit\n\nHello Dan"
    ORIGINAL = "Friday works.\n\n-----Original Message-----\nFrom: A\nSent: B\nTo: C\nCc: D\nSubject: E\n\nolder"

    def test_the_header_block_and_its_separator_fold_and_his_words_stay(self):
        head, quoted = richtext.split_outlook_text(self.WEB)
        self.assertEqual(head, "Friday at 3 works for me.")
        self.assertTrue(quoted.startswith("________________________________\nFrom:") and quoted.endswith("Hello Dan, would Friday suit?"))
        self.assertEqual(richtext.split_outlook_text(self.MAC)[0], "Friday at 3 works for me.")
        self.assertEqual(richtext.split_outlook_text(self.ORIGINAL)[0], "Friday works.")

    def test_no_block_or_nothing_before_it_hides_nothing(self):
        for text in ("Just a reply.\n\nOn Tue, 3 Nov 2026, Spa 99 wrote:\n> old", "From: the team\nTo: you", "From: A\nSent: B\nTo: C\nSubject: D\n\nold stuff", "",
                     "Fine.\nFrom: A\nTo: C\nSubject: D"):  # no Sent: or Date: line
            self.assertEqual(richtext.split_outlook_text(text), (text, ""))


class OutlookInboundTests(Base):
    def test_an_outlook_reply_is_stored_with_his_words_first_the_rest_as_the_earlier_text_and_the_html_marked(self):
        whole = OutlookTextTests.WEB
        payload = payload_for(self.thread, text=whole, message_id="pm-ol", StrippedTextReply=whole, HtmlBody=OUTLOOK_WEB)  # Postmark did not manage to strip an Outlook quote
        self.assertEqual(inbound_post(payload).status_code, 200)
        message = Message.objects.get(provider_id="pm-ol")
        self.assertEqual(message.body_text, "Friday at 3 works for me.")
        self.assertEqual(message.body_full, whole)
        self.assertIn(MARK, message.body_html)
        self.assertEqual(services.message_dict(message)["body_full"], whole)
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.last_preview, "Friday at 3 works for me.")
        plain = payload_for(self.thread, text="Thanks!", message_id="pm-plain")
        inbound_post(plain)
        self.assertEqual((Message.objects.get(provider_id="pm-plain").body_text, Message.objects.get(provider_id="pm-plain").body_full), ("Thanks!", ""))

    @override_settings(EMAIL_INBOUND_DOMAIN="reply.example.test")
    def test_the_frame_page_script_marks_survive_to_the_frame(self):
        payload = payload_for(self.thread, text="x", message_id="pm-frame", HtmlBody=OUTLOOK_MAC)
        inbound_post(payload)
        message = Message.objects.get(provider_id="pm-frame")
        document, _ = services.frame_html(message)
        self.assertIn(f'<div class="{MARK}"></div>', document)
