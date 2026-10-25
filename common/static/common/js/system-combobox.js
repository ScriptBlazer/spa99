/* System: the searchable multi-select ("add people") and the delivery box on Approval. Enhancement only: without this script the
   page is a plain multiple <select> and a submit button, and the delivery form always shows its address box.

   Combobox (ARIA 1.2 pattern, multi-select): <select multiple data-combo> whose <option>s carry data-name, data-email, data-level.
   The select stays the form's data (options are selected as chips are chosen), so the form posts exactly what it did without JS.
   Keys: type to filter; Down/Up move (Down opens); Enter chooses the active one (or the first match); Esc closes (a second Esc clears
   the text); Backspace in an empty box removes the last chip; Home/End jump; Tab leaves. The list is never shown in full on the page. */

const $ = (selector, root = document) => root.querySelector(selector);
let counter = 0;

const el = (tag, attrs = {}, ...kids) => {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) { if (value !== false && value != null) node.setAttribute(key, value === true ? '' : value); }
  node.append(...kids);
  return node;
};

function initCombobox(select) {
  const id = `combo-${++counter}`;
  const people = [...select.options].map((o) => ({ option: o, id: o.value, name: o.dataset.name || o.textContent, email: o.dataset.email || '', level: o.dataset.level || '' }));
  const labelText = select.getAttribute('aria-label') || 'Team members';
  const form = select.form;
  const submit = $('[data-combo-submit]', form);
  people.forEach((p) => { p.option.selected = false; });

  const chips = el('ul', { class: 'sys-chips', 'aria-label': 'Chosen' });
  const input = el('input', { type: 'text', role: 'combobox', id: `${id}-input`, 'aria-expanded': 'false', 'aria-controls': `${id}-list`, 'aria-autocomplete': 'list', 'aria-label': labelText, placeholder: select.dataset.comboPlaceholder || 'Search', autocomplete: 'off', autocapitalize: 'off', spellcheck: 'false', enterkeyhint: 'done' });
  const box = el('div', { class: 'sys-combo-box' }, chips, input);
  const list = el('ul', { class: 'sys-combo-list', role: 'listbox', id: `${id}-list`, 'aria-multiselectable': 'true', 'aria-label': labelText, hidden: true });
  const status = el('p', { class: 'sr', role: 'status', 'aria-live': 'polite' });
  const root = el('div', { class: 'sys-combo' }, box, list, status);
  select.hidden = true; select.tabIndex = -1; select.removeAttribute('size'); select.removeAttribute('id');
  select.after(root);
  // the visible label points at the input now that the native select is hidden
  const label = form.querySelector(`label[for="${select.dataset.comboFor || ''}"]`) || form.querySelector('.sys-add-label');
  if (label) label.setAttribute('for', input.id);

  let active = -1; let shown = [];
  const chosen = () => people.filter((p) => p.option.selected);
  const q = () => input.value.trim().toLowerCase();
  const matches = () => people.filter((p) => !p.option.selected && (!q() || `${p.name} ${p.email} ${p.level}`.toLowerCase().includes(q())));

  function highlight(text) {
    const needle = q(); const frag = document.createDocumentFragment();
    const at = needle ? text.toLowerCase().indexOf(needle) : -1;
    if (at < 0) { frag.append(text); return frag; }
    frag.append(text.slice(0, at), el('mark', {}, text.slice(at, at + needle.length)), text.slice(at + needle.length));
    return frag;
  }

  function renderChips() {
    chips.replaceChildren(...chosen().map((p) => {
      const remove = el('button', { type: 'button', 'aria-label': `Remove ${p.name}`, tabindex: '-1' });
      remove.innerHTML = '<svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true" focusable="false"><path d="M1.5 1.5l7 7M8.5 1.5l-7 7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" fill="none"/></svg>';
      remove.addEventListener('click', () => { p.option.selected = false; sync(); input.focus(); });
      return el('li', { class: 'sys-chip', 'data-chip': p.id }, el('span', {}, p.name), remove);
    }));
    box.removeAttribute('data-invalid');
  }

  function renderList() {
    shown = matches();
    list.replaceChildren(...(shown.length
      ? shown.map((p, i) => {
        const row = el('li', { class: 'sys-combo-opt', role: 'option', id: `${id}-o${i}`, 'aria-selected': 'false', 'data-id': p.id });
        row.append(el('span', {}, highlight(p.name)), el('span', { class: 'sys-badge' }, p.level));
        if (p.email && p.email !== p.name) row.append(el('span', { class: 'mono' }, p.email));
        return row;
      })
      : [el('li', { class: 'sys-combo-none', role: 'presentation' }, people.every((p) => p.option.selected) ? 'Everyone is chosen.' : 'No one matches.')]));
    if (active >= shown.length) active = shown.length - 1;
    paintActive();
    status.textContent = open() ? (shown.length ? `${shown.length} ${shown.length === 1 ? 'person' : 'people'} found` : 'No one matches') : '';
  }

  function paintActive() {
    [...list.querySelectorAll('[role=option]')].forEach((row, i) => {
      row.toggleAttribute('data-active', i === active);
      if (i === active) row.scrollIntoView({ block: 'nearest' });
    });
    if (active >= 0 && shown[active]) input.setAttribute('aria-activedescendant', `${id}-o${active}`); else input.removeAttribute('aria-activedescendant');
  }

  const open = () => !list.hidden;
  function show() { if (!open()) { list.hidden = false; input.setAttribute('aria-expanded', 'true'); } renderList(); }
  function hide() { list.hidden = true; input.setAttribute('aria-expanded', 'false'); input.removeAttribute('aria-activedescendant'); active = -1; status.textContent = ''; }
  function sync() { renderChips(); if (open()) renderList(); if (submit) submit.disabled = !chosen().length; select.dispatchEvent(new Event('change', { bubbles: true })); }

  function choose(person) {
    if (!person) return;
    person.option.selected = true; input.value = '';
    status.textContent = `${person.name} chosen`;
    active = -1; sync(); show();
  }

  input.addEventListener('input', () => { active = q() ? 0 : -1; show(); });
  input.addEventListener('focus', () => { if (matches().length && window.matchMedia('(pointer: fine)').matches) show(); });
  box.addEventListener('mousedown', (event) => { if (event.target !== input && !event.target.closest('button')) { event.preventDefault(); input.focus(); if (open() && !q()) hide(); else show(); } });
  list.addEventListener('mousedown', (event) => event.preventDefault()); // keep focus in the input
  list.addEventListener('click', (event) => { const row = event.target.closest('[role=option]'); if (row) choose(people.find((p) => p.id === row.dataset.id)); });
  list.addEventListener('mousemove', (event) => { const row = event.target.closest('[role=option]'); if (row) { const i = shown.findIndex((p) => p.id === row.dataset.id); if (i !== active) { active = i; paintActive(); } } });
  input.addEventListener('blur', () => { setTimeout(() => { if (!root.contains(document.activeElement)) hide(); }, 0); });

  input.addEventListener('keydown', (event) => {
    const key = event.key;
    if (key === 'ArrowDown' || key === 'ArrowUp') {
      event.preventDefault();
      if (!open()) { show(); active = key === 'ArrowDown' ? 0 : shown.length - 1; paintActive(); return; }
      if (!shown.length) return;
      active = key === 'ArrowDown' ? (active + 1) % shown.length : (active - 1 + shown.length) % shown.length;
      paintActive();
    } else if (key === 'Home' && open() && shown.length) { event.preventDefault(); active = 0; paintActive(); }
    else if (key === 'End' && open() && shown.length) { event.preventDefault(); active = shown.length - 1; paintActive(); }
    else if (key === 'Enter') {
      event.preventDefault(); // Enter never submits from here; the Add button does
      if (open() && shown.length) choose(shown[active >= 0 ? active : 0]);
    } else if (key === 'Escape') {
      if (open()) { event.preventDefault(); event.stopPropagation(); hide(); } else if (input.value) { event.preventDefault(); input.value = ''; }
    } else if (key === 'Backspace' && !input.value) {
      const last = chosen().pop();
      if (last) { event.preventDefault(); last.option.selected = false; status.textContent = `${last.name} removed`; sync(); }
    } else if (key === 'Tab') hide();
  });

  form.addEventListener('reset', () => { people.forEach((p) => { p.option.selected = false; }); input.value = ''; sync(); });
  renderChips(); if (submit) submit.disabled = true;
  select.dataset.comboReady = '1';
}

/* the delivery box: untick "Send to their account email" to type another address; Save only while the choice differs from what is saved */
function initDelivery(form) {
  const tick = $('input[type=checkbox]', form); const address = $('input[type=email]', form);
  const start = { tick: tick.checked, address: address.value };
  const refresh = () => {
    form.toggleAttribute('data-account', tick.checked);
    address.required = !tick.checked;
    form.toggleAttribute('data-dirty', tick.checked !== start.tick || (!tick.checked && address.value.trim() !== start.address.trim()));
  };
  tick.addEventListener('change', () => { refresh(); if (!tick.checked) address.focus(); });
  address.addEventListener('input', refresh);
  refresh();
}

export function initApproval() {
  document.querySelectorAll('select[data-combo]').forEach(initCombobox);
  document.querySelectorAll('[data-system-delivery-form]').forEach(initDelivery);
}
