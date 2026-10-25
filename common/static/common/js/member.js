/* My Spa 99: the small behaviours. Everything works without this file; it only removes steps.
   - the tab bar hides while a field has focus (never floats over the keyboard)
   - toasts leave after 4 seconds
   - choosing a membership tile marks it at once and offers "Switch to ..." (or "Choose ..." with no tier yet)
   - the marketing switch saves as it is flipped */
import { csrfToken } from './api.js';
import { dismiss, showMessage } from './messages.js';

const FIELD = 'input:not([type="checkbox"]):not([type="radio"]):not([type="button"]):not([type="submit"]), textarea, select';

function initTabbar() {
  const set = (on) => document.body.classList.toggle('m-typing', on);
  document.addEventListener('focusin', (event) => { if (event.target.matches?.(FIELD)) set(true); });
  document.addEventListener('focusout', (event) => {
    if (!event.relatedTarget?.matches?.(FIELD)) set(false);
  });
}

function initToasts() {
  const list = document.getElementById('messages');
  if (!list) return;
  const arm = (item) => {
    if (item.dataset.level !== 'success' || item.dataset.timed) return;
    item.dataset.timed = 'true';
    setTimeout(() => { if (item.isConnected) dismiss(item); }, 4000);
  };
  list.querySelectorAll('[data-message]').forEach(arm);
  new MutationObserver((records) => records.forEach((r) => r.addedNodes.forEach((n) => n.nodeType === 1 && arm(n)))).observe(list, { childList: true });
}

function initInterest() {
  const form = document.querySelector('[data-interest]');
  if (!form) return;
  const button = form.querySelector('[data-keep]');
  const update = () => {
    const chosen = form.querySelector('input[name="plan"]:checked');
    const changed = !!chosen && chosen.value !== form.dataset.current;
    if (changed) {
      form.dataset.changed = 'true';
      const name = chosen.closest('[data-plan-name]').dataset.planName;
      button.textContent = form.dataset.current ? `Switch to ${name}` : `Choose ${name}`;
    } else {
      delete form.dataset.changed;
    }
  };
  form.addEventListener('change', update);
  update();
}

function initEmails() {
  const form = document.querySelector('[data-emails-form]');
  if (!form) return;
  const box = form.querySelector('input[type="checkbox"]');
  box.addEventListener('change', async () => {
    const wanted = box.checked;
    box.disabled = true;
    try {
      const response = await fetch(form.action, {
        method: 'POST', credentials: 'same-origin',
        headers: { Accept: 'application/json', 'X-CSRFToken': csrfToken(), 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ marketing: wanted ? '1' : '0' }),
      });
      if (!response.ok) throw new Error(String(response.status));
      showMessage('success', 'Saved.');
    } catch {
      box.checked = !wanted;
      showMessage('error', 'We could not save that. Please try again.');
    } finally {
      box.disabled = false;
    }
  });
}

initTabbar();
initToasts();
initInterest();
initEmails();
