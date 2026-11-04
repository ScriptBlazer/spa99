/* The Email tab of the Office: the thread list (search, filters, Show more, a quiet refresh), opening a thread or New email in the right pane on a wide screen (the address
 * changes, so Back and deep links work), the unread count in the title and the app icon, and the thread itself (email-thread.js, email-new.js).
 * The list rows and the pages are server rendered; this only moves them around. On a phone a thread is its own page (a normal link). Same shape as office-whatsapp.js. */
import { EmailThread } from './email-thread.js';
import { NewEmail } from './email-new.js';
import { setEmailUnread } from './wa-badge.js';

const wide = () => window.matchMedia('(min-width: 64em)').matches;
const BUSY_AFTER_MS = 300;
const LIST_REFRESH_MS = 15000;
const PANE = /^\/email\/([0-9a-f-]{36}|new)\/$/;

export function initEmail() {
  const app = document.querySelector('[data-em-app]');
  if (!app) return;
  const rowsEl = app.querySelector('[data-em-rows]');
  const pane = app.querySelector('[data-em-pane]');
  const input = app.querySelector('[data-em-q]');
  const scroller = app.querySelector('[data-em-list-scroll]');
  const baseTitle = app.dataset.title || 'Email | Spa 99 Office';
  let filter = app.querySelector('[data-em-filter][aria-pressed="true"]')?.dataset.emFilter || '';
  let current = null;
  let selected = '';
  let seq = 0;
  let timer = 0;
  let busyTimer = 0;
  let lastHtml = '';

  setEmailUnread(Number(document.body.dataset.emUnread) || 0, baseTitle);
  document.addEventListener('em:unread', (event) => { setEmailUnread(event.detail.total); if (event.detail.read) refreshList(); });

  // ---------- the list ----------
  const query = () => {
    const params = new URLSearchParams();
    if (input.value.trim()) params.set('q', input.value.trim());
    if (filter) params.set('filter', filter);
    return params;
  };

  const markSelected = () => {
    rowsEl.querySelectorAll('.o-em-row').forEach((row) => {
      const on = row.dataset.thread === selected;
      row.classList.toggle('is-selected', on);
      if (on) row.setAttribute('aria-current', 'page'); else row.removeAttribute('aria-current');
    });
  };

  async function fetchRows(url) {
    const response = await fetch(url, { credentials: 'same-origin', headers: { 'HX-Request': 'true', 'X-Requested-With': 'fetch' } });
    if (!response.ok || new URL(response.url).pathname.startsWith('/login')) throw new Error(String(response.status));
    return response.text();
  }

  async function loadList(pushQuery) {
    const mine = ++seq;
    clearTimeout(busyTimer);
    busyTimer = setTimeout(() => { rowsEl.style.opacity = '0.5'; }, BUSY_AFTER_MS);
    try {
      const params = query();
      const html = await fetchRows(`/email/?${params}`);
      if (mine !== seq) return;
      rowsEl.innerHTML = html; // the server's own rows (escaped by Django)
      lastHtml = html;
      rowsEl.dataset.page = '1';
      markSelected();
      if (pushQuery && !selected) { const url = new URL(location.href); url.search = params.toString(); history.replaceState(history.state, '', url); }
    } catch { /* the old rows stay */ } finally {
      clearTimeout(busyTimer);
      rowsEl.style.opacity = '';
    }
  }

  let debounce = 0;
  input.addEventListener('input', () => { clearTimeout(debounce); debounce = setTimeout(() => loadList(true), 250); });
  app.querySelector('[data-em-search]').addEventListener('submit', (event) => { event.preventDefault(); clearTimeout(debounce); loadList(true); });
  app.querySelectorAll('[data-em-filter]').forEach((chip) => chip.addEventListener('click', () => {
    filter = chip.dataset.emFilter;
    app.querySelectorAll('[data-em-filter]').forEach((c) => c.setAttribute('aria-pressed', String(c === chip)));
    loadList(true);
  }));

  rowsEl.addEventListener('click', async (event) => {
    const more = event.target.closest('[data-em-more]');
    if (more) {
      event.preventDefault();
      try {
        const html = await fetchRows(more.getAttribute('href'));
        const holder = more.closest('li');
        const tmp = document.createElement('ul');
        tmp.innerHTML = html;
        holder.replaceWith(...tmp.children);
        rowsEl.dataset.page = String(Number(rowsEl.dataset.page || 1) + 1);
        markSelected();
      } catch { /* try again */ }
      return;
    }
    const row = event.target.closest('a.o-em-row');
    if (!row || !wide() || event.metaKey || event.ctrlKey || event.shiftKey || event.button) return;
    event.preventDefault();
    openPane(row.getAttribute('href'), true);
  });

  async function refreshList() {
    if (document.visibilityState !== 'visible' || Number(rowsEl.dataset.page || 1) > 1) return;
    try {
      const html = await fetchRows(`/email/?${query()}`);
      if (html !== lastHtml && Number(rowsEl.dataset.page || 1) === 1) { rowsEl.innerHTML = html; lastHtml = html; markSelected(); }
    } catch { /* quiet */ }
  }
  const tick = () => { clearTimeout(timer); timer = setTimeout(async () => { await refreshList(); tick(); }, LIST_REFRESH_MS); };
  tick();

  // ---------- a thread or New email in the right pane (wide screens) ----------
  function mountPane() {
    current?.destroy();
    current = null;
    const thread = pane.querySelector('[data-em-thread-root]');
    const fresh = pane.querySelector('[data-em-new-root]');
    if (thread) { selected = thread.dataset.thread; current = new EmailThread(thread); } else if (fresh) { selected = ''; current = new NewEmail(fresh); } else selected = '';
    document.body.toggleAttribute('data-em-thread', !!(thread || fresh));
    markSelected();
  }

  async function openPane(url, push) {
    try {
      const response = await fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } });
      if (!response.ok || new URL(response.url).pathname.startsWith('/login')) throw new Error(String(response.status));
      const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
      const root = doc.querySelector('[data-em-thread-root]') || doc.querySelector('[data-em-new-root]');
      if (!root) throw new Error('no pane');
      current?.destroy();
      pane.replaceChildren(document.importNode(root, true));
      if (push) history.pushState({ pane: url }, '', url);
      mountPane();
      document.title = doc.title || baseTitle;
      setEmailUnread(Number(document.body.dataset.emUnread) || 0);
      if (wide()) (pane.querySelector('[data-reply-open]') || pane.querySelector('[data-to-input]:not([hidden])') || pane.querySelector('[data-subject-input]'))?.focus({ preventScroll: true });
    } catch { location.assign(url); }
  }

  function showBlank() {
    current?.destroy();
    current = null;
    selected = '';
    document.body.removeAttribute('data-em-thread');
    const wrap = document.createElement('div');
    wrap.className = 'o-wa-blank';
    wrap.dataset.emBlank = '';
    const mark = document.querySelector('.o-brand .mark')?.cloneNode(true);
    if (mark) { const m = document.createElement('div'); m.className = 'o-wa-blank-mark'; m.setAttribute('aria-hidden', 'true'); m.append(mark); wrap.append(m); }
    const p = document.createElement('p');
    p.className = 'o-wa-pill';
    p.textContent = 'Choose an email.';
    wrap.append(p);
    pane.replaceChildren(wrap);
    document.title = baseTitle;
    markSelected();
  }

  document.addEventListener('click', (event) => {
    const link = event.target.closest('[data-em-new]');
    if (!link || !wide() || event.metaKey || event.ctrlKey || event.shiftKey || event.button) return;
    event.preventDefault();
    openPane(link.getAttribute('href'), true);
  });
  document.addEventListener('em:open-thread', (event) => {
    if (!wide()) return; // a phone loads the page
    event.preventDefault();
    openPane(event.detail.url, true).then(refreshList);
  });
  window.addEventListener('popstate', () => {
    if (!wide()) { location.reload(); return; }
    if (PANE.test(location.pathname)) openPane(location.pathname + location.search, false); else showBlank();
  });

  mountPane();
  if (scroller && selected) scroller.querySelector('.is-selected')?.scrollIntoView({ block: 'nearest' });
}
