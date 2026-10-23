/* The spa page scenes (docs/design/SPA-PAGE.md, with the 2026-10-22 decisions: the door shrinks onto its frame inside a short pin, the same method as Home's arrival).
 * Loaded only by spa.html, after the vendored GSAP, ScrollTrigger, SplitText and CustomEase. scenes.js (imported) owns the registry,
 * the matchMedia setup, the header and the shared patterns; this file adds the scenes of this page so Home's script stays as small as it was.
 * Same rules as scenes.js: transform and opacity only, scroll-driven tweens use ease "none", a scene that throws shows its static content.
 *   door   S1 the opener (docs/design/SPA-OPENER.md): the full-screen picture (the robe, or the door) shrinks onto .door-target inside a short pin
 *          (windowTo, Home's method), four lines fade one into the next as it goes (text never moves), the chips arrive at the end
 *   moment AMENITIES.md M1 to M3: a full-bleed band (the picture travels a little and settles) or the overlapping pair of mounts; words rise or fade
 *   feature S2a/c/d: name rises, line and pills fade up, hairline draws (scrubbed), frame settles and drifts, inset and thumbnail travel more
 *   tiles  S2b: intro, staggered tiles settle at their own depth (desktop only), captions lag
 *   steps  S3: the line draws through the three steps (scrubbed), numbers come up as it reaches them
 *   band   S4: heading, line, buttons, the tote mount settles, the swan pattern drifts
 * Hooks: data-door-window / data-door-media / data-door-target, data-opener-line / data-opener-tick, data-band, data-rule, data-step, data-steps, data-walk (the future room walk).
 */
import { SCENES, cleanups, lineRise, fadeUp, settle, depth, drift, windowTo, pinnedScene } from './scenes.js';

const { gsap, ScrollTrigger } = window;

if (gsap && ScrollTrigger) {
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

  /** AMENITIES.md M1/M3: the picture of a band travels a little against the page (transform only, scrubbed). Desktop only. */
  const bandTravel = (band, scrub) => {
    gsap.fromTo(band.querySelector('.frame-media'), { yPercent: -4 }, { yPercent: 4, ease: 'none', scrollTrigger: { trigger: band, start: 'top bottom', end: 'bottom top', scrub } });
  };

  /* ---------- S1 the opener ---------- */
  // Where the shrinking window centres the picture, per picture (x, y as a share of the screen): the robe sits right of centre, the door a little more; the old zoomed door keeps its ease-back.
  const OPENER_FOCUS = {
    robe: { desktop: { x: 0.73, y: 0.47 }, phone: { x: 0.5, y: 0.32 } },   // 16:9 robe (2026-10-23): the robe sits at 58 to 87% across
    door: { desktop: { x: 0.62, y: 0.5 }, phone: { x: 0.58, y: 0.45 } },
    'door-gold': { desktop: { x: 0.53, y: 0.5 }, phone: { x: 0.51, y: 0.44 } },
  };

  SCENES.door = (el, { desktop }) => {
    const q = (s) => el.querySelector(s);
    const mode = el.dataset.opener in OPENER_FOCUS ? el.dataset.opener : 'robe';
    // Same method as Home's arrival, a little longer because four lines read inside it: the length in screens is the token --opener-pin (0.8 desktop, 0.6 phone).
    const per = parseFloat(getComputedStyle(el).getPropertyValue('--opener-pin')) || (desktop ? 0.8 : 0.6);
    const tl = pinnedScene(el, { segments: 2, perSegment: per, scrub: desktop ? 0.5 : 0.3 });
    tl.to({}, { duration: 1 }, 0);

    // on load: the heading rises, then line 1 and the ticks come up as one group (the picture fades in from espresso in CSS)
    lineRise(q('.door-title'), { trigger: false, delay: 0.2 });
    const lines = [...el.querySelectorAll('[data-opener-line]')], ticks = [...el.querySelectorAll('[data-opener-tick]')];
    const first = [...(lines[0]?.children || []), q('.opener-ticks')].filter(Boolean);
    if (first.length) gsap.fromTo(first, { opacity: 0, y: desktop ? 12 : 8 }, { opacity: 1, y: 0, duration: 0.8, delay: 0.6 });

    // on scroll: the window shrinks onto the frame (0.15 to 0.85); the veil holds, then clears once the picture has left the words; the lights come up
    const focus = OPENER_FOCUS[mode][desktop ? 'desktop' : 'phone'];
    windowTo(q('[data-door-window]'), q('[data-door-media]'), q('[data-door-target]'), tl, 0.15, 0.7, focus);
    tl.to(q('.door-window .hero-veil'), { opacity: 0, duration: 0.25 }, 0.55)
      .to(q('.door-window .frame-tint'), { opacity: 0.14, duration: 0.15 }, 0.7);
    // only the old zoomed-in door eases back around the swan while the window shrinks; the robe and the wide door are already composed
    if (mode === 'door-gold') tl.fromTo(q('.door-zoom'), { scale: 1, transformOrigin: `${focus.x * 100}% ${focus.y * 100}%` }, { scale: desktop ? 0.68 : 0.66, duration: 0.7 }, 0.15);

    // the lines: each one fades out, the next fades in a beat later (never both legible), the ticks follow. Text and ticks only change opacity.
    // With N lines the changes are spread evenly over 0.14 to 0.68 (SPA-OPENER 5.2); two lines fade over 0.02 of each other at most.
    const N = lines.length;
    if (N > 1) {
      const step = N > 2 ? (0.68 - 0.14 - 0.1) / (N - 2) : 0;
      for (let k = 0; k < N - 1; k++) {
        const at = 0.14 + k * step;
        tl.fromTo(lines[k + 1], { opacity: 0 }, { opacity: 1, duration: 0.06 }, at + 0.04)
          .fromTo(lines[k], { opacity: 1 }, { opacity: 0, duration: 0.06, immediateRender: false }, at);
        if (ticks.length === N) {
          tl.fromTo(ticks[k + 1], { opacity: 0.3 }, { opacity: 1, duration: 0.06 }, at + 0.04)
            .fromTo(ticks[k], { opacity: 1 }, { opacity: 0.3, duration: 0.06, immediateRender: false }, at);
        }
      }
    }

    // the room chips arrive in the last fifth
    tl.fromTo(q('.door-chips'), { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.2 }, 0.8);

    // the living still (one cycle per 48s), the optional door video
    const still = q('.door-still'), media = q('[data-door-media]'), video = q('.door-video');
    const loops = [gsap.to(still, { scale: 1.03, duration: 24, yoyo: true, repeat: -1, ease: 'sine.inOut' })];
    let inView = true, playing = false, shrunk = false;
    const sync = () => {
      // once the picture has shrunk (15% of the pin) nothing keeps moving: the loop and the video stop
      const run = inView && !document.hidden && !shrunk;
      loops.forEach((t) => (run && !playing ? t.resume() : t.pause()));
      if (video && playing) (run ? video.play() : video.pause())?.catch?.(() => {});
    };
    document.addEventListener('visibilitychange', sync);
    cleanups.push(() => document.removeEventListener('visibilitychange', sync));
    ScrollTrigger.create({ trigger: el, start: 'top bottom', end: 'bottom top', onToggle: (self) => { inView = self.isActive; sync(); } });
    tl.eventCallback('onUpdate', () => { const past = tl.time() >= 0.15; if (past !== shrunk) { shrunk = past; sync(); } });
    sync();

    // the video (only when the page was built with one, which means the door is the opener): after the page, never on Save-Data, poster only otherwise
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

  /* ---------- the amenity moments (AMENITIES.md M1 to M3) ---------- */
  SCENES.moment = (el, { desktop }) => {
    const scrub = desktop ? 0.4 : 0.3;
    const band = el.querySelector('[data-band]');
    frames(el, { scrub, travel: desktop });          // the band and the mounts settle; the pair drifts at its own depths (desktop)
    if (band && desktop) bandTravel(band, scrub);
    const title = el.querySelector('[data-rise]'), words = el.querySelectorAll('[data-fade]');
    if (el.classList.contains('sp-moment--over')) {
      // words on the veil never move: heading and line fade up once, with the band
      fadeUp([title, ...words].filter(Boolean), { trigger: band, start: 'top 60%', delay: 0.1, stagger: 0.12 });
    } else {
      if (title) lineRise(title);
      fadeUp(words, { trigger: title || el, start: 'top 80%', delay: 0.15 });
    }
    const rule = el.querySelector('[data-rule]');
    if (rule) gsap.fromTo(rule, { scaleX: 0 }, { scaleX: 1, ease: 'none', transformOrigin: '0 50%', scrollTrigger: { trigger: title || el, start: 'top 90%', end: 'top 60%', scrub } });
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
  SCENES.band = (el, { desktop }) => {
    el.querySelectorAll('[data-frame]').forEach((f) => settle(f, desktop ? 0.4 : 0.3));   // the tote mount, when there is one
    const h = el.querySelector('[data-rise]');
    lineRise(h);
    fadeUp(el.querySelectorAll('[data-fade]'), { trigger: h, start: 'top 90%', delay: 0.3, stagger: 0.12 });
    gsap.to(el.querySelector('[data-pattern]'), { yPercent: -8, ease: 'none', scrollTrigger: { trigger: el, start: 'top bottom', end: 'bottom top', scrub: true } });
  };
}
