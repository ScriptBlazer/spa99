/* Spa 99 System behaviour (docs/design/SYSTEM.md). Everything here is an enhancement: every page works as plain forms.
   Sections: helpers, dirty state and save bar, confirm dialog, submit interception, lock countdown, keyboard, audit log, menu.
   Toasts and the confirm modal are the shared ones (feedback.js, docs/design/FEEDBACK.md). */
import { toast, confirmModal, formModal, initFeedback } from './feedback.js';
import { initFormProblems, collectProblems, showProblems } from './form-problems.js';
import { initApproval } from './system-combobox.js';

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const body = document.body;
const ENV = (body.dataset.env || 'dev').toUpperCase();
const IS_LIVE = ENV === 'LIVE';
let submitting = false;
let resetIdle = () => {};

const bare = (name) => (name || '').split('.')[0].split('-').pop(); // "<row id>-price_ex_vat" -> "price_ex_vat"; "<row id>-plan_points.tier-2" -> "plan_points"
const plural = (n, one, many) => (n === 1 ? one : many);

/* ---------- dirty state and the save bar ---------- */

const allForms = () => $$('form[data-system-form]');
// "Add" forms (data-system-add) have their own Add button: they never count as unsaved changes or show the save bar
const forms = () => allForms().filter((f) => !f.hasAttribute('data-system-add'));
const controlsOf = (form) => [...form.elements].filter((el) => el.name && !['hidden', 'submit', 'button'].includes(el.type) && el.name !== 'csrfmiddlewaretoken');
// money boxes compare and show as amounts (299 and 299.00 are the same price)
const money = (v) => (v.trim() !== '' && !Number.isNaN(Number(v.replace(/,/g, ''))) ? Number(v.replace(/,/g, '')).toFixed(2) : v);
const readValue = (el) => (el.type === 'checkbox' || el.type === 'radio' ? (el.checked ? 'on' : 'off') : el.hasAttribute('data-money') ? money(el.value) : el.value);
document.addEventListener('focusout', (e) => { const el = e.target; if (el.matches?.('input[data-money]')) { el.value = money(el.value); el.dispatchEvent(new Event('input', { bubbles: true })); } });
const initial = new WeakMap();

function shownValue(el, value) {
  if (el.type === 'checkbox') return value === 'on' ? 'On' : 'Off';
  if (el.tagName === 'SELECT') return el.querySelector(`option[value="${CSS.escape(value)}"]`)?.textContent.trim() || value || 'empty';
  return value === '' ? 'empty' : value;
}

function labelOf(el) {
  const row = el.closest('tr[data-row-label]');
  const own = el.getAttribute('aria-label');
  if (row) return `${row.dataset.rowLabel} · ${own || ''}`.replace(/ · $/, '');
  const label = el.closest('.sys-row')?.querySelector('label');
  if (label) { const copy = label.cloneNode(true); copy.querySelectorAll('small').forEach((s) => s.remove()); return copy.textContent.trim(); }
  return own || el.name;
}

function snapshot(form) { initial.set(form, new Map(controlsOf(form).map((el) => [el, readValue(el)]))); }

function dirtyControls(form) {
  const start = initial.get(form);
  return controlsOf(form).filter((el) => start.has(el) && start.get(el) !== readValue(el));
}

function isRisky(el, form) {
  if (el.closest('[data-risky]')) return true;
  return (form.dataset.systemRisky || '').split(',').includes(bare(el.name));
}

function changesOf(form) {
  return dirtyControls(form).map((el) => ({ el, form, label: labelOf(el), old: shownValue(el, initial.get(form).get(el)), now: shownValue(el, readValue(el)), risky: isRisky(el, form) }));
}

function mark(form) {
  const start = initial.get(form);
  controlsOf(form).forEach((el) => {
    const changed = start.has(el) && start.get(el) !== readValue(el);
    const holder = el.closest('td') || el.closest('.sys-row');
    if (!holder) return;
    if (holder.tagName === 'TD') {
      holder.toggleAttribute('data-edited', changed || $$('input,select,textarea', holder).some((c) => c !== el && start.has(c) && start.get(c) !== readValue(c)));
      if (changed) holder.title = `Was ${shownValue(el, start.get(el))}`; else holder.removeAttribute('title');
    } else holder.toggleAttribute('data-dirty', changed);
    el.closest('.sys-toggle')?.querySelector('[data-system-state]')?.replaceChildren(shownValue(el, readValue(el)).replace('empty', ''));
  });
}

const bar = $('[data-system-savebar]');
function refreshBar() {
  const all = forms().flatMap(changesOf);
  const count = all.length;
  $('[data-system-dot]')?.toggleAttribute('hidden', count === 0);
  if (!bar) return;
  bar.hidden = count === 0;
  $('[data-system-count]', bar).textContent = `${count} unsaved ${plural(count, 'change', 'changes')}`;
  const list = $('[data-system-list]', bar);
  list.replaceChildren(...all.map(({ label, old, now }) => diffLine(label, old, now, 'li')));
  if (!count) { list.hidden = true; $('[data-system-show]', bar).setAttribute('aria-expanded', 'false'); }
  bar.removeAttribute('data-error');
}
const isDirty = () => forms().some((f) => initial.has(f) && dirtyControls(f).length);

function diffLine(label, old, now, tag = 'div') {
  const row = document.createElement(tag);
  const name = document.createElement('b'); name.textContent = `${label}  `;
  const o = document.createElement('span'); o.className = 'sys-old'; o.textContent = old;
  const a = document.createElement('span'); a.className = 'sys-arrow'; a.textContent = '→';
  const n = document.createElement('span'); n.className = 'sys-new'; n.textContent = now;
  row.append(name, o, a, n);
  return row;
}

function initForms() {
  allForms().forEach(snapshot); // add forms too: a risky value in them still gets the confirm
  const onEdit = (event) => {
    const form = event.target.form;
    if (!form || !initial.has(form) || form.hasAttribute('data-system-add')) return;
    mark(form); refreshBar();
  };
  document.addEventListener('input', onEdit);
  document.addEventListener('change', onEdit);
  if (!bar) return;
  $('[data-system-show]', bar).addEventListener('click', (event) => {
    const list = $('[data-system-list]', bar);
    list.hidden = !list.hidden;
    event.currentTarget.setAttribute('aria-expanded', String(!list.hidden));
  });
  $('[data-system-discard]', bar).addEventListener('click', () => {
    forms().forEach((form) => { form.reset(); mark(form); });
    $$('[data-system-field] [aria-invalid]').forEach((el) => el.removeAttribute('aria-invalid'));
    refreshBar();
  });
  $('[data-system-save]', bar).addEventListener('click', save);
  window.addEventListener('beforeunload', (event) => { if (!submitting && isDirty()) { event.preventDefault(); event.returnValue = ''; } });
}

async function save() {
  const dirty = forms().filter((f) => dirtyControls(f).length);
  if (!dirty.length) return;
  if (dirty.length === 1) { dirty[0].requestSubmit(); return; }
  // Several rows edited: every problem in the rows goes in one dialog first (nothing is sent), then confirm once and save them one after another.
  const found = (await Promise.all(dirty.map((form) => collectProblems(form)))).flat();
  if (found.length) { await showProblems(dirty[0], found, { opener: $('[data-system-save]', bar) }); return; }
  // Several rows edited: confirm once, then save them one after another.
  const spec = riskSpec(dirty.flatMap(changesOf));
  if (spec && !(await confirmDialog(spec))) return;
  const button = $('[data-system-save]', bar);
  button.disabled = true; button.textContent = 'Saving...';
  for (const form of dirty) {
    const response = await fetch(form.action, { method: 'POST', body: new FormData(form), credentials: 'same-origin' });
    if (!response.ok) { // show the server's own error page for that row
      button.disabled = false; button.textContent = 'Save';
      form._confirmed = true; form.requestSubmit();
      return;
    }
  }
  submitting = true;
  location.reload();
}

/* ---------- confirm dialog ---------- */

/** spec: {title, rows: [{label, old, now}], line, action, guard (true = type LIVE), danger} -> Promise<boolean>
 *  The shared confirm modal: the diff goes in `details`, the consequence line is the body, LIVE is the guard word. */
function confirmDialog(spec) {
  const details = document.createElement('div');
  details.className = 'sys-diff';
  details.replaceChildren(...(spec.rows || []).map((r) => diffLine(r.label, r.old, r.now)));
  return confirmModal({
    title: spec.title,
    details: spec.rows?.length ? details : undefined,
    body: spec.line || '',
    confirmLabel: spec.action,
    tone: IS_LIVE || spec.danger ? 'danger' : 'neutral',
    guard: spec.guard ? 'LIVE' : undefined,
  });
}

/** Risky changes (price, VAT, stage switches ...): old -> new, the environment in the title, a named action. */
function riskSpec(changes) {
  const risky = changes.filter((c) => c.risky);
  if (!risky.length) return null;
  const n = risky.length;
  const holders = risky.map((c) => c.el.closest('[data-noun]'));
  const nouns = [...new Set(holders.map((h) => h?.dataset.noun || 'setting'))];
  const plurals = [...new Set(holders.map((h) => h?.dataset.plural || 'settings'))];
  const lines = [...new Set(holders.map((h) => h?.dataset.line).filter(Boolean))];
  const noun = nouns.length === 1 ? nouns[0] : 'setting';
  const many = plurals.length === 1 ? plurals[0] : 'settings';
  const stages = $$('[data-stage] input');
  const allOff = IS_LIVE && stages.length && stages.every((s) => !s.checked) && stages.some((s) => s.form && initial.get(s.form)?.get(s) === 'on');
  return { title: `Change ${many} on ${ENV}?`, rows: risky, line: lines.join(' '), action: `Change ${n} ${plural(n, noun, many)}`, guard: allOff };
}

/* ---------- submit interception (confirm before risky saves, Team, undo, delete) ---------- */

function specFor(form) {
  if (form.matches('[data-sale-form]')) return saleSpec(form);
  if (form.matches('form[data-system-form]') && initial.has(form)) return riskSpec(changesOf(form));
  if (form.matches('[data-system-access-form]')) {
    const select = $('select[name=level]', form);
    const describe = (level) => select.querySelector(`option[value="${level}"]`)?.textContent || level;
    const was = describe(form.dataset.level), now = describe(select.value);
    if (was === now) return null;
    return { title: `Change access on ${ENV}?`, rows: [{ label: form.dataset.systemPersonLabel, old: was, now }], line: form.dataset.line, action: 'Change 1 access' };
  }
  if (form.matches('[data-system-active-form]')) {
    const active = form.dataset.active === '1';
    return { title: `${active ? 'Deactivate' : 'Reactivate'} account on ${ENV}?`, rows: [{ label: form.dataset.systemPersonLabel, old: active ? 'Active' : 'Inactive', now: active ? 'Inactive' : 'Active' }], line: form.dataset.line, action: `${active ? 'Deactivate' : 'Reactivate'} 1 account` };
  }
  if (form.matches('[data-system-undo-form][data-system-risky]')) {
    const d = form.dataset;
    return { title: `Undo ${d.noun} change on ${ENV}?`, rows: [{ label: d.what, old: d.old, now: d.new }], line: d.line, action: `Undo 1 ${d.noun}` };
  }
  if (form.matches('[data-approval-remove]')) { // Approval: "Remove X as approver?" with the consequence, no diff
    return { title: form.dataset.confirmTitle, rows: [], line: form.dataset.confirmBody, action: 'Remove', danger: true };
  }
  if (form.matches('[data-system-confirm][data-confirm-title]')) { // End now / Delete on Sales: the page words the whole question
    const d = form.dataset;
    return { title: d.confirmTitle, rows: [], line: d.confirmBody, action: d.confirmAction, danger: true };
  }
  if (form.matches('[data-system-confirm]')) {
    const d = form.dataset;
    return { title: `Remove ${d.systemConfirm} on ${ENV}?`, rows: [{ label: d.systemConfirmWhat || d.systemConfirm, old: 'Present', now: 'Removed' }], line: d.line, action: d.systemConfirmLabel || 'Remove' };
  }
  return null;
}

/* Sales: saving a new sale, or moving the end of a live one, asks first (docs/design/SYSTEM-SALES.md 3.2). */
const SALE_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
function saleWhen(value) { const m = /^\d{4}-(\d{2})-(\d{2})T(\d{2}:\d{2})/.exec(value || ''); return m ? { date: `${+m[2]} ${SALE_MONTHS[+m[1] - 1]}`, time: m[3], text: `${+m[2]} ${SALE_MONTHS[+m[1] - 1]}, ${m[3]}` } : null; }
function saleSpec(form) {
  const name = $('[name=name]', form)?.value.trim() || 'this sale';
  const ends = $('[name=ends_at]', form);
  if (form.hasAttribute('data-new')) {
    const names = $$('input[name=plans]:checked', form).map((p) => p.closest('label').textContent.trim());
    const list = names.length > 1 ? `${names.slice(0, -1).join(', ')} and ${names.at(-1)}` : names[0] || 'the chosen plans';
    const now = $('input[name=ss_starts_mode][value=now]', form)?.checked;
    const start = saleWhen($('[name=starts_at]', form)?.value);
    return { title: `Save ${name} on ${ENV}?`, rows: [], line: `${now || !start ? 'It starts now' : `It starts on ${start.date} at ${start.time}`} for ${list}. The bar appears on every page then.`, action: 'Save sale' };
  }
  if (form.dataset.state === 'live' && ends && form.dataset.endsWas && ends.value !== form.dataset.endsWas) {
    return { title: `Change when ${name} ends?`, rows: [{ label: 'Ends', old: saleWhen(form.dataset.endsWas)?.text || '', now: saleWhen(ends.value)?.text || '' }], line: 'The countdown on the site changes at once.', action: 'Change end' };
  }
  return null;
}

/* Undo on a change a script made asks for the System code again, in the shared modal. The code goes to the same undo URL;
 * a wrong one comes back as 403 JSON {needs_code, message} and the message stays in the modal (nothing is undone). */
async function askCodeAndUndo(form, opener) {
  const next = $('[name=next]', form)?.value || location.href;
  const done = await formModal((dialog, close) => {
    const heading = document.createElement('h2');
    heading.className = 'fb-modal-title'; heading.id = 'sys-undo-code-title';
    heading.textContent = 'Enter the System code to undo a script change.';
    const field = document.createElement('label');
    field.className = 'fb-modal-field';
    const name = document.createElement('span'); name.textContent = 'System code';
    const input = document.createElement('input');
    Object.assign(input, { type: 'password', name: 'code', autocomplete: 'off', maxLength: 64, className: 'fb-modal-input' });
    input.setAttribute('inputmode', 'numeric'); input.setAttribute('pattern', '[0-9]*'); input.setAttribute('autofocus', '');
    const error = document.createElement('p');
    error.className = 'fb-modal-error'; error.setAttribute('role', 'alert'); error.hidden = true;
    field.append(name, input);
    const actions = document.createElement('div');
    actions.className = 'fb-modal-actions';
    const cancel = document.createElement('button');
    Object.assign(cancel, { type: 'button', className: 'fb-btn fb-btn--secondary', textContent: 'Cancel' });
    cancel.addEventListener('click', () => close(null));
    const ok = document.createElement('button');
    Object.assign(ok, { type: 'submit', className: 'fb-btn fb-btn--primary', textContent: 'Undo' });
    actions.append(cancel, ok);
    dialog.append(heading, field, error, actions);
    dialog.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (!input.value.trim()) { error.textContent = 'Enter the System code.'; error.hidden = false; input.focus(); return; }
      ok.disabled = true;
      try {
        const data = new FormData(form); data.set('code', input.value);
        const response = await fetch(form.action, { method: 'POST', body: data, credentials: 'same-origin', redirect: 'manual', headers: { 'X-Requested-With': 'fetch' } });
        if (response.type === 'opaqueredirect' || response.ok) { close(true); return; }
        let message = 'Could not undo. Try again.';
        try { message = (await response.json()).message || message; } catch (e) { /* not JSON: keep the plain line */ }
        error.textContent = message; error.hidden = false; input.value = ''; input.focus();
      } catch (e) {
        error.textContent = 'Could not reach the server. Try again.'; error.hidden = false;
      } finally { ok.disabled = false; }
    });
  }, { opener });
  if (done) { submitting = true; location.assign(next); }
}

function initSubmit() {
  window.addEventListener('pageshow', (event) => { // back/forward cache: a restored page must ask again
    if (!event.persisted) return;
    $$('form').forEach((form) => { form._confirmed = false; form.querySelectorAll('input[data-confirm-yes]').forEach((input) => { input.value = ''; }); });
  });
  document.addEventListener('submit', async (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || form.method !== 'post') return;
    if (form.matches('[data-system-needs-code]')) { event.preventDefault(); askCodeAndUndo(form, event.submitter || document.activeElement); return; }
    if (form._confirmed) { form._confirmed = false; begin(form); return; }
    const spec = specFor(form);
    if (spec) {
      event.preventDefault();
      if (await confirmDialog(spec)) { form.querySelectorAll('input[data-confirm-yes]').forEach((input) => { input.value = 'yes'; }); form._confirmed = true; form.requestSubmit(event.submitter || undefined); }
      return;
    }
    begin(form);
  }, true);
}

function begin(form) {
  submitting = true;
  const button = $('[data-system-save]', bar || document);
  if (button && form.matches('[data-system-form]:not([data-system-add])')) { button.disabled = true; button.textContent = 'Saving...'; }
}

/* ---------- toasts: the shared ones; a server message carrying an undo link shows Undo (feedback.js) ---------- */

initFeedback();
initFormProblems(); // before initSubmit below: problems are listed before any "change this?" confirm
document.addEventListener('spa99:leaving', () => { submitting = true; });
$('[data-system-keys]')?.addEventListener('click', (event) => { if (event.target === event.currentTarget) event.currentTarget.close(); }); // backdrop closes the shortcuts list

/* ---------- lock countdown: the server is the clock; activity slides it ---------- */

function initTimer() {
  const text = $('[data-system-timer-text]'); const mirror = $('[data-system-timer-mirror]');
  const box = $('[data-system-timer]'); const stay = $('[data-system-stay]');
  if (!text) return;
  const idle = Number(body.dataset.systemIdle || 900);
  const showAt = Math.min(120, idle / 2) * 1000; // the countdown shows only in the last 2 minutes
  const throttle = Math.min(60000, idle * 250); // at most one ping a minute (a quarter of the idle time when that is shorter)
  const unlockUrl = () => `${body.dataset.systemUnlockUrl}?next=${encodeURIComponent(location.pathname + location.search)}`;
  let deadline = Date.now() + Number(body.dataset.systemRemaining ?? idle) * 1000;
  let lastPing = Date.now(); let inflight = false; let checking = false;
  const sync = (remaining) => { deadline = Date.now() + remaining * 1000; tick(); };
  resetIdle = () => { lastPing = Date.now(); sync(idle); }; // a request to a System page just slid the server's clock

  async function ask(peek) {
    const token = $('#system-csrf')?.content.querySelector('input')?.value || '';
    const response = await fetch(body.dataset.systemPing, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': token, 'X-Requested-With': 'fetch', 'Content-Type': 'application/x-www-form-urlencoded' }, body: peek ? 'peek=1' : '' });
    if (response.status === 403 || response.status === 404) return null;
    if (!response.ok) throw new Error(`ping ${response.status}`);
    return (await response.json()).remaining;
  }
  async function ping(peek = false) {
    if (inflight) return;
    inflight = true;
    try {
      const remaining = await ask(peek);
      if (remaining === null) return lockNow();
      if (!peek) lastPing = Date.now();
      sync(remaining);
    } catch { /* offline: keep the local clock; the server still decides */ } finally { inflight = false; }
  }
  function lockNow() { submitting = true; location.href = unlockUrl(); }
  function activity() {
    if (Date.now() - lastPing >= throttle && Date.now() < deadline) ping();
  }
  function tick() {
    const left = deadline - Date.now();
    const soon = left <= showAt;
    const secs = Math.max(0, Math.ceil(left / 1000));
    let message = 'Unlocked';
    if (soon) message = left <= 0 ? 'Locking' : `Locks in ${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, '0')}`;
    if (soon && isDirty()) message += ', unsaved changes will be lost';
    text.textContent = message; if (mirror) mirror.textContent = message;
    box.toggleAttribute('data-warn', soon); stay.hidden = !soon;
    if (left <= 0 && !checking) { // another tab may have kept the session alive: ask the server before locking (without sliding it)
      checking = true;
      ask(true).then((remaining) => { if (remaining === null || remaining <= 0) { if (!isDirty()) return lockNow(); setTimeout(() => { checking = false; }, 10000); } else { checking = false; sync(remaining); } }, () => { setTimeout(() => { checking = false; }, 10000); });
    }
  }
  stay.addEventListener('click', async () => { stay.disabled = true; await ping(); stay.disabled = false; });
  for (const name of ['mousemove', 'keydown', 'scroll', 'click', 'touchstart']) window.addEventListener(name, activity, { passive: true, capture: true });
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') { tick(); activity(); } });
  tick(); setInterval(tick, 1000);
}

/* ---------- keyboard ---------- */

const typing = (el) => el && (['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) || el.isContentEditable);
function initKeys() {
  let g = 0;
  document.addEventListener('keydown', (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
      if (forms().length) { event.preventDefault(); if (isDirty()) save(); }
      return;
    }
    if (event.metaKey || event.ctrlKey || event.altKey || typing(event.target) || ($('dialog[open]') || $('.fb-overlay'))) return;
    if (event.key === '/') {
      const search = $('[data-system-search]') || $('input[type=search]');
      if (search) { event.preventDefault(); search.focus(); }
    } else if (event.key === '?') { $('[data-system-keys]')?.showModal(); }
    else if (event.key === 'g') { g = Date.now(); }
    else if (Date.now() - g < 1500 && (event.key === 'd' || event.key === 'a' || event.key === 'c')) {
      g = 0; submitting = isDirty() ? submitting : true;
      location.href = $(`[data-system-nav-item=${event.key === 'd' ? 'dashboard' : 'changes'}]`)?.href || location.href;
    }
  });
}

/* ---------- audit log: filters in the URL swapped in place, load more, expand, drawer, jump links, keys, phone sheet ---------- */

function initAudit() {
  const root = $('[data-system-audit]');
  if (!root) return;
  const form = $('[data-system-filters]', root);
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let expandAll = false; let lastUrl = location.href; let opener = null;
  const results = () => $('[data-system-results]', root);

  // sticky offsets: the day header sticks under the filter bar, whatever height the bar has
  const fit = () => root.style.setProperty('--au-bar-h', `${form.offsetHeight}px`);
  fit(); new ResizeObserver(fit).observe(form);

  const fetchDoc = async (url) => {
    const response = await fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } });
    if (!response.ok) throw new Error(String(response.status));
    resetIdle();
    return new DOMParser().parseFromString(await response.text(), 'text/html');
  };
  const showError = (on) => { $('[data-system-error]', root).hidden = !on; };

  /* expand all / collapse all */
  const folds = () => $$('details[data-system-more-items]', root);
  function syncExpand() {
    const any = folds().length > 0;
    const button = $('[data-system-expand-all]', root);
    button.hidden = !any;
    if (expandAll) folds().forEach((d) => { d.open = true; });
    button.textContent = expandAll ? 'Collapse all' : 'Expand all';
  }
  root.addEventListener('click', (event) => {
    if (!event.target.closest('[data-system-expand-all]')) return;
    expandAll = !expandAll;
    folds().forEach((d) => { d.open = expandAll; });
    syncExpand();
  });

  /* swapping the list after a filter change */
  const parts = ['[data-system-results]', '[data-system-pages]', '[data-system-summary] [data-system-clear]', '[data-system-chips]', '[data-system-range]', '[data-system-filter-count]', '[data-system-drawer]', '[data-system-drawer-scrim]'];
  const state = { timer: 0 };
  async function swap(url, { push = true, keepExpand = false } = {}) {
    lastUrl = url;
    const list = results();
    clearTimeout(state.timer);
    state.timer = setTimeout(() => list.setAttribute('data-loading', ''), 150); // under 150ms nothing changes
    try {
      const doc = await fetchDoc(url);
      showError(false);
      for (const selector of parts) {
        const fresh = $(selector, doc); const old = $(selector, document);
        if (fresh && old) old.replaceWith(fresh);
        else if (!fresh && old && selector.includes('clear')) old.remove();
        else if (fresh && !old && selector.includes('clear')) $('[data-system-expand-all]', root).before(fresh);
      }
      $('[data-system-count-text]', root).innerHTML = $('[data-system-count-text]', doc).innerHTML;
      $$('[data-system-export]').forEach((a, i) => { a.href = $$('[data-system-export]', doc)[i]?.href || a.href; });
      if (!keepExpand) expandAll = false;
      if (push) history.pushState(null, '', url);
      syncExpand(); fit(); syncDrawer();
    } catch { showError(true); }
    finally { clearTimeout(state.timer); results().removeAttribute('data-loading'); }
  }
  $('[data-system-retry]', root).addEventListener('click', () => swap(lastUrl, { push: false }));

  /* filters */
  const cleanQuery = (query) => { [...query.keys()].forEach((k) => { if (!query.get(k)) query.delete(k); }); return query; };
  const go = (submitter) => {
    const query = new URLSearchParams(new FormData(form));
    query.delete('page'); query.delete('entry');
    if (submitter?.name === 'category') query.set('category', submitter.value);
    if (submitter?.name === 'range') {
      const same = submitter.getAttribute('aria-pressed') === 'true';
      query.set('range', same ? '' : submitter.value);
      if (!same) { query.set('date_from', ''); query.set('date_to', ''); form.elements.date_from.value = ''; form.elements.date_to.value = ''; }
    }
    if ((submitter?.name === undefined || submitter?.name === '') && (form.elements.date_from.value || form.elements.date_to.value)) query.set('range', '');
    const text = cleanQuery(query).toString();
    swap(`${location.pathname}${text ? `?${text}` : ''}`);
  };
  form.addEventListener('submit', (event) => { event.preventDefault(); go(event.submitter); });
  form.addEventListener('change', (event) => { if (event.target.matches('select, input[type=date]')) go(); });
  let timer; form.elements.q.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => go(), 300); });
  root.addEventListener('click', (event) => {
    const clear = event.target.closest('[data-system-clear]');
    if (!clear) return;
    event.preventDefault();
    for (const el of form.elements) { if (el.name === 'q' || el.name === 'user' || el.name === 'section' || el.name.startsWith('date_')) el.value = ''; }
    swap(clear.getAttribute('href'));
  });
  form.addEventListener('click', (event) => { // Custom date range: show the two date boxes
    const custom = event.target.closest('[data-system-custom]');
    if (!custom) return;
    const open = $('[data-system-dates]', form).toggleAttribute('data-open');
    custom.setAttribute('aria-pressed', String(open));
    if (open) form.elements.date_from.focus();
  });

  /* load more: append groups, merging a day that continues */
  document.addEventListener('click', async (event) => {
    const more = event.target.closest('[data-system-more]');
    if (!more || more.getAttribute('aria-disabled') === 'true') return;
    event.preventDefault();
    const label = more.textContent; more.textContent = 'Loading'; more.setAttribute('aria-disabled', 'true');
    try {
      const doc = await fetchDoc(more.href);
      const list = results();
      for (const day of $$('[data-system-day]', doc)) {
        const same = $(`[data-system-day="${day.dataset.systemDay}"]`, list);
        if (same) { $('.au-groups', same).append(...$$('.au-groups > li', day)); $('.au-daycount', same).replaceWith($('.au-daycount', day)); }
        else list.append(day);
      }
      $('[data-system-pages]').replaceWith($('[data-system-pages]', doc));
      showError(false); syncExpand();
    } catch { more.textContent = label; more.removeAttribute('aria-disabled'); showError(true); lastUrl = more.href; }
  });

  /* back and forward: the URL is the state */
  window.addEventListener('popstate', () => {
    const query = new URLSearchParams(location.search);
    for (const el of form.elements) { if (['q', 'user', 'section', 'date_from', 'date_to'].includes(el.name)) el.value = query.get(el.name) || ''; }
    $('[data-system-dates]', form).toggleAttribute('data-open', !!(query.get('date_from') || query.get('date_to')));
    swap(location.href, { push: false });
  });

  /* detail drawer */
  const drawer = () => $('[data-system-drawer]');
  const inertTargets = () => $$('.sys-head, [data-system-audit], .sys-top, [data-system-nav]');
  function syncDrawer() {
    const open = !!drawer() && !drawer().hidden;
    inertTargets().forEach((el) => { el.inert = open; });
    if (open) { const title = $('#au-drawer-title'); drawer().focus({ preventScroll: true }); title?.setAttribute('tabindex', '-1'); }
  }
  async function openEntry(href, from) {
    opener = from || opener;
    try {
      const doc = await fetchDoc(href);
      for (const selector of ['[data-system-drawer]', '[data-system-drawer-scrim]']) $(selector).replaceWith($(selector, doc));
      history.pushState(null, '', href); lastUrl = href;
      syncDrawer();
    } catch { showError(true); }
  }
  function closeDrawer(push = true) {
    const url = new URL(location.href); url.searchParams.delete('entry');
    const aside = drawer(); aside.hidden = true; aside.replaceChildren(); $('[data-system-drawer-scrim]').hidden = true;
    if (push) history.pushState(null, '', url);
    syncDrawer();
    if (opener?.isConnected) opener.focus(); else $('.au-group', root)?.focus();
  }
  document.addEventListener('click', (event) => {
    const link = event.target.closest('a[data-system-entry]');
    if (link) { event.preventDefault(); openEntry(link.href, link); return; }
    if (event.target.closest('[data-system-drawer-close]')) { event.preventDefault(); closeDrawer(); return; }
    if (event.target.closest('[data-system-drawer-scrim]')) { closeDrawer(); return; }
    const copy = event.target.closest('[data-system-copy], [data-system-copy-text]');
    if (copy) copyText(copy);
  });
  async function copyText(button) {
    const text = button.dataset.systemCopyText ?? $(button.dataset.systemCopy)?.textContent ?? '';
    try { await navigator.clipboard.writeText(text); } catch {
      const area = document.createElement('textarea'); area.value = text; area.style.position = 'fixed'; area.style.opacity = '0';
      document.body.append(area); area.select(); document.execCommand('copy'); area.remove();
    }
    const old = button.textContent; button.textContent = 'Copied';
    const live = $('[data-system-copied]'); if (live) live.textContent = 'Copied';
    setTimeout(() => { button.textContent = old; if (live) live.textContent = ''; }, 1500);
  }
  document.addEventListener('keydown', (event) => { // keep Tab inside the drawer while it is open
    if (event.key !== 'Tab' || !drawer() || drawer().hidden) return;
    const items = $$('a[href], button:not([disabled]), pre[tabindex], [tabindex="0"]', drawer()).filter((el) => !el.hidden && el.offsetParent !== null);
    if (!items.length) return;
    const first = items[0]; const last = items[items.length - 1];
    if (event.shiftKey && (document.activeElement === first || document.activeElement === drawer())) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });
  syncDrawer();

  /* links that jump to a group on this page */
  document.addEventListener('click', (event) => {
    const link = event.target.closest('a[data-system-jump]');
    if (!link) return;
    const target = document.getElementById(new URL(link.href).hash.slice(1));
    if (!target) return; // another page: let the server find it (?focus=)
    event.preventDefault();
    if (link.closest('[data-system-drawer]')) closeDrawer();
    const fold = target.closest('details'); if (fold) fold.open = true;
    target.scrollIntoView({ block: 'center', behavior: reduced ? 'auto' : 'smooth' });
    target.focus({ preventScroll: true });
    target.removeAttribute('data-flash'); void target.offsetWidth; target.setAttribute('data-flash', '');
    setTimeout(() => target.removeAttribute('data-flash'), 1600);
  });

  /* phone: the filters sheet */
  const sheet = $('[data-system-sheet]', root); const sheetScrim = $('[data-system-sheet-scrim]', root);
  const setSheet = (open) => {
    sheet.toggleAttribute('data-open', open); sheetScrim.hidden = !open;
    const button = $('[data-system-sheet-open]', root); button.setAttribute('aria-expanded', String(open));
    if (open) $('select', sheet)?.focus(); else button.focus();
  };
  $('[data-system-sheet-open]', root).addEventListener('click', () => setSheet(true));
  $('[data-system-sheet-close]', root).addEventListener('click', () => setSheet(false));
  sheetScrim.addEventListener('click', () => setSheet(false));

  /* keys: j / k move between groups, Enter opens or expands, u undoes, Esc closes the drawer or sheet */
  const groups = () => $$('.au-group', root);
  const current = () => document.activeElement?.closest?.('.au-group');
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      if (drawer() && !drawer().hidden) { event.preventDefault(); closeDrawer(); }
      else if (sheet.hasAttribute('data-open')) setSheet(false);
      return;
    }
    if (event.metaKey || event.ctrlKey || event.altKey || typing(event.target) || ($('dialog[open]') || $('.fb-overlay')) || (drawer() && !drawer().hidden)) return;
    const list = groups();
    if (event.key === 'j' || event.key === 'k') {
      if (!list.length) return;
      event.preventDefault();
      const at = list.indexOf(current());
      const next = list[Math.min(list.length - 1, Math.max(0, at + (event.key === 'j' ? 1 : -1)))];
      next.focus();
    } else if (event.key === 'Enter' && event.target.matches?.('.au-group')) {
      const fold = $('details[data-system-more-items]', event.target);
      if (fold && !fold.open) { fold.open = true; return; }
      $('a[data-system-entry]', event.target)?.click();
    } else if (event.key === 'u') {
      const group = current(); if (!group) return;
      const item = document.activeElement.closest('.au-item');
      const form = $('form[data-system-undo-form]', item || group) || $('form[data-system-undo-form]', group);
      if (form) { event.preventDefault(); form.requestSubmit(); } else toast('Nothing to undo here.', { kind: 'info' });
    }
  });

  syncExpand();
  if (location.hash.startsWith('#g-')) document.getElementById(location.hash.slice(1))?.focus({ preventScroll: true });
}

/* ---------- menu sheet, person menu ---------- */

function initMenu() {
  const button = $('[data-system-menu]'); const nav = $('[data-system-nav]'); const scrim = $('[data-system-scrim]');
  const set = (open) => { nav.toggleAttribute('data-open', open); scrim.hidden = !open; button.setAttribute('aria-expanded', String(open)); };
  button?.addEventListener('click', () => set(!nav.hasAttribute('data-open')));
  scrim?.addEventListener('click', () => set(false));
  nav?.addEventListener('click', (event) => { if (event.target.closest('a')) set(false); });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') { set(false); const who = $('[data-system-who]'); if (who?.open) { who.open = false; $('summary', who).focus(); } } });
  document.addEventListener('click', (event) => { const who = $('[data-system-who]'); if (who?.open && !who.contains(event.target)) who.open = false; });
}

/* ---------- rows that open a second row of settings ---------- */

function initExpand() {
  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-system-expand]');
    if (!button) return;
    const sub = document.getElementById(button.getAttribute('aria-controls'));
    const open = !sub.hasAttribute('data-open');
    sub.toggleAttribute('data-open', open); button.setAttribute('aria-expanded', String(open));
    button.textContent = open ? 'Less' : 'More';
  });
  $$('[data-system-expand][aria-expanded=true]').forEach((b) => { b.textContent = 'Less'; });
}

initForms(); initApproval(); initExpand(); initSubmit(); initTimer(); initKeys(); initAudit(); initMenu(); refreshBar();
