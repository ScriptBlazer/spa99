/* The Rooms index on The spa page (desktop): tracks which room is in view. State only, no motion. */

const index = document.querySelector('[data-spa-index]');
if (index && 'IntersectionObserver' in window) {
  const links = new Map([...index.querySelectorAll('[data-index-link]')].map((a) => [a.dataset.indexLink, a]));
  const visible = new Set();
  const setCurrent = () => {
    const first = [...document.querySelectorAll('[data-facility]')].find((section) => visible.has(section.id));
    links.forEach((link, id) => { if (first && id === first.id) link.setAttribute('aria-current', 'true'); else link.removeAttribute('aria-current'); });
  };
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => (entry.isIntersecting ? visible.add(entry.target.id) : visible.delete(entry.target.id)));
    setCurrent();
  }, { rootMargin: '-30% 0px -40% 0px' });
  document.querySelectorAll('[data-facility]').forEach((section) => observer.observe(section));
}
