/* Register interest: plan picker and membership card, date of birth in three fields, password checks. The shared validate.js
   does the live feedback (see form.spaValidation); this adds the parts only this form has. */
import './forms.js';

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
  // A tier is required: stop the submit and say so next to the chips (the server checks too).
  form?.addEventListener('submit', (e) => {
    if (document.querySelector('input[name="plan"]:checked') || !planError) return;
    e.preventDefault();
    planError.hidden = false;
    planError.scrollIntoView({ block: 'center' });
  }, true);
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
