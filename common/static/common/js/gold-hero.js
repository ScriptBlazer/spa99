/* The Gold Card page hero scene (docs/design/GOLD-CARD-3D.md). Loaded only by gold.html; scenes.js (imported) owns the registry and the card.
 * Kept out of scenes.js so Home's script stays under its size cap. */
import { SCENES, lineRise } from './scenes.js';
import { goldCard } from './gold-card.js';

const { gsap } = window;

if (gsap) {
  /** G1 The Gold Card page hero: on load the card fades in at -25 degrees, the line draws, becomes metal, one sheen crosses it as it settles at -12.
   *  On scroll a slow half turn (-12 to +168) shows the back as the hero leaves. */
  SCENES['gold-hero'] = (el, { desktop, fine, ctx }) => {
    const mount = el.querySelector('[data-gold-card]');
    const gc = goldCard(mount, el, { desktop, fine, ctx });
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
}
