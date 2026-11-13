"""Numbered pagination links, for the one component `common/_pagination.html` (read its header for how to use it).

`pager(number, num_pages, base_query, anchor="")` is what a view puts in its context; the template draws it. `page_links` is the list inside it. Nothing here touches the
database: the view works out the page count (`num_pages(total, size)`) and clamps the page asked for (`clamp(raw, pages)`).
"""
from urllib.parse import parse_qsl, urlencode


def num_pages(total, size):
    """How many pages `total` rows make at `size` a page (at least 1)."""
    return max(1, -(-max(int(total or 0), 0) // max(int(size or 1), 1)))


def clamp(raw, pages):
    """The page asked for as a whole number from 1 to `pages`: garbage is page 1, a page past the end is the last page."""
    try:
        return min(max(1, int(raw)), pages)
    except (TypeError, ValueError):
        return 1


def _href(base_query, number, anchor):
    """`?` + the query with `page` replaced (every other key and its order kept, repeats too) + `page=number`, then the anchor."""
    if hasattr(base_query, "lists"):
        pairs = [(key, value) for key, values in base_query.lists() for value in values]
    elif isinstance(base_query, dict):
        pairs = list(base_query.items())
    else:
        pairs = parse_qsl(str(base_query or "").lstrip("?"), keep_blank_values=True)
    pairs = [(key, value) for key, value in pairs if key != "page"]
    return "?" + urlencode(pairs + [("page", number)]) + anchor


def _numbers(number, pages):
    """The page numbers to show, with None for a gap: always the first, the last and the one either side of the current; near either end the first (or last) four."""
    keep = {1, pages, number - 1, number, number + 1}
    if number <= 3:
        keep |= {1, 2, 3, 4}
    if number >= pages - 2:
        keep |= {pages - 3, pages - 2, pages - 1, pages}
    keep = sorted(n for n in keep if 1 <= n <= pages)
    out = []
    for n in keep:
        if out:
            gap = n - out[-1]
            if gap == 2:
                out.append(out[-1] + 1)   # one hidden page is not worth a gap
            elif gap > 2:
                out.append(None)
        out.append(n)
    return out


def page_links(number, num_pages, base_query="", anchor=""):
    """The items for page `number` of `num_pages`: Previous, the numbers (with a gap item between runs) and Next. [] when there is one page or none.
    Each item: {kind: prev | page | gap | next, label, number, href, current, disabled}. A gap, and a Previous or Next that has nowhere to go, have no href."""
    if num_pages <= 1:
        return []
    number = clamp(number, num_pages)
    items = [{"kind": "prev", "label": "Previous", "number": number - 1, "href": _href(base_query, number - 1, anchor) if number > 1 else "", "current": False, "disabled": number == 1}]
    for n in _numbers(number, num_pages):
        if n is None:
            items.append({"kind": "gap", "label": "…", "number": None, "href": "", "current": False, "disabled": False})
        else:
            items.append({"kind": "page", "label": str(n), "number": n, "href": _href(base_query, n, anchor), "current": n == number, "disabled": False})
    items.append({"kind": "next", "label": "Next", "number": number + 1, "href": _href(base_query, number + 1, anchor) if number < num_pages else "", "current": False, "disabled": number == num_pages})
    return items


def pager(number, pages, base_query="", anchor=""):
    """The context for `{% include "common/_pagination.html" with pager=pager %}`: {items, number, num_pages}. `base_query` is `request.GET` (or its urlencoded text); `anchor` ("#list") lands the reader on the list."""
    number = clamp(number, pages)
    return {"items": page_links(number, pages, base_query, anchor), "number": number, "num_pages": pages}
