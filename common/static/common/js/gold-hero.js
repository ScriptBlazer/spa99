/* The Gold Card page hero scene (docs/design/GOLD-CARD-3D.md). Loaded only by gold.html; scenes.js (imported) owns the registry and the card.
 * Kept out of scenes.js so Home's script stays under its size cap. */
import { SCENES, lineRise, cleanups } from './scenes.js';
import { goldCard } from './gold-card.js';

const { gsap } = window;

if (gsap) {
  /** G1 The Gold Card page hero: on load the card is already at rest (-12 degrees, swan complete) and only fades in (0.4 s).
   *  On scroll a slow half turn (-12 to +168) shows the back as the hero leaves. */
  SCENES['gold-hero'] = (el, { desktop, fine, ctx }) => {
    const mount = el.querySelector('[data-gold-card]');
    const gc = goldCard(mount, el, { desktop, fine, ctx });
    // Moishe 2026-10-23: no swing-in. The card loads straight in its resting pose (-12 degrees), swan complete, with only a short fade.
    const k = gc.k;
    Object.assign(gc, { ry: -12 * k, rx: desktop ? 3 : 1, lift: 0, sheen: -0.35, fade: 0 });
    gc.swan();
    gc.render();
    gsap.to(gc, { fade: 1, duration: 0.4, ease: 'soft', onUpdate: gc.render });
    // safety net: if the 3D card hasn't appeared in 5 s for any reason, show the flat card (CSS hides it meanwhile)
    const safety = setTimeout(() => { if (!mount.classList.contains('is-gl') && !mount.classList.contains('has-gl')) mount.classList.add('gl-off'); }, 5000);   // only if 3D never started; once its canvas exists it fades in itself
    cleanups.push(() => clearTimeout(safety));
    // The half turn runs over the first 45% of the hero's scroll while the card drifts up 35% slower than the page: the back is fully on screen (under the header, clear of the next section) when it arrives.
    const dropEnd = () => (0.35 * 0.45 * el.offsetHeight) / mount.offsetHeight * 100;
    const turn = gsap.timeline({ defaults: { ease: 'none' }, onUpdate: gc.render, scrollTrigger: { trigger: el, start: 'top top', end: () => '+=' + 0.45 * el.offsetHeight, scrub: desktop ? 0.5 : 0.3, invalidateOnRefresh: true } });
    turn.fromTo(gc, { turn: 0 }, { turn: 180, duration: 1 }, 0)
      .fromTo(gc, { drop: 0 }, { drop: dropEnd, duration: 1 }, 0);
    lineRise(el.querySelector('[data-rise]'), { trigger: false, delay: 0.4 });
    gsap.fromTo(el.querySelectorAll('.gold-hero-text [data-fade]'), { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.9, delay: 0.9, stagger: 0.12 });
  };
}
