/* My Spa 99: the small behaviours. Everything works without this file; it only removes steps.
   - the tab bar hides while a field has focus (never floats over the keyboard)
   - choosing a membership tile marks it at once and offers "Switch to ..." (or "Choose ..." with no tier yet)
   - the marketing switch saves as it is flipped */
import { csrfToken } from './api.js';
import { toast, confirmModal } from './feedback.js';

const FIELD = 'input:not([type="checkbox"]):not([type="radio"]):not([type="button"]):not([type="submit"]), textarea, select';

function initTabbar() {
  const set = (on) => document.body.classList.toggle('m-typing', on);
  document.addEventListener('focusin', (event) => { if (event.target.matches?.(FIELD)) set(true); });
  document.addEventListener('focusout', (event) => {
    if (!event.relatedTarget?.matches?.(FIELD)) set(false);
  });
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
  // A kept sale price is for one plan: switching to another means the full price, so ask first (shared modal).
  let confirmed = false;
  form.addEventListener('submit', async (event) => {
    const chosen = form.querySelector('input[name="plan"]:checked');
    if (confirmed || !form.dataset.keptPlan || !chosen || (form.dataset.keptCovers || form.dataset.keptPlan).split(' ').includes(chosen.value)) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const name = chosen.closest('[data-plan-name]').dataset.planName;
    const ok = await confirmModal({
      title: `Switch to ${name}?`,
      body: `Your ${form.dataset.keptName} price is for ${form.dataset.keptPlanName}. Switching to ${name} means paying the full price.`,
      confirmLabel: `Switch to ${name}`, opener: button,
    });
    if (ok) { confirmed = true; form.requestSubmit(); }
  }, true);
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
      if (response.status === 401) { box.checked = !wanted; toast('You\'ve been signed out. Please sign in again.', { kind: 'error' }); return; }
      const data = response.ok && !response.redirected ? await response.json().catch(() => null) : null;
      if (!data || !data.saved) throw new Error(String(response.status));
      toast('Saved.');
    } catch {
      box.checked = !wanted;
      toast('We couldn\'t save that. Please try again.', { kind: 'error' });
    } finally {
      box.disabled = false;
    }
  });
}

initTabbar();
initInterest();
initEmails();
