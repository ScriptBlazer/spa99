/* Choice controls shared by the journey and the Gold application: tiles (radio or checkbox in a label) and the
   segmented control. Real inputs inside labels, so keyboard, screen readers and Space/arrow keys work natively. */
import { el, splitLabel } from './api.js';

let counter = 0;
const nextId = () => `c${(counter += 1)}`;
const markSpan = () => el('span', { class: 'tile-mark', 'aria-hidden': 'true' });

/** Swan glyphs for the Company answers, by option value: alone 1 gold; sometimes 1 gold + 1 line; often 2 gold. Any other value: none. */
const COMPANY_GLYPHS = { alone: ['gold'], sometimes: ['gold', 'line'], often: ['gold', 'gold'] };
export const companyGlyphs = (value) => COMPANY_GLYPHS[value] || [];

/** Two frames after a screen is rendered, mark it settled so follow-ups rise in (and nothing animates on first paint). */
export function settle(screen) {
  const body = screen.querySelector('.screen-body');
  if (!body) return;
  requestAnimationFrame(() => requestAnimationFrame(() => body.setAttribute('data-live', '')));
}

export const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/** kind: '' | 'large' | 'small' | 'image'. image: { src, alt } (src '' shows the calm placeholder). */
export function tileEl({ name, value, label, multi = false, kind = '', checked = false, image = null, glyphs = [], dataset = {} }) {
  const id = nextId();
  const { main, sub } = splitLabel(label);
  const input = el('input', { type: multi ? 'checkbox' : 'radio', name, value, id, dataset });
  if (checked) input.checked = true;
  const classes = ['tile', multi ? 'tile-multi' : '', kind === 'large' ? 'tile-large tile-company' : '', kind === 'small' ? 'tile-small' : '', kind === 'image' ? 'tile-image' : ''].filter(Boolean).join(' ');
  const body = el('span', { class: 'tile-body' }, el('span', { class: 'tile-label', text: main }), sub ? el('span', { class: 'tile-sub', text: sub }) : null);
  if (kind === 'image') {
    const thumb = el('span', { class: 'tile-thumb' }, image?.src
      ? el('img', { class: 'photo', src: image.src, alt: '', loading: 'lazy', decoding: 'async' })
      : el('span', { class: 'photo photo-placeholder', 'aria-hidden': 'true' }, el('span', { class: 'mark-glyph' })));
    return el('label', { class: classes, for: id }, input, thumb, body, markSpan());
  }
  const cue = glyphs.length
    ? el('span', { class: 'tile-glyphs', 'aria-hidden': 'true' }, glyphs.map((tone) => el('span', { class: `mark-glyph${tone === 'line' ? ' is-line' : ''}` })))
    : null;
  return el('label', { class: classes, for: id }, input, cue, body, markSpan());
}

export function tilesEl({ cls, options, ...rest }) {
  return el('div', { class: cls }, options.map((option) => tileEl({ ...rest, value: option.value, label: option.label, checked: rest.isChecked?.(option.value) || false })));
}

/** options: [{ value, label }]. Wraps to two rows on a phone when a label is long. */
export function segmentedEl({ name, options, labelledby, isChecked, dataset = {} }) {
  const wide = options.some((o) => o.label.length > 10);
  return el('div', { class: `segmented${wide ? ' segmented--wrap' : ''}`, role: 'radiogroup', 'aria-labelledby': labelledby },
    options.map((option) => {
      const id = nextId();
      const input = el('input', { type: 'radio', name, value: option.value, id, dataset });
      if (isChecked?.(option.value)) input.checked = true;
      return el('label', { class: 'seg', for: id }, input, el('span', { text: option.label }));
    }));
}

export function arrowIcon(spriteUrl) {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('class', 'icon');
  svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS(ns, 'use');
  use.setAttribute('href', `${spriteUrl}#arrow-right`);
  svg.append(use);
  return svg;
}

/** Single-choice tiles can be tapped again to clear the answer (Space on the chosen one too). A radio cannot uncheck itself,
   so remember whether it was chosen before the press, and if it was, uncheck it and fire the same `change` a checkbox would.
   `scope` is the screen root; only tile radios are touched (segmented scales keep their normal behaviour). */
const JOURNEY_ANSWER = '[data-q], [data-jq]'; // journey answers only; the Gold form's own fields (data-g) are not cleared this way
export function clearableTiles(scope) {
  let pressed = null;
  const radioFor = (target) => {
    const label = target.closest?.('label.tile');
    const input = target.closest?.('input[type="radio"]') || label?.querySelector('input[type="radio"]');
    return input && input.matches(JOURNEY_ANSWER) ? input : null;
  };
  const remember = (event) => { const input = radioFor(event.target); pressed = input ? { input, was: input.checked } : null; };
  scope.addEventListener('pointerdown', remember, true);
  scope.addEventListener('keydown', (event) => { if (event.key === ' ') remember(event); }, true);
  scope.addEventListener('click', (event) => {
    const input = event.target.closest?.('input[type="radio"]');
    if (!input || !input.closest('.tile') || !input.matches(JOURNEY_ANSWER)) return;
    const was = pressed && pressed.input === input ? pressed.was : false;
    pressed = null;
    if (was && input.checked) {
      input.checked = false;
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }, true);
}
