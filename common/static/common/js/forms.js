/* Small form behaviours shared by sign in, sign up, password reset and "check your email". */
import { passwordChecks, passwordStrength } from './validate.js';
import { csrfToken } from './api.js';

/** Show / hide on every password field, and the live checklist and strength line where the markup has them. */
export function initPasswordFields(root = document) {
  root.querySelectorAll('[data-password-toggle]').forEach((button) => {
    const input = document.getElementById(button.getAttribute('aria-controls'));
    button.addEventListener('click', () => {
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      button.textContent = show ? 'Hide' : 'Show';
      button.setAttribute('aria-pressed', String(show));
    });
  });

  root.querySelectorAll('[data-password-checklist]').forEach((list) => {
    const field = list.closest('.field');
    const input = field.querySelector('input[type="password"], input[data-password-input]') || field.querySelector('input');
    const strength = field.querySelector('[data-password-strength]');
    const word = field.querySelector('[data-password-word]');
    const form = input.form;
    const related = () => {
      const out = {};
      (input.dataset.passwordRelated || '').split(',').filter(Boolean).forEach((name) => { if (form.elements[name]) out[name] = form.elements[name].value; });
      return out;
    };
    const update = () => {
      const checks = passwordChecks(input.value, related());
      checks.forEach((check) => { const li = list.querySelector(`[data-check="${check.id}"]`); if (li) li.dataset.ok = String(check.ok); });
      const result = passwordStrength(input.value, related());
      if (strength) strength.dataset.level = String(result.level);
      if (word) word.textContent = result.word;
    };
    input.addEventListener('input', update);
    // The email and name fields feed the "not your name or email" check.
    (input.dataset.passwordRelated || '').split(',').filter(Boolean).forEach((name) => form.elements[name]?.addEventListener('input', update));
    update();
  });
}

/** "Send it again" without leaving the page: the button becomes "Sent" with the time. */
export function initResend(root = document) {
  root.querySelectorAll('form[data-resend]').forEach((form) => {
    const status = document.querySelector('[data-resend-status]');
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const button = form.querySelector('button');
      if (button.dataset.sentOnce === 'true' && Date.now() - Number(button.dataset.sentAt) < 60000) return; // a minute between sends
      button.disabled = true;
      button.setAttribute('aria-busy', 'true');
      const label = button.textContent;
      button.textContent = button.dataset.workingText || 'Sending';
      try {
        const response = await fetch(form.action, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrfToken() } });
        if (response.status === 429) throw new Error('limit');
        if (!response.ok) throw new Error('failed');
        const time = new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
        button.textContent = `Sent at ${time}`;
        button.dataset.sentOnce = 'true';
        button.dataset.sentAt = String(Date.now());
        if (status) status.textContent = 'A new link is on its way.';
        setTimeout(() => { button.textContent = label; }, 60000);
      } catch (error) {
        button.textContent = label;
        if (status) status.textContent = error.message === 'limit' ? 'That was a lot at once. Please wait a minute and try again.' : "We couldn't send that just now. Please try again.";
      } finally {
        button.disabled = false;
        button.removeAttribute('aria-busy');
        delete form.dataset.submitting;
      }
    });
  });
}

initPasswordFields();
initResend();
