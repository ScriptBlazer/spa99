/* Privacy notice and Terms of use: the contents list marks the part being read (aria-current), and stays open as a
 * side rail on desktop. No scroll listeners: one IntersectionObserver. Without JS the list is a plain open list. */

const toc = document.querySelector('[data-legal-toc]');
const desktop = window.matchMedia('(min-width: 64em)');

if (toc) {
  const links = new Map([...toc.querySelectorAll('a[href^="#"]')].map((a) => [a.hash.slice(1), a]));
  const parts = [...links.keys()].map((id) => document.getElementById(id)).filter(Boolean);

  const keepOpen = () => { if (desktop.matches) toc.open = true; };
  keepOpen();
  desktop.addEventListener('change', keepOpen);

  const mark = (id) => links.forEach((a, key) => {
    if (key === id) a.setAttribute('aria-current', 'true');
    else a.removeAttribute('aria-current');
  });

  if ('IntersectionObserver' in window && parts.length) {
    const visible = new Set();
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => (entry.isIntersecting ? visible.add(entry.target) : visible.delete(entry.target)));
      const current = parts.find((part) => visible.has(part));
      if (current) mark(current.id);
    }, { rootMargin: '-20% 0px -60% 0px' });
    parts.forEach((part) => observer.observe(part));
  }
}
