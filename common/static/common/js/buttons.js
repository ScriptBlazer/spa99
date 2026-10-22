/* Instant feedback on buttons and no double submits.
 *
 * Forms: on submit, submit buttons are disabled and show data-working-text (default "Working...").
 * A second submit while one is running is blocked. Buttons outside forms: add data-instant.
 */

const DEFAULT_TEXT = 'Working…';

export function setWorking(button, text) {
  if (button.dataset.working === 'true') return;
  button.dataset.working = 'true';
  button.dataset.originalText = button.textContent;
  button.textContent = text || button.dataset.workingText || DEFAULT_TEXT;
  button.setAttribute('aria-busy', 'true');
  button.disabled = true;
}

export function clearWorking(button) {
  if (button.dataset.working !== 'true') return;
  button.textContent = button.dataset.originalText;
  delete button.dataset.working;
  button.removeAttribute('aria-busy');
  button.disabled = false;
}

function submitButtons(form) {
  return [...form.querySelectorAll('button[type="submit"], button:not([type]), input[type="submit"]')];
}

export function initButtons(root = document) {
  root.addEventListener('submit', (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || event.defaultPrevented) return;
    if (form.dataset.submitting === 'true') { event.preventDefault(); return; }
    form.dataset.submitting = 'true';
    // Disable after the browser has read the submitter's name/value, so they still get sent.
    setTimeout(() => submitButtons(form).forEach((button) => button.tagName === 'BUTTON' && setWorking(button)), 0);
  });

  root.addEventListener('click', (event) => {
    const button = event.target.closest?.('button[data-instant]');
    if (button && !button.form) setWorking(button);
  });

  // Back button restores the page from cache with buttons still disabled: reset them.
  window.addEventListener('pageshow', (event) => {
    if (!event.persisted) return;
    document.querySelectorAll('form[data-submitting]').forEach((form) => {
      delete form.dataset.submitting;
      submitButtons(form).forEach((button) => button.tagName === 'BUTTON' && clearWorking(button));
    });
  });
}
