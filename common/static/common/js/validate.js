/* Live field validation. Mirrors common/validators.py (Python is authoritative; this is for instant feedback).
 *
 * Mark fields:  <input name="email" data-validate="required email">
 *               <input name="mobile" data-validate="mobile">
 *               <input name="password1" data-validate="password" data-password-related="email,first_name,last_name">
 * Messages go in  <p data-error-for="email"></p>  (created under the field if missing).
 * Server-side checks (e.g. "email already registered") plug in via attachValidation(form, { remote: { email: async v => msg|null } }).
 */

export const MESSAGES = {
  required: 'This field is required.',
  emailRequired: 'Enter your email address.',
  emailInvalid: 'Enter a valid email address.',
  mobileInvalid: 'Enter a valid UK mobile number, like 07123 456789.',
  nameRequired: 'Enter your name.',
  nameLong: 'That name is too long.',
  dobRequired: 'Enter your date of birth.',
  dobInvalid: 'Enter a valid date of birth.',
  dobUnderAge: 'You must be 18 or over.',
  passwordShort: 'This password is too short. It must contain at least 10 characters.',
  passwordCommon: 'This password is too common.',
  passwordNumeric: 'This password is entirely numeric.',
  passwordSimilar: (what) => `The password is too similar to the ${what}.`,
};

export const PASSWORD_MIN_LENGTH = 10;
export const NAME_MAX_LENGTH = 100;
export const MINIMUM_AGE = 18; // mirrors settings.MINIMUM_AGE

// A short list only: the server checks Django's full list of ~20,000 common passwords.
const COMMON_PASSWORDS = new Set([
  'password', 'password1', 'password123', '1234567890', '12345678910', 'qwertyuiop', 'qwerty123', 'letmein123',
  'iloveyou123', 'welcome123', 'admin12345', 'abc1234567', 'passw0rd123', 'monkey1234', 'football123', 'baseball123',
  'superman123', 'trustno1234', 'changeme123', 'london12345', 'spa9999999', 'spa99spa99',
]);

export function normaliseEmail(value) {
  return (value || '').trim().toLowerCase();
}

export function validateEmail(value) {
  const email = normaliseEmail(value);
  if (!email) return MESSAGES.emailRequired;
  // Same shape Django accepts for practical purposes: something@domain.tld, no spaces.
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) return MESSAGES.emailInvalid;
  return null;
}

/** '07123 456789' / '+44 7123 456789' -> '+447123456789', or null if it is not a plausible UK mobile. */
export function normaliseUkMobile(value) {
  let digits = (value || '').replace(/[\s().-]/g, '');
  if (digits.startsWith('+44')) digits = digits.slice(3);
  else if (digits.startsWith('0044')) digits = digits.slice(4);
  else if (digits.startsWith('0')) digits = digits.slice(1);
  else return null;
  digits = digits.replace(/^0/, ''); // +44 (0)7123...
  return /^7([1-57-9]\d{8}|624\d{6})$/.test(digits) ? `+44${digits}` : null;
}

export function validateMobile(value) {
  return normaliseUkMobile(value) ? null : MESSAGES.mobileInvalid;
}

export function validateName(value) {
  const name = (value || '').trim().replace(/\s+/g, ' ');
  if (!name) return MESSAGES.nameRequired;
  if (name.length > NAME_MAX_LENGTH) return MESSAGES.nameLong;
  return null;
}

/** `value` is 'YYYY-MM-DD' (what <input type="date"> gives). */
export function validateDateOfBirth(value, today = new Date()) {
  if (!value) return MESSAGES.dobRequired;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return MESSAGES.dobInvalid;
  const [year, month, day] = [Number(match[1]), Number(match[2]), Number(match[3])];
  const dob = new Date(Date.UTC(year, month - 1, day));
  if (dob.getUTCFullYear() !== year || dob.getUTCMonth() !== month - 1 || dob.getUTCDate() !== day) return MESSAGES.dobInvalid;
  const [ty, tm, td] = [today.getFullYear(), today.getMonth() + 1, today.getDate()];
  if (year > ty || (year === ty && (month > tm || (month === tm && day > td))) || year < 1900) return MESSAGES.dobInvalid;
  const hadBirthday = tm > month || (tm === month && td >= day);
  const age = ty - year - (hadBirthday ? 0 : 1);
  return age < MINIMUM_AGE ? MESSAGES.dobUnderAge : null;
}

/** Array of problems (empty = fine). `related` is { email, first_name, last_name }. */
export function passwordProblems(password, related = {}) {
  const problems = [];
  if (password.length < PASSWORD_MIN_LENGTH) problems.push(MESSAGES.passwordShort);
  if (COMMON_PASSWORDS.has(password.toLowerCase())) problems.push(MESSAGES.passwordCommon);
  if (password && /^\d+$/.test(password)) problems.push(MESSAGES.passwordNumeric);
  const lower = password.toLowerCase();
  const labels = { email: 'email address', first_name: 'first name', last_name: 'last name' };
  for (const [key, label] of Object.entries(labels)) {
    const raw = (related[key] || '').toLowerCase();
    const parts = key === 'email' ? [raw, raw.split('@')[0]] : [raw];
    if (parts.some((part) => part.length >= 3 && (lower.includes(part) || part.includes(lower) && lower.length >= 3))) {
      problems.push(MESSAGES.passwordSimilar(label));
    }
  }
  return problems;
}

function errorSlot(field) {
  const form = field.form;
  let slot = form.querySelector(`[data-error-for="${CSS.escape(field.name)}"]`);
  if (!slot) {
    slot = document.createElement('p');
    slot.className = 'field-error';
    slot.dataset.errorFor = field.name;
    slot.id = `error-${field.name}`;
    slot.setAttribute('role', 'alert');
    field.insertAdjacentElement('afterend', slot);
  }
  if (!slot.id) slot.id = `error-${field.name}`;
  field.setAttribute('aria-describedby', slot.id);
  return slot;
}

function showErrors(field, messages) {
  const slot = errorSlot(field);
  slot.textContent = messages.join(' ');
  slot.hidden = messages.length === 0;
  field.setAttribute('aria-invalid', messages.length ? 'true' : 'false');
}

function localMessages(field, form) {
  const rules = (field.dataset.validate || '').split(/\s+/).filter(Boolean);
  const value = field.value;
  const messages = [];
  if (rules.includes('required') && !value.trim()) return [MESSAGES.required];
  if (!value.trim()) return messages; // optional and empty: fine
  if (rules.includes('email')) { const m = validateEmail(value); if (m) messages.push(m); }
  if (rules.includes('mobile')) { const m = validateMobile(value); if (m) messages.push(m); }
  if (rules.includes('name')) { const m = validateName(value); if (m) messages.push(m); }
  if (rules.includes('dob')) { const m = validateDateOfBirth(value); if (m) messages.push(m); }
  if (rules.includes('password')) {
    const related = {};
    (field.dataset.passwordRelated || '').split(',').filter(Boolean).forEach((name) => {
      const other = form.elements[name];
      if (other) related[name] = other.value;
    });
    messages.push(...passwordProblems(value, related));
  }
  return messages;
}

/** Attach live validation to a form. Returns { validateAll } for custom flows. */
export function attachValidation(form, { remote = {} } = {}) {
  const fields = () => [...form.querySelectorAll('[data-validate]')];
  const latest = new Map();

  async function validateField(field) {
    let messages = localMessages(field, form);
    if (!messages.length && remote[field.name] && field.value.trim()) {
      const token = Symbol();
      latest.set(field, token);
      try {
        const remoteMessage = await remote[field.name](field.value);
        if (latest.get(field) !== token) return true; // a newer keystroke superseded this check
        if (remoteMessage) messages = [remoteMessage];
      } catch { /* network trouble: the server re-checks on submit */ }
    }
    showErrors(field, messages);
    return messages.length === 0;
  }

  fields().forEach((field) => {
    let touched = false;
    field.addEventListener('blur', () => { touched = true; validateField(field); });
    field.addEventListener('input', () => { if (touched) validateField(field); });
  });

  async function validateAll() {
    const results = await Promise.all(fields().map(validateField));
    const firstBad = fields().find((_, index) => !results[index]);
    if (firstBad) firstBad.focus();
    return !firstBad;
  }

  form.noValidate = true; // our messages replace the browser's bubbles
  form.addEventListener('submit', async (event) => {
    if (form.dataset.validated === 'true') return;
    event.preventDefault();
    if (await validateAll()) {
      form.dataset.validated = 'true';
      try { form.requestSubmit(event.submitter || undefined); } finally { delete form.dataset.validated; }
    }
  });
  // Back button (bfcache): a restored form must validate again.
  window.addEventListener('pageshow', () => { delete form.dataset.validated; });

  return { validateAll };
}

export function initValidation(root = document) {
  root.querySelectorAll('form[data-live-validate]').forEach((form) => attachValidation(form));
}
