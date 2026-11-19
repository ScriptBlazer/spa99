# The shared calendar

One calendar for the whole app, built on flatpickr 4.6.13 (vendored in `common/static/common/vendor/flatpickr/4.6.13/`, MIT, licence beside it). It is used by the Revenue date filter (Office) and System > Revenue (the assumed start date). It is not loaded on any other page.

Files:

| File | What |
|---|---|
| `common/templates/common/_date_picker.html` | The include: a date RANGE (two real date inputs, `from` and `to`) |
| `common/templates/common/_date_picker_assets.html` | Vendor CSS, `date-picker.css`, vendor JS, `date-picker.js`. Put it in `head_extra` |
| `common/static/common/css/date-picker.css` | Every style, loaded after flatpickr's own; reads only `--cal-*` tokens |
| `common/static/common/js/date-picker.js` | Finds every `[data-date-picker]` |

## A range (a filter)

```django
{% block head_extra %}{% include "common/_date_picker_assets.html" %}{% endblock %}
...
{% include "common/_date_picker.html" with id="rev-dates" label="Money due between" label_class="o-filter-label" empty="Choose dates" from=start to=end min=first max=last format=date_format note="A line under the days." sheet=True %}
```

- `from` and `to` are date objects (or empty); `min` and `max` are ISO text (the first and last day that can be picked); `format` is `SiteSettings.flatpickr_date_format` (the page's `date_format`). `note` is optional. `sheet=True` when the page moves the field into a phone sheet (the Leads pattern, `filterSheet()` in `office-ui.js`): below 64em the calendar then lies open in place, because a popover appended to `body` would sit behind the modal `<dialog>`.
- Put it inside a plain `<form method="get">`. The inputs are named `from` and `to` and always hold ISO dates (`2027-03-01`); the field shows the System format ("01/03/2027 to 31/05/2027").
- Without JavaScript the two date inputs are the control and the include's Apply button sends them. With it they hide, stay in the form, and one read-only field takes over.
- A backwards range cannot be picked (one calendar, two ends). The server still refuses one that arrives in the address (`office.views_approvals._date_range`).
- On a computer the second day closes the calendar and submits the form. In a sheet nothing submits until the sheet's own submit button. One day picked then closed counts as that one day. "Clear" empties both ends (and, on a computer, sends the page again if dates were in force).

## One date (an ordinary field)

Give the Django widget `data-date-picker data-mode="single" data-format="d/m/Y"` on its `type="date"` input and load the assets. `system.forms.RevenueForm` does it:

```python
date_field.widget.attrs.update({"data-date-picker": True, "data-mode": "single", "data-format": self.instance.flatpickr_date_format, "data-empty": "Choose a date"})
```

The input keeps its name and its ISO value, so the form, the server and the System save bar see no difference. The calendar sets the value and fires `input` and `change` on it (the System row is marked edited). The page template does not change (`_field_row.html`). A required field has no Clear.

## Tone

Office pages (`.office`) and System (`body.system`) each define the `--cal-*` aliases at the top of `date-picker.css`; nothing in the calendar uses another variable. A new tone adds one block of aliases there. No colour is new.

## Rules it keeps

- `disableMobile: true`: otherwise flatpickr hands a phone the browser's own picker.
- No month slide (`animate: false`); the popover fades in and rises 4px in 240ms, transform and opacity only; nothing moves under reduced motion.
- Week starts on Monday. Days of other months are hidden. Hover only with a fine pointer. Focus is a 2px ring inside the cell.
- Day cells are 2.5rem (2.75rem below 64em) high; Office arrows are 2.75rem below 64em.

## Not here

Time pickers, week numbers, multiple dates, and the public site: none of them use it.
