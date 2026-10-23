/* The Gold Card: the CSS card, its pose proxy (gc), the swan draw and the Home section's scene (docs/design/GOLD-CARD-3D.md).
 * Loaded lazily (scenes.js, when the Home section is near; gold-hero.js on the Gold Card page) so Home's first script stays under its size cap.
 * gold-card-3d.js (three.js) reads the same pose proxy; gold-gl.js decides whether it loads. */
import { cleanups, lineRise, fadeUp, thread } from './scenes.js';

const { gsap, ScrollTrigger } = window;
const root = document.documentElement;

/* TEMPORARY (2026-10-23): add ?glcheck to the URL to see whether the 3D card can run here, and if not, why. Remove once diagnosed. */
if (new URLSearchParams(location.search).has('glcheck')) {
  const why = [];
  if (root.dataset.webgl === 'off') why.push('SITE_WEBGL is off');
  if (!matchMedia('(min-width: 64em)').matches) why.push(`window too narrow (${innerWidth}px, needs 1024)`);
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) why.push('Reduce motion is on');
  if (navigator.connection?.saveData || matchMedia('(prefers-reduced-data: reduce)').matches) why.push('save data is on');
  if ((navigator.deviceMemory ?? 8) < 4) why.push(`low memory reported (${navigator.deviceMemory} GB)`);
  if ((navigator.hardwareConcurrency ?? 8) < 4) why.push(`few CPU cores reported (${navigator.hardwareConcurrency})`);
  const strict = document.createElement('canvas').getContext('webgl2', { failIfMajorPerformanceCaveat: true });
  const loose = document.createElement('canvas').getContext('webgl2');
  if (!strict) why.push(loose ? 'WebGL2 only in slow software mode (graphics acceleration off?)' : 'no WebGL2');
  const tag = document.createElement('div');
  tag.textContent = why.length ? `3D card OFF: ${why.join('; ')}` : '3D card ON';
  tag.style.cssText = 'position:fixed;left:12px;bottom:12px;z-index:9999;padding:10px 14px;background:#000;color:#fff;font:14px/1.4 sans-serif;border-radius:6px';
  document.body.append(tag);
  const errors = [];
  addEventListener('error', (e) => errors.push(e.message || String(e.error)));
  addEventListener('unhandledrejection', (e) => errors.push(String(e.reason?.message || e.reason)));
  setTimeout(() => {
    const canvas = document.querySelector('.gc-gl canvas');
    const mount = document.querySelector('.gold-card');
    tag.textContent += ` | after 8 s: canvas ${canvas ? `opacity ${(+getComputedStyle(canvas).opacity).toFixed(2)}` : 'missing'}, ${mount?.classList.contains('is-gl') ? '3D showing' : 'flat card showing'}${errors.length ? ` | errors: ${errors.join(' / ')}` : ''}`;
  }, 8000);
}

/* ---------- the Gold Card (docs/design/GOLD-CARD-3D.md) ---------- */

const ramp = (pts) => (t) => {                            // piecewise linear through [t, value] points
  for (let i = 1; i < pts.length; i++) if (t <= pts[i][0]) return pts[i - 1][1] + ((pts[i][1] - pts[i - 1][1]) * (t - pts[i - 1][0])) / (pts[i][0] - pts[i - 1][0] || 1);
  return pts[pts.length - 1][1];
};
const HOME_RY = ramp([[0, -25], [0.05, -25], [0.3, -14], [0.45, -8], [0.75, 12], [1, 25]]);
const HOME_RX = ramp([[0, 8], [0.05, 8], [0.3, 5], [0.45, 3], [0.75, -2], [1, -6]]);
const HOME_SHEEN = ramp([[0, -1], [0.45, -1], [0.75, 1], [1, 1]]);

/** The pose proxy and the CSS card. Everything that moves the card writes to `gc`; render() puts it on the CSS card (and the page-level opacity);
 *  gold-card-3d.js reads the same fields. ry/rx are the base pose in degrees (rx positive tips the face up), turn is the scroll half turn (hero),
 *  bob/roll are the idle float, lift/drop are in percent of the card height. */
export function goldCard(mount, scene, { desktop, fine, ctx }) {
  const q = (sel) => mount.querySelector(sel);
  const k = desktop ? 1 : 18 / 25;
  const gc = { ry: -25 * k, rx: desktop ? 8 : 5, turn: 0, tiltX: 0, tiltY: 0, roll: 0, bob: 0, lift: 0, drop: 0, sheen: -1, draw: 1, line: 0, relief: 1, fade: 1, gl: false, k, p: 0 };
  const el = { card: q('.gc-card'), float: q('.gc-float'), shade: q('.gc-shade'), sheen: q('.gc-sheen'), pool: q('.gc-pool') };
  gc.render = () => {
    mount.style.opacity = gc.fade;
    mount.style.transform = gc.lift + gc.drop ? `translate3d(0, ${gc.lift + gc.drop}%, 0)` : '';   // the whole mount (canvas, pool, card) moves, so nothing is ever cut by a canvas edge
    if (gc.gl) return;
    const ry = gc.ry + gc.turn + gc.tiltY, a = ((ry % 360) + 540) % 360 - 180, n = a / (25 * k);
    el.card.style.transform = `rotateX(${gc.rx + gc.tiltX}deg) rotateY(${ry}deg)`;
    el.float.style.transform = `translate3d(0, ${gc.bob}%, 0) rotate(${gc.roll}deg)`;
    el.shade.style.opacity = n < 0 ? 0.3 * Math.min(1, -n) : 0.12 * Math.min(1, n);
    el.sheen.style.transform = `translateX(${gc.sheen * 130}%) skewX(-14deg)`;
    el.pool.style.opacity = 0.85 + 0.15 * (gc.bob / 1.6);
  };
  cleanups.push(() => { mount.style.opacity = ''; mount.style.transform = ''; ['card', 'float', 'shade', 'sheen', 'pool'].forEach((n) => el[n].removeAttribute('style')); });

  // Swan: the CSS card draws with DrawSVG, the canvas reads the same moments from the proxy. windows are [from, to] in timeline units.
  // Moishe 2026-10-23: the swan is there, complete and in full relief, from the first frame (no outline drawing in). Same signature, so callers stay.
  gc.swan = (tl) => {
    const svg = q('.mark-draw');
    gsap.set(svg.querySelectorAll('.mark-line path'), { drawSVG: '100%' });
    gsap.set(svg.querySelector('.mark-fill'), { opacity: 1 });
    gsap.set(q('.gc-swan-shadow'), { opacity: 0.5 });
    gsap.set(svg.querySelector('.mark-line'), { opacity: 0 });
    Object.assign(gc, { draw: 1, relief: 1, line: 0 });
    return tl;
  };

  // Idle float (18s bob, 23s roll), paused off screen and in a hidden tab (BRAND 7A loop rule).
  const floats = [
    gsap.fromTo(gc, { bob: -1.6 }, { bob: 1.6, duration: 9, ease: 'sine.inOut', yoyo: true, repeat: -1, onUpdate: gc.render }),
    gsap.fromTo(gc, { roll: -0.6 }, { roll: 0.6, duration: 11.5, ease: 'sine.inOut', yoyo: true, repeat: -1 }),
  ];
  let onScreen = false;
  const sync = () => floats.forEach((t) => (onScreen && !document.hidden ? t.resume() : t.pause()));
  ScrollTrigger.create({ trigger: scene, start: 'top bottom', end: 'bottom top', onToggle: (self) => { onScreen = self.isActive; sync(); } });
  document.addEventListener('visibilitychange', sync);
  cleanups.push(() => document.removeEventListener('visibilitychange', sync));
  sync();

  // Pointer tilt (desktop, fine pointer): up to 6 degrees, damped, no overshoot.
  if (desktop && fine) {
    const max = 6, target = { x: 0, y: 0 };
    const move = (e) => { const r = scene.getBoundingClientRect(); target.y = ((e.clientX - r.left) / r.width * 2 - 1) * max; target.x = -((e.clientY - r.top) / r.height * 2 - 1) * max; };
    const leave = () => { target.x = target.y = 0; };
    const follow = (_, dt) => {
      const f = 1 - Math.pow(0.94, dt / 16.7);
      if (Math.abs(target.x - gc.tiltX) + Math.abs(target.y - gc.tiltY) < 0.002) return;
      gc.tiltX += (target.x - gc.tiltX) * f; gc.tiltY += (target.y - gc.tiltY) * f; gc.render();
    };
    scene.addEventListener('pointermove', move); scene.addEventListener('pointerleave', leave); gsap.ticker.add(follow);
    cleanups.push(() => { scene.removeEventListener('pointermove', move); scene.removeEventListener('pointerleave', leave); gsap.ticker.remove(follow); });
  }
  gc.render();
  // the three.js layer (capable desktops only): the gate and loader are in gold-gl.js, fetched only when this could pass
  if (desktop && root.dataset.webgl !== 'off' && mount.dataset.webglGate) import(mount.dataset.webglGate).then((m) => m.loadCards(ctx, { mount, gc, gsap, ScrollTrigger, cleanups, root })).catch((e) => { console.error('gold card 3d', e); mount.classList.add('gl-off'); });
  return gc;
}

/** R6b The Gold Card (Home): no pin. The card swings -25 to +25 degrees as the section passes; the swan draws itself on its face (shaded, line),
 *  becomes raised metal, a band of light crosses it with the card square to you, the edge catches the light as it leaves. */
export const gold = (el, { desktop, fine, ctx }) => {
  const scrub = desktop ? 0.5 : 0.3;
  if (desktop) thread(el, 0.4, { start: 'top 90%', end: 'top 55%' });
  const gc = goldCard(el.querySelector('[data-gold-card]'), el, { desktop, fine, ctx });
  const tl = gsap.timeline({ defaults: { ease: 'none' }, scrollTrigger: { trigger: el, start: 'top 85%', end: 'bottom 15%', scrub } });
  tl.to(gc, { p: 1, duration: 1, onUpdate: () => { gc.ry = HOME_RY(gc.p) * gc.k; gc.rx = gc.k === 1 ? HOME_RX(gc.p) : 5 + (HOME_RX(gc.p) - 8) * (9 / 14); gc.sheen = HOME_SHEEN(gc.p); gc.render(); } }, 0);
  gc.swan(tl, { draw: [0.05, 0.3], relief: [0.3, 0.42], line: [0.36, 0.45] }, 'none');
  const h = el.querySelector('[data-rise]');
  lineRise(h);
  fadeUp(el.querySelectorAll('.gold-text > [data-fade]'), { trigger: h, start: 'top 75%', delay: 0.3, stagger: 0.15 });
  fadeUp(el.querySelectorAll('[data-pill]'), { trigger: el.querySelector('.pills'), start: 'top 90%', delay: 0.2, stagger: 0.06 });
};
