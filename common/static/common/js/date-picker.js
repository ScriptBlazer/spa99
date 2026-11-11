/* Spa 99 shared calendar (docs/features/calendar.md). Finds every [data-date-picker] and puts the vendored flatpickr behind it.
   Two shapes, one script:
   - RANGE: a `.dp` wrapper from common/_date_picker.html. Two real date inputs (from, to) hold ISO dates and stay in the form; they hide and one `.dp-field` takes over.
   - SINGLE: an ordinary <input type="date" data-date-picker data-mode="single" data-format="d/m/Y">. The input keeps its name and ISO value (so the form, the server and the
     System save bar see exactly what they saw before); it hides and one `.dp-field` takes over.
   Without JavaScript (or if flatpickr did not load) nothing here runs and the real inputs are the control. Everything is read from data-* attributes:
   data-mode, data-format (flatpickr format, from the System date_format setting), data-min, data-max (ISO), data-empty (the field's words while empty), data-sheet (range: the page moves
   this field into a phone sheet, so below 64em the calendar lies open in place instead of floating), data-note (a line under the days).
   A backwards range cannot be picked: it is one calendar, and flatpickr orders the two days. Loaded only on pages that include common/_date_picker_assets.html. */
(function () {
  'use strict';
  if (!window.flatpickr) return;

  const DESKTOP = window.matchMedia('(min-width: 64em)');
  const ARROW_PREV = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m14.5 5-7 7 7 7"/></svg>';
  const ARROW_NEXT = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m9.5 5 7 7-7 7"/></svg>';
  const pad = (n) => (n < 10 ? '0' + n : String(n));
  const iso = (d) => d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
  const parse = (text) => {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text || '');
    return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : null;
  };
  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  };

  function setup(root) {
    const single = root.tagName === 'INPUT';
    const format = root.dataset.format || 'd/m/Y';
    const empty = root.dataset.empty || (single ? 'Choose a date' : 'Choose dates');
    const note = root.dataset.note || '';
    const sheetMode = !single && root.hasAttribute('data-sheet');
    const form = root.closest('form');
    if (form && !single) form.noValidate = true;  // the calendar's own bounds apply: an old link's date outside them must not silently block the form
    const fromInput = single ? root : root.querySelector('[data-dp-from]');
    const toInput = single ? null : root.querySelector('[data-dp-to]');
    if (!fromInput || (!single && !toInput)) return;
    const hideNative = single ? fromInput : root.querySelector('[data-dp-native]');
    const label = single ? document.querySelector('label[for="' + fromInput.id + '"]') : root.querySelector('label');
    const baseId = fromInput.id || 'dp-' + Math.random().toString(36).slice(2, 8);
    const clearable = !single || !fromInput.required;
    const bounds = { min: parse(root.dataset.min), max: parse(root.dataset.max) };

    let inst = null;
    let field = null;
    let hint = null;
    let clear = null;
    let openedActive = false;
    let allowOpen = true;
    let submitting = false;

    const readNative = () => {
      const days = single ? [parse(fromInput.value)] : [parse(fromInput.value), parse(toInput.value)];
      const found = days.filter(Boolean);
      return !single && found.length === 1 ? [found[0], found[0]] : found;
    };

    const writeNative = (days) => {
      const before = fromInput.value;
      fromInput.value = days[0] ? iso(days[0]) : '';
      if (!single) toInput.value = days.length ? iso(days[days.length - 1]) : '';
      if (single && before !== fromInput.value) { // the System save bar listens to these
        fromInput.dispatchEvent(new Event('input', { bubbles: true }));
        fromInput.dispatchEvent(new Event('change', { bubbles: true }));
      }
    };

    /* a range of one day reads as that day, not "01/03/2027 to 01/03/2027" */
    const showText = () => {
      if (!inst || !field) return;
      const days = inst.selectedDates;
      if (!single && days.length === 2 && iso(days[0]) === iso(days[1])) field.value = inst.formatDate(days[0], format);
    };

    const refresh = () => {
      if (!inst) return;
      const count = inst.selectedDates.length;
      if (hint) hint.textContent = count === 0 ? 'Pick the first day.' : count === 1 ? 'Now pick the last day.' : '';
      if (clear) clear.hidden = count === 0;
    };

    /* One day picked, then closed or "Show results": it counts as that one day. */
    const commit = () => {
      if (single || !inst || inst.selectedDates.length !== 1) return;
      const day = inst.selectedDates[0];
      inst.setDate([day, day], false);
      writeNative([day, day]);
      showText();
      refresh();
    };

    const submit = () => {
      if (!form || submitting) return;
      submitting = true;
      commit();
      setTimeout(() => { submitting = false; }, 600);
      if (form.requestSubmit) form.requestSubmit(); else form.submit();
    };

    const teardown = () => {
      if (inst) inst.destroy();
      if (field) field.remove();
      inst = field = hint = clear = null;
    };

    function build() {
      teardown();
      const inline = sheetMode && !DESKTOP.matches;
      const chosen = readNative();
      field = make('input', 'dp-field');
      field.type = 'text';
      field.readOnly = true;
      field.autocomplete = 'off';
      field.placeholder = empty;
      field.id = baseId + '-dp';
      if (!inline) field.setAttribute('aria-haspopup', 'dialog');
      // Returning focus to the field after a keyboard pick must not open the calendar again: this listener runs before flatpickr's own.
      field.addEventListener('focus', (event) => { if (!allowOpen) event.stopImmediatePropagation(); });
      if (single) fromInput.after(field); else root.append(field);
      hideNative.hidden = true;
      if (label) { label.htmlFor = field.id; if (!label.id) label.id = baseId + '-label'; }
      if (label) field.setAttribute('aria-labelledby', label.id);
      // A chosen day outside the usual bounds (an old link) still shows: the bounds stretch to hold it.
      let min = bounds.min;
      let max = bounds.max;
      if (chosen.length && min && chosen[0] < min) min = chosen[0];
      if (chosen.length && max && chosen[chosen.length - 1] > max) max = chosen[chosen.length - 1];
      inst = window.flatpickr(field, {
        mode: single ? 'single' : 'range',
        dateFormat: format,
        ariaDateFormat: 'j F Y',
        disableMobile: true, // otherwise a phone gets the browser's own picker
        showMonths: !single && DESKTOP.matches ? 2 : 1,
        inline,
        position: 'auto left',
        monthSelectorType: 'static',
        animate: false,
        locale: { firstDayOfWeek: 1, rangeSeparator: ' to ' },
        minDate: min || undefined,
        maxDate: max || undefined,
        defaultDate: chosen.length ? chosen : undefined,
        prevArrow: ARROW_PREV,
        nextArrow: ARROW_NEXT,
        onReady(_days, _text, instance) { ready(instance, inline); },
        onOpen() { openedActive = readNative().length > 0; refresh(); },
        onValueUpdate: showText,
        onChange(days) { changed(days, inline); },
        onClose() { closed(inline); },
      });
      showText();
      refresh();
    }

    function ready(instance, inline) {
      const calendar = instance.calendarContainer;
      calendar.classList.add('dp-cal');
      if (single) calendar.classList.add('dp-cal--single');
      if (instance.currentYearElement) { instance.currentYearElement.readOnly = true; instance.currentYearElement.tabIndex = -1; } // the year is text, not a box
      if (!inline) { calendar.setAttribute('role', 'dialog'); calendar.setAttribute('aria-label', label ? label.textContent.trim() : 'Calendar'); }
      [[instance.prevMonthNav, 'Previous month', -1], [instance.nextMonthNav, 'Next month', 1]].forEach(([arrow, name, step]) => {
        arrow.setAttribute('role', 'button');
        arrow.setAttribute('tabindex', '0');
        arrow.setAttribute('aria-label', name);
        arrow.addEventListener('keydown', (event) => {
          if (event.key !== 'Enter' && event.key !== ' ') return;
          event.preventDefault();
          event.stopPropagation();
          instance.changeMonth(step);
        });
      });
      if (single && !clearable && !note) return;
      const foot = make('div', 'dp-foot');
      if (!single) { hint = make('p', 'dp-hint'); hint.setAttribute('aria-live', 'polite'); foot.append(hint); }
      if (clearable) {
        clear = make('button', 'dp-clear', 'Clear');
        clear.type = 'button';
        clear.addEventListener('click', () => {
          const wasActive = openedActive; // were dates in force when he opened it? then the page must be sent again without them
          instance.clear(); // onChange empties both ends
          writeNative([]);
          refresh();
          if (inline) return;
          returnFocus();
          instance.close();
          if (!single && wasActive) submit();
        });
        foot.append(clear);
      }
      if (note) foot.append(make('p', 'dp-note', note));
      calendar.append(foot);
    }

    function returnFocus() {
      if (!field) return;
      allowOpen = false;
      field.focus({ preventScroll: true });
      allowOpen = true;
    }

    function changed(days, inline) {
      refresh();
      if (single) { writeNative(days); return; }
      if (days.length === 0) { writeNative([]); return; }
      if (days.length === 2) {
        writeNative(days);
        if (!inline) { returnFocus(); inst.close(); submit(); }
      }
    }

    function closed(inline) {
      if (single || inline || !inst || inst.selectedDates.length !== 1) return;
      // flatpickr drops a lone first day right after closing; put it back as one day, then send it.
      const instance = inst;
      setTimeout(() => {
        if (instance !== inst) return;
        commit();
        submit();
      }, 0);
    }

    const syncFromNative = () => {
      if (!inst) return;
      inst.setDate(readNative(), false);
      showText();
      refresh();
    };

    if (!single) root.addEventListener('dp:clear', () => { if (inst) inst.clear(); writeNative([]); showText(); refresh(); });   // a page can empty the dates without opening the calendar (Activity: picking a range)
    if (form) {
      form.addEventListener('submit', () => {
        if (single) return;
        commit();
        [fromInput, toInput].forEach((input) => { // an empty date is not sent: the page keeps its plain address
          if (input.value) return;
          input.disabled = true;
          setTimeout(() => { input.disabled = false; }, 0);
        });
      });
      form.addEventListener('reset', () => setTimeout(syncFromNative, 0));
    }
    window.addEventListener('pageshow', (event) => { if (event.persisted) { submitting = false; syncFromNative(); } });
    if (DESKTOP.addEventListener) DESKTOP.addEventListener('change', build); else DESKTOP.addListener(build);
    build();
  }

  document.querySelectorAll('[data-date-picker]').forEach(setup);
})();
