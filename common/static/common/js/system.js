/* Spa 99 System behaviour (docs/design/SYSTEM.md). Everything here is an enhancement: every page works as plain forms.
   Sections: helpers, dirty state and save bar, confirm dialog, submit interception, toasts, lock countdown, keyboard, change log, menu. */

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

const forms = () => $$('form[data-system-form]');
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
  forms().forEach(snapshot);
  const onEdit = (event) => {
    const form = event.target.form;
    if (!form || !initial.has(form)) return;
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

const dialog = $('[data-system-confirm]');

/** spec: {title, rows: [{label, old, now}], line, action, guard (true = type LIVE), danger} -> Promise<boolean> */
function confirmDialog(spec) {
  if (!dialog?.showModal) return Promise.resolve(window.confirm(spec.title));
  $('[data-system-confirm-title]', dialog).textContent = spec.title;
  $('[data-system-confirm-diff]', dialog).replaceChildren(...(spec.rows || []).map((r) => diffLine(r.label, r.old, r.now)));
  $('[data-system-confirm-line]', dialog).textContent = spec.line || '';
  const ok = $('[data-system-confirm-ok]', dialog);
  ok.textContent = spec.action;
  ok.className = `sys-btn ${IS_LIVE ? 'danger' : 'primary'}`;
  const guardBox = $('[data-system-confirm-guard]', dialog);
  const input = $('[data-system-confirm-input]', dialog);
  guardBox.hidden = !spec.guard; input.value = '';
  ok.disabled = !!spec.guard;
  input.oninput = () => { ok.disabled = input.value.trim() !== 'LIVE'; };
  $('[data-system-confirm-cancel]', dialog).onclick = () => dialog.close('cancel');
  return new Promise((resolve) => {
    dialog.addEventListener('close', () => resolve(dialog.returnValue === 'ok'), { once: true });
    dialog.returnValue = '';
    dialog.showModal();
    $('[data-system-confirm-cancel]', dialog).focus();
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
  if (form.matches('form[data-system-form]') && initial.has(form)) return riskSpec(changesOf(form));
  if (form.matches('[data-system-roles-form]')) {
    const boxes = $$('input[name=roles]', form);
    const was = boxes.filter((b) => b.defaultChecked).map((b) => b.value);
    const now = boxes.filter((b) => b.checked).map((b) => b.value);
    if (was.join() === now.join()) return null;
    const lastSystem = was.includes('System') && !now.includes('System') && onlySystemHolder(form);
    return { title: `Change roles on ${ENV}?`, rows: [{ label: form.dataset.systemPersonLabel, old: was.join(', ') || 'none', now: now.join(', ') || 'none' }], line: form.dataset.line, action: 'Change 1 role', guard: IS_LIVE && lastSystem };
  }
  if (form.matches('[data-system-active-form]')) {
    const active = form.dataset.active === '1';
    const holder = form.closest('tr');
    const last = active && holder?.querySelector('input[value=System]')?.checked && onlySystemHolder($('[data-system-roles-form]', holder));
    return { title: `${active ? 'Deactivate' : 'Reactivate'} account on ${ENV}?`, rows: [{ label: form.dataset.systemPersonLabel, old: active ? 'Active' : 'Inactive', now: active ? 'Inactive' : 'Active' }], line: form.dataset.line, action: `${active ? 'Deactivate' : 'Reactivate'} 1 account`, guard: IS_LIVE && last };
  }
  if (form.matches('[data-system-undo-form][data-system-risky]')) {
    const d = form.dataset;
    return { title: `Undo ${d.noun} change on ${ENV}?`, rows: [{ label: d.what, old: d.old, now: d.new }], line: d.line, action: `Undo 1 ${d.noun}` };
  }
  if (form.matches('[data-system-confirm]')) {
    const d = form.dataset;
    return { title: `Remove ${d.systemConfirm} on ${ENV}?`, rows: [{ label: d.systemConfirmWhat || d.systemConfirm, old: 'Present', now: 'Removed' }], line: d.line, action: d.systemConfirmLabel || 'Remove' };
  }
  return null;
}

/** True when no one else could still sign in to System: no other superuser and no other person holding the System role. */
function onlySystemHolder(rolesForm) {
  return !$$('[data-system-roles-form]').some((other) => other !== rolesForm && (other.dataset.superuser === '1' || $('input[value=System]', other)?.defaultChecked));
}

function initSubmit() {
  document.addEventListener('submit', async (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || form.method !== 'post') return;
    if (form._confirmed) { form._confirmed = false; begin(form); return; }
    const spec = specFor(form);
    if (spec) {
      event.preventDefault();
      if (await confirmDialog(spec)) { form._confirmed = true; form.requestSubmit(event.submitter || undefined); }
      return;
    }
    begin(form);
  }, true);
}

function begin(form) {
  submitting = true;
  const button = $('[data-system-save]', bar || document);
  if (button && form.matches('[data-system-form]')) { button.disabled = true; button.textContent = 'Saving...'; }
}

/* ---------- toasts ---------- */

const toasts = $('[data-system-toasts]');
function toast(text, { kind = 'success', undoUrl = '' } = {}) {
  const el = document.createElement('div');
  el.className = 'sys-toast'; el.dataset.kind = kind;
  const message = document.createElement('span'); message.textContent = text; el.append(message);
  if (undoUrl) {
    const undo = document.createElement('button'); undo.type = 'button'; undo.textContent = 'Undo';
    undo.addEventListener('click', () => {
      const f = document.createElement('form'); f.method = 'post'; f.action = undoUrl;
      const token = $('#system-csrf')?.content.querySelector('input')?.cloneNode(); if (token) f.append(token);
      const next = document.createElement('input'); next.type = 'hidden'; next.name = 'next'; next.value = location.pathname + location.search; f.append(next);
      document.body.append(f); submitting = true; f.submit();
    });
    el.append(undo);
  }
  let timer;
  const close = () => { el.dataset.out = ''; setTimeout(() => el.remove(), 130); };
  const start = () => { clearTimeout(timer); timer = setTimeout(close, 6000); };
  el.addEventListener('mouseenter', () => clearTimeout(timer)); el.addEventListener('mouseleave', start);
  el.addEventListener('focusin', () => clearTimeout(timer)); el.addEventListener('focusout', start);
  toasts.append(el); start();
}
window.systemToast = toast;

function initMessages() {
  const list = $('[data-system-messages]');
  if (!list || !toasts) return;
  $$('li', list).forEach((li) => toast(li.textContent.trim(), { kind: li.dataset.systemMessage === 'error' ? 'error' : 'success', undoUrl: li.dataset.undo || '' }));
  list.remove();
}

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
    if (event.metaKey || event.ctrlKey || event.altKey || typing(event.target) || $('dialog[open]')) return;
    if (event.key === '/') {
      const search = $('[data-system-search]') || $('input[type=search]');
      if (search) { event.preventDefault(); search.focus(); }
    } else if (event.key === '?') { $('[data-system-keys]')?.showModal(); }
    else if (event.key === 'g') { g = Date.now(); }
    else if (Date.now() - g < 1500 && (event.key === 'd' || event.key === 'c')) {
      g = 0; submitting = isDirty() ? submitting : true;
      location.href = $(`[data-system-nav-item=${event.key === 'd' ? 'dashboard' : 'changes'}]`)?.href || location.href;
    }
  });
}

/* ---------- change log: filters in the URL, swapped in place; search; load more ---------- */

function initChangeLog() {
  const form = $('[data-system-filters]');
  if (!form) return;
  const search = $('[data-system-search]'); const range = $('[data-system-range]');
  search.hidden = false; range.hidden = false; $('button[type=submit]', form)?.remove();
  const rows = () => $$('[data-system-changes] tbody tr[data-system-searchable]');
  const applySearch = () => { const q = search.value.trim().toLowerCase(); rows().forEach((tr) => { tr.hidden = !!q && !tr.textContent.toLowerCase().includes(q); }); };
  search.addEventListener('input', applySearch);
  const iso = (date) => date.toLocaleDateString('en-CA');
  const days = (n) => { const d = new Date(); d.setDate(d.getDate() - (n - 1)); return iso(d); };
  const from = form.elements.date_from; const to = form.elements.date_to;
  const syncRange = () => { const hit = [1, 7, 30].find((n) => from.value === days(n) && to.value === iso(new Date()) || (n > 1 && from.value === days(n) && !to.value)); $$('input[name=range]', form).forEach((r) => { r.checked = r.value === String(hit || ''); }); };
  syncRange();
  async function swap(url, push = true) {
    resetIdle();
    const html = await (await fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } })).text();
    const doc = new DOMParser().parseFromString(html, 'text/html');
    for (const sel of ['[data-system-results]', '[data-system-pages]']) $(sel).replaceWith($(sel, doc));
    const clear = $('[data-system-clear]', doc); $('[data-system-clear]', form)?.remove();
    if (clear) form.append(clear);
    if (push) history.pushState(null, '', url);
    applySearch();
  }
  const go = () => {
    const query = new URLSearchParams(new FormData(form)); query.delete('range');
    [...query.keys()].forEach((k) => { if (!query.get(k)) query.delete(k); });
    swap(`${location.pathname}${query.toString() ? `?${query}` : ''}`);
  };
  form.addEventListener('submit', (event) => { event.preventDefault(); go(); });
  form.addEventListener('change', (event) => {
    if (event.target.name === 'range') { const n = Number(event.target.value); if (n) { from.value = days(n); to.value = n === 1 ? iso(new Date()) : ''; } else return; }
    else if (event.target.name === 'date_from' || event.target.name === 'date_to') syncRange();
    go();
  });
  let timer; form.elements.user.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(go, 300); });
  document.addEventListener('click', async (event) => {
    const more = event.target.closest('[data-system-more]');
    if (!more) return;
    event.preventDefault();
    const doc = new DOMParser().parseFromString(await (await fetch(more.href, { credentials: 'same-origin' })).text(), 'text/html');
    $('[data-system-changes] tbody').append(...$$('[data-system-changes] tbody tr', doc));
    $('[data-system-pages]').replaceChildren(...$('[data-system-pages]', doc).childNodes);
    resetIdle(); applySearch();
  });
  window.addEventListener('popstate', () => location.reload());
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

initForms(); initExpand(); initSubmit(); initMessages(); initTimer(); initKeys(); initChangeLog(); initMenu(); refreshBar();
