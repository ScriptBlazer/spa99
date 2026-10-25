/* Office navigation without full reloads (a small stand-in for HTMX; the pages work without it).
 *
 *   Range picker      change a radio: fetch the page for that range, swap [data-region] parts in place (cross-fade), morph
 *                     [data-morph] parts (rings, sparkline paths, funnel bars) from their old values, push the URL, Back works.
 *   Filters           search (300ms) and filters fetch the rows partial (HX-Request header) into the table.
 *   Show more         appends the next 50 rows.
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

function lists() {
  const form = document.querySelector('[data-filter-form]');
  const tbody = document.querySelector('[data-office-list]');
  if (!form || !tbody) return;
  const card = document.querySelector('[data-list-card]');
  let timer; let run = 0;
  const refresh = async () => {
    const params = new URLSearchParams();
    new FormData(form).forEach((value, key) => { if (value) params.append(key, value); });
    const query = params.toString();
    const url = location.pathname + (query ? `?${query}` : '');
    const mine = ++run;
    const busy = setTimeout(() => card?.setAttribute('aria-busy', 'true'), BUSY_AFTER_MS);
    try {
      const { text } = await fetchDoc(url, { 'HX-Request': 'true' });
      if (mine !== run) return;
      setRows(tbody, text, false);
      history.replaceState({ office: true }, '', url);
      const exportLink = document.querySelector('[data-export-csv]');
      if (exportLink) exportLink.href = `${exportLink.dataset.exportBase}${query ? `?${query}` : ''}`;
      const clear = form.querySelector('[data-clear]');
      if (clear) {
        const changed = [...form.querySelectorAll('input[type="search"], select')].some((el) => el.value)
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
  form.querySelector('[data-clear]')?.addEventListener('click', (event) => {
    event.preventDefault();
    form.querySelectorAll('input[type="search"]').forEach((el) => { el.value = ''; });
    form.querySelectorAll('select').forEach((el) => { el.selectedIndex = 0; });
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
    if (!more) return;
    event.preventDefault();
    const label = more.textContent;
    more.setAttribute('aria-busy', 'true');
    more.textContent = more.dataset.workingText || 'Loading';
    try {
      const { text } = await fetchDoc(more.href, { 'HX-Request': 'true' });
      setRows(tbody, text, true);
    } catch { more.textContent = label; more.removeAttribute('aria-busy'); }
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
  actions();
}
