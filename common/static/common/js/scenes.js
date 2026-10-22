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
function thread(scene, scrub, { start = 'top 60%', end = 'bottom 60%' } = {}) {
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

  // the living still (one cycle per 48s), the optional video, and the Pause control
  const media = q('.window-media');
  const still = q('.hero-still-wrap');
  const loops = [gsap.to(still, { scale: 1.03, duration: 24, yoyo: true, repeat: -1, ease: 'sine.inOut' })];
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
  ScrollTrigger.create({ trigger: el, start: 'top bottom', end: 'bottom top', onToggle: (self) => { inView = self.isActive; sync(); } });
  sync();

  const loadVideo = () => {
    if (!video?.dataset.sources || navigator.connection?.saveData) return;
    const pick = JSON.parse(video.dataset.sources).find((s) => matchMedia(s.media).matches && video.canPlayType(s.type));
    if (!pick) return;
    video.addEventListener('playing', () => { playing = true; video.classList.add('is-playing'); media.classList.add('has-video'); sync(); }, { once: true });
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

/* ---------- the Gold Card (docs/design/GOLD-CARD-3D.md) ---------- */

export const cards = new Map();                                  // mount -> pose proxy, for the three.js loader
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
function goldCard(mount, scene, { desktop, fine }) {
  const q = (sel) => mount.querySelector(sel);
  const k = desktop ? 1 : 18 / 25;
  const gc = { ry: -25 * k, rx: desktop ? 8 : 5, turn: 0, tiltX: 0, tiltY: 0, roll: 0, bob: 0, lift: 0, drop: 0, sheen: -1, draw: 0, line: 1, relief: 0, fade: 1, gl: false, k, p: 0 };
  const el = { card: q('.gc-card'), float: q('.gc-float'), shade: q('.gc-shade'), sheen: q('.gc-sheen'), pool: q('.gc-pool') };
  gc.render = () => {
    mount.style.opacity = gc.fade;
    if (gc.gl) return;
    const ry = gc.ry + gc.turn + gc.tiltY, a = ((ry % 360) + 540) % 360 - 180, n = a / (25 * k);
    el.card.style.transform = `rotateX(${gc.rx + gc.tiltX}deg) rotateY(${ry}deg)`;
    el.float.style.transform = `translate3d(0, ${gc.lift + gc.drop + gc.bob}%, 0) rotate(${gc.roll}deg)`;
    el.shade.style.opacity = n < 0 ? 0.55 * Math.min(1, -n) : 0.25 * Math.min(1, n);
    el.sheen.style.transform = `translateX(${gc.sheen * 130}%) skewX(-14deg)`;
    el.pool.style.opacity = 0.85 + 0.15 * (gc.bob / 1.6);
  };
  cards.set(mount, gc);
  cleanups.push(() => { cards.delete(mount); mount.style.opacity = ''; ['card', 'float', 'shade', 'sheen', 'pool'].forEach((n) => el[n].removeAttribute('style')); });

  // Swan: the CSS card draws with DrawSVG, the canvas reads the same moments from the proxy. windows are [from, to] in timeline units.
  gc.swan = (tl, { draw, relief, line }, ease) => {
    const svg = q('.mark-draw'), W = draw[1] - draw[0];
    const shadow = q('.gc-swan-shadow');
    tl.fromTo(svg.querySelectorAll('.mark-line path'), { drawSVG: '0%' }, { drawSVG: '100%', duration: (W * 0.4) / 0.7, stagger: (W * 0.1) / 0.7, ease }, draw[0])
      .fromTo(gc, { draw: 0 }, { draw: 1, duration: W, ease }, draw[0])
      .fromTo(svg.querySelector('.mark-fill'), { opacity: 0 }, { opacity: 1, duration: relief[1] - relief[0], ease }, relief[0])
      .fromTo(shadow, { opacity: 0 }, { opacity: 0.5, duration: relief[1] - relief[0], ease }, relief[0])
      .fromTo(gc, { relief: 0 }, { relief: 1, duration: relief[1] - relief[0], ease }, relief[0])
      .fromTo(svg.querySelector('.mark-line'), { opacity: 1 }, { opacity: 0, duration: line[1] - line[0], ease }, line[0])
      .fromTo(gc, { line: 1 }, { line: 0, duration: line[1] - line[0], ease }, line[0]);
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
  return gc;
}

/** R6b The Gold Card (Home): no pin. The card swings -25 to +25 degrees as the section passes; the swan draws itself on its face (shaded, line),
 *  becomes raised metal, a band of light crosses it with the card square to you, the edge catches the light as it leaves. */
SCENES.gold = (el, { desktop, fine }) => {
  const scrub = desktop ? 0.5 : 0.3;
  if (desktop) thread(el, 0.4, { start: 'top 90%', end: 'top 55%' });
  const gc = goldCard(el.querySelector('[data-gold-card]'), el, { desktop, fine });
  const tl = gsap.timeline({ defaults: { ease: 'none' }, scrollTrigger: { trigger: el, start: 'top 85%', end: 'bottom 15%', scrub } });
  tl.to(gc, { p: 1, duration: 1, onUpdate: () => { gc.ry = HOME_RY(gc.p) * gc.k; gc.rx = gc.k === 1 ? HOME_RX(gc.p) : 5 + (HOME_RX(gc.p) - 8) * (9 / 14); gc.sheen = HOME_SHEEN(gc.p); gc.render(); } }, 0);
  gc.swan(tl, { draw: [0.05, 0.3], relief: [0.3, 0.42], line: [0.36, 0.45] }, 'none');
  const h = el.querySelector('[data-rise]');
  lineRise(h);
  fadeUp(el.querySelectorAll('.gold-text > [data-fade]'), { trigger: h, start: 'top 75%', delay: 0.3, stagger: 0.15 });
  fadeUp(el.querySelectorAll('[data-pill]'), { trigger: el.querySelector('.pills'), start: 'top 90%', delay: 0.2, stagger: 0.06 });
};

/** G1 The Gold Card page hero: on load the card fades in at -25 degrees, the line draws, becomes metal, one sheen crosses it as it settles at -12.
 *  On scroll a slow half turn (-12 to +168) shows the back as the hero leaves. */
SCENES['gold-hero'] = (el, { desktop, fine }) => {
  const mount = el.querySelector('[data-gold-card]');
  const gc = goldCard(mount, el, { desktop, fine });
  gc.fade = 0; gc.lift = 4; gc.render();
  const soft = 'soft', k = gc.k;
  const tl = gsap.timeline({ defaults: { ease: soft }, onUpdate: gc.render });
  tl.to(gc, { fade: 1, lift: 0, duration: 1.2 }, 0);
  gc.swan(tl, { draw: [0.3, 2.7], relief: [2.4, 3], line: [2.4, 3] }, soft);
  tl.to(gc, { ry: -12 * k, rx: desktop ? 3 : 1, duration: 1.6 }, 3)
    .fromTo(gc, { sheen: -1 }, { sheen: 0.05, duration: 0.9 }, 3)
    .to(gc, { sheen: -0.35, duration: 0.7 }, 3.9);
  // The half turn runs over the first 45% of the hero's scroll while the card drifts up 35% slower than the page: the back is fully on screen (under the header, clear of the next section) when it arrives.
  const dropEnd = () => (0.35 * 0.45 * el.offsetHeight) / mount.offsetHeight * 100;
  const turn = gsap.timeline({ defaults: { ease: 'none' }, onUpdate: gc.render, scrollTrigger: { trigger: el, start: 'top top', end: () => '+=' + 0.45 * el.offsetHeight, scrub: desktop ? 0.5 : 0.3, invalidateOnRefresh: true } });
  turn.fromTo(gc, { turn: 0 }, { turn: 180, duration: 1 }, 0)
    .fromTo(gc, { drop: 0 }, { drop: dropEnd, duration: 1 }, 0);
  lineRise(el.querySelector('[data-rise]'), { trigger: false, delay: 0.4 });
  gsap.fromTo(el.querySelectorAll('.gold-hero-text [data-fade]'), { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.9, delay: 0.9, stagger: 0.12 });
};

/** R7 Opening: the quiet end of the visit. */
SCENES.opening = (el) => {
  const h = el.querySelector('[data-rise]');
  lineRise(h);
  fadeUp(el.querySelectorAll('[data-fade]'), { trigger: h, start: 'top 90%', delay: 0.4, stagger: 0.12 });
};

/* ---------- three.js (IMMERSIVE 14.0 and 14.3): a layer on top of the CSS card, never a replacement ---------- */

/** One synchronous gate: large screen, motion allowed, no Save-Data, a real GPU with WebGL2. Phones and tablets never pass. */
function webglGate() {
  if (root.dataset.webgl === 'off') return false;
  if (!matchMedia('(min-width: 64em)').matches || matchMedia('(prefers-reduced-motion: reduce)').matches) return false;
  if (navigator.connection?.saveData || matchMedia('(prefers-reduced-data: reduce)').matches) return false;
  if ((navigator.deviceMemory ?? 8) < 4 || (navigator.hardwareConcurrency ?? 8) < 4) return false;
  const gl = document.createElement('canvas').getContext('webgl2', { failIfMajorPerformanceCaveat: true });
  if (!gl) return false;
  gl.getExtension('WEBGL_lose_context')?.loseContext();
  return true;
}
const tokens = (name) => getComputedStyle(root).getPropertyValue(name).trim();

/** Load gold-card-3d.js after `load` + idle, and (Home) only when the mount is within two screens. Returns nothing; teardown goes to cleanups. */
function loadCards(ctx) {
  if (!ctx.conditions.desktop || !cards.size || !webglGate()) return;
  cards.forEach((gc, mount) => {
    let inst = null, dead = false, io = null;
    const go = () => import(mount.dataset.webglSrc)
      .then((m) => { if (!dead) ctx.add(() => { inst = m.create(mount, { gsap, ScrollTrigger, tokens, card: gc }); inst.ready.catch((e) => { console.error('gold card 3d', e); inst.dispose(); }); }); })
      .catch((e) => console.error('gold card 3d', e));
    const near = () => {
      if (mount.dataset.goldCard === 'hero' || !('IntersectionObserver' in window)) return go();
      io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { io.disconnect(); go(); } }, { rootMargin: '200% 0px' });
      io.observe(mount);
    };
    const start = () => (window.requestIdleCallback || setTimeout)(() => { if (!dead) near(); }, { timeout: 2000 });
    if (document.readyState === 'complete') start(); else window.addEventListener('load', start, { once: true });
    cleanups.push(() => { dead = true; io?.disconnect(); inst?.dispose(); inst = null; });
  });
}

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
      try { if (SCENES[el.dataset.scene]) SCENES[el.dataset.scene](el, { desktop, fine }); else el.classList.add('scene-failed'); }
      catch (error) { console.error(`scene ${el.dataset.scene}`, error); el.classList.add('scene-failed'); }
    });
    loadCards(ctx);
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
