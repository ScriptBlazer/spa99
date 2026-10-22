/* Choice controls shared by the journey and the Gold application: tiles (radio or checkbox in a label) and the
   segmented control. Real inputs inside labels, so keyboard, screen readers and Space/arrow keys work natively. */
import { el, splitLabel } from './api.js';

let counter = 0;
const nextId = () => `c${(counter += 1)}`;
const markSpan = () => el('span', { class: 'tile-mark', 'aria-hidden': 'true' });

/** kind: '' | 'large' | 'small' | 'image'. image: { src, alt } (src '' shows the calm placeholder). */
export function tileEl({ name, value, label, multi = false, kind = '', checked = false, image = null, dataset = {} }) {
  const id = nextId();
  const { main, sub } = splitLabel(label);
  const input = el('input', { type: multi ? 'checkbox' : 'radio', name, value, id, dataset });
  if (checked) input.checked = true;
  const classes = ['tile', multi ? 'tile-multi' : '', kind === 'large' ? 'tile-large' : '', kind === 'small' ? 'tile-small' : '', kind === 'image' ? 'tile-image' : ''].filter(Boolean).join(' ');
  const body = el('span', { class: 'tile-body' }, el('span', { class: 'tile-label', text: main }), sub ? el('span', { class: 'tile-sub', text: sub }) : null);
  if (kind === 'image') {
    const thumb = el('span', { class: 'tile-thumb' }, image?.src
      ? el('img', { class: 'photo', src: image.src, alt: '', loading: 'lazy', decoding: 'async' })
      : el('span', { class: 'photo photo-placeholder', 'aria-hidden': 'true' }, el('span', { class: 'mark-glyph' })));
    return el('label', { class: classes, for: id }, input, thumb, body, markSpan());
  }
  return el('label', { class: classes, for: id }, input, body, markSpan());
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
