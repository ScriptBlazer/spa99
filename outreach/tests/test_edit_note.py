"""R9: edit a sticky note by clicking it. Mocked: sync queue and in-memory mail."""
from gold.models import ApplicationEvent
from office.tests.test_leads import lead
from outreach import services
from outreach.models import NoteEvent, StickyNote
from outreach.tests.test_outreach import Base, call


class EditNoteTests(Base):
    def setUp(self):
        super().setUp()
        self.application = self.application(email="dan@example.com")
        _, self.note = services.add_note("dan@example.com", self.reader, "Owns flats")
        self.url = f"/gold/{self.application.pk}/notes/{self.note.pk}/edit/"

    def test_edit_keeps_author_and_date_and_leaves_the_old_text_in_both_histories(self):
        created = self.note.created_at
        response = call(self.approver, "post", self.url, {"note": "  Owns three flats "}, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.note.refresh_from_db()
        self.assertEqual((self.note.text, self.note.created_at, self.note.author_label), ("Owns three flats", created, self.note.author_label))
        self.assertEqual((self.note.edited_by_label, bool(self.note.edited_at)), (services.label(self.approver), True))
        event = NoteEvent.objects.get(kind="edited")
        self.assertEqual((event.text, event.by_label), ("Owns flats", services.label(self.approver)))
        gold = ApplicationEvent.objects.get(action="note_edited")
        self.assertEqual((gold.message, gold.meta["note"]), ("Owns flats", str(self.note.pk)))
        self.assertIn(("note_edited", f"Note edited by {services.label(self.approver)}", "Owns flats"), [(e[1], e[2], e[3]) for e in services.timeline_entries(["dan@example.com"])])
        page = call(self.approver, "get", f"/gold/{self.application.pk}/")
        self.assertContains(page, "Note edited")
        self.assertContains(page, "edited")  # the meta line of the note

    def test_the_note_carries_edit_url_only_for_people_who_can_edit(self):
        notes = lambda user: call(user, "get", f"/gold/{self.application.pk}/").context["notes"]
        self.assertEqual(notes(self.approver)[0]["edit_url"], self.url)
        self.assertEqual(notes(self.reader)[0]["edit_url"], "")  # view-only

    def test_unchanged_text_is_a_no_op(self):
        for text in ("Owns flats", "  Owns flats\n"):
            self.assertEqual(call(self.approver, "post", self.url, {"note": text}, HTTP_HX_REQUEST="true").status_code, 200)
        self.note.refresh_from_db()
        self.assertIsNone(self.note.edited_at)
        self.assertEqual((NoteEvent.objects.count(), ApplicationEvent.objects.filter(action="note_edited").count()), (0, 0))

    def test_empty_and_too_long_are_refused_with_a_message(self):
        for text, message in (("   ", "Write the note."), ("x" * 1001, "keep it to 1000")):
            response = call(self.approver, "post", self.url, {"note": text}, HTTP_HX_REQUEST="true")
            self.assertEqual(response.status_code, 400)
            self.assertContains(response, message, status_code=400)
        self.note.refresh_from_db()
        self.assertEqual(self.note.text, "Owns flats")
        self.assertEqual(services.edit_note(self.note, self.approver, "x" * 1001), services.TOO_LONG)
        self.assertEqual(services.edit_note(self.note, self.approver, ""), services.EMPTY)

    def test_a_view_only_member_gets_403_and_changes_nothing(self):
        self.assertEqual(call(self.reader, "post", self.url, {"note": "Hacked"}).status_code, 403)
        self.note.refresh_from_db()
        self.assertEqual(self.note.text, "Owns flats")

    def test_another_persons_or_a_deleted_note_is_404(self):
        _, other = services.add_note("other@example.com", self.approver, "Not his")
        self.assertEqual(call(self.approver, "post", f"/gold/{self.application.pk}/notes/{other.pk}/edit/", {"note": "x"}).status_code, 404)
        services.delete_note(self.note, self.approver)
        self.assertEqual(call(self.approver, "post", self.url, {"note": "Back"}).status_code, 404)
        self.assertEqual(StickyNote.objects.get(pk=other.pk).text, "Not his")

    def test_lead_and_person_urls_edit_too_and_the_edited_line_shows_in_the_lead_timeline(self):
        session = lead("hugo@example.com")
        _, note = services.add_note("hugo@example.com", self.approver, "Hot")
        self.assertEqual(call(self.approver, "post", f"/leads/{session.pk}/notes/{note.pk}/edit/", {"note": "Very hot"}).status_code, 302)
        note.refresh_from_db()
        self.assertEqual(note.text, "Very hot")
        items = [i for d in call(self.approver, "get", f"/leads/{session.pk}/").context["timeline_days"] for i in d["items"] if i["kind"] == "note_edited"]
        self.assertEqual([(i["label"].startswith("Note edited by"), i["detail"]) for i in items], [(True, "Hot")])
