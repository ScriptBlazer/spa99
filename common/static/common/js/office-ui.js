/* Small shell behaviours: header hairline once scrolled, the person menu, segmented thumbs, and the phone's filter sheet. */

export function initOfficeUi() {
  header();
  personMenu();
  segmented();
  filterSheet();
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
