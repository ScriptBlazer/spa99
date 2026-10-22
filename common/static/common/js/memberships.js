/* Memberships: keeps the Continue bar, the compare table and the phone picker in step with the radio group,
   and counts the visits up once. The form itself is a plain GET and works without this file. */

const form = document.querySelector('[data-mem-form]');
if (form) {
  const radios = [...form.querySelectorAll('input[name="plan"]')];
  const el = (name) => form.querySelector(`[data-summary-${name}]`);
  const [nameEl, priceEl, incEl] = [el('name'), el('price'), el('inc')];
  const cells = [...document.querySelectorAll('.compare-table [data-slug]')];
  const table = document.querySelector('.compare-table');
  const picker = [...document.querySelectorAll('input[name="compare"]')];
  const button = form.querySelector('[data-continue]');

  const sync = () => {
    const on = radios.find((r) => r.checked);
    nameEl.textContent = on ? on.dataset.name : form.dataset.emptyText;
    priceEl.textContent = on ? on.dataset.price : '';
    incEl.textContent = on ? on.dataset.inc : '';
    button.setAttribute('aria-disabled', on ? 'false' : 'true');
    cells.forEach((c) => c.classList.toggle('is-selected', !!on && c.dataset.slug === on.value));
    const view = on && picker.find((p) => p.dataset.slug === on.value);
    if (view && table) { view.checked = true; table.dataset.active = view.value; }
  };
  radios.forEach((r) => r.addEventListener('change', sync));
  window.addEventListener('pageshow', sync); // back/forward restores the checked radio
  sync();

  // Nothing chosen: Continue moves focus to the choice instead of submitting.
  form.addEventListener('submit', (e) => {
    if (radios.some((r) => r.checked)) return;
    e.preventDefault();
    radios[0]?.focus();
  });

  // Visits count up once when the group arrives. Screen readers get the real number.
  if (!matchMedia('(prefers-reduced-motion: reduce)').matches && 'IntersectionObserver' in window) {
    const counters = [...form.querySelectorAll('[data-count]')].map((node) => {
      const end = parseInt(node.textContent, 10);
      const sr = Object.assign(document.createElement('span'), { className: 'sr-only', textContent: node.textContent });
      node.after(sr);
      node.setAttribute('aria-hidden', 'true');
      node.textContent = '0';
      return { node, end };
    });
    const run = () => counters.forEach(({ node, end }) => {
      const t0 = performance.now();
      const tick = (now) => {
        const p = Math.min(1, (now - t0) / 1200);
        node.textContent = Math.round(end * (1 - Math.pow(1 - p, 3)));
        if (p < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
    const io = new IntersectionObserver((entries) => {
      const e = entries[0];
      if (e.isIntersecting && (e.intersectionRatio >= 0.15 || form.offsetHeight > innerHeight)) { io.disconnect(); run(); }
    }, { threshold: [0, 0.15] });
    io.observe(form);
  }
}
