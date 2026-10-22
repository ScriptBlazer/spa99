/* Account page: copy the account ID, reveal the interest picker and the delete form. */
import './forms.js';

document.querySelectorAll('[data-copy]').forEach((button) => {
  button.addEventListener('click', async () => {
    const source = document.querySelector(button.dataset.copy);
    const label = button.textContent;
    try {
      await navigator.clipboard.writeText(source.textContent.trim());
      button.textContent = button.dataset.copiedLabel || 'Copied';
    } catch {
      // No clipboard permission: select the text so it can be copied by hand.
      const range = document.createRange();
      range.selectNodeContents(source);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      button.textContent = 'Press copy now';
    }
    setTimeout(() => { button.textContent = label; }, 2000);
  });
});

function toggle(button, panelId) {
  const panel = document.getElementById(panelId);
  button.addEventListener('click', () => {
    panel.hidden = !panel.hidden;
    button.setAttribute('aria-expanded', String(!panel.hidden));
    if (!panel.hidden) (panel.querySelector('input:checked, input') || panel).focus?.();
  });
}
const change = document.querySelector('[data-interest-change]');
if (change) toggle(change, 'interest-form');
const del = document.querySelector('[data-delete-open]');
if (del) toggle(del, 'delete-form');
