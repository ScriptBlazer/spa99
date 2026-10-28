/* Immersive marketing scenes (docs/design/IMMERSIVE.md sections 2 and 8). Loaded only by the marketing templates, after the
 * vendored GSAP, plugins and Lenis (classic deferred scripts that attach window.gsap, window.Lenis).
 *
 * How it hangs together
 *  - Everything is created inside one gsap.matchMedia() callback, so a switch to reduced motion or a breakpoint change reverts
 *    every tween, trigger and text split cleanly and the static layout (CSS without html.motion) takes over.
 *  - A scene is a <section data-scene="name">. SCENES[name](el, { desktop, fine }) builds its motion. To add a scene on another
 *    page (part 2: spa, memberships, gold, book, visit), add a function to SCENES below and the data-scene to the markup.
 *    A scene that throws is marked .scene-failed and shows its static content.
 *  - Only transform and opacity animate (plus SVG stroke drawing). Scroll-driven tweens use ease "none" (the scroll is the easing).
 *  - Home (docs/design/IMMERSIVE-R2.md, round 3): one short pin, the hero (the window shrinks onto the frame). Everywhere else frames settle
 *    (1.06 to 1), drift at different speeds (data-depth), captions lag them (data-drift), a thread draws down the margin, and the Gold swan
 *    draws as you scroll. pinnedScene() also serves The spa room walk.
 *  - The Gold Card (docs/design/GOLD-CARD-3D.md): goldCard() owns the pose proxy; the CSS card and gold-card-3d.js (lazy, capable desktops) both read it.
 *  - Markup hooks: data-rise (line rise), data-fade (fade up), data-fade-row (fade up as a group), data-caption (fade up, one each),
 *    data-count (small whole numbers), data-glow (pointer light), data-frame (settle), data-depth (frame drift), data-drift (caption lag).
 */
const { gsap, ScrollTrigger, SplitText, DrawSVGPlugin, CustomEase } = window;
const root = document.documentElement;

export const SCENES = {};
export const cleanups = [];   // teardown callbacks (matchMedia revert); scene modules on other pages (spa.js) push to it
let lenis = null;

/* ---------- patterns (8.3 to 8.9) ---------- */

/** Line rise: lines of a heading rise out of a mask (1.1s, 0.08s apart). On enter (once), or on load with trigger:false. */
export function lineRise(el, { trigger = true, delay = 0 } = {}) {
  return SplitText.create(el, {
    type: 'lines', mask: 'lines', linesClass: 'line', autoSplit: true,
    onSplit: (self) => {
      gsap.set(el, { opacity: 1 });
      // Hide the lines under their masks right now. A from() with a delay leaves them in place until the delay has run, so the heading flashed, dropped, then rose.
      gsap.set(self.lines, { yPercent: 125 });
      return gsap.fromTo(self.lines, { yPercent: 125 }, {
        yPercent: 0, stagger: 0.08, delay, immediateRender: true,
        scrollTrigger: trigger ? { trigger: el, start: 'top 80%', once: true } : undefined,
      });
    },
  });
}

/** Split once for a scrubbed swap inside a pinned timeline (no auto re-split: the timeline holds the pieces). */
function splitLines(el) {
  gsap.set(el, { opacity: 1 });
  return SplitText.create(el, { type: 'lines', mask: 'lines', linesClass: 'line' });
}

/** Fade up (opacity 0 to 1, 16px, 0.9s) once when `trigger` enters. */
export function fadeUp(targets, { trigger, start = 'top 80%', delay = 0, stagger = 0 } = {}) {
  const items = gsap.utils.toArray(targets);
  if (!items.length) return;
  gsap.fromTo(items, { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.9, delay, stagger, scrollTrigger: { trigger: trigger || items[0], start, once: true } });
}

/** Settle: the picture arrives (scale 1.06 to 1) and the lights come up (tint 0.3 to 0.14), from the frame entering to its centre. */
export function settle(frame, scrub) {
  const media = frame.querySelector('.frame-media'), tint = frame.querySelector('.frame-tint');
  gsap.timeline({ defaults: { ease: 'none' }, scrollTrigger: { trigger: frame, start: 'top bottom', end: 'center center', scrub } })
    .fromTo(media, { scale: 1.06 }, { scale: 1 }, 0)
    .fromTo(tint, { opacity: 0.3 }, { opacity: 0.14 }, 0);
}

/** Depth: a frame drifts against the page at its own speed (data-depth, percent of its height). Never on text. */
export function depth(el, scrub) {
  const amount = parseFloat(el.dataset.depth);
  gsap.fromTo(el, { yPercent: amount }, { yPercent: -amount, ease: 'none', scrollTrigger: { trigger: el.closest('.scene'), start: 'top bottom', end: 'bottom top', scrub } });
}

/** Drift: a caption lags its picture by a few pixels as the scene passes (data-drift, px, applied to its children so the fade-up on the
 *  caption itself does not fight it). Parallax depth between frame and words. */
export function drift(el, scrub) {
  const amount = parseFloat(el.dataset.drift) || 12;
  gsap.fromTo(el.children, { y: amount }, { y: -amount, ease: 'none', scrollTrigger: { trigger: el, start: 'top bottom', end: 'bottom top', scrub } });
}

/** Thread (desktop): the hairline in the left margin draws down as the scene passes. */
export function thread(scene, scrub, { start = 'top 60%', end = 'bottom 60%' } = {}) {
  const line = scene.querySelector('.thread');
  if (line) gsap.fromTo(line, { scaleY: 0 }, { scaleY: 1, ease: 'none', transformOrigin: '50% 0', scrollTrigger: { trigger: scene, start, end, scrub } });
}

/** What every Home scene shares: its frames settle and drift, the thread draws (desktop). */
function frames(el, { desktop }) {
  const scrub = desktop ? 0.4 : 0.3;
  el.querySelectorAll('[data-frame]').forEach((f) => settle(f, scrub));
  el.querySelectorAll('[data-depth]').forEach((f) => depth(f, scrub));
  el.querySelectorAll('[data-drift]').forEach((c) => drift(c, scrub));
  if (desktop) thread(el, scrub);
}

/** A pinned scene whose timeline is scrubbed. The section is pinned; .scene-stage fills it (CSS). */
export function pinnedScene(el, { segments, perSegment = 1, snap = false, scrub = 0.8 }) {
  return gsap.timeline({
    defaults: { ease: 'none' },
    scrollTrigger: {
      trigger: el, start: 'top top', end: () => '+=' + (segments - 1) * perSegment * window.innerHeight,
      pin: true, pinSpacing: true, scrub, anticipatePin: 1, invalidateOnRefresh: true,
      snap: snap ? { snapTo: 'labelsDirectional', duration: { min: 0.3, max: 0.8 }, delay: 0.08, ease: 'power1.inOut' } : false,
    },
  });
}

/** Window (8.6): the full-bleed frame shrinks into `target`, the media inside is counter-scaled so it is a pure crop (transforms only).
 *  `focus` keeps that point of the media centred in the shrinking frame. */
export function windowTo(frame, media, target, tl, at, span, focus = { x: 0.5, y: 0.5 }) {
  const p = { v: 0 };
  const radius = () => parseFloat(getComputedStyle(target).borderTopLeftRadius) || 0;   // the frame's inner-corner radius (left side of a right-bleed frame)
  const setF = gsap.quickSetter(frame, 'css'), setM = gsap.quickSetter(media, 'css');
  let m;
  const measure = () => {
    gsap.set([frame, media], { clearProps: 'transform' });
    gsap.set(frame, { clearProps: 'borderRadius' });
    const a = frame.getBoundingClientRect(), b = target.getBoundingClientRect();
    m = { sx: b.width / a.width, sy: b.height / a.height, x: b.left - a.left, y: b.top - a.top, w: a.width, h: a.height };
  };
  const apply = () => {
    if (!m) return;
    const v = p.v, sx = 1 + (m.sx - 1) * v, sy = 1 + (m.sy - 1) * v;
    const fx = 0.5 + (focus.x - 0.5) * v, fy = 0.5 + (focus.y - 0.5) * v;
    const tx = Math.min(0, Math.max(m.w * sx - m.w, (m.w * sx) / 2 - fx * m.w));
    const ty = Math.min(0, Math.max(m.h * sy - m.h, (m.h * sy) / 2 - fy * m.h));
    // The window is the clipping element, so it carries the radius. It is scaled, so the radius is divided by the scale: it lands as exactly the token radius.
    const R = radius() * v, rx = R / sx, ry = R / sy;
    setF({ x: m.x * v, y: m.y * v, scaleX: sx, scaleY: sy, transformOrigin: '0 0' });
    // Set natively: GSAP's css plugin drops the elliptical part after the "/", which left the vertical radius at rx (too round on a tall window, almost square on a wide one).
    frame.style.borderRadius = `${rx}px 0 0 ${rx}px / ${ry}px 0 0 ${ry}px`;
    setM({ x: tx / sx, y: ty / sy, scaleX: 1 / sx, scaleY: 1 / sy, transformOrigin: '0 0' });
  };
  const onInit = () => measure();
  const onRefresh = () => apply();
  ScrollTrigger.addEventListener('refreshInit', onInit);
  ScrollTrigger.addEventListener('refresh', onRefresh);
  cleanups.push(() => { ScrollTrigger.removeEventListener('refreshInit', onInit); ScrollTrigger.removeEventListener('refresh', onRefresh); });
  measure();
  tl.to(p, { v: 1, duration: span, ease: 'none', onUpdate: apply }, at);
}

/** Draw (8.7): outline paths draw (DrawSVG), the gold fill fades in, the outline fades out. T is the total length in timeline units. */
function drawSwan(svg, tl, at = 0, T = 1, ease = 'none') {
  const lines = svg.querySelectorAll('.mark-line path');
  tl.fromTo(lines, { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.4 * T, stagger: 0.1 * T, ease }, at)
    .fromTo(svg.querySelector('.mark-fill'), { opacity: 0 }, { opacity: 1, duration: 0.25 * T, ease }, at + 0.55 * T)
    .to(svg.querySelector('.mark-line'), { opacity: 0, duration: 0.2 * T, ease }, at + 0.7 * T);
}

/** Count: a small whole number counts up once when it enters. Screen readers get the real value from a hidden copy. */
function count(el) {
  const end = parseInt(el.textContent, 10);
  if (!Number.isFinite(end) || end > 99 || ScrollTrigger.isInViewport(el)) return;
  const label = el.textContent;
  const sr = Object.assign(document.createElement('span'), { className: 'sr-only', textContent: label });
  el.after(sr);
  el.setAttribute('aria-hidden', 'true');
  el.textContent = '0';
  const n = { v: 0 };
  ScrollTrigger.create({
    trigger: el, start: 'top 85%', once: true,
    onEnter: () => gsap.to(n, { v: end, duration: 1.2, snap: { v: 1 }, onUpdate: () => { el.textContent = n.v; } }),
  });
  cleanups.push(() => { el.textContent = label; el.removeAttribute('aria-hidden'); sr.remove(); });
}

/** Glow (8.9): a soft gold light follows the pointer on dark scenes (desktop, fine pointer). */
function initGlow() {
  document.querySelectorAll('[data-glow]').forEach((scene) => {
    const glow = scene.querySelector('.glow');
    if (!glow) return;
    const x = gsap.quickTo(glow, 'x', { duration: 0.8, ease: 'power3' });
    const y = gsap.quickTo(glow, 'y', { duration: 0.8, ease: 'power3' });
    const move = (e) => { const r = scene.getBoundingClientRect(); x(e.clientX - r.left); y(e.clientY - r.top); };
    const enter = () => gsap.to(glow, { opacity: 1, duration: 0.6 });
    const leave = () => gsap.to(glow, { opacity: 0, duration: 0.6 });
    scene.addEventListener('pointermove', move);
    scene.addEventListener('pointerenter', enter);
    scene.addEventListener('pointerleave', leave);
    cleanups.push(() => { scene.removeEventListener('pointermove', move); scene.removeEventListener('pointerenter', enter); scene.removeEventListener('pointerleave', leave); });
  });
}

/** Header (8.10): transparent over the first dark scene, solid after 64px. Always visible (Moishe, 2026-10-28: no hide on scroll). */
function initHeader() {
  const header = document.querySelector('.site-header');
  if (!header) return;
  ScrollTrigger.create({ start: 64, end: 'max', toggleClass: { targets: header, className: 'is-solid' } });
}

/** Lenis (2.5): desktop with a fine pointer only, behind html[data-smooth="on"]. */
function startLenis() {
  if (!window.Lenis) return;
  lenis = new window.Lenis({ lerp: 0.1, smoothWheel: true, syncTouch: false });
  lenis.on('scroll', ScrollTrigger.update);
  const tick = (t) => lenis.raf(t * 1000);
  gsap.ticker.add(tick);
  gsap.ticker.lagSmoothing(0);
  const dialogs = [...document.querySelectorAll('dialog')];
  const sync = () => (dialogs.some((d) => d.open) ? lenis?.stop() : lenis?.start());
  const mo = new MutationObserver(sync);
  dialogs.forEach((d) => mo.observe(d, { attributes: true, attributeFilter: ['open'] }));
  const anchor = (e) => {
    const a = e.target.closest('a[href^="#"]');
    const target = a && !a.classList.contains('skip-link') && a.hash.length > 1 && document.querySelector(a.hash);
    if (!target || !lenis) return;
    e.preventDefault();
    lenis.scrollTo(target, { duration: 1.2 });
  };
  document.addEventListener('click', anchor);
  cleanups.push(() => {
    mo.disconnect(); document.removeEventListener('click', anchor);
    gsap.ticker.remove(tick); lenis?.destroy(); lenis = null; gsap.ticker.lagSmoothing(500, 33);
  });
}

/* ---------- scenes ---------- */

/** R6b The Gold Card (Home) is built in gold-card.js (the CSS card, its pose and the swan), fetched when the section is within two screens.
 *  The 3D layer's gate is in gold-gl.js. Both are named by data attributes (static file URLs). */
SCENES.gold = (el, o) => {
  const src = el.querySelector('[data-gold-card]').dataset.sceneSrc;
  let dead = false, io = null;
  cleanups.push(() => { dead = true; io?.disconnect(); });
  const go = () => import(src).then((m) => { if (!dead) o.ctx.add(() => m.gold(el, o)); }).catch((e) => { console.error('scene gold', e); el.classList.add('scene-failed'); });
  if ('IntersectionObserver' in window) { io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { io.disconnect(); go(); } }, { rootMargin: '200% 0px' }); io.observe(el); } else go();
};

/** R1 Arrival (round 3): the fish tank fills the screen with the words on it; scrolling shrinks the window onto the frame on the right
 *  (short pin: +=60% desktop, +=40% phone), the first words leave and the round 2 words come in. Living still until a video exists. */
SCENES.hero = (el, { desktop }) => {
  const q = (s) => el.querySelector(s);
  const tl = pinnedScene(el, { segments: 2, perSegment: desktop ? 0.6 : 0.4, scrub: desktop ? 0.5 : 0.3 });
  tl.to({}, { duration: 1 }, 0);

  // on load
  lineRise(q('.hero-title'), { trigger: false, delay: 0.2 });
  gsap.fromTo(el.querySelectorAll('.hero-copy [data-fade]'), { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.9, delay: 0.5 });

  // on scroll: words out, window onto the frame (veil clears, corners round), round 2 words in
  const words = q('[data-hero-words]');
  tl.to(q('[data-hero-copy]'), { autoAlpha: 0, y: -32, duration: 0.3 }, 0)
    .to(q('.hero-veil'), { opacity: 0, duration: 0.5 }, 0.05)
    .to(q('.hero-window .frame-tint'), { opacity: 0.14, duration: 0.7 }, 0);
  windowTo(q('.hero-window'), q('.window-media'), q('[data-hero-target]'), tl, 0, 0.7, desktop ? { x: 0.46, y: 0.52 } : { x: 0.5, y: 0.5 });
  tl.fromTo(words, { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.01 }, 0.66)
    .fromTo(words.children, { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.26, stagger: 0.08 }, 0.66);
  if (desktop) tl.fromTo(q('.thread'), { scaleY: 0 }, { scaleY: 1, transformOrigin: '50% 0', duration: 0.3 }, 0.7);

  // the living still (one cycle per 48s), the optional video, (no Pause control: removed 2026-10-23)
  const media = q('.window-media');
  const still = q('.hero-still-wrap');
  const video = q('.hero-video');
  // With a video the poster holds still (it is the video's first frame, framed identically), so the hand-over is invisible; the still breathes only without one.
  const willPlay = !!video?.dataset.sources && !navigator.connection?.saveData;
  const loops = willPlay ? [] : [gsap.to(still, { scale: 1.03, duration: 24, yoyo: true, repeat: -1, ease: 'sine.inOut' })];
  let inView = true, playing = false;
  // The video loops by itself (v3, 2026-10-23: a 14 s file whose last 2 s cross-fade into its start, so the native loop is invisible).
  const sync = () => {
    const run = inView && !document.hidden;
    loops.forEach((t) => (run && !playing ? t.resume() : t.pause()));
    if (video && playing) (run ? video.play() : video.pause())?.catch?.(() => {});
  };
  document.addEventListener('visibilitychange', sync);
  cleanups.push(() => document.removeEventListener('visibilitychange', sync));
  ScrollTrigger.create({ trigger: el, start: 'top bottom', end: 'bottom top', onToggle: (self) => { inView = self.isActive; sync(); } });
  sync();

  const loadVideo = () => {
    if (!video?.dataset.sources || navigator.connection?.saveData) return;
    const pick = JSON.parse(video.dataset.sources).find((s) => matchMedia(s.media).matches && video.canPlayType(s.type));
    if (!pick) return;
    const show = () => { playing = true; video.classList.add('is-playing'); media.classList.add('has-video'); sync(); };
    video.addEventListener('playing', show, { once: true });
    video.src = pick.src;
    video.play().catch(() => {});
  };
  const idle = () => (window.requestIdleCallback || setTimeout)(loadVideo);
  if (document.readyState === 'complete') idle(); else window.addEventListener('load', idle, { once: true });
};

/** R2 The ritual: heading rises; three rooms settle and drift at their own speeds; captions follow as a progression. No pin, no snap. */
SCENES.ritual = (el, { desktop }) => {
  lineRise(el.querySelector('[data-rise]'));
  frames(el, { desktop });
  el.querySelectorAll('[data-caption]').forEach((c, i) => fadeUp(c, { trigger: c, start: 'top 88%', delay: desktop ? i * 0.1 : 0 }));
};

/** R3 What's inside: heading, the preview frame, facts that count once, the room index as one group. */
SCENES.inside = (el, { desktop }) => {
  lineRise(el.querySelector('[data-rise]'));
  frames(el, { desktop });
  fadeUp(el.querySelectorAll('[data-fade-row]'), { trigger: el.querySelector('.inside-index'), start: 'top 85%' });
  el.querySelectorAll('[data-count]').forEach(count);
};

/** R4 Find your membership: heading rises, the group follows, the lounge settles and drifts, the swan pattern drifts like steam. */
SCENES.entry = (el, { desktop }) => {
  const h = el.querySelector('[data-rise]');
  lineRise(h);
  fadeUp(el.querySelector('[data-fade]'), { trigger: h, start: 'top 70%' });
  frames(el, { desktop });
  el.querySelectorAll('[data-caption]').forEach((c) => fadeUp(c, { trigger: c, start: 'top 88%' }));
  gsap.to(el.querySelector('[data-pattern]'), { yPercent: -8, ease: 'none', scrollTrigger: { trigger: el, start: 'top bottom', end: 'bottom top', scrub: true } });
};

/** R5 Memberships, briefly: heading, rows as one group, small numbers count; the thread continues in caramel. */
SCENES.plans = (el, { desktop }) => {
  lineRise(el.querySelector('[data-rise]'));
  fadeUp(el.querySelectorAll('.plans-head [data-fade]'), { trigger: el.querySelector('.plans-head') });
  fadeUp(el.querySelectorAll('[data-fade-row]'), { trigger: el.querySelector('.plans-list'), start: 'top 85%', stagger: desktop ? 0.1 : 0 });
  el.querySelectorAll('[data-count]').forEach(count);
  if (desktop) thread(el, 0.4);
};

/** R7 Opening: the quiet end of the visit. */
SCENES.opening = (el) => {
  const h = el.querySelector('[data-rise]');
  lineRise(h);
  fadeUp(el.querySelectorAll('[data-fade]'), { trigger: h, start: 'top 90%', delay: 0.4, stagger: 0.12 });
};

/** Sale band (docs/design/SYSTEM-SALES.md R2.5): the name rises, then offer, countdown, ends line and button fade up once. Numbers never animate. */
SCENES.sale = (el) => {
  const name = el.querySelector('[data-rise]');
  lineRise(name);
  fadeUp(el.querySelectorAll('[data-fade]'), { trigger: name, start: 'top 80%', stagger: 0.12 });
};

/* ---------- setup (8.2) ---------- */

function boot() {
  gsap.registerPlugin(...[ScrollTrigger, SplitText, DrawSVGPlugin, CustomEase].filter(Boolean)); // DrawSVG is only loaded by pages that draw the swan
  CustomEase.create('soft', '0.22,1,0.36,1'); // = --ease-soft
  gsap.defaults({ ease: 'soft', duration: 1.1 });
  ScrollTrigger.config({ ignoreMobileResize: true }); // the address bar showing and hiding does not re-layout pins
  root.dataset.scenes = 'ready';

  const mm = gsap.matchMedia();
  mm.add({
    motion: '(prefers-reduced-motion: no-preference)',
    desktop: '(min-width: 64em)',
    fine: '(pointer: fine) and (hover: hover)',
  }, (ctx) => {
    const { motion, desktop, fine } = ctx.conditions;
    if (!motion) return;
    if (fine && root.dataset.smooth === 'on') startLenis();
    initHeader();
    if (fine) initGlow();
    document.querySelectorAll('[data-scene]').forEach((el) => {
      try { if (SCENES[el.dataset.scene]) SCENES[el.dataset.scene](el, { desktop, fine, ctx }); else el.classList.add('scene-failed'); }
      catch (error) { console.error(`scene ${el.dataset.scene}`, error); el.classList.add('scene-failed'); }
    });
    return () => { cleanups.splice(0).forEach((fn) => fn()); };
  });

  // Asking for reduced motion while the page is open: back to the static layout.
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  reduce.addEventListener('change', () => { if (reduce.matches) { root.classList.remove('motion'); ScrollTrigger.refresh(); } });
  window.addEventListener('load', () => ScrollTrigger.refresh());
  document.fonts?.ready.then(() => ScrollTrigger.refresh());
}

if (gsap && ScrollTrigger && SplitText && root.classList.contains('motion')) {
  // Scenes are built once Signika is in, so line breaks and pin positions are right the first time (capped at 1.5s).
  Promise.race([document.fonts?.ready, new Promise((resolve) => setTimeout(resolve, 1500))]).then(boot);
} else if (root.classList.contains('motion')) {
  root.classList.remove('motion'); // a vendor file failed to load: show the static layout
}
