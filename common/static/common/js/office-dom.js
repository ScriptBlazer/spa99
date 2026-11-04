/* Small helpers shared by the WhatsApp chat and the email thread: building nodes without ever parsing HTML, icons from the sprite, London times, file sizes. */
export const LONDON = 'Europe/London';
const TIME = new Intl.DateTimeFormat('en-GB', { timeZone: LONDON, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
const DAYKEY = new Intl.DateTimeFormat('en-CA', { timeZone: LONDON, year: 'numeric', month: '2-digit', day: '2-digit' });
const WEEKDAY = new Intl.DateTimeFormat('en-GB', { timeZone: LONDON, weekday: 'long' });
const FULLDAY = new Intl.DateTimeFormat('en-GB', { timeZone: LONDON, day: 'numeric', month: 'short', year: 'numeric' });
const LONGDAY = new Intl.DateTimeFormat('en-GB', { timeZone: LONDON, day: 'numeric', month: 'long' });

export const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
export const desktopKeys = () => window.matchMedia('(hover: hover) and (pointer: fine)').matches;
export const phone = () => window.matchMedia('(max-width: 63.99em)').matches;

const SVG = 'http://www.w3.org/2000/svg';
export function icon(name, cls = 'o-icon') {
  const svg = document.createElementNS(SVG, 'svg');
  svg.setAttribute('class', cls);
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  const use = document.createElementNS(SVG, 'use');
  use.setAttribute('href', `#i-${name}`);
  svg.append(use);
  return svg;
}

/** createElement with attributes and children; strings become text nodes (never HTML). */
export function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children) if (child !== null && child !== undefined && child !== false) node.append(child);
  return node;
}

export const dayOf = (iso) => DAYKEY.format(new Date(iso));
export const timeOf = (iso) => TIME.format(new Date(iso));
export function dayLabel(iso) {
  const key = dayOf(iso);
  const today = DAYKEY.format(new Date());
  const toNum = (k) => Date.UTC(...k.split('-').map((n, i) => (i === 1 ? Number(n) - 1 : Number(n))));
  const days = Math.round((toNum(today) - toNum(key)) / 86400000);
  if (days <= 0) return 'Today';
  if (days === 1) return 'Yesterday';
  if (days < 7) return WEEKDAY.format(new Date(iso));
  return FULLDAY.format(new Date(iso));
}
export const fullStamp = (iso) => `${FULLDAY.format(new Date(iso))}, ${timeOf(iso)}`;
/** "3 November, 14:20": the form read out for an email sheet. */
export const spokenStamp = (iso) => `${LONGDAY.format(new Date(iso))}, ${timeOf(iso)}`;
export function bytes(n) {
  if (!n) return '';
  if (n < 1024 * 1024) return `${Math.max(1, Math.round(n / 1024))} KB`;
  return `${(n / 1024 / 1024).toFixed(1).replace(/\.0$/, '')} MB`;
}
export const mb = (n) => `${Math.round(n / 1024 / 1024)} MB`;
