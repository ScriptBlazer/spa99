/* Sale bar: quiet countdown on the minute, dismiss for the session, removal at the end. No scroll listeners, no setInterval. */
const bar = document.querySelector('[data-sale-bar]');
if (bar) {
  const root = document.documentElement;
  const KEY = 'spa99.sale.dismissed';
  const header = document.querySelector('.site-header');
  const count = bar.querySelector('[data-sale-count]');
  const ends = Date.parse(bar.dataset.ends);
  const offset = Date.parse(bar.dataset.now) - Date.now();
  const now = () => Date.now() + offset;
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  let timer = 0;
  let visible = true;

  const two = (n) => String(n).padStart(2, '0');
  function format(ms) {
    const total = Math.max(1, Math.ceil(ms / 60000));
    const d = Math.floor(total / 1440), h = Math.floor((total % 1440) / 60), m = total % 60;
    if (d) return [`${d}d ${two(h)}h`, ` ${two(m)}m`, true];
    if (h) return [`${h}h ${two(m)}m`, '', false];
    return [`${m}m`, '', false];
  }
  function render() {
    const [lead, tail, days] = format(ends - now());
    count.textContent = lead;
    if (days) { const s = document.createElement('span'); s.className = 'sale-bar-m'; s.textContent = tail; count.append(s); }
  }
  function refreshPins() { window.dispatchEvent(new Event('resize')); }
  function remove(fade) {
    clearTimeout(timer);
    const height = bar.offsetHeight;
    const done = () => {
      bar.hidden = true;
      root.classList.add('sale-off');
      root.style.removeProperty('--sale-shift');
      if (fade === false && !visible) window.scrollBy(0, -height);
      refreshPins();
    };
    if (fade === false || reduce.matches) { done(); return; }
    bar.classList.add('is-leaving');
    setTimeout(done, 400);
  }
  function tick() {
    const left = ends - now();
    if (left <= 0) { remove(visible); return; }
    render();
    timer = setTimeout(tick, (left % 60000) || 60000);
  }

  if (!('animation-timeline' in root.style) && !(window.CSS && CSS.supports('animation-timeline: scroll()')) && header && 'IntersectionObserver' in window && root.dataset.page === 'marketing') {
    const h = bar.offsetHeight;
    const thresholds = Array.from({ length: 21 }, (_, i) => i / 20);
    new IntersectionObserver(([e]) => { visible = e.isIntersecting; root.style.setProperty('--sale-shift', `${(e.intersectionRatio * h).toFixed(1)}px`); }, { threshold: thresholds }).observe(bar);
  } else if ('IntersectionObserver' in window) {
    new IntersectionObserver(([e]) => { visible = e.isIntersecting; }).observe(bar);
  }

  bar.querySelector('[data-sale-close]').addEventListener('click', () => {
    try { sessionStorage.setItem(KEY, bar.dataset.sale); } catch (e) { /* private mode: hides for this page only */ }
    remove(true);
    document.querySelector('.site-header .brand, .menu-toggle')?.focus();
  });

  if (!('upcoming' in bar.dataset) && count) {
    tick();
    document.addEventListener('visibilitychange', () => { if (!document.hidden) { clearTimeout(timer); tick(); } });
  }
}
