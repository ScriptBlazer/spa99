/* Sale bar and sale band: countdown to the second (text only, no animation), removal of the bar at the end (the bar is always on, not dismissible) or an in-place "ended" line (band). No scroll listeners, no setInterval; the clock pauses while the tab is hidden. */
const bar = document.querySelector('[data-sale-bar]');
const bands = [...document.querySelectorAll('[data-sale-band]')];
const reduce = matchMedia('(prefers-reduced-motion: reduce)');
const two = (n) => String(n).padStart(2, '0');

/** Seconds rounded up so a live sale never says 0s. Returns { d, h, m, s }. */
function format(ms) {
  const t = Math.max(1, Math.ceil(ms / 1000));
  return { d: Math.floor(t / 86400), h: Math.floor((t % 86400) / 3600), m: Math.floor((t % 3600) / 60), s: t % 60 };
}
/** Run `fn` now and then on each second boundary of the end time (one setTimeout aligned to the next second, so it never drifts), and again when the tab comes back. Nothing runs while the tab is hidden. `fn` returns false to stop. */
function clock(ends, offset, fn) {
  let timer = 0;
  let stopped = false;
  const tick = () => {
    clearTimeout(timer);
    if (stopped || document.hidden) return;
    const left = ends - (Date.now() + offset);
    if (fn(left) === false) { stopped = true; return; }
    timer = setTimeout(tick, (left % 1000) || 1000);
  };
  tick();
  document.addEventListener('visibilitychange', tick);
}

for (const band of bands) {
  if ('upcoming' in band.dataset) continue;
  const count = band.querySelector('[data-sale-count]');
  const ends = Date.parse(band.dataset.ends);
  const offset = Date.parse(band.dataset.now) - Date.now();
  let inView = true;
  if ('IntersectionObserver' in window) new IntersectionObserver(([e]) => { inView = e.isIntersecting; }).observe(band);
  const unit = (n, one, many) => `<span class="sale-band-unit"><span class="sale-band-num">${n}</span><span class="sale-band-label">${n === '1' || n === '01' ? one : many}</span></span>`;
  let last = '';
  clock(ends, offset, (left) => {
    if (left <= 0) { finish(); return false; }
    const { d, h, m, s } = format(left);
    const html = (d ? unit(String(d), 'day', 'days') : '') + (d || h ? unit(d ? two(h) : String(h), 'hour', 'hours') : '') + (d || h || m ? unit(d || h ? two(m) : String(m), 'minute', 'minutes') : '') + unit(d || h || m ? two(s) : String(s), 'second', 'seconds');
    if (html !== last) { count.innerHTML = html; last = html; }
  });
  function finish() {
    count.style.minBlockSize = `${count.offsetHeight}px`;
    const swap = () => {
      count.innerHTML = '<p class="sale-band-over">This sale has now ended.</p>';
      count.removeAttribute('aria-hidden');
      band.querySelector('[data-sale-ends]')?.setAttribute('hidden', '');
      count.classList.remove('is-leaving');
    };
    if (reduce.matches || !inView) swap();
    else { count.classList.add('is-leaving'); setTimeout(swap, 400); }
  }
}

// The Memberships band button scrolls up to the tier cards and moves focus to their group.
document.querySelector('[data-sale-jump]')?.addEventListener('click', (event) => {
  const target = document.getElementById('plans');
  if (!target) return;
  event.preventDefault();
  target.scrollIntoView({ behavior: reduce.matches ? 'auto' : 'smooth', block: 'start' });
  const legend = target.querySelector('.tiers legend');
  if (legend) { legend.tabIndex = -1; legend.focus({ preventScroll: true }); }
});

if (bar) {
  const root = document.documentElement;
  const count = bar.querySelector('[data-sale-count]');
  const ends = Date.parse(bar.dataset.ends);
  const offset = Date.parse(bar.dataset.now) - Date.now();
  const now = () => Date.now() + offset;
  let timer = 0;
  let removed = false;

  function render() {
    const { d, h, m, s } = format(ends - now());
    count.textContent = d ? `${d}d ${two(h)}h ${two(m)}m ${two(s)}s` : h ? `${h}h ${two(m)}m ${two(s)}s` : m ? `${m}m ${two(s)}s` : `${s}s`;
  }
  /** The sale is over: the bar goes and the header takes the top (html.has-sale drives --sale-top). A bar in the flow also takes its height with it, so the page is scrolled up by the same amount to stay put. */
  function remove() {
    clearTimeout(timer);
    const inFlow = getComputedStyle(bar).position === 'sticky';
    const height = bar.offsetHeight;
    const done = () => {
      bar.hidden = true;
      root.classList.remove('has-sale');
      if (inFlow && window.scrollY > 0) window.scrollBy(0, -Math.min(height, window.scrollY));
      window.dispatchEvent(new Event('resize'));
    };
    if (reduce.matches) { done(); return; }
    bar.classList.add('is-leaving');
    setTimeout(done, 400);
  }
  function tick() {
    clearTimeout(timer);
    if (document.hidden || removed) return;
    const left = ends - now();
    if (left <= 0) { removed = true; remove(); return; }
    render();
    timer = setTimeout(tick, (left % 1000) || 1000);
  }

  if (!('upcoming' in bar.dataset) && count) {
    tick();
    document.addEventListener('visibilitychange', tick);
  }

  // After "End preview", Back may restore this page from the back/forward cache with the old preview bar: reload it.
  if ('preview' in bar.dataset) window.addEventListener('pageshow', (e) => { if (e.persisted) location.reload(); });
}
