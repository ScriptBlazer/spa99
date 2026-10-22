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
 *  - Markup hooks: data-rise (line rise), data-fade (fade up), data-fade-row (fade up as a group), data-words (word light),
 *    data-count (small whole numbers), data-glow (pointer light), .scene-item / data-label (pinned sequences).
 */
const { gsap, ScrollTrigger, SplitText, DrawSVGPlugin, CustomEase } = window;
const root = document.documentElement;

export const SCENES = {};
const cleanups = [];
let lenis = null;

/* ---------- patterns (8.3 to 8.9) ---------- */

/** Line rise: lines of a heading rise out of a mask (1.1s, 0.08s apart). On enter (once), or on load with trigger:false. */
function lineRise(el, { trigger = true, delay = 0 } = {}) {
  return SplitText.create(el, {
    type: 'lines', mask: 'lines', linesClass: 'line', autoSplit: true,
    onSplit: (self) => {
      gsap.set(el, { opacity: 1 });
      return gsap.from(self.lines, {
        yPercent: 105, stagger: 0.08, delay,
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

/** Word light: words go from 0.15 to 1 opacity across a span of the pinned timeline. */
function wordLight(el, tl, at, span) {
  gsap.set(el, { opacity: 1 });
  const split = SplitText.create(el, { type: 'words' });
  tl.fromTo(split.words, { opacity: 0.15 }, { opacity: 1, ease: 'none', stagger: span / split.words.length, duration: span / 4 }, at);
}

/** Fade up (opacity 0 to 1, 16px, 0.9s) once when `trigger` enters. */
function fadeUp(targets, { trigger, start = 'top 80%', delay = 0, stagger = 0 } = {}) {
  const items = gsap.utils.toArray(targets);
  if (!items.length) return;
  gsap.fromTo(items, { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.9, delay, stagger, scrollTrigger: { trigger: trigger || items[0], start, once: true } });
}

/** A pinned scene whose timeline is scrubbed. The section is pinned; .scene-stage fills it (CSS). */
function pinnedScene(el, { segments, perSegment = 1, snap = false, scrub = 0.8 }) {
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
function windowTo(frame, media, target, tl, at, span, focus = { x: 0.5, y: 0.5 }) {
  const p = { v: 0 };
  const setF = gsap.quickSetter(frame, 'css'), setM = gsap.quickSetter(media, 'css');
  let m;
  const measure = () => {
    gsap.set([frame, media], { clearProps: 'transform' });
    const a = frame.getBoundingClientRect(), b = target.getBoundingClientRect();
    m = { sx: b.width / a.width, sy: b.height / a.height, x: b.left - a.left, y: b.top - a.top, w: a.width, h: a.height };
  };
  const apply = () => {
    if (!m) return;
    const v = p.v, sx = 1 + (m.sx - 1) * v, sy = 1 + (m.sy - 1) * v;
    const fx = 0.5 + (focus.x - 0.5) * v, fy = 0.5 + (focus.y - 0.5) * v;
    const tx = Math.min(0, Math.max(m.w * sx - m.w, (m.w * sx) / 2 - fx * m.w));
    const ty = Math.min(0, Math.max(m.h * sy - m.h, (m.h * sy) / 2 - fy * m.h));
    setF({ x: m.x * v, y: m.y * v, scaleX: sx, scaleY: sy, transformOrigin: '0 0' });
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

/** Header (8.10): transparent over the first dark scene, solid after 64px, hidden on scroll down past the first screen. */
function initHeader() {
  const header = document.querySelector('.site-header');
  if (!header) return;
  const show = () => gsap.to(header, { yPercent: 0, duration: 0.45, overwrite: true });
  ScrollTrigger.create({ start: 64, end: 'max', toggleClass: { targets: header, className: 'is-solid' } });
  let last = 0;
  ScrollTrigger.create({
    start: () => window.innerHeight, end: 'max', onLeaveBack: show,
    onUpdate: (self) => {
      const y = self.scroll(), delta = y - last;
      if (Math.abs(delta) < 8) return;
      last = y;
      if (header.contains(document.activeElement) || document.querySelector('[data-menu][open]')) return show();
      gsap.to(header, { yPercent: delta > 0 ? -100 : 0, duration: 0.45, overwrite: true });
    },
  });
  cleanups.push(() => gsap.set(header, { clearProps: 'transform' }));
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

/** H1 Arrival: load reveal, then the window shrinks, the statement lights word by word. Living still until a video exists (8.11). */
SCENES.hero = (el, { desktop }) => {
  const q = (s) => el.querySelector(s);
  const tl = pinnedScene(el, { segments: 2, perSegment: desktop ? 0.9 : 0.7, scrub: desktop ? 0.8 : 0.5 });
  tl.to({}, { duration: 1 }, 0);

  // on load
  lineRise(q('.hero-title'), { trigger: false, delay: 0.2 });
  gsap.fromTo(el.querySelectorAll('.hero-copy [data-fade]'), { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.9, delay: 0.5 });

  // on scroll
  tl.to(q('[data-hero-copy]'), { autoAlpha: 0, y: -32, duration: 0.3 }, 0)
    .to(q('.hero-stage .veil'), { opacity: 0.4, duration: 0.3 }, 0)
    .to(q('.hero-stage .veil'), { opacity: 0, duration: 0.45 }, 0.3)
    .fromTo(q('.hero-zoom'), { scale: 1 }, { scale: 1.08, duration: 0.75 }, 0);
  windowTo(q('.window'), q('.window-media'), q('[data-window-target]'), tl, 0, 0.75, { x: 0.62, y: 0.5 });
  const statement = q('[data-statement]');
  tl.fromTo(statement, { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.05 }, 0.35);
  wordLight(q('[data-words]'), tl, 0.35, 0.5);
  if (desktop) tl.fromTo(statement.querySelector('[data-fade]'), { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.2 }, 0.8);

  // the living still and the steam loop (one cycle per 48s and 60s), the optional video, and the Pause control
  const loops = [];
  const wrap = q('.hero-still-wrap'), steam = q('.hero-steam'), zoom = q('.hero-zoom');
  loops.push(gsap.to(wrap, { scale: 1.06, duration: 24, yoyo: true, repeat: -1, ease: 'sine.inOut' }));
  if (steam) loops.push(gsap.fromTo(steam, { xPercent: -6 }, { xPercent: 6, duration: 30, yoyo: true, repeat: -1, ease: 'sine.inOut' }));
  const video = q('.hero-video');
  const button = q('[data-hero-pause]');
  let userPaused = sessionStorage.getItem('spa99-hero-paused') === '1', inView = true, playing = false;
  const sync = () => {
    const run = inView && !userPaused && !document.hidden;
    loops.forEach((t) => (run && !playing ? t.resume() : t.pause()));
    if (video && playing) (run ? video.play() : video.pause())?.catch?.(() => {});
  };
  const label = () => { button.textContent = userPaused ? 'Play' : 'Pause'; button.setAttribute('aria-pressed', String(userPaused)); };
  button.addEventListener('click', () => { userPaused = !userPaused; sessionStorage.setItem('spa99-hero-paused', userPaused ? '1' : '0'); label(); sync(); });
  label();
  document.addEventListener('visibilitychange', sync);
  cleanups.push(() => document.removeEventListener('visibilitychange', sync));
  ScrollTrigger.create({ start: 0, end: () => tl.scrollTrigger.end, onToggle: (self) => { inView = self.isActive; sync(); } });
  sync();

  const loadVideo = () => {
    if (!video?.dataset.sources || navigator.connection?.saveData) return;
    const pick = JSON.parse(video.dataset.sources).find((s) => matchMedia(s.media).matches && video.canPlayType(s.type));
    if (!pick) return;
    video.addEventListener('playing', () => { playing = true; video.classList.add('is-playing'); zoom.classList.add('has-video'); sync(); }, { once: true });
    video.src = pick.src;
    video.play().catch(() => {});
  };
  const idle = () => (window.requestIdleCallback || setTimeout)(loadVideo);
  if (document.readyState === 'complete') idle(); else window.addEventListener('load', idle, { once: true });
};

/** H2 The ritual: heat, cold, rest. Cross-fade, settle, caption swap and a three-segment hairline, all on one pinned timeline. */
SCENES.ritual = (el, { desktop }) => {
  const items = gsap.utils.toArray('.scene-item', el);
  const bars = gsap.utils.toArray('.ritual-progress b', el);
  const tl = pinnedScene(el, { segments: items.length, perSegment: 1, scrub: desktop ? 0.8 : 0.5, snap: desktop });
  gsap.set(items.slice(1), { autoAlpha: 0 });
  items.forEach((item, i) => {
    const last = i === items.length - 1;
    const split = splitLines(item.querySelector('.scene-caption'));
    tl.addLabel(item.dataset.label, i);
    if (i > 0) tl.to(item, { autoAlpha: 1, duration: 0.35 }, i - 0.35).set(items[i - 1], { autoAlpha: 0 }, i);
    tl.fromTo(item.querySelector('.scene-media'), { scale: 1.12 }, { scale: 1, duration: 1 }, Math.max(0, i - 0.35));
    if (bars[i]) tl.fromTo(bars[i], { scaleX: 0 }, { scaleX: 1, duration: 1 }, Math.max(0, i - 0.35));
    if (i === 0) {
      gsap.from(split.lines, { yPercent: 105, stagger: 0.08, scrollTrigger: { trigger: el, start: 'top 70%', once: true } });
    } else {
      tl.fromTo(split.lines, { yPercent: 105 }, { yPercent: 0, duration: 0.3 }, i - 0.3);
    }
    if (!last) tl.to(split.lines, { yPercent: -105, duration: 0.2 }, i + 0.45);
    const link = item.querySelector('.btn-quiet');
    if (link) tl.fromTo(link, { opacity: 0 }, { opacity: 1, duration: 0.35 }, i - 0.35);
  });
  tl.to({}, { duration: 0.35 });
  const onLoad = () => ScrollTrigger.refresh();
  if (document.readyState !== 'complete') window.addEventListener('load', onLoad, { once: true });
};

/** H3 Find your membership: heading rises, the group follows, the swan pattern drifts like steam. */
SCENES.entry = (el) => {
  const h = el.querySelector('[data-rise]');
  lineRise(h);
  fadeUp(el.querySelector('[data-fade]'), { trigger: h, start: 'top 70%' });
  gsap.to(el.querySelector('[data-pattern]'), { yPercent: -8, ease: 'none', scrollTrigger: { trigger: el, start: 'top bottom', end: 'bottom top', scrub: true } });
};

/** H4 Memberships, briefly: heading, rows as a progression (stagger on desktop), small numbers count. */
SCENES.plans = (el, { desktop }) => {
  lineRise(el.querySelector('[data-rise]'));
  fadeUp(el.querySelectorAll('.plans-head [data-fade]'), { trigger: el.querySelector('.plans-head') });
  fadeUp(el.querySelectorAll('[data-fade-row]'), { trigger: el.querySelector('.plans-list'), start: 'top 85%', stagger: desktop ? 0.1 : 0 });
  el.querySelectorAll('[data-count]').forEach(count);
};

/** H5 The Gold Card: the swan draws itself across the pin, then the words. */
SCENES.gold = (el, { desktop }) => {
  const tl = pinnedScene(el, { segments: 2, perSegment: desktop ? 0.6 : 0.4, scrub: desktop ? 0.8 : 0.5 });
  tl.to({}, { duration: 1 }, 0);
  drawSwan(el.querySelector('.mark-draw'), tl, 0, 0.9);
  const split = splitLines(el.querySelector('[data-rise]'));
  tl.fromTo(split.lines, { yPercent: 105 }, { yPercent: 0, duration: 0.25 }, 0.5)
    .fromTo(el.querySelectorAll('[data-fade]'), { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.2 }, 0.7);
};

/** H6 Opening: the quiet end of the visit. */
SCENES.opening = (el) => {
  const h = el.querySelector('[data-rise]');
  lineRise(h);
  fadeUp(el.querySelectorAll('[data-fade]'), { trigger: h, delay: 0.5, stagger: 0.15 });
};

/* ---------- setup (8.2) ---------- */

function boot() {
  gsap.registerPlugin(ScrollTrigger, SplitText, DrawSVGPlugin, CustomEase);
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
      try { SCENES[el.dataset.scene]?.(el, { desktop, fine }); }
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
