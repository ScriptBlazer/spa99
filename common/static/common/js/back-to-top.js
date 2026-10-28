/* Back to top. One IntersectionObserver on a sentinel at 100vh (no scroll listener): the button shows once the page is past
   the first screen. Click scrolls to the top (Lenis when it is running, instant for reduced motion) and moves focus to the brand link. */
const link = document.querySelector('[data-back-to-top]');
const sentinel = document.querySelector('[data-btt-sentinel]');

if (link && sentinel && 'IntersectionObserver' in window) {
  const io = new IntersectionObserver(([entry]) => {
    link.classList.toggle('is-visible', !entry.isIntersecting && entry.boundingClientRect.top < 0);
  });
  io.observe(sentinel);

  link.addEventListener('click', (e) => {
    e.preventDefault();
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (window.spaLenis && !reduce) window.spaLenis.scrollTo(0, { duration: 1.2 });
    else window.scrollTo({ top: 0, left: 0, behavior: reduce ? 'auto' : 'smooth' });
    // Keyboard and screen-reader users land at the top; focusing the brand link also brings the header back (scenes.js).
    (document.querySelector('.site-header .brand') || document.querySelector('.skip-link'))?.focus({ preventScroll: true });
  });
}
