/* Activity: the When seg and the Dates field exclude each other, and the seg follows what the server says it is showing.
 *   - Picking a seg item (or Clear) empties the dates first, so the form sends one or the other. This runs in the capture phase, before office-swap.js reads the form.
 *   - After the page parts are swapped (office-swap.js fires 'office:filtered') the seg shows the fetched page's range: none checked while dates are set (its thumb hides).
 * Without script the plain form still works: the server lets dates win over the range. */
const form = document.querySelector('[data-activity-form]');

if (form) {
  const clearDates = () => form.querySelector('[data-date-picker]')?.dispatchEvent(new CustomEvent('dp:clear'));
  form.addEventListener('change', (event) => { if (event.target.name === 'range') clearDates(); }, true);
  document.addEventListener('click', (event) => { if (event.target.closest?.('[data-clear]')) clearDates(); }, true);
  document.addEventListener('office:filtered', (event) => {
    const next = event.detail.doc.querySelector('[data-activity-seg]');
    const seg = form.querySelector('[data-activity-seg]');
    if (!next || !seg) return;
    const wanted = next.querySelector('input:checked')?.value || '';
    seg.querySelectorAll('input[name="range"]').forEach((input) => { input.checked = input.value === wanted; });
    seg.style.setProperty('--i', next.style.getPropertyValue('--i') || '0');
    seg.dataset.default = next.dataset.default || '';
  });
}
