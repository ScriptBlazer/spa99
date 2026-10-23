/* The Gold Card page below the card (docs/design/GOLD-PAGE-R3.md): G2 the back of the card, G3 who it is for, G4 how it works and apply.
 * Registers its scenes with scenes.js (the registry, the line rise and the fade up). Transform and opacity only; reduced motion keeps the static page. */
import { SCENES, cleanups, lineRise, fadeUp, settle } from './scenes.js';

const { gsap, ScrollTrigger } = window;

if (gsap && ScrollTrigger) {
  /** A small whole number counts up once when its group enters. Screen readers get the real value from a hidden copy. */
  const count = (el, trigger) => {
    const end = parseInt(el.textContent, 10);
    if (!Number.isFinite(end) || end > 99 || ScrollTrigger.isInViewport(trigger)) return;
    const label = el.textContent;
    const sr = Object.assign(document.createElement('span'), { className: 'sr-only', textContent: label });
    el.after(sr);
    el.setAttribute('aria-hidden', 'true');
    el.textContent = '0';
    const n = { v: 0 };
    ScrollTrigger.create({ trigger, start: 'top 85%', once: true, onEnter: () => gsap.to(n, { v: end, duration: 1.2, snap: { v: 1 }, onUpdate: () => { el.textContent = n.v; } }) });
    cleanups.push(() => { el.textContent = label; el.removeAttribute('aria-hidden'); sr.remove(); });
  };

  /** G2 The back of the card: the panel fades up as one block, its words follow, "7" and "2" count, and one sheen crosses it once. */
  SCENES['gold-holds'] = (el, { desktop }) => {
    const panel = el.querySelector('.gold-back');
    fadeUp(panel, { trigger: panel, start: 'top 85%' });
    lineRise(el.querySelector('[data-rise]'), { trigger: true });
    fadeUp(el.querySelectorAll('.gb-head [data-fade]'), { trigger: panel, start: 'top 80%', delay: 0.2 });
    const figures = el.querySelector('.gb-figures');
    fadeUp(figures.querySelectorAll('[data-fade-row]'), { trigger: figures, start: 'top 85%', delay: 0.1, stagger: desktop ? 0.1 : 0 });
    figures.querySelectorAll('[data-count]').forEach((n) => count(n, figures));
    fadeUp(el.querySelectorAll('.gb-pills [data-fade-row]'), { trigger: el.querySelector('.gb-pills'), start: 'top 90%' });
    fadeUp(el.querySelectorAll('.gb-perks [data-fade-row]'), { trigger: el.querySelector('.gb-perks') || panel, start: 'top 90%', stagger: desktop ? 0.1 : 0 });
    // one sheen when half the panel is in view, once per page view
    ScrollTrigger.create({ trigger: panel, start: 'center bottom', once: true, onEnter: () => panel.classList.add('is-sheen') });
    cleanups.push(() => panel.classList.remove('is-sheen'));
  };

  /** G3 Who it is for: the picture settles, the inset drifts against it, the heading rises, the roles arrive as one group. */
  SCENES['gold-who'] = (el, { desktop }) => {
    const scrub = desktop ? 0.4 : 0.3;
    lineRise(el.querySelector('[data-rise]'));
    el.querySelectorAll('[data-frame]').forEach((f) => settle(f, scrub));
    const inset = el.querySelector('[data-inset]');
    if (inset && desktop) gsap.fromTo(inset, { yPercent: 6 }, { yPercent: -6, ease: 'none', scrollTrigger: { trigger: el, start: 'top bottom', end: 'bottom top', scrub } });
    fadeUp(el.querySelectorAll('[data-fade-row]'), { trigger: el.querySelector('.gw-roles'), start: 'top 85%' });
    fadeUp(el.querySelectorAll('.gw-text [data-fade]'), { trigger: el.querySelector('.gw-roles'), start: 'top 85%', delay: 0.15 });
    el.querySelectorAll('[data-caption]').forEach((c) => fadeUp(c, { trigger: c, start: 'top 90%' }));
  };

  /** G4 How it works: the line draws through the steps (scrubbed) and each number comes up as it arrives; the card settles; the apply words arrive together. */
  SCENES['gold-how'] = (el, { desktop }) => {
    const scrub = desktop ? 0.4 : 0.3;
    lineRise(el.querySelector('[data-rise]'));
    const steps = [...el.querySelectorAll('[data-gstep]')];
    steps.forEach((s) => fadeUp(s, { trigger: s, start: 'top 85%' }));
    const seg = 1 / Math.max(1, steps.length - 1);
    const tl = gsap.timeline({ defaults: { ease: 'none' }, scrollTrigger: { trigger: el.querySelector('[data-gsteps]'), start: 'top 70%', end: 'bottom 60%', scrub } });
    steps.forEach((s, i) => {
      tl.fromTo(s.querySelector('.gstep-num'), { opacity: 0.4 }, { opacity: 1, duration: 0.1 * seg }, i * seg);
      const line = s.querySelector('.gstep-line');
      if (line) tl.fromTo(line, { scaleY: 0 }, { scaleY: 1, duration: 0.9 * seg, transformOrigin: '50% 0' }, i * seg + 0.05 * seg);
    });
    const card = el.querySelector('[data-card]');
    gsap.fromTo(card, { opacity: 0, scale: 0.98 }, { opacity: 1, scale: 1, duration: 1, scrollTrigger: { trigger: card, start: 'top 85%', once: true } });
    fadeUp(el.querySelectorAll('.gh-apply [data-fade]'), { trigger: card, start: 'top 80%', delay: 0.2 });
  };
}
