/* Lists that load themselves (docs/features/office-2-design.md, "Auto-loading on scroll"): Leads, Registered, Approach list, Gold, Archived, Approvals, Invited, Assistant.
 *
 * An IntersectionObserver watches each list's "Show more" row (never a scroll listener). The row is watched 600px before it comes into view, so the next rows are usually there before
 * he arrives. With this on, the card carries data-auto and its "Show more" link steps aside (it is what shows with no script). Three dots breathe while rows load, but only after 150ms,
 * so a quick load does not flicker (reduced motion: the word "Loading" instead). A failure says so and waits for "Try again". The end of a list says "That is everyone." (the server writes it).
 *
 * Registered with two tables on a computer is the one place that must not load itself: the first table would load for ever and the second would never be reached, so a page with more than
 * one list on screen keeps its "Show more" buttons.
 *
 * Coming back from a person: the number of pages loaded and the scroll position are kept in history.state, so back (or a reload) puts him at the same row even with 200 loaded.
 * A filter change starts over at the first page (office-swap.js writes a fresh state). One load at a time for each list: a fast scroll never loads the same rows twice. Focus is never moved. */
import { loadMoreRows } from './office-swap.js';

const AHEAD = '0px 0px 600px 0px';
const SHOW_AFTER_MS = 150;

const pageOf = (url) => Number(new URL(url, location.href).searchParams.get('page')) || 1;

export function initMore() {
  if (!document.querySelector('[data-list-card] [data-office-list]')) return;
  const state = () => history.state || {};
  const keep = (patch) => { try { history.replaceState({ ...state(), office: true, ...patch }, ''); } catch { /* a page that cannot keep state loses only the return to the row */ } };
  const lists = () => [...document.querySelectorAll('[data-list-card] [data-office-list]')];
  const auto = 'IntersectionObserver' in window;
  const busy = new WeakSet();
  const watched = new WeakSet();
  let observer = null;
  let ready = false;   // not before the rows he had are back: a load of its own then would race the restore

  /** Cards that can load themselves: only when one list is on screen. */
  function sync() {
    if (!ready) return;
    const shown = [...document.querySelectorAll('[data-list-card]')].filter((card) => card.getClientRects().length);
    document.querySelectorAll('[data-list-card]').forEach((card) => card.toggleAttribute('data-auto', auto && shown.length === 1 && card === shown[0]));
    watch();
  }

  function watch() {
    if (!observer) return;
    document.querySelectorAll('[data-list-card][data-auto] [data-more-row]').forEach((row) => {
      if (watched.has(row) || busy.has(row)) return;
      watched.add(row);
      observer.observe(row);
    });
  }

  async function run(row) {
    const link = row.querySelector('[data-show-more]');
    const card = row.closest('[data-list-card]');
    if (!link || !card?.hasAttribute('data-auto') || busy.has(row)) return;
    busy.add(row);
    observer.unobserve(row);
    const dots = row.querySelector('[data-load]');
    const fail = row.querySelector('[data-load-fail]');
    if (fail) fail.hidden = true;
    const timer = setTimeout(() => { if (dots) dots.hidden = false; }, SHOW_AFTER_MS);
    try {
      await loadMoreRows(link);   // the row is replaced by the new rows and the next "Show more" row
      clearTimeout(timer);
      watch();
    } catch {
      clearTimeout(timer);
      if (dots) dots.hidden = true;
      if (fail) fail.hidden = false;   // not watched again until "Try again"
      busy.delete(row);
    }
  }

  if (auto) {
    observer = new IntersectionObserver((entries) => entries.forEach((entry) => { if (entry.isIntersecting) run(entry.target); }), { rootMargin: AHEAD });
    document.addEventListener('click', (event) => {
      const retry = event.target.closest?.('[data-load-retry]');
      if (!retry) return;
      const row = retry.closest('[data-more-row]');
      if (!row) return;
      event.preventDefault();
      busy.delete(row);
      watched.delete(row);
      run(row);
    });
    window.matchMedia('(min-width: 64em)').addEventListener('change', sync);
    const main = document.getElementById('office-main');
    if (main && 'MutationObserver' in window) {
      let queued = false;
      new MutationObserver(() => { if (queued) return; queued = true; requestAnimationFrame(() => { queued = false; sync(); }); }).observe(main, { childList: true, subtree: true });
    }
  }

  // ---- coming back: the pages he had loaded, and where he was ----
  document.addEventListener('office:more', (event) => {
    const list = event.detail.list;
    keep({ loaded: { ...state().loaded, [list.dataset.officeList]: Number(list.dataset.loaded) || undefined } });
  });
  if (document.querySelector('[data-office-list]')) history.scrollRestoration = 'manual';   // this page puts him back himself, after the rows are there
  const leave = () => keep({ y: Math.round(window.scrollY) });
  window.addEventListener('pagehide', leave);
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') leave(); });

  restore().finally(() => { ready = true; sync(); });

  async function restore() {
    const saved = state();
    const wanted = saved.loaded || {};
    const cards = [];
    for (const list of lists()) {
      const want = Number(wanted[list.dataset.officeList]) || 0;
      if (want > pageOf(location.href)) cards.push([list, want]);
    }
    cards.forEach(([list]) => list.closest('[data-list-card]').setAttribute('data-restoring', ''));
    try {
      for (const [list, want] of cards) {
        let guard = 0;
        while ((Number(list.dataset.loaded) || pageOf(location.href)) < want && guard < 60) {
          guard += 1;
          const link = list.querySelector('[data-more-row] [data-show-more]');
          if (!link) break;
          await loadMoreRows(link);
        }
      }
    } catch { /* he lands where the rows end */ } finally {
      cards.forEach(([list]) => list.closest('[data-list-card]').removeAttribute('data-restoring'));
    }
    if (Number.isFinite(saved.y) && saved.y > 0) {
      requestAnimationFrame(() => requestAnimationFrame(() => window.scrollTo(0, saved.y)));
    }
  }
}
