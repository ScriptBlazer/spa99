/* The one confirm modal for the whole app. Never alert()/confirm()/prompt().
 *
 * Code:   if (await confirmModal({ title, message, confirmLabel, danger: true })) { ... }
 * Markup: <button data-confirm data-confirm-title="Delete invoice #1042?" data-confirm-message="This also removes
 *          its 3 payments. It cannot be undone." data-confirm-label="Delete invoice" data-confirm-danger>
 * Needs the <dialog id="confirm-modal"> from common/_modal.html on the page.
 */

import { setWorking } from './buttons.js';

export function confirmModal({ title, message, confirmLabel = 'Confirm', cancelLabel = 'Cancel', danger = false }) {
  const dialog = document.getElementById('confirm-modal');
  if (!dialog) return Promise.resolve(false); // fail safe: no modal on the page means no destructive action
  dialog.querySelector('[data-modal-title]').textContent = title || '';
  dialog.querySelector('[data-modal-message]').textContent = message || '';
  const confirmButton = dialog.querySelector('[data-modal-confirm]');
  const cancelButton = dialog.querySelector('[data-modal-cancel]');
  confirmButton.textContent = confirmLabel;
  cancelButton.textContent = cancelLabel;
  confirmButton.classList.toggle('is-danger', danger);

  return new Promise((resolve) => {
    const finish = (result) => {
      confirmButton.removeEventListener('click', onConfirm);
      cancelButton.removeEventListener('click', onCancel);
      dialog.removeEventListener('cancel', onCancel);
      dialog.close();
      resolve(result);
    };
    const onConfirm = () => finish(true);
    const onCancel = (event) => { event?.preventDefault?.(); finish(false); };
    confirmButton.addEventListener('click', onConfirm);
    cancelButton.addEventListener('click', onCancel);
    dialog.addEventListener('cancel', onCancel); // Escape key
    dialog.showModal();
    cancelButton.focus(); // safe default for dangerous actions
  });
}

export function initConfirm(root = document) {
  root.addEventListener('click', async (event) => {
    const trigger = event.target.closest?.('[data-confirm]');
    if (!trigger || trigger.dataset.confirmed === 'true') return;
    event.preventDefault();
    const accepted = await confirmModal({
      title: trigger.dataset.confirmTitle,
      message: trigger.dataset.confirmMessage,
      confirmLabel: trigger.dataset.confirmLabel || 'Confirm',
      danger: trigger.hasAttribute('data-confirm-danger'),
    });
    if (!accepted) return;
    trigger.dataset.confirmed = 'true';
    try {
      if (trigger.form) trigger.form.requestSubmit(trigger);
      else if (trigger.href) window.location.assign(trigger.href);
      else setWorking(trigger);
    } finally {
      delete trigger.dataset.confirmed; // used once: the next click always asks again
    }
  });
  // Back button (bfcache) can restore the page as it was: make sure nothing stays pre-confirmed.
  window.addEventListener('pageshow', () => {
    root.querySelectorAll?.('[data-confirmed]').forEach((el) => delete el.dataset.confirmed);
  });
}
