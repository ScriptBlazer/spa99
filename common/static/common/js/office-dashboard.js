/* Dashboard: big numbers count up once per session, with their card. The final value is already in the HTML; this only animates it. */

const KEY = 'office-counted';
const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const ease = (t) => 1 - (1 - t) ** 5; // easeOutQuint, as the charts

function duration() {
  const raw = getComputedStyle(document.documentElement).getPropertyValue('--duration-count').trim();
  return raw.endsWith('ms') ? parseFloat(raw) : parseFloat(raw) * 1000 || 0;
}

function format(el, value) {
  const decimals = Number(el.dataset.decimals || 0);
  const text = decimals ? value.toFixed(decimals) : Math.round(value).toLocaleString('en-GB');
  return text + (el.dataset.suffix || '');
}

function count(el, ms) {
  const target = Number(el.dataset.count);
  if (!Number.isFinite(target) || target <= 0) return;
  const start = performance.now();
  el.textContent = format(el, 0);
  const frame = (now) => {
    const t = Math.min((now - start) / ms, 1);
    el.textContent = format(el, target * ease(t));
    if (t < 1) requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

export function initCounts() {
  const items = [...document.querySelectorAll('[data-office-dashboard] [data-count]')];
  if (!items.length) return;
  let seen = false;
  try { seen = sessionStorage.getItem(KEY) === '1'; sessionStorage.setItem(KEY, '1'); } catch { /* private mode: count again */ }
  const ms = duration();
  if (seen || reduced() || !ms || !('IntersectionObserver' in window)) return;
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      observer.unobserve(entry.target);
      count(entry.target, ms);
    });
  }, { threshold: 0.15 });
  items.forEach((el) => { el.textContent = format(el, 0); observer.observe(el); });
}
