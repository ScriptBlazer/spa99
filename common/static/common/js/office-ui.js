/* Small shell behaviours: header shadow once scrolled, the person menu, segmented thumbs, and the phone's filter sheet. */

import { noteModal } from './feedback.js';

export function initOfficeUi() {
  sendBack();
  header();
  personMenu();
  segmented();
  filterSheet();
  wants();
}

function header() {
  const bar = document.querySelector('[data-office-header]');
  const sentinel = document.querySelector('[data-office-sentinel]');
  if (!bar || !sentinel || !('IntersectionObserver' in window)) return;
  new IntersectionObserver(([entry]) => bar.toggleAttribute('data-scrolled', !entry.isIntersecting)).observe(sentinel);
}

function personMenu() {
  const menu = document.querySelector('[data-person-menu]');
  if (!menu) return;
  document.addEventListener('click', (event) => { if (menu.open && !menu.contains(event.target)) menu.open = false; });
  menu.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && menu.open) { menu.open = false; menu.querySelector('summary').focus(); }
  });
}

/** The thumb slides to the chosen segment: --i is the index of the checked radio. */
function segmented() {
  document.addEventListener('change', (event) => {
    const input = event.target;
    const group = input.closest?.('.o-seg');
    if (!group || input.type !== 'radio') return;
    group.style.setProperty('--i', String([...group.querySelectorAll('input[type="radio"]')].indexOf(input)));
  });
}

/** Below 64em the filter controls move into a bottom sheet behind a "Filters" button; the same nodes, so nothing is duplicated. */
function filterSheet() {
  const sheet = document.querySelector('[data-filter-sheet]');
  const body = document.querySelector('[data-filter-body]');
  const slot = document.querySelector('[data-filters-slot]');
  const open = document.querySelector('[data-filters-open]');
  if (!sheet || !body || !slot || !open) return;
  const target = sheet.querySelector('[data-sheet-slot]');
  const phone = window.matchMedia('(max-width: 63.99em)');
  const place = () => {
    if (phone.matches) { target.append(body); open.hidden = false; }
    else { if (sheet.open) sheet.close(); slot.append(body); open.hidden = true; }
  };
  place();
  phone.addEventListener('change', place);
  open.addEventListener('click', () => sheet.showModal());
  sheet.querySelector('[data-sheet-close]').addEventListener('click', () => sheet.close());
  sheet.addEventListener('click', (event) => { if (event.target === sheet) sheet.close(); }); // the backdrop
  sheet.addEventListener('close', () => open.focus());
}

/** Dashboard "What people want": the plus is a <details> summary (works without JS); this keeps aria-expanded true and animates the card's height. */
function wants() {
  const details = document.querySelector('[data-wants-details]');
  const stage = document.querySelector('[data-wants-stage]');
  const summary = details?.querySelector('summary');
  if (!details || !stage || !summary) return;
  const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const sync = () => summary.setAttribute('aria-expanded', String(details.open));
  let running = null;
  sync();
  details.addEventListener('toggle', sync);
  summary.addEventListener('click', (event) => {
    if (reduced() || !stage.animate) return;          // the browser's own toggle, instantly
    event.preventDefault();
    running?.cancel();
    const from = stage.offsetHeight;
    details.open = !details.open;                      // CSS swaps the tiles for the full list
    sync();
    const to = stage.offsetHeight;
    stage.style.overflow = 'hidden';
    running = stage.animate([{ height: `${from}px` }, { height: `${to}px` }], { duration: 400, easing: 'cubic-bezier(0.22, 1, 0.36, 1)' });
    const done = () => { stage.style.overflow = ''; running = null; };
    running.onfinish = done;
    running.oncancel = done;
  });
}

/** "Send back for review": the optional note is asked for in the shared dialog, then the form posts as it always did
 *  (the plain textarea in the rail is what a page without JS uses; with JS it is hidden and this writes into it). */
function sendBack() {
  document.addEventListener('click', async (event) => {
    const button = event.target.closest?.('[data-send-back]');
    if (!button?.form) return;
    event.preventDefault();
    const d = button.dataset;
    const form = button.form;
    const text = await noteModal({
      title: d.noteTitle, body: d.noteBody, label: d.noteLabel, max: Number(d.noteMax) || 1000,
      confirmLabel: d.noteConfirm || 'Send back', cancelLabel: d.noteCancel || 'Cancel', opener: button,
    });
    if (text === null) return;
    let field = form.elements.note;
    if (!field) { field = document.createElement('input'); field.type = 'hidden'; field.name = 'note'; form.append(field); }
    field.value = text;
    form.requestSubmit(button);
  });
}
