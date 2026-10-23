/* The gate and loader for the three.js Gold Card (docs/design/GOLD-CARD-3D.md, IMMERSIVE 14.0 and 14.3): a layer on top of the CSS card, never a replacement.
 * Imported by gold-card.js only on desktop so the checks below are not in Home's first script.
 * loadCards(ctx, { mount, gc, gsap, ScrollTrigger, cleanups, root }) is called inside scenes.js's matchMedia context (ctx). */

/** One synchronous gate: large screen, motion allowed, no Save-Data, a real GPU with WebGL2. Phones and tablets never pass. */
function webglGate(root) {
  if (root.dataset.webgl === 'off') return false;
  if (!matchMedia('(min-width: 64em)').matches || matchMedia('(prefers-reduced-motion: reduce)').matches) return false;
  if (navigator.connection?.saveData || matchMedia('(prefers-reduced-data: reduce)').matches) return false;
  if ((navigator.deviceMemory ?? 8) < 4 || (navigator.hardwareConcurrency ?? 8) < 4) return false;
  const gl = document.createElement('canvas').getContext('webgl2', { failIfMajorPerformanceCaveat: true });
  if (!gl) return false;
  gl.getExtension('WEBGL_lose_context')?.loseContext();
  return true;
}

/** Load gold-card-3d.js after `load` + idle, and (Home) only when the mount is within two screens. Teardown goes to cleanups. */
export function loadCards(ctx, { mount, gc, gsap, ScrollTrigger, cleanups, root }) {
  if (!ctx.conditions.desktop || !webglGate(root)) { mount.classList.add('gl-off'); return; }
  const off = (e) => { console.error('gold card 3d', e); mount.classList.add('gl-off'); };
  const tokens = (name) => getComputedStyle(root).getPropertyValue(name).trim();
  let inst = null, dead = false, io = null;
  const go = () => import(mount.dataset.webglSrc)
    .then((m) => { if (!dead) ctx.add(() => { inst = m.create(mount, { gsap, ScrollTrigger, tokens, card: gc }); inst.ready.catch((e) => { off(e); inst.dispose(); }); }); })
    .catch(off);
  const near = () => {
    if (mount.dataset.goldCard === 'hero' || !('IntersectionObserver' in window)) return go();
    io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { io.disconnect(); go(); } }, { rootMargin: '200% 0px' });
    io.observe(mount);
  };
  const start = () => (window.requestIdleCallback || setTimeout)(() => { if (!dead) near(); }, { timeout: 2000 });
  // the Gold Card page hero loads at once (its flat card is hidden meanwhile); Home waits for load + idle
  if (mount.dataset.goldCard === 'hero') near();
  else if (document.readyState === 'complete') start(); else window.addEventListener('load', start, { once: true });
  cleanups.push(() => { dead = true; io?.disconnect(); inst?.dispose(); inst = null; });
}
