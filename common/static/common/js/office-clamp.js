/* Long text in the Office (docs/features/office-outreach-design.md R3): `.o-clamp` shows a few lines (--lines), and "Read more" / "Show less"
 * appears only where the text is really cut. Markup:
 *
 *   <div class="o-clamp" style="--lines: 3" data-clamp>...</div>
 *   <button type="button" class="o-quiet o-clamp-more" data-clamp-more data-more-label="Read more" hidden>Read more</button>
 *
 * The button is the element right after the clamp. Without this script nothing is clamped (html:not(.js) in office.css) and the button stays
 * hidden. Measured on what is on screen: on load, on resize, and whenever the page swaps rows, notes or timeline in (a MutationObserver on
 * the main area), and by `measureClamps()` after a sheet opens. */

const next = () => requestAnimationFrame(() => measureClamps());   // the frame time must not become `root`
let queued = false;

/** Show or hide each "Read more" by whether its text is cut now. An opened clamp keeps its button (it reads "Show less"). */
export function measureClamps(root = document) {
  root.querySelectorAll('[data-clamp]').forEach((clamp) => {
    const more = clamp.nextElementSibling?.matches('[data-clamp-more]') ? clamp.nextElementSibling : null;
    if (!more || !clamp.offsetParent) return;                  // not on screen (a closed sheet): measured when it opens
    if (clamp.hasAttribute('data-open')) { more.hidden = false; return; }
    more.hidden = !(clamp.scrollHeight > clamp.clientHeight + 1);
  });
}

function toggle(button) {
  const clamp = button.previousElementSibling;
  if (!clamp?.matches('[data-clamp]')) return;
  const open = !clamp.hasAttribute('data-open');
  clamp.toggleAttribute('data-open', open);
  button.setAttribute('aria-expanded', String(open));
  button.textContent = open ? 'Show less' : (button.dataset.moreLabel || 'Read more');
}

export function initClamp() {
  document.addEventListener('click', (event) => {
    const button = event.target.closest?.('[data-clamp-more]');
    if (button) { event.preventDefault(); toggle(button); }
  });
  window.addEventListener('resize', next);
  const area = document.getElementById('office-main');
  if (area && 'MutationObserver' in window) {
    new MutationObserver(() => { if (!queued) { queued = true; requestAnimationFrame(() => { queued = false; measureClamps(); }); } }).observe(area, { childList: true, subtree: true });
  }
  if (document.fonts?.ready) document.fonts.ready.then(next);   // the handwriting font changes line breaks
  next();
}
