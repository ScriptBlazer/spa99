/* The spa page scenes (docs/design/SPA-PAGE.md, with the 2026-10-22 decisions: the door shrinks onto its frame inside a short pin, the same method as Home's arrival).
 * Loaded only by spa.html, after the vendored GSAP, ScrollTrigger, SplitText and CustomEase. scenes.js (imported) owns the registry,
 * the matchMedia setup, the header and the shared patterns; this file adds the scenes of this page so Home's script stays as small as it was.
 * Same rules as scenes.js: transform and opacity only, scroll-driven tweens use ease "none", a scene that throws shows its static content.
 *   door   S1: the full-screen door shrinks onto .door-target inside a short pin (windowTo), facts and chips arrive, "8" counts once
 *   feature S2a/c/d: name rises, line and pills fade up, hairline draws (scrubbed), frame settles and drifts, inset and thumbnail travel more
 *   tiles  S2b: intro, staggered tiles settle at their own depth (desktop only), captions lag
 *   steps  S3: the line draws through the three steps (scrubbed), numbers come up as it reaches them
 *   band   S4: heading, line, buttons, the swan pattern drifts
 * Hooks: data-door-window / data-door-media / data-door-target / data-door-pause, data-rule, data-step, data-steps, data-walk (the future room walk).
 */
import { SCENES, cleanups, lineRise, fadeUp, settle, depth, drift, windowTo, pinnedScene } from './scenes.js';

const { gsap, ScrollTrigger } = window;

if (gsap && ScrollTrigger) {
  /** A small whole number that counts up once when cued (the cue is a scroll position, not "in view": the number sits in view before it appears). */
  const countCue = (el) => {
    const end = parseInt(el.textContent, 10);
    if (!Number.isFinite(end) || end > 99) return () => {};
    const label = el.textContent;
    const sr = Object.assign(document.createElement('span'), { className: 'sr-only', textContent: label });
    el.after(sr);
    el.setAttribute('aria-hidden', 'true');
    el.textContent = '0';
    cleanups.push(() => { el.textContent = label; el.removeAttribute('aria-hidden'); sr.remove(); });
    let done = false;
    return () => {
      if (done) return;
      done = true;
      const n = { v: 0 };
      gsap.to(n, { v: end, duration: 1.2, snap: { v: 1 }, onUpdate: () => { el.textContent = n.v; } });
    };
  };

  /** Frames of a scene: settle for all, depth for those that travel (data-depth > 0), caption drift. */
  const frames = (el, { scrub, travel = true }) => {
    el.querySelectorAll('[data-frame]').forEach((f) => settle(f, scrub));
    if (travel) {
      el.querySelectorAll('[data-depth]').forEach((f) => { if (parseFloat(f.dataset.depth)) depth(f, scrub); });
      el.querySelectorAll('[data-drift]').forEach((c) => drift(c, scrub));
    }
  };

  /** The words of one room: name rises, line and description fade up with it, the pills follow (0.06s apart on desktop, one group on phone). */
  const roomWords = (box, desktop) => {
    const name = box.querySelector('[data-rise]');
    if (name) lineRise(name);
    fadeUp(box.querySelectorAll('[data-fade]'), { trigger: name || box, start: 'top 80%', delay: 0.15, stagger: 0.1 });
    const pills = box.querySelectorAll('[data-pill]');
    if (pills.length) fadeUp(pills, { trigger: pills[0].parentElement, start: 'top 90%', delay: 0.2, stagger: desktop ? 0.06 : 0 });
  };

  /* ---------- S1 the door ---------- */
  SCENES.door = (el, { desktop }) => {
    const q = (s) => el.querySelector(s);
    // Same method as Home's arrival: a short pin (+=50% desktop, +=35% phone of a screen) with the same scrub, so the picture never also moves with the page while it shrinks.
    const per = desktop ? 0.5 : 0.35;
    const tl = pinnedScene(el, { segments: 2, perSegment: per, scrub: desktop ? 0.5 : 0.3 });
    tl.to({}, { duration: 1 }, 0);

    // on load: the words come in (the picture fades in from espresso in CSS)
    lineRise(q('.door-title'), { trigger: false, delay: 0.2 });
    gsap.fromTo(q('.door-lead'), { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.9, delay: 0.5 });

    // on scroll: the window shrinks onto the frame; the veil clears once the picture has left the words; the lights come up
    tl.to(q('.door-window .hero-veil'), { opacity: 0, duration: 0.25 }, 0.45)
      .to(q('.door-window .frame-tint'), { opacity: 0.14, duration: 0.25 }, 0.45);
    const focus = desktop ? { x: 0.53, y: 0.5 } : { x: 0.51, y: 0.44 };
    windowTo(q('[data-door-window]'), q('[data-door-media]'), q('[data-door-target]'), tl, 0, 0.7, focus);
    // the picture eases back around the swan while the window shrinks (a pure crop would show only a part of it in the frame)
    tl.fromTo(q('.door-zoom'), { scale: 1, transformOrigin: `${focus.x * 100}% ${focus.y * 100}%` }, { scale: desktop ? 0.68 : 0.66, duration: 0.7 }, 0);

    // the facts and the room chips arrive in the last third; "8" counts once
    const play = countCue(q('[data-count]') || document.createElement('i'));
    tl.fromTo(q('.door-facts'), { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.3 }, 0.66)
      .fromTo(q('.door-chips'), { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.28 }, 0.72);
    tl.call(play, null, 0.66);

    // the living still (one cycle per 48s) and its Pause control (the choice is remembered with Home's)
    const loop = gsap.to(q('.door-still'), { scale: 1.03, duration: 24, yoyo: true, repeat: -1, ease: 'sine.inOut' });
    const button = q('[data-door-pause]');
    let userPaused = sessionStorage.getItem('spa99-hero-paused') === '1', inView = true;
    let shrunk = false;   // the living still only runs while the door is the full-screen picture, so the Pause control is only needed then
    const sync = () => (inView && !shrunk && !userPaused && !document.hidden ? loop.resume() : loop.pause());
    const label = () => { button.textContent = userPaused ? 'Play' : 'Pause'; button.setAttribute('aria-pressed', String(userPaused)); };
    const toggle = () => { userPaused = !userPaused; sessionStorage.setItem('spa99-hero-paused', userPaused ? '1' : '0'); label(); sync(); };
    button.addEventListener('click', toggle);
    document.addEventListener('visibilitychange', sync);
    cleanups.push(() => { button.removeEventListener('click', toggle); document.removeEventListener('visibilitychange', sync); });
    ScrollTrigger.create({ trigger: el, start: 'top bottom', end: 'bottom top', onToggle: (self) => { inView = self.isActive; sync(); } });
    tl.to(button, { autoAlpha: 0, duration: 0.2 }, 0.05);
    ScrollTrigger.create({ trigger: el, start: 'top top', end: () => '+=' + Math.max(1, per * window.innerHeight), onUpdate: (self) => { const next = self.progress > 0.7; if (next !== shrunk) { shrunk = next; sync(); } } });
    label();
    sync();
  };

  /* ---------- S2 rooms ---------- */
  SCENES.feature = (el, { desktop }) => {
    const scrub = desktop ? 0.4 : 0.3;
    frames(el, { scrub });
    el.querySelectorAll('.sp-copy, .sp-companion-copy').forEach((box) => roomWords(box, desktop));
    // the gold hairline above the name draws as the room arrives (scrubbed)
    gsap.fromTo(el.querySelector('[data-rule]'), { scaleX: 0 }, { scaleX: 1, ease: 'none', transformOrigin: '0 50%', scrollTrigger: { trigger: el, start: 'top 85%', end: 'top 55%', scrub } });
  };

  SCENES.tiles = (el, { desktop }) => {
    const scrub = desktop ? 0.4 : 0.3;
    const intro = el.querySelector('.sp-tiles-intro');
    if (intro) {
      lineRise(intro.querySelector('[data-rise]'));
      fadeUp(intro.querySelectorAll('[data-fade]'), { trigger: intro, start: 'top 80%', delay: 0.2 });
    }
    frames(el, { scrub, travel: desktop });   // phone: settle only, depth would fight the sideways swipe
    el.querySelectorAll('[data-caption]').forEach((c, i) => fadeUp(c, { trigger: c, start: 'top 90%', delay: desktop ? i * 0.1 : 0 }));
  };

  /* ---------- S3 how a visit works ---------- */
  SCENES.steps = (el, { desktop }) => {
    const scrub = desktop ? 0.4 : 0.3;
    lineRise(el.querySelector('[data-rise]'));
    frames(el, { scrub });
    const steps = [...el.querySelectorAll('[data-step]')];
    steps.forEach((s) => fadeUp(s, { trigger: s, start: 'top 85%' }));
    fadeUp(el.querySelectorAll('.sp-hours'), { trigger: el.querySelector('.sp-hours') || el, start: 'top 90%' });
    // the line draws through the steps; each number comes up (opacity only) as the line reaches it
    const seg = 1 / Math.max(1, steps.length - 1);
    const tl = gsap.timeline({ defaults: { ease: 'none' }, scrollTrigger: { trigger: el.querySelector('[data-steps]'), start: 'top 70%', end: 'bottom 60%', scrub } });
    steps.forEach((s, i) => {
      tl.fromTo(s.querySelector('.vstep-num'), { opacity: 0.4 }, { opacity: 1, duration: 0.1 * seg }, i * seg);
      const line = s.querySelector('.vstep-line');
      if (line) tl.fromTo(line, { scaleY: 0 }, { scaleY: 1, duration: 0.9 * seg, transformOrigin: '50% 0' }, i * seg + 0.05 * seg);
    });
  };

  /* ---------- S4 next ---------- */
  SCENES.band = (el) => {
    const h = el.querySelector('[data-rise]');
    lineRise(h);
    fadeUp(el.querySelectorAll('[data-fade]'), { trigger: h, start: 'top 90%', delay: 0.3, stagger: 0.12 });
    gsap.to(el.querySelector('[data-pattern]'), { yPercent: -8, ease: 'none', scrollTrigger: { trigger: el, start: 'top bottom', end: 'bottom top', scrub: true } });
  };
}
