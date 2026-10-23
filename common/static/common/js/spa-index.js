/* The spa page: a sideways scroll row (the phone tile row) with nothing focusable inside it gets a tab stop while it overflows,
   so keyboard users can scroll it with the arrow keys. Not needed once it fits (desktop). Works without motion or GSAP. */
const rows = [...document.querySelectorAll('[data-scroller]')];
const FOCUSABLE = 'a[href], button, input, select, textarea, [tabindex]';

const update = (row) => {
  const overflows = row.scrollWidth > row.clientWidth + 1;
  if (overflows && !row.querySelector(FOCUSABLE)) row.setAttribute('tabindex', '0');
  else row.removeAttribute('tabindex');
};

if (rows.length && 'ResizeObserver' in window) {
  const observer = new ResizeObserver((entries) => entries.forEach((entry) => update(entry.target)));
  rows.forEach((row) => { update(row); observer.observe(row); });
}
