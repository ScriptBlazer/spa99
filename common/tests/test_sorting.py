"""Header sorting: whitelist, directions, header links (docs/features/office-outreach.md R1)."""
from django.db.models import F
from django.http import QueryDict
from django.test import SimpleTestCase

from common import sorting
from common.sorting import Column

COLUMNS = [Column("name", "Name", "name"), Column("when", "When", "created", first=sorting.DESC), Column("wants", "Wants"), Column("old", "Old", "old", hidden=True)]


class SortingTests(SimpleTestCase):
    def test_unknown_or_unsortable_keys_fall_back_and_dir_is_checked(self):
        self.assertEqual(sorting.resolve(COLUMNS, {"sort": "name", "dir": "desc"}, "when"), ("name", "desc", True))
        self.assertEqual(sorting.resolve(COLUMNS, {"sort": "name", "dir": "sideways"}, "when"), ("name", "asc", True))  # natural direction
        self.assertEqual(sorting.resolve(COLUMNS, {"sort": "when"}, "name"), ("when", "desc", True))
        for bad in ("wants", "password", "name; drop", ""):
            self.assertEqual(sorting.resolve(COLUMNS, {"sort": bad}, "when", "desc"), ("when", "desc", False))
        order = sorting.ordering_from(COLUMNS, {"sort": "id__gt", "dir": "asc"}, "when", ("pk",))  # a hand-made filter cannot inject a field
        self.assertEqual(order, [F("created").desc(nulls_last=True), "pk"])

    def test_order_is_nulls_last_both_ways_with_a_stable_tiebreak(self):
        self.assertEqual(sorting.order_by(COLUMNS, "name", "asc", ("pk",)), [F("name").asc(nulls_last=True), "pk"])
        self.assertEqual(sorting.order_by(COLUMNS, "name", "desc", ("-pk",)), [F("name").desc(nulls_last=True), "-pk"])

    def test_header_links_toggle_keep_filters_and_reset_the_page(self):
        get = QueryDict("q=dan&plan=a&plan=b&page=3&sort=name&dir=asc")
        cols = {c["key"]: c for c in sorting.header_columns(COLUMNS, "name", "asc", "/people/", get)}
        self.assertNotIn("old", cols)  # hidden
        self.assertEqual((cols["name"]["active"], cols["name"]["aria_sort"], cols["name"]["dir"]), (True, "ascending", "asc"))
        self.assertIn("sort=name&dir=desc", cols["name"]["url"])  # the active one reverses
        self.assertIn("sort=when&dir=desc", cols["when"]["url"])  # a new one starts at its natural direction
        for c in (cols["name"], cols["when"]):
            self.assertTrue(c["url"].startswith("/people/?q=dan&plan=a&plan=b&"))
            self.assertNotIn("page=", c["url"])
        self.assertEqual((cols["wants"]["sortable"], cols["wants"]["url"], cols["wants"]["aria_sort"]), (False, "", "none"))
