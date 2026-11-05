/* The WhatsApp page of the Office: the chat list (search, filters, Show more, a quiet refresh), choosing a chat on a wide screen (the chat pane is swapped
 * in and the address changes, so Back and deep links work), the unread count in the title and the app icon, and the chat itself (wa-thread.js).
 * The list rows and the chat page are server rendered; this only moves them around. On a phone a chat is its own page (a normal link). */
import { Thread } from './wa-thread.js';
import { setUnread } from './wa-badge.js';

const wide = () => window.matchMedia('(min-width: 64em)').matches;
const BUSY_AFTER_MS = 300;
const LIST_REFRESH_MS = 10000;
const UUID = /^\/whatsapp\/([0-9a-f-]{36})\/$/;

export function initWhatsApp() {
  const app = document.querySelector('[data-wa-app]');
  if (!app) return;
  const rowsEl = app.querySelector('[data-wa-rows]');
  const pane = app.querySelector('[data-wa-pane]');
  const input = app.querySelector('[data-wa-q]');
  const scroller = app.querySelector('[data-wa-list-scroll]');
  const baseTitle = app.dataset.title || 'WhatsApp | Spa 99 Office';
  let filter = app.querySelector('[data-wa-filter][aria-pressed="true"]')?.dataset.waFilter || '';
  let thread = null;
  let selected = '';
  let seq = 0;
  let timer = 0;
  let busyTimer = 0;
  let lastHtml = '';

  // ---------- the unread count: title, app icon, navigation badges ----------
  setUnread(Number(document.body.dataset.waUnread) || 0, baseTitle);
  document.addEventListener('wa:unread', (event) => { setUnread(event.detail.total); if (event.detail.read) refreshList(); });

  // ---------- the list ----------
  const query = () => {
    const params = new URLSearchParams();
    if (input.value.trim()) params.set('q', input.value.trim());
    if (filter === 'unread') params.set('unread', '1');
    if (filter === 'noreply') params.set('noreply', '1');
    return params;
  };

  const markSelected = () => {
    rowsEl.querySelectorAll('.o-wa-row').forEach((row) => {
      const on = row.dataset.chat === selected;
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
      const html = await fetchRows(`/whatsapp/?${params}`);
      if (mine !== seq) return;
      rowsEl.innerHTML = html; // the server's own rows (escaped by Django)
      lastHtml = html;
      rowsEl.dataset.page = '1';
      markSelected();
      if (pushQuery) {
        const url = new URL(location.href);
        url.search = params.toString();
        if (!selected) history.replaceState(history.state, '', url);
      }
    } catch { /* the old rows stay */ } finally {
      clearTimeout(busyTimer);
      rowsEl.style.opacity = '';
    }
  }

  let debounce = 0;
  input.addEventListener('input', () => { clearTimeout(debounce); debounce = setTimeout(() => loadList(true), 250); });
  app.querySelector('[data-wa-search]').addEventListener('submit', (event) => { event.preventDefault(); clearTimeout(debounce); loadList(true); });
  app.querySelectorAll('[data-wa-filter]').forEach((chip) => chip.addEventListener('click', () => {
    filter = chip.dataset.waFilter;
    app.querySelectorAll('[data-wa-filter]').forEach((c) => c.setAttribute('aria-pressed', String(c === chip)));
    loadList(true);
  }));

  // Show more appends the next page of rows
  rowsEl.addEventListener('click', async (event) => {
    const more = event.target.closest('[data-wa-more]');
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
    const row = event.target.closest('a.o-wa-row');
    if (!row || !wide() || event.metaKey || event.ctrlKey || event.shiftKey || event.button) return;
    event.preventDefault();
    openChat(row.getAttribute('href'), true);
  });

  async function refreshList() {
    if (document.visibilityState !== 'visible' || Number(rowsEl.dataset.page || 1) > 1) return;
    try {
      const html = await fetchRows(`/whatsapp/?${query()}`);
      if (html !== lastHtml && Number(rowsEl.dataset.page || 1) === 1) { rowsEl.innerHTML = html; lastHtml = html; markSelected(); }
    } catch { /* quiet */ }
  }
  const tick = () => { clearTimeout(timer); timer = setTimeout(async () => { await refreshList(); tick(); }, LIST_REFRESH_MS); };
  tick();

  // ---------- a chat in the right pane (wide screens) ----------
  function mountThread() {
    thread?.destroy();
    thread = null;
    const root = pane.querySelector('[data-wa-thread-root]');
    if (!root) { selected = ''; document.body.removeAttribute('data-wa-thread'); markSelected(); return; }
    selected = root.dataset.contact;
    document.body.setAttribute('data-wa-thread', '');
    thread = new Thread(root);
    markSelected();
  }

  async function openChat(url, push) {
    try {
      const response = await fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } });
      if (!response.ok || new URL(response.url).pathname.startsWith('/login')) throw new Error(String(response.status));
      const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
      const root = doc.querySelector('[data-wa-thread-root]');
      if (!root) throw new Error('no chat');
      thread?.destroy();
      pane.replaceChildren(document.importNode(root, true));
      if (push) history.pushState({ chat: url }, '', url);
      mountThread();
      setUnread(Number(document.body.dataset.waUnread) || 0, baseTitle);
      if (wide()) (pane.querySelector('[data-input]') || pane.querySelector('[data-tpl-open]'))?.focus({ preventScroll: true });
    } catch { location.assign(url); }
  }

  function showBlank() {
    thread?.destroy();
    thread = null;
    selected = '';
    document.body.removeAttribute('data-wa-thread');
    pane.replaceChildren(blankNode());
    markSelected();
  }

  const blankNode = () => {
    const wrap = document.createElement('div');
    wrap.className = 'o-wa-blank';
    wrap.dataset.waBlank = '';
    const mark = document.querySelector('.o-brand .mark')?.cloneNode(true);
    if (mark && rowsEl.querySelector('.o-wa-row')) { const m = document.createElement('div'); m.className = 'o-wa-blank-mark'; m.setAttribute('aria-hidden', 'true'); m.append(mark); wrap.append(m); }
    const p = document.createElement('p');
    p.className = 'o-wa-pill';
    p.textContent = 'Choose a chat.';
    wrap.append(p);
    return wrap;
  };

  window.addEventListener('popstate', () => {
    if (!wide()) { location.reload(); return; }
    const match = UUID.exec(location.pathname);
    if (match) openChat(location.pathname + location.search, false); else showBlank();
  });
  document.addEventListener('wa:back-to-list', () => {
    if (!wide()) return;
    const row = rowsEl.querySelector('.o-wa-row.is-selected') || rowsEl.querySelector('.o-wa-row');
    row?.focus();
  });

  // the back arrow of a chat on a phone is a link; on a wide screen it is hidden. After a swap, a phone-sized window leaves the page as it is.
  mountThread();
  if (!pane.querySelector('[data-wa-thread-root]')) { const blank = pane.querySelector('[data-wa-blank]'); if (blank && !rowsEl.querySelector('.o-wa-row')) blank.querySelector('.o-wa-blank-mark')?.remove(); }
  if (scroller && selected) scroller.querySelector('.is-selected')?.scrollIntoView({ block: 'nearest' });
}
