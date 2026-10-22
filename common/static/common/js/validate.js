/* Live field validation. Mirrors common/validators.py (Python is authoritative; this is for instant feedback).
 *
 * Mark fields:  <input name="email" data-validate="required email">
 *               <input name="mobile" data-validate="mobile">
 *               <input name="password1" data-validate="password" data-password-related="email,first_name,last_name">
 * Messages go in  <p data-error-for="email"></p>  (created under the field if missing).
 * Server-side checks (e.g. "email already registered") plug in via attachValidation(form, { remote: { email: async v => msg|null } }).
 *
 * Feedback lines (<p class="feedback" data-error-for="email" data-hint="..." data-good="...">) show, in order: the hint before
 * typing, "Checking" while a server check runs, a quiet "good" line while the rule is met, and the error only after the field
 * has lost focus (or on submit). A remote check may return a string (an error) or { state: 'info', text, link: { href, label } }.
 * The form's API is kept on form.spaValidation. A field may name another element to focus via data-focus-target.
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
  dobUnderAge: 'That date makes you under 18. Spa 99 is for 18 and over.',
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

/** The password checklist, using the same rules as passwordProblems. [{ id, ok }] */
export function passwordChecks(password, related = {}) {
  const problems = passwordProblems(password, related);
  const has = (text) => problems.some((p) => p === text);
  const similar = problems.some((p) => p.startsWith('The password is too similar'));
  return [
    { id: 'length', ok: password.length >= PASSWORD_MIN_LENGTH },
    { id: 'common', ok: Boolean(password) && !has(MESSAGES.passwordCommon) && !has(MESSAGES.passwordNumeric) },
    { id: 'similar', ok: Boolean(password) && !similar },
  ];
}

/** 0 to 4 and a word. A guide only: the server rules decide. */
export function passwordStrength(password, related = {}) {
  if (!password) return { level: 0, word: '' };
  const checks = passwordChecks(password, related);
  if (!checks.every((c) => c.ok)) return { level: 1, word: 'Too weak' };
  let points = 2;
  if (password.length >= 14) points += 1;
  if (/[a-z]/.test(password) && /[A-Z]/.test(password) && /\d/.test(password)) points += 1;
  if (/[^A-Za-z0-9]/.test(password) && password.length >= 12) points = Math.max(points, 4);
  const level = Math.min(4, points);
  return { level, word: level >= 4 ? 'Strong' : level === 3 ? 'Good' : 'Fair' };
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

/** Show one state on a field's feedback line. state: hint | checking | good | error | info. */
function render(field, { state, text = '', link = null }) {
  const slot = errorSlot(field);
  const feedback = slot.classList.contains('feedback');
  slot.textContent = text;
  if (link) {
    slot.append(' ');
    const a = document.createElement('a');
    a.href = link.href;
    a.textContent = link.label;
    slot.append(a);
  }
  if (feedback) slot.dataset.state = state;
  else slot.hidden = state !== 'error';
  field.setAttribute('aria-invalid', state === 'error' ? 'true' : 'false');
}

/** The calm "needs filling in" wording for the kind of field. */
function requiredMessage(rules) {
  if (rules.includes('email')) return MESSAGES.emailRequired;
  if (rules.includes('mobile')) return 'Enter your mobile number.';
  if (rules.includes('name')) return MESSAGES.nameRequired;
  if (rules.includes('dob')) return MESSAGES.dobRequired;
  if (rules.includes('password')) return 'Choose a password.';
  return MESSAGES.required;
}

function localMessages(field, form) {
  const rules = (field.dataset.validate || '').split(/\s+/).filter(Boolean);
  const value = field.value;
  const messages = [];
  if (rules.includes('required')) {
    if (field.type === 'checkbox' ? !field.checked : !value.trim()) return [field.dataset.requiredMessage || requiredMessage(rules)];
  }
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

const REMOTE_DELAY_MS = 450;

/** Attach live validation to a form. Returns { validateAll, validateField } for custom flows. */
export function attachValidation(form, { remote = {} } = {}) {
  const fields = () => [...form.querySelectorAll('[data-validate]')];
  const latest = new Map();
  const timers = new Map();

  const hintOf = (field) => {
    const slot = errorSlot(field);
    return slot.classList.contains('feedback') ? { state: 'hint', text: slot.dataset.hint || '' } : { state: 'hint', text: '' };
  };
  const goodOf = (field) => {
    const slot = errorSlot(field);
    return slot.dataset.good ? { state: 'good', text: slot.dataset.good } : hintOf(field);
  };

  /** `show`: errors may be shown (the field was left, or the form was submitted). */
  async function validateField(field, { show = true, remoteNow = true } = {}) {
    clearTimeout(timers.get(field));
    const messages = localMessages(field, form);
    if (messages.length) {
      render(field, show ? { state: 'error', text: messages.join(' ') } : hintOf(field));
      return false;
    }
    if (!field.value.trim()) { render(field, hintOf(field)); return true; }
    const check = remote[field.name];
    if (!check) { render(field, goodOf(field)); return true; }
    const token = Symbol();
    latest.set(field, token);
    const run = async () => {
      render(field, { state: 'checking', text: 'Checking' });
      try {
        const result = await check(field.value);
        if (latest.get(field) !== token) return true; // a newer keystroke superseded this check
        if (typeof result === 'string' && result) { render(field, { state: 'error', text: result }); return false; }
        if (result && result.state === 'info') { render(field, result); return true; }
      } catch { /* network trouble: the server re-checks on submit */ }
      if (latest.get(field) === token) render(field, goodOf(field));
      return true;
    };
    if (remoteNow) return run();
    render(field, goodOf(field));
    timers.set(field, setTimeout(run, REMOTE_DELAY_MS));
    return true;
  }

  fields().forEach((field) => {
    let touched = false;
    const eventName = field.type === 'checkbox' ? 'change' : 'input';
    field.addEventListener('blur', () => { touched = true; validateField(field, { show: true }); });
    field.addEventListener(eventName, () => validateField(field, { show: touched, remoteNow: false }));
  });

  async function validateAll() {
    const results = await Promise.all(fields().map((f) => validateField(f, { show: true })));
    const firstBad = fields().find((_, index) => !results[index]);
    if (firstBad) {
      const target = (firstBad.dataset.focusTarget && form.querySelector(firstBad.dataset.focusTarget)) || firstBad;
      target.focus();
      target.scrollIntoView?.({ block: 'center', behavior: 'auto' });
    }
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

  const api = { validateAll, validateField };
  form.spaValidation = api;
  return api;
}

/** The "already registered" check: yes/no from the server, shown as a neutral line with a sign-in link. */
function emailCheck(form) {
  const url = form.dataset.checkEmailUrl;
  if (!url) return {};
  return {
    email: async (value) => {
      const response = await fetch(`${url}?email=${encodeURIComponent(value.trim())}`, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      if (!response.ok) return null;
      const data = await response.json();
      if (!data.registered) return null;
      return { state: 'info', text: 'You already have an account.', link: { href: form.dataset.loginUrl || '/login/', label: 'Sign in' } };
    },
  };
}

export function initValidation(root = document) {
  root.querySelectorAll('form[data-live-validate]').forEach((form) => attachValidation(form, { remote: emailCheck(form) }));
}
