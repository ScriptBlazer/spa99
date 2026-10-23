/* The one shared reveal module (BRAND section 7). CSS does the motion; this only adds .is-visible.
 *
 *   data-reveal            a group: heading + copy + actions together (fade and rise)
 *   data-reveal="image"    a standalone image (scale 0.98 to 1)
 *   data-reveal="hero"     the hero on load (0.8s, no delay)
 *   data-reveal="stagger"  2 to 4 siblings that show a progression (0.1s apart from tablet up)
 *
 * A group reveals once, on its own, when 15% of it is in view (as soon as any of it is, if it is taller than the
 * screen). Reduced motion: everything is visible at once. No scroll listeners.
 */

const reduceMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
let observer = null;

function show(el) {
  el.classList.add('is-visible');
  observer?.unobserve(el);
}

function pending(root) {
  return [...root.querySelectorAll('[data-reveal]:not(.is-visible)')];
}

/** Reveal groups inside `root` (the page, or a part that was just added, such as a journey screen). */
export function observeReveals(root = document) {
  const groups = pending(root);
  if (root !== document && root.matches?.('[data-reveal]') && !root.classList.contains('is-visible')) groups.unshift(root);
  if (!groups.length) return;
  if (reduceMotion() || !('IntersectionObserver' in window)) {
    groups.forEach((el) => el.classList.add('is-visible'));
    return;
  }
  if (!observer) {
    observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        const el = entry.target;
        const tall = el.offsetHeight > window.innerHeight;
        if (entry.isIntersecting && (tall || entry.intersectionRatio >= 0.15)) show(el);
      });
    }, { threshold: [0, 0.15] });
  }
  groups.forEach((el) => {
    if (el.dataset.reveal === 'hero' || el.dataset.reveal === 'hero-image') {
      requestAnimationFrame(() => requestAnimationFrame(() => el.classList.add('is-visible')));
    } else {
      observer.observe(el);
    }
  });
}

export function initReveal() {
  document.documentElement.dataset.reveal = 'ready'; // tells the head failsafe that this script loaded
  observeReveals(document);
}
