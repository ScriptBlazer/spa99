/* Seamless paging for the shared pagination (common/_pagination.html). Everything here is an enhancement: without script the page links are plain links and land on the anchor.
 *
 * A "See all" / "Show less" link opts in the same way: an <a data-page-target="#list" data-page-scroll="#head" href> swaps in place too (add data-page-open on it while the list is open, so Back knows the state).
 * A pager opts in by naming what to swap:  {% include "common/_pagination.html" with pager=pager target="#list" scroll="#card" %}  (the nav gets data-page-target and data-page-scroll).
 *   - A click on a page link fetches that URL (with fragment=1: a view may answer with just the list and the pager; a full page works too), swaps the target and the pager, and pushes the address.
 *     Anything else that must change with the page is marked data-page-part (replaced, by position, from the answer).
 *   - Back and forward swap again. If the filters in the address are not the ones on screen, the page is reloaded instead. A page that handles popstate itself marks an element data-page-host.
 *   - Afterwards, if the heading (the scroll element) is above the visible area it scrolls smoothly into view below the sticky header (the element's scroll-margin-top; reduced motion: it jumps);
 *     if it is already in view the page does not move at all.
 *   - While loading (after 150 ms) the target gets data-page-loading (a light fade). On any failure the link is followed as a normal page load.
 * Fires 'pager:swapped' on document (detail: {url, doc}) once the swap is done. */
const LOAD_MS = 150;
const IGNORED = ['page', 'fragment', 'shift', 'all'];
const HOOK = '[data-page-target]';
let seq = 0;

const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const pagerNav = (root = document) => root.querySelector('nav.pager[data-page-target]');
const sameKeys = (a, b) => a.length === b.length && a.every((v, i) => v === b[i]);

/** The address without its page: path and the other parameters, in a fixed order (what the list is, apart from which page of it). */
function listKey(url) {
  const u = new URL(url, location.href);
  return u.pathname + '?' + [...u.searchParams].filter(([k]) => !IGNORED.includes(k)).map(([k, v]) => `${k}=${v}`).sort().join('&');
}

function pageOf(url) {
  const n = parseInt(new URL(url, location.href).searchParams.get('page'), 10);
  return n > 0 ? n : 1;
}

/** What the screen shows now: the list key (from the links that carry a target), whether it is open (a pager, or the toggle says so) and its page number. null when nothing is hooked. */
function shown() {
  const link = document.querySelector(`a${HOOK}[href]`);
  if (!link) return null;
  const nav = pagerNav();
  return { key: listKey(link.href), open: !!nav || !!document.querySelector('a[data-page-open]'), number: parseInt(nav?.querySelector('[aria-current="page"]')?.textContent, 10) || 1 };
}

async function fetchDoc(href) {
  const u = new URL(href, location.href);
  u.hash = '';
  u.searchParams.set('fragment', '1');
  const response = await fetch(u.pathname + u.search, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } });
  if (!response.ok || (response.redirected && new URL(response.url).pathname !== u.pathname)) throw new Error(`GET ${href} ${response.status}`);
  return new DOMParser().parseFromString(await response.text(), 'text/html');
}

function scrollIntoPlace(ctx) {
  const el = (ctx.scroll && document.querySelector(ctx.scroll)) || document.querySelector(ctx.target);
  if (!el) return;
  const margin = parseFloat(getComputedStyle(el).scrollMarginTop) || 0;
  if (el.getBoundingClientRect().top < margin - 1) el.scrollIntoView({ behavior: reduced() ? 'auto' : 'smooth', block: 'start' });   // only when the heading is above the view
}

/** Swap to `href`. Throws when the answer is not usable (the caller falls back to a normal page load). */
/** The control the reader pressed, found again after the swap: the pager, else the See all / Show less link. */
function anchorOf(kind) {
  return kind === 'nav' ? (pagerNav() || document.querySelector(`a${HOOK}:not(.pager-link)`)) : (document.querySelector(`a${HOOK}:not(.pager-link)`) || pagerNav());
}

async function swap(href, push, keepFocus, hook) {
  const pressed = hook && hook.isConnected ? { kind: hook.matches('nav') ? 'nav' : 'link', top: hook.getBoundingClientRect().top } : null;   // where it sat on screen
  hook = hook || document.querySelector(HOOK);
  if (!hook) throw new Error('nothing to swap');
  const selector = hook.dataset.pageTarget;
  const ctx = { target: selector, scroll: hook.dataset.pageScroll };
  const target = document.querySelector(selector);
  if (!target) throw new Error('no target');
  const mine = ++seq;
  const timer = setTimeout(() => { target.setAttribute('data-page-loading', ''); target.setAttribute('aria-busy', 'true'); }, LOAD_MS);
  try {
    const doc = await fetchDoc(href);
    if (mine !== seq) return;
    const fresh = doc.querySelector(selector);
    if (!fresh) throw new Error('no list in the answer');
    const freshNav = pagerNav(doc);
    const parts = [...document.querySelectorAll('[data-page-part]')];
    const freshParts = [...doc.querySelectorAll('[data-page-part]')];
    if (parts.length !== freshParts.length) throw new Error('parts differ');
    target.replaceWith(document.importNode(fresh, true));
    parts.forEach((old, i) => old.replaceWith(document.importNode(freshParts[i], true)));
    if (!freshParts.some((part) => freshNav && part.contains(freshNav))) {   // the pager itself, unless a swapped part held it
      const current = pagerNav();
      if (freshNav) { if (current) current.replaceWith(document.importNode(freshNav, true)); } else current?.remove();
    }
    if (push) {
      const u = new URL(href, location.href);
      history.pushState({ pager: true }, '', u.pathname + u.search);
    }
    if (pressed?.kind === 'nav') {   // a page link: the new page starts at the top of the card, its heading just below the sticky header (Moishe 2026-11-11)
      const el = (ctx.scroll && document.querySelector(ctx.scroll)) || document.querySelector(ctx.target);
      if (el) el.scrollIntoView({ behavior: reduced() ? 'auto' : 'smooth', block: 'start' });
    } else if (pressed) {   // See all / Show less: the list grows or shrinks below, the reader stays exactly where they are
      const anchor = anchorOf(pressed.kind);
      if (anchor) window.scrollBy(0, anchor.getBoundingClientRect().top - pressed.top);
    } else scrollIntoPlace(ctx);   // Back and Forward: bring the card's heading into view if it is above
    if (keepFocus) {   // the link that was clicked is gone: put focus on the current page (or the new toggle link) so a keyboard or screen reader user stays in place
      const here = pagerNav()?.querySelector('[aria-current="page"]') || document.querySelector('a[data-page-open]') || document.querySelector(`a${HOOK}[href]`);
      if (here) { here.setAttribute('tabindex', '-1'); here.focus({ preventScroll: true, focusVisible: false }); }   // focusVisible false: keep the keyboard place without drawing a focus ring after a click
    }
    document.dispatchEvent(new CustomEvent('pager:swapped', { detail: { url: location.pathname + location.search, doc } }));
  } finally {
    clearTimeout(timer);
    const now = document.querySelector(selector);
    if (mine === seq && now) { now.removeAttribute('data-page-loading'); now.removeAttribute('aria-busy'); }
  }
}

document.addEventListener('click', (event) => {
  const link = event.target.closest?.('nav.pager[data-page-target] a.pager-link[href], a[data-page-target][href]');
  if (!link || event.defaultPrevented || event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  if (link.target && link.target !== '_self') return;
  const href = link.href;
  if (new URL(href).origin !== location.origin) return;
  event.preventDefault();
  swap(href, true, document.activeElement === link, link.closest('nav') || link).catch((error) => { console.warn('pager: falling back to a page load', error); location.assign(href); });
});

window.addEventListener('popstate', () => {
  if (document.querySelector('[data-page-host]')) return;   // the page swaps everything itself on Back and Forward
  const now = shown();
  const url = location.pathname + location.search;
  if (!now) { if (document.querySelector(HOOK)) location.reload(); return; }
  if (listKey(url) !== now.key) { location.reload(); return; }   // other filters than the ones on screen: a normal load of this address
  const open = new URL(url, location.href).searchParams.get('all') === '1';
  if (open === now.open && (!open || pageOf(url) === now.number)) return;   // only the hash changed
  swap(url, false, false).catch(() => location.reload());
});
