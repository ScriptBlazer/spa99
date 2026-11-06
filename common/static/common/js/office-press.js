/* The press (docs/features/office-2-design.md, "The press, used everywhere"). CSS :active alone barely shows on iOS: it can clear before the page changes.
 * pointerdown adds .is-pressed to the closest [data-press], and it stays at least 120ms. pointercancel clears it, so a scroll that starts on a row never flashes it:
 * the class waits a moment (40ms) before it is added, and a tap that ends sooner adds it at once. A control inside a row (Approve, Mark done, Archive) does not press the row. */
const HOLD_MS = 120;
const WAIT_MS = 40;
const CONTROL = 'a[href], button, input, select, textarea, label, summary, [data-no-press]';

export function initPress() {
  const live = new Map(); // element -> { timer, at }
  const add = (el) => {
    const entry = live.get(el);
    if (!entry || entry.at) return;
    clearTimeout(entry.timer);
    entry.at = performance.now();
    el.classList.add('is-pressed');
  };
  const clear = (el) => {
    const entry = live.get(el);
    if (!entry) return;
    clearTimeout(entry.timer);
    live.delete(el);
    el.classList.remove('is-pressed');
  };
  document.addEventListener('pointerdown', (event) => {
    if (event.button > 0 || !event.isPrimary) return;
    const el = event.target.closest?.('[data-press]');
    if (!el) return;
    const control = event.target.closest(CONTROL);
    if (control && control !== el && !control.classList.contains('o-rowlink') && !control.classList.contains('o-wait-link')) return;   // the row's own link covers the row; any other control is its own target
    clear(el);
    live.set(el, { timer: setTimeout(() => add(el), WAIT_MS), at: 0 });
  }, { passive: true });
  const release = () => {
    live.forEach((entry, el) => {
      add(el);
      const wait = Math.max(0, HOLD_MS - (performance.now() - entry.at));
      clearTimeout(entry.timer);
      entry.timer = setTimeout(() => clear(el), wait);
    });
  };
  document.addEventListener('pointerup', release, { passive: true });
  const cancel = () => live.forEach((_, el) => clear(el));
  document.addEventListener('pointercancel', cancel, { passive: true });
  window.addEventListener('pagehide', cancel);
  document.addEventListener('dragstart', cancel);
}
