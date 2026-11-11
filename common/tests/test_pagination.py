"""The shared pagination helper (common/pagination.py) and its template (common/_pagination.html)."""
from django.http import QueryDict
from django.template.loader import render_to_string
from django.test import SimpleTestCase

from common import pagination
from common.pagination import page_links


def shown(number, pages, query=""):
    """The items as text: "<Previous>" and "<Next>" (in [] when greyed), the numbers, "..." for a gap and the current page in ()."""
    out = []
    for item in page_links(number, pages, query):
        label = item["label"]
        if item["kind"] == "gap":
            out.append("...")
        elif item["kind"] == "page":
            out.append(f"({label})" if item["current"] else label)
        else:
            out.append(f"[{label}]" if item["disabled"] else label)
    return " ".join(out)


class PageListTests(SimpleTestCase):
    def test_one_page_or_none_has_no_links(self):
        self.assertEqual(page_links(1, 1), [])
        self.assertEqual(page_links(1, 0), [])

    def test_five_pages_show_every_number(self):
        self.assertEqual(shown(1, 5), "[Previous] (1) 2 3 4 5 Next")
        self.assertEqual(shown(3, 5), "Previous 1 2 (3) 4 5 Next")
        self.assertEqual(shown(5, 5), "Previous 1 2 3 4 (5) [Next]")

    def test_twenty_pages_at_the_start_the_middle_and_the_end(self):
        self.assertEqual(shown(1, 20), "[Previous] (1) 2 3 4 ... 20 Next")
        self.assertEqual(shown(3, 20), "Previous 1 2 (3) 4 ... 20 Next")
        self.assertEqual(shown(4, 20), "Previous 1 2 3 (4) 5 ... 20 Next")
        self.assertEqual(shown(5, 20), "Previous 1 ... 4 (5) 6 ... 20 Next")
        self.assertEqual(shown(10, 20), "Previous 1 ... 9 (10) 11 ... 20 Next")
        self.assertEqual(shown(17, 20), "Previous 1 ... 16 (17) 18 19 20 Next")
        self.assertEqual(shown(20, 20), "Previous 1 ... 17 18 19 (20) [Next]")

    def test_a_page_past_the_end_is_the_last_page_and_garbage_the_first(self):
        self.assertEqual(shown(99, 20), shown(20, 20))
        self.assertEqual(shown(0, 20), shown(1, 20))
        self.assertEqual(shown(-4, 20), shown(1, 20))
        self.assertEqual(shown("x", 20), shown(1, 20))

    def test_first_and_last_are_always_there_and_the_current_page_is_marked_once(self):
        for pages in (2, 3, 7, 20, 200):
            for number in range(1, pages + 1):
                items = [i for i in page_links(number, pages) if i["kind"] == "page"]
                numbers = [i["number"] for i in items]
                self.assertEqual((numbers[0], numbers[-1]), (1, pages))
                self.assertEqual([i["number"] for i in items if i["current"]], [number])
                self.assertEqual(numbers, sorted(set(numbers)))
                self.assertTrue({number - 1, number, number + 1} & set(range(1, pages + 1)) <= set(numbers))

    def test_a_gap_never_hides_just_one_page(self):
        for number in range(1, 21):
            items = page_links(number, 20)
            for before, gap, after in zip(items, items[1:], items[2:]):
                if gap["kind"] == "gap":
                    self.assertGreater(after["number"] - before["number"], 2)

    def test_previous_and_next_are_links_except_at_the_ends(self):
        items = page_links(1, 5, "")
        self.assertEqual((items[0]["disabled"], items[0]["href"]), (True, ""))
        self.assertFalse(items[-1]["disabled"])
        last = page_links(5, 5, "")
        self.assertEqual((last[-1]["disabled"], last[-1]["href"]), (True, ""))
        self.assertEqual(last[0]["href"], "?page=4")


class LinkTests(SimpleTestCase):
    def test_the_query_is_kept_and_page_is_replaced(self):
        items = page_links(2, 5, "all=1&range=30d&page=2&staff=a%40b.c")
        self.assertEqual([i["href"] for i in items if i["kind"] in ("prev", "next")], ["?all=1&range=30d&staff=a%40b.c&page=1", "?all=1&range=30d&staff=a%40b.c&page=3"])

    def test_a_querydict_keeps_repeats_and_the_anchor_goes_last(self):
        query = QueryDict("tag=a&tag=b&page=9")
        self.assertEqual(page_links(1, 3, query, "#list")[-1]["href"], "?tag=a&tag=b&page=2#list")

    def test_helpers(self):
        self.assertEqual([pagination.num_pages(n, 25) for n in (0, 1, 25, 26, 500)], [1, 1, 1, 2, 20])
        self.assertEqual([pagination.clamp(x, 4) for x in ("2", "0", "9", "", None, "z")], [2, 1, 4, 1, 1, 1])


class TemplateTests(SimpleTestCase):
    def render(self, number, pages, query=""):
        return render_to_string("common/_pagination.html", {"pager": pagination.pager(number, pages, query), "label": "Things"})

    def test_it_draws_nothing_for_one_page(self):
        self.assertEqual(self.render(1, 1).strip(), "")

    def test_current_page_greyed_ends_and_the_phone_line(self):
        html = self.render(1, 20, "a=1")
        self.assertIn('aria-label="Things"', html)
        self.assertEqual(html.count('aria-current="page"'), 1)
        self.assertIn('<span class="pager-link" aria-disabled="true">Previous</span>', html)
        self.assertIn('href="?a=1&amp;page=2" rel="next">Next</a>', html)
        self.assertIn("Page 1 of 20", html)
        last = self.render(20, 20)
        self.assertIn('<span class="pager-link" aria-disabled="true">Next</span>', last)
        self.assertIn('<a class="pager-link" href="?page=19" rel="prev">Previous</a>', last)

    def test_the_swap_target_is_marked_only_when_asked_for(self):
        plain = self.render(2, 5)
        self.assertNotIn("data-page-target", plain)
        marked = render_to_string("common/_pagination.html", {"pager": pagination.pager(2, 5), "target": "#list", "scroll": "#head"})
        self.assertIn('data-page-target="#list" data-page-scroll="#head"', marked)
