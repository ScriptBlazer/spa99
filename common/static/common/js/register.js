/* Register: plan picker and membership card, date of birth in three fields, password checks. The shared validate.js
   does the live feedback (see form.spaValidation); this adds the parts only this form has. */
import './forms.js';
import { formModal } from './feedback.js';
import { csrfToken } from './api.js';

const form = document.getElementById('register-form');

/* The membership card follows the plan chips. The server renders the chosen plan, so the card is right before this runs. */
const panel = document.querySelector('[data-plan-panel]');
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
if (panel) {
  const [body, ...spare] = panel.querySelectorAll('[data-plan-body]');
  spare.forEach((extra) => extra.remove());
  const empty = panel.querySelector('[data-plan-empty]');
  const eyebrow = panel.querySelector('[data-plan-eyebrow]');
  const text = panel.querySelector('[data-plan-text]');
  const plainEyebrow = eyebrow.textContent.trim() === eyebrow.dataset.suggestedText ? 'Your membership' : eyebrow.textContent.trim();
  const fill = (selector, value) => { body.querySelector(selector).textContent = value; };

  const showPlan = (animate) => {
    const chosen = document.querySelector('input[name="plan"]:checked');
    body.hidden = !chosen;
    empty.hidden = Boolean(chosen);
    if (!chosen) { eyebrow.textContent = plainEyebrow; return; }
    fill('[data-plan-name]', chosen.dataset.name);
    fill('[data-plan-character]', chosen.dataset.character);
    fill('[data-plan-price]', `£${chosen.dataset.price}`);
    fill('[data-plan-vat]', `ex VAT (£${chosen.dataset.inc} inc VAT)`);
    eyebrow.textContent = chosen.value === eyebrow.dataset.suggested ? eyebrow.dataset.suggestedText : plainEyebrow;
    // One 240ms fade of the text block (opacity only). Reduced motion: none.
    if (animate && !reduceMotion.matches && text.animate) {
      const fade = getComputedStyle(document.documentElement).getPropertyValue('--duration-ack').trim();
      [eyebrow, text].forEach((el) => el.animate({ opacity: [0, 1] }, { duration: parseFloat(fade) || 240, easing: 'ease-out' }));
    }
  };
  const planError = document.querySelector('[data-plan-error]');
  document.querySelectorAll('input[name="plan"]').forEach((input) => input.addEventListener('change', () => { if (planError) planError.hidden = true; showPlan(true); }));
  showPlan(false);
}

/* Date of birth: Day / Month / Year, auto-advance after 2 / 2 / 4 digits, one shared feedback line. The real field
   (type="date" without scripts) stays in the form and carries the composed value. */
const dob = document.querySelector('[data-dob]');
if (form && dob) {
  const native = dob.querySelector('[data-dob-native] input');
  const group = dob.querySelector('[data-dob-fields]');
  const [day, month, year] = ['dob-day', 'dob-month', 'dob-year'].map((id) => document.getElementById(id));
  native.type = 'text'; // so an impossible date (31 February) reaches the validator instead of being blanked
  native.hidden = true;
  native.dataset.focusTarget = '#dob-day';
  dob.querySelector('[data-dob-native]').hidden = true;
  group.hidden = false;

  const parts = /^(\d{4})-(\d{2})-(\d{2})$/.exec(native.value);
  if (parts) { [, year.value, month.value, day.value] = parts; }

  const pad = (value, size) => value.padStart(size, '0');
  const compose = () => {
    const [d, m, y] = [day.value.trim(), month.value.trim(), year.value.trim()];
    native.value = d && m && y.length === 4 ? `${y}-${pad(m, 2)}-${pad(d, 2)}` : '';
  };
  const api = () => form.spaValidation;
  const order = [day, month, year];
  order.forEach((input, index) => {
    input.addEventListener('input', () => {
      input.value = input.value.replace(/\D/g, '');
      const max = Number(input.maxLength);
      compose();
      // Move on once the field is full, unless a day or month is still obviously incomplete (e.g. "3" could be 3 or 31).
      if (input.value.length >= max && order[index + 1]) order[index + 1].focus();
      const complete = day.value && month.value && year.value.length === 4;
      if (complete) { native.dispatchEvent(new Event('input')); }
    });
    input.addEventListener('blur', () => {
      if (!input.value) return;
      compose();
      // Validate only once the person has left the whole group.
      setTimeout(() => {
        if (!group.contains(document.activeElement)) api()?.validateField(native, { show: true });
      }, 0);
    });
  });
}

/* Register: every problem in one dialog. On Register the browser checks, the live rules and the membership choice run
   together; anything wrong opens the shared centred dialog with a list (label and short message) and nothing moves.
   Closing it returns to the form with everything still filled in, and focuses the first problem. The server is asked
   with fetch (never a reload), so its answers (an email or mobile already registered) come back the same way and the
   password is not wiped. Without JavaScript the form posts normally and the page shows the errors beside the fields. */
const LABELS = {
  plan: 'Membership', first_name: 'First name', last_name: 'Last name', email: 'Email', mobile: 'Mobile', password: 'Password',
  date_of_birth: 'Date of birth', men_only_accepted: 'Men-only policy', privacy_accepted: 'Privacy notice',
};
const PLAN_MESSAGE = 'Choose a membership to continue.';
const FAILED = "We couldn't send that just now. Please check your connection and try again.";

if (form?.hasAttribute('data-register-fetch')) { // only the register page (the Gold invite set-up shares this script and posts normally)
  const button = form.querySelector('button[type="submit"]');
  const planError = document.querySelector('[data-plan-error]');
  const firstPlan = () => document.querySelector('input[name="plan"]:checked') || document.querySelector('input[name="plan"]');
  const targetFor = (name) => {
    if (name === 'plan') return firstPlan();
    const field = form.elements[name];
    return (field?.dataset?.focusTarget && form.querySelector(field.dataset.focusTarget)) || field || null;
  };

  const showProblems = (items, opener) => formModal((dialog, close) => {
    const heading = document.createElement('h2');
    heading.className = 'fb-modal-title';
    heading.id = 'register-problems-title';
    heading.textContent = items.length > 1 ? 'A few things to check' : 'One thing to check';
    const list = document.createElement('ul');
    list.className = 'register-problems';
    items.forEach((item) => {
      const row = document.createElement('li');
      if (item.label) { const name = document.createElement('strong'); name.textContent = item.label; row.append(name, ' '); }
      row.append(item.message);
      list.append(row);
    });
    const actions = document.createElement('div');
    actions.className = 'fb-modal-actions';
    const ok = document.createElement('button');
    ok.type = 'button';
    ok.className = 'fb-btn fb-btn--primary';
    ok.textContent = 'OK';
    ok.setAttribute('autofocus', '');
    ok.addEventListener('click', () => close(true));
    actions.append(ok);
    dialog.append(heading, list, actions);
  }, { opener });

  // After the dialog: first problem into view, gently, and focused. No jump if he asked for less motion.
  const goToFirst = (items) => {
    const target = items.map((item) => targetFor(item.field)).find(Boolean);
    if (!target) return;
    target.focus({ preventScroll: true });
    const box = target.closest('.field, .plan-picker') || target;
    box.scrollIntoView({ block: 'center', behavior: reduceMotion.matches ? 'auto' : 'smooth' });
  };

  const setWorking = (on) => {
    if (!button) return;
    if (on) {
      button.dataset.label = button.textContent;
      button.textContent = button.dataset.workingText || 'One moment';
    } else if (button.dataset.label) {
      button.textContent = button.dataset.label;
    }
    button.disabled = on;
    if (on) button.setAttribute('aria-busy', 'true'); else button.removeAttribute('aria-busy');
  };

  const markPlan = (message) => { if (planError) { planError.textContent = message; planError.hidden = false; } };

  /** The browser's own constraint checks plus the live rules plus the membership choice, in page order (membership first). */
  const localProblems = async () => {
    const found = (await form.spaValidation?.problems?.()) || [];
    const items = found.map(({ name, message }) => ({ field: name, label: LABELS[name] || '', message }));
    form.querySelectorAll(':invalid').forEach((el) => {
      if (el.name && el.validationMessage && !items.some((item) => item.field === el.name)) items.push({ field: el.name, label: LABELS[el.name] || '', message: el.validationMessage });
    });
    if (!document.querySelector('input[name="plan"]:checked') && planError) {
      markPlan(PLAN_MESSAGE);
      items.unshift({ field: 'plan', label: LABELS.plan, message: PLAN_MESSAGE });
    }
    return items;
  };

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    event.stopImmediatePropagation(); // validate.js's own submit handling is replaced by this one
    if (form.dataset.sending === 'true') return;
    form.dataset.sending = 'true';
    let leaving = false;
    setWorking(true);
    try {
      const local = await localProblems();
      if (local.length) { setWorking(false); await showProblems(local, button); goToFirst(local); return; }

      let items = null;
      try {
        const response = await fetch(form.action || window.location.href, {
          method: 'POST', credentials: 'same-origin', body: new FormData(form),
          headers: { 'X-Requested-With': 'fetch', Accept: 'application/json', 'X-CSRFToken': form.elements.csrfmiddlewaretoken?.value || csrfToken() },
        });
        let data = null;
        try { data = await response.json(); } catch { /* not JSON: a gateway or CSRF page */ }
        if (data?.ok && data.redirect) { leaving = true; window.location.assign(data.redirect); return; } // stays "working" while the next page loads
        items = (data?.errors || []).map((e) => ({ field: e.field, label: e.label || '', message: e.message }));
        if (!items.length) items = [{ field: '__all__', label: '', message: FAILED }];
      } catch {
        items = [{ field: '__all__', label: '', message: FAILED }];
      }
      items.forEach((item) => {
        if (item.field === 'plan') markPlan(item.message);
        else if (item.field !== '__all__') form.spaValidation?.showError(item.field, item.message);
      });
      setWorking(false);
      await showProblems(items, button);
      goToFirst(items);
    } finally {
      if (!leaving) delete form.dataset.sending;
    }
  }, true);

  // Back button after a successful register (bfcache): the button must work again.
  window.addEventListener('pageshow', () => { delete form.dataset.sending; if (button?.disabled) setWorking(false); });
}
