/* Compare everything on a phone: the segmented control picks which membership's column shows. */

const root = document.querySelector('[data-compare]');
if (root) {
  const table = root.querySelector('.compare-table');
  root.querySelectorAll('input[name="compare"]').forEach((input) => {
    input.addEventListener('change', () => { if (input.checked) table.dataset.active = input.value; });
  });
}
