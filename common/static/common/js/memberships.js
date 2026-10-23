/* Memberships: keeps the choice tag, the compare table and the phone picker in step with the radio group,
   and counts the visits up once. The form itself is a plain GET and works without this file. */

// Which input was used last: a mouse or touch click must not leave a focus ring (a stray border round a card or a heading); the keyboard keeps it.
const mode = (kind) => () => { document.documentElement.dataset.input = kind; };
document.addEventListener('pointerdown', mode('pointer'), true);
document.addEventListener('keydown', mode('keyboard'), true);

const form = document.querySelector('[data-mem-form]');
if (form) {
  const radios = [...form.querySelectorAll('input[name="plan"]')];
  const el = (name) => form.querySelector(`[data-summary-${name}]`);
  const [nameEl, priceEl, incEl] = [el('name'), el('price'), el('inc')];
  const cells = [...document.querySelectorAll('.compare-table [data-slug]')];
  const table = document.querySelector('.compare-table');
  const picker = [...document.querySelectorAll('input[name="compare"]')];
  const button = form.querySelector('[data-continue]');

  // The pound sign is set small and raised, as on a price tag (.cur); the sentence still reads "£399 a month".
  const setPrice = (node, text) => {
    node.textContent = '';
    if (text.startsWith('£')) node.append(Object.assign(document.createElement('span'), { className: 'cur', textContent: '£' }), text.slice(1));
    else node.append(text);
  };
  // The tag fades its new words in once (opacity only; restarting the CSS animation), never on arrival.
  const acknowledge = () => [nameEl, priceEl, incEl].forEach((n) => { n.classList.remove('is-ack'); void n.offsetWidth; n.classList.add('is-ack'); });

  const sync = (ack = false) => {
    const on = radios.find((r) => r.checked);
    nameEl.textContent = on ? on.dataset.name : form.dataset.emptyText;
    setPrice(priceEl, on ? on.dataset.price : '');
    setPrice(incEl, on ? on.dataset.inc : '');
    if (ack) acknowledge();
    button.setAttribute('aria-disabled', on ? 'false' : 'true');
    cells.forEach((c) => c.classList.toggle('is-selected', !!on && c.dataset.slug === on.value));
    const view = on && picker.find((p) => p.dataset.slug === on.value);
    if (view && table) { view.checked = true; table.dataset.active = view.value; }
  };
  const tiers = form.querySelector('.tiers');
  // After the first change a new choice plays its sheen at once (the arrival pass is delayed in CSS).
  radios.forEach((r) => r.addEventListener('change', () => { tiers?.classList.add('is-settled'); sync(true); }));
  window.addEventListener('pageshow', () => sync()); // back/forward restores the checked radio
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

  // The pointer light inside the chosen card (desktop, fine pointer, motion allowed): --px / --py on that card only, one write per frame.
  if (matchMedia('(hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)').matches && tiers) {
    let frame = 0, point = null;
    const chosen = () => radios.find((r) => r.checked)?.closest('.tier');
    const clear = () => { cancelAnimationFrame(frame); frame = 0; tiers.querySelectorAll('.tier').forEach((t) => { t.style.removeProperty('--px'); t.style.removeProperty('--py'); }); };
    tiers.addEventListener('pointermove', (e) => {
      const card = chosen();
      if (!card || !card.contains(e.target)) { if (point) { point = null; clear(); } return; }
      point = e;
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        const box = card.getBoundingClientRect();
        card.style.setProperty('--px', `${point.clientX - box.left}px`);
        card.style.setProperty('--py', `${point.clientY - box.top}px`);
      });
    });
    tiers.addEventListener('pointerleave', () => { point = null; clear(); });
    radios.forEach((r) => r.addEventListener('change', clear));
  }
}
