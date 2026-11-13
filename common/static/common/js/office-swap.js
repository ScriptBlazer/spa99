/* Office navigation without full reloads (a small stand-in for HTMX; the pages work without it).
 *
 *   Range picker      change a radio: fetch the page for that range, swap [data-region] parts in place (cross-fade), morph
 *                     [data-morph] parts (rings, sparkline paths, funnel bars) from their old values, push the URL, Back works.
 *   Filters           search (300ms) and filters fetch the page and put its rows and its sortable head into the table (and, where the form says data-full, its tiles and total line).
 *   Sorting           a click on a table head (a plain link) does the same for that URL; the phone's Sort radios sit in the same form and keep step with it.
 *   Show more         appends the next page of rows (office-more.js does it by itself as the last row comes near); Show earlier (a person's timeline) adds the next 20 events.
 *   Phone Home        the range stays on All: below 64em the dashboard asks for range=all (the server cannot see the screen, and a saved range would stick).
 *   Actions           Approve, Decline, Resend post in the background, show the server's message as a toast and refresh the page parts.
 * If anything fails the plain link or form still works. The chart script listens for 'office:series'. */
import { toastsFromDocument } from './feedback.js';
import { clearWorking } from './buttons.js';

const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const BUSY_AFTER_MS = 300;
const COPY = ['style', 'd', 'aria-label'];
const LABELS = { today: 'Today', '7d': '7 days', '30d': '30 days', '90d': '90 days', all: 'All time' };
let seq = 0;
let shown = null; // the range currently on screen
let failedUrl = '';
let loadList = null;   // the list's own loader (set by lists()): a click on a sortable head goes through it

const main = () => document.getElementById('office-main');
const forms = () => [...document.querySelectorAll('[data-range-form]')];
const parse = (html) => new DOMParser().parseFromString(html, 'text/html');

async function fetchDoc(url, headers = {}) {
  const response = await fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch', ...headers } });
  if (!response.ok || new URL(response.url).pathname.startsWith('/login')) throw new Error(`GET ${url} ${response.status}`);
  return { response, text: await response.text() };
}

// ---------- parts ----------

function copyAttrs(to, from) {
  COPY.forEach((name) => { if (from.hasAttribute(name)) to.setAttribute(name, from.getAttribute(name)); });
}

function apply(doc) {
  document.querySelectorAll('.o-rings, .o-stat, .o-funnel, .o-wants, .o-kpi').forEach((card) => card.classList.add('is-settled')); // intro is over
  doc.querySelectorAll('[data-region]').forEach((next) => {
    const old = document.querySelector(`[data-region="${next.dataset.region}"]`);
    if (!old) return;
    const clone = document.importNode(next, true);
    clone.querySelectorAll('[data-morph]').forEach((fresh) => {   // keep the old element alive so its CSS transition runs
      const alive = old.querySelector(`[data-morph="${fresh.dataset.morph}"]`);
      if (alive) { copyAttrs(alive, fresh); fresh.replaceWith(alive); }
    });
    if (clone.hasAttribute('data-fade') && !reduced()) clone.classList.add('o-fade-in');
    old.replaceWith(clone);
  });
  doc.querySelectorAll('[data-morph]').forEach((fresh) => {
    if (fresh.closest('[data-region]')) return;
    const alive = document.querySelector(`[data-morph="${fresh.dataset.morph}"]`);
    if (alive) copyAttrs(alive, fresh);
  });
  const series = doc.getElementById('office-series');
  const here = document.getElementById('office-series');
  if (series && here) { here.textContent = series.textContent; document.dispatchEvent(new CustomEvent('office:series')); }
  const checked = doc.querySelector('[data-range-form] input[name="range"]:checked');
  if (checked) { shown = checked.value; syncRange(shown); }
  document.title = doc.title;
}

function syncRange(value) {
  forms().forEach((form) => {
    const inputs = [...form.querySelectorAll('input[name="range"]')];
    inputs.forEach((input) => { input.checked = input.value === value; });
    form.querySelector('.o-seg')?.style.setProperty('--i', String(Math.max(inputs.findIndex((i) => i.value === value), 0)));
  });
}

// ---------- range switching ----------

function setBusy(on) {
  const m = main();
  if (on) m.setAttribute('aria-busy', 'true'); else m.removeAttribute('aria-busy');
  forms().forEach((f) => (on ? f.setAttribute('aria-busy', 'true') : f.removeAttribute('aria-busy')));
}

function showError(on) {
  document.querySelectorAll('[data-error]').forEach((el) => {
    el.hidden = !on;
    const text = el.querySelector('[data-error-text]');
    if (on && text) text.textContent = `Couldn’t refresh. Showing ${LABELS[shown] || shown}.`;
  });
}

async function go(url, push) {
  const mine = ++seq;
  const timer = setTimeout(() => setBusy(true), BUSY_AFTER_MS);
  showError(false);
  try {
    const { text } = await fetchDoc(url);
    if (mine !== seq) return;
    apply(parse(text));
    if (push) history.pushState({ office: true }, '', url);
  } catch {
    if (mine !== seq) return;
    failedUrl = url;
    syncRange(shown);
    showError(true);
  } finally {
    clearTimeout(timer);
    if (mine === seq) setBusy(false);
  }
}

function rangeUrl(value) {
  const url = new URL(location.href);
  url.searchParams.set('range', value);
  return url.pathname + url.search;
}

// ---------- lists ----------

function setRows(tbody, html, append) {
  const template = document.createElement('template');
  template.innerHTML = html;
  if (append) { tbody.querySelector('[data-more-row]')?.remove(); tbody.append(template.content); } else tbody.replaceChildren(template.content);
}

/** The table head again from a fetched page: aria-sort and the links follow the order that was asked for (one head for each table card). */
function swapHead(doc) {
  const fresh = [...doc.querySelectorAll('[data-list-card] thead')];
  [...document.querySelectorAll('[data-list-card] thead')].forEach((old, at) => { if (fresh[at]) old.replaceWith(document.importNode(fresh[at], true)); });
}

/** Load the next rows of a list: `link` is its "Show more" link. The rows (and the next "Show more" row, or "That is everyone.") replace the row the link sat in.
 *  Used by a click on the link and by office-more.js as the row comes near. A list whose rows can leave it (Approvals, the Approach list) says how many have left (data-left). */
export async function loadMoreRows(link) {
  const list = link.closest('[data-office-list]');
  if (!list) throw new Error('no list');
  const url = new URL(link.href, location.href);
  const left = Number(list.dataset.left) || 0;   // rows of the earlier pages that have left the list (decided, done, archived): the next page carries on from the right place
  if (left) url.searchParams.set('shift', String(left));
  const { text } = await fetchDoc(url.pathname + url.search, { 'HX-Request': 'true' });
  setRows(list, text, true);
  list.dataset.loaded = url.searchParams.get('page') || '';
  document.dispatchEvent(new CustomEvent('office:more', { detail: { list } }));
}

/** Every list on the page from a fetched page: the rows of the list with the same name (Registered has two tables), back to the first page. */
function swapLists(doc) {
  doc.querySelectorAll('[data-office-list]').forEach((fresh) => {
    const old = document.querySelector(`[data-office-list="${fresh.dataset.officeList}"]`);
    if (!old) return;
    setRows(old, fresh.innerHTML, false);
    delete old.dataset.loaded;
    delete old.dataset.left;
  });
}

/** The phone's Sort radios and the quiet "Sort: X" button show what the fetched page is sorted by (the order may have come from a table head). */
function syncSortControls(doc) {
  doc.querySelectorAll('[data-sort-group]').forEach((group, at) => {
    const mine = document.querySelectorAll('[data-sort-group]')[at];
    if (!mine) return;
    const sort = group.querySelector('input[name="sort"]:checked');
    const dir = group.querySelector('input[name="dir"]:checked');
    mine.querySelectorAll('input[name="sort"]').forEach((input) => { input.checked = input.value === sort?.value; });
    mine.querySelectorAll('input[name="dir"]').forEach((input) => { input.checked = input.value === dir?.value; });
    document.dispatchEvent(new CustomEvent('office:sort', { detail: { group: mine } }));
  });
}

function lists() {
  const form = document.querySelector('[data-filter-form]');
  const tbody = document.querySelector('[data-office-list]');
  if (!form || !tbody) return;
  const card = document.querySelector('[data-list-card]');
  const full = form.hasAttribute('data-full');
  let timer; let run = 0;
  const refresh = async (asked) => {   // `asked`: a URL to load as it is (a click on a table head), else the form says
    const params = new URLSearchParams();
    new FormData(form).forEach((value, key) => { if (value) params.append(key, value); });
    const target = typeof asked === 'string' ? new URL(asked, location.href) : null;
    const query = target ? target.search.slice(1) : params.toString();
    const url = target ? target.pathname + target.search : location.pathname + (query ? `?${query}` : '');
    const mine = ++run;
    const busy = setTimeout(() => card?.setAttribute('aria-busy', 'true'), BUSY_AFTER_MS);
    try {
      const { text } = await fetchDoc(url);   // the whole page: its rows, its sortable head and (data-full) its other parts
      if (mine !== run) return;
      const doc = parse(text);
      if (!doc.querySelector('[data-office-list]')) throw new Error('no list in the answer');
      swapHead(doc);
      swapLists(doc);
      if (full) {   // every other [data-region] (summary tiles, the total line) is replaced in place
        doc.querySelectorAll('[data-region]:not([data-office-list])').forEach((next) => {
          const old = document.querySelector(`[data-region="${next.dataset.region}"]`);
          if (!old) return;
          const clone = document.importNode(next, true);
          if (clone.hasAttribute('data-fade') && !reduced()) clone.classList.add('o-fade-in');
          old.replaceWith(clone);
        });
        const series = doc.getElementById('office-series'); const here = document.getElementById('office-series');   // a page with charts (Activity): the charts morph to the new figures
        if (series && here) { here.textContent = series.textContent; document.dispatchEvent(new CustomEvent('office:series')); }
        document.dispatchEvent(new CustomEvent('office:filtered', { detail: { doc } }));
        document.title = doc.title;
      }
      syncSortControls(doc);
      history.replaceState({ office: true }, '', url);
      document.querySelectorAll('[data-export-csv]').forEach((link) => { link.href = `${link.dataset.exportBase}${query ? `?${query}` : ''}`; });
      const clear = full ? null : form.querySelector('[data-clear]');
      if (clear) {
        const changed = [...form.querySelectorAll('input[type="search"]')].some((el) => el.value)
          || [...form.querySelectorAll('select')].some((el) => (el.dataset.default !== undefined ? el.value !== el.dataset.default : el.selectedIndex > 0))
          || [...form.querySelectorAll('.o-seg')].some((seg) => (seg.querySelector('input:checked')?.value || '') !== (seg.dataset.default || ''));
        clear.hidden = !changed;
      }
    } catch { /* keep the rows that are there; the form still submits normally on Enter without JS */ } finally {
      clearTimeout(busy);
      if (mine === run) card?.removeAttribute('aria-busy');
    }
  };
  form.addEventListener('input', (event) => {
    if (!event.target.matches('[data-search]')) return;
    clearTimeout(timer);
    timer = setTimeout(refresh, 300);
  });
  form.addEventListener('change', (event) => { if (!event.target.matches('[data-search]')) refresh(); });
  form.addEventListener('submit', (event) => { event.preventDefault(); clearTimeout(timer); refresh(); });
  loadList = refresh;
  document.addEventListener('click', (event) => {
    if (!event.target.closest?.('[data-clear]')) return;
    event.preventDefault();
    form.querySelectorAll('input[type="search"]').forEach((el) => { el.value = ''; });
    form.querySelectorAll('input[type="checkbox"]').forEach((el) => { el.checked = false; });
    form.querySelectorAll('select').forEach((el) => {
      const wanted = el.dataset.default;
      const at = wanted === undefined ? -1 : [...el.options].findIndex((o) => o.value === wanted);
      el.selectedIndex = at >= 0 ? at : 0;
    });
    form.querySelectorAll('.o-seg').forEach((seg) => {
      const wanted = seg.dataset.default || '';
      const inputs = [...seg.querySelectorAll('input[type="radio"]')];
      inputs.forEach((input) => { input.checked = input.value === wanted; });
      seg.style.setProperty('--i', String(Math.max(inputs.findIndex((i) => i.checked), 0)));
    });
    refresh();
  });
  document.addEventListener('click', async (event) => {
    const more = event.target.closest?.('[data-show-more]');
    if (!more || more.getAttribute('aria-busy') === 'true') return;
    event.preventDefault();
    const label = more.textContent;
    more.setAttribute('aria-busy', 'true');
    more.textContent = more.dataset.workingText || 'Loading';
    try { await loadMoreRows(more); } catch { more.textContent = label; more.removeAttribute('aria-busy'); }
  });
}

// ---------- sorting: a click on a table head is a plain link (works without script); with script the list is swapped in place ----------

function sorting() {
  document.addEventListener('click', (event) => {
    const link = event.target.closest?.('a.o-sort');
    if (!link || event.defaultPrevented || event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (!loadList || !link.closest('[data-list-card]')) return;   // no list on this page: follow the link
    event.preventDefault();
    loadList(link.href);
  });
}

// ---------- the timeline: "Show earlier" adds the next 20 events in place (the plain link still opens them) ----------

function timeline() {
  document.addEventListener('click', async (event) => {
    const button = event.target.closest?.('[data-show-earlier]');
    if (!button) return;
    event.preventDefault();
    const holder = button.closest('[data-timeline-more]');
    const label = button.textContent;
    button.setAttribute('aria-busy', 'true');
    button.textContent = button.dataset.workingText || 'Loading';
    try {
      const { text } = await fetchDoc(button.href, { 'HX-Request': 'true' });
      const chunk = parse(text).querySelector('[data-timeline-chunk]');
      if (!chunk) throw new Error('no chunk');
      const last = [...document.querySelectorAll('[data-timeline-day]')].pop();
      const first = chunk.querySelector('[data-timeline-day]');
      if (last && first && last.textContent === first.textContent) first.remove();   // the same day continues: one heading
      const fresh = document.importNode(chunk, true);
      if (!reduced()) fresh.classList.add('o-fade-in');
      holder.replaceWith(fresh);
      fresh.querySelector('[data-timeline-item]')?.closest('li')?.setAttribute('tabindex', '-1');
    } catch { button.textContent = label; button.removeAttribute('aria-busy'); }
  });
}

// ---------- actions (approve, decline, resend) ----------

function actions() {
  document.addEventListener('submit', async (event) => {
    const form = event.target.closest?.('form[data-office-action]');
    if (!form) return;
    event.preventDefault();
    try {
      const response = await fetch(form.action, { method: 'POST', body: new FormData(form), credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } });
      if (!response.ok) throw new Error(String(response.status));
      const doc = parse(await response.text());
      toastsFromDocument(doc);
      if (new URL(response.url).pathname === location.pathname) apply(doc);
      else apply(parse((await fetchDoc(location.href)).text));
    } catch {
      delete form.dataset.submitting;
      form.querySelectorAll('button').forEach(clearWorking);
      form.submit(); // the plain form post still works
    }
  });
}

// ---------- phone Home: the range stays on All ----------

/** Below 64em the range picker is not there, so the page must not show a saved 7 or 30 days with no way to change it. The server cannot see the screen width, so hiding the bar with CSS
 *  is not enough: ask for All here (the answer is remembered in the session, as any range is). */
function phoneHome() {
  if (!document.querySelector('[data-office-dashboard]')) return;
  const phone = window.matchMedia('(max-width: 63.99em)');
  const ask = () => {
    if (!phone.matches || !shown || shown === 'all') return;
    syncRange('all');
    go(rangeUrl('all'), false);
  };
  ask();
  phone.addEventListener('change', ask);
}

// ---------- start ----------

export function initSwap() {
  shown = document.querySelector('[data-range-form] input[name="range"]:checked')?.value || null;
  forms().forEach((form) => {
    form.addEventListener('submit', (event) => event.preventDefault());
    form.addEventListener('change', (event) => {
      if (event.target.name !== 'range') return;
      syncRange(event.target.value);
      go(rangeUrl(event.target.value), true);
    });
  });
  document.addEventListener('click', (event) => { if (event.target.closest?.('[data-retry]')) go(failedUrl || location.href, false); });
  window.addEventListener('popstate', () => { if (forms().length) go(location.pathname + location.search, false); });
  lists();
  phoneHome();
  sorting();
  timeline();
  actions();
}
