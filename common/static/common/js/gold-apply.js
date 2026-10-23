/* The Gold Card application: about you first, personal last. One screen at a time, one URL per screen.
 *
 *  - Choices come from /gold/options/ (with anything already known: the journey, or the signed-in person).
 *  - The visit answers are the journey's own questions: they are saved through the journey endpoints as they are tapped,
 *    and never asked again when the journey was done.
 *  - Everything typed or chosen is also kept in sessionStorage, so a refresh or Back keeps it.
 *  - Sent with POST /gold/apply/. No account is created.
 */
import { el, getJson, postJson, postWithRetry, splitLabel } from './api.js';
import { observeReveals } from './reveal.js';
import { attachValidation } from './validate.js';
import { setWorking, clearWorking } from './buttons.js';
import { arrowIcon as makeArrow, clearableTiles, companyGlyphs, reducedMotion, segmentedEl, settle, tileEl } from './choices.js';
import { dismiss, showMessage } from './messages.js';

const config = JSON.parse(document.getElementById('gold-config').textContent);
const copy = config.copy;
const jcopy = config.journeyCopy;
const wrapper = document.querySelector('[data-journey]');
const root = document.querySelector('[data-flow-root]');
const progress = document.querySelector('[data-progress]');
const fill = document.querySelector('[data-progress-fill]');
const STORE = 'spa99.gold.form';
const SENT = 'spa99.gold.sent';
const STEPS = [1, 2, 3];
const SENT_STEP = 4;
const PROPERTY_KEYS = ['property_link', 'size_range'];
const VISIT_KEYS = ['time', 'frequency', 'facilities', 'company'];

const c = (key) => copy[key] || { heading: '', body: '', cta: '' };
const jc = (key) => jcopy[key] || { heading: '', body: '', cta: '' };
const arrowIcon = () => makeArrow(config.iconSprite);

let options = null; // from /gold/options/
let journey = null; // from /journey/state/
let form = {}; // what the person has chosen or typed
let journeyAnswers = {}; // journey question key -> { options: [], skipped }
let current = 1;
let changingVisits = false;

/* ---------- form state kept for refresh and Back ---------- */

function loadForm() {
  try { form = JSON.parse(sessionStorage.getItem(STORE) || '{}'); } catch { form = {}; }
}
function saveForm() {
  try { sessionStorage.setItem(STORE, JSON.stringify(form)); } catch { /* private mode: it still works on this page */ }
}
function setField(name, value) {
  form[name] = value;
  saveForm();
}

/* ---------- visit answers: the journey endpoints ---------- */

let chain = Promise.resolve();
let errorMessage = null;
function saveJourney(key) {
  const a = journeyAnswers[key];
  const payload = a.skipped ? { question: key, skipped: true } : a.text !== undefined ? { question: key, text: a.text } : { question: key, options: a.options };
  chain = chain.then(async () => {
    const result = await postWithRetry('/journey/answer/', payload);
    if (result.ok) { if (errorMessage) { dismiss(errorMessage); errorMessage = null; } }
    else if (result.status >= 500 || result.status === 0 || result.status === 429) {
      if (!errorMessage?.isConnected) errorMessage = showMessage('error', "We couldn't save that just now. Your answers are safe on this page.");
    }
  }).catch(() => {});
}
const journeyQuestions = () => (journey ? journey.screens.flatMap((s) => s.questions).filter((q) => VISIT_KEYS.includes(q.key)) : []);
const visitsDone = () => journeyQuestions().some((q) => journeyAnswers[q.key] && !journeyAnswers[q.key].skipped && journeyAnswers[q.key].options.length);
const labelOf = (q, value) => splitLabel(q.options.find((o) => o.value === value)?.label || value).main;

/* ---------- screens ---------- */

function field(name, label, { optional = true, help = '', type = 'text', autocomplete = 'off', rules = '', hint = '' } = {}) {
  const id = `g-${name}`;
  const input = el('input', { id, name, type, autocomplete, class: 'input', 'data-validate': rules || null });
  input.value = form[name] || '';
  input.addEventListener('input', () => setField(name, input.value));
  return el('div', { class: 'field' },
    el('label', { for: id }, label, optional ? el('span', { class: 'optional' }, ' (optional)') : null),
    input,
    el('p', { class: 'feedback', 'data-error-for': name, id: `error-${name}`, 'aria-live': 'polite', 'data-hint': help || hint, 'data-good': rules ? 'Looks right' : '', 'data-state': 'hint', text: help || hint }));
}

function choiceGroup(name, title, optionList, { kind = '', help = '', layout = 'tiles', cls = 'tiles tiles--stack', sub = false, hidden = false } = {}) {
  const labelId = `l-${name}`;
  const isChecked = (value) => form[name] === value;
  const controls = layout === 'segmented'
    ? segmentedEl({ name, options: optionList, labelledby: labelId, isChecked, dataset: { g: name } })
    : el('div', { class: cls }, optionList.map((o) => tileEl({ name, value: o.value, label: o.label, kind, checked: isChecked(o.value), dataset: { g: name } })));
  return el('fieldset', { class: `question${sub ? ' sub-question' : ''}`, dataset: { group: name }, hidden },
    el('legend', {}, el('span', { id: labelId, text: title })),
    help ? el('span', { class: 'question-help', text: help }) : null,
    controls,
    el('p', { class: 'feedback flow-error', 'data-error-slot': name, 'aria-live': 'polite', 'data-state': 'hint' }));
}

const isProperty = () => (options.property_when?.any_of || ['property']).includes(form.industry);
const isOther = () => form.industry === (options.industry.other_value || 'other');

function screenAbout() {
  const ind = options.industry;
  const otherId = 'g-industry_other';
  const otherInput = el('input', { id: otherId, name: 'industry_other', type: 'text', maxlength: '100', autocomplete: 'off', class: 'input' });
  otherInput.value = form.industry_other || '';
  otherInput.addEventListener('input', () => setField('industry_other', otherInput.value));
  otherInput.addEventListener('change', () => saveIndustryOther());
  const other = el('div', { class: 'question sub-question', dataset: { sub: 'industry_other' }, hidden: !isOther() },
    el('div', { class: 'field' }, el('label', { for: otherId }, ind.other_label || 'Tell us more', el('span', { class: 'optional' }, ' (optional)')), otherInput));
  return [
    choiceGroup('industry', ind.question, ind.options, { cls: 'tiles tiles--4' }),
    other,
    choiceGroup('property_link', 'Your link to property', options.property_link.filter((o) => o.value !== 'none'), { cls: 'tiles tiles--stack', sub: true, hidden: !isProperty() }),
    choiceGroup('size_range', 'How large?', options.size_range, { layout: 'segmented', help: 'Units or properties', sub: true, hidden: !isProperty() }),
    choiceGroup('location', 'Where?', options.location, { cls: 'tiles tiles--2' }),
    choiceGroup('bml_relationship', 'Do you work with BML?', options.bml_relationship, { layout: 'segmented' }),
    el('div', { class: 'question' },
      el('p', { class: 'question-title', text: 'Company and role' }),
      el('div', { class: 'field-pair fieldset-gap' }, field('company', 'Company'), field('role', 'Role'))),
    el('div', { class: 'question' }, field('referred_by', 'Referred by', { help: 'If someone suggested you apply.' })),
  ];
}

function saveIndustryOther() {
  const text = (form.industry_other || '').trim().replace(/\s+/g, ' ');
  journeyAnswers.industry_other = text ? { options: [], text, skipped: false } : { options: [], skipped: true };
  saveJourney('industry_other');
}

/** Show or hide the follow-ups to match the industry. Values stay in the form, so they come back if he switches back. */
function syncAbout() {
  root.querySelectorAll('[data-group="property_link"], [data-group="size_range"]').forEach((block) => { block.hidden = !isProperty(); });
  const other = root.querySelector('[data-sub="industry_other"]');
  if (other) other.hidden = !isOther();
}

function revealFollowUp() {
  if (!isProperty()) return;
  const legend = root.querySelector('[data-group="property_link"] legend');
  if (legend && legend.getBoundingClientRect().top > window.innerHeight * 0.75) {
    legend.scrollIntoView({ block: 'center', behavior: reducedMotion() ? 'auto' : 'smooth' });
  }
}

function visitControls() {
  return journeyQuestions().map((q) => {
    const multi = q.type === 'multi';
    const isChecked = (value) => (journeyAnswers[q.key]?.options || []).includes(value);
    const dataset = { jq: q.key };
    const labelId = `l-${q.key}`;
    let controls;
    if (q.type === 'scale') {
      controls = segmentedEl({ name: `j-${q.key}`, options: q.options, labelledby: labelId, isChecked, dataset });
    } else {
      const kind = q.key === 'company' ? 'large' : '';
      const cls = q.key === 'company' ? 'tiles tiles--1 tiles-company' : 'tiles tiles--2';
      controls = el('div', { class: cls }, q.options.map((o) => tileEl({ name: `j-${q.key}`, value: o.value, label: o.label, multi, kind, checked: isChecked(o.value), glyphs: q.key === 'company' ? companyGlyphs(o.value) : [], dataset })));
    }
    return el('fieldset', { class: 'question' }, el('legend', {}, el('span', { id: labelId, text: q.text })), q.help ? el('span', { class: 'question-help', text: q.help }) : null, controls);
  });
}

function screenVisits() {
  if (!journeyQuestions().length) return [el('p', { class: 'muted', text: 'Nothing more to ask here.' })];
  if (visitsDone() && !changingVisits) {
    const lines = journeyQuestions()
      .map((q) => (journeyAnswers[q.key]?.options || []).map((v) => labelOf(q, v)).join(', '))
      .filter(Boolean);
    return [el('div', { class: 'summary-panel' },
      el('h2', { text: 'From your earlier answers' }),
      el('ul', {}, lines.map((line) => el('li', { text: line }))),
      el('button', { type: 'button', class: 'btn-quiet', 'data-change-visits': '', text: 'Change' }))];
  }
  return visitControls();
}

function screenYou() {
  const note = el('textarea', { id: 'g-note', name: 'note', rows: '4', maxlength: '2000', autocomplete: 'off' });
  note.value = form.note || '';
  note.addEventListener('input', () => setField('note', note.value));
  const privacy = el('input', { type: 'checkbox', id: 'g-privacy', name: 'privacy_accepted', 'data-validate': 'required', 'data-required-message': 'Please accept the privacy notice.' });
  privacy.checked = Boolean(form.privacy_accepted);
  privacy.addEventListener('change', () => setField('privacy_accepted', privacy.checked));
  const marketing = el('input', { type: 'checkbox', id: 'g-marketing', name: 'marketing_opt_in' });
  marketing.checked = Boolean(form.marketing_opt_in);
  marketing.addEventListener('change', () => setField('marketing_opt_in', marketing.checked));
  return [
    el('div', { class: 'field-pair' }, field('first_name', 'First name', { optional: false, rules: 'required name', autocomplete: 'given-name' }), field('last_name', 'Last name', { optional: false, rules: 'required name', autocomplete: 'family-name' })),
    el('div', { class: 'question' }, field('email', 'Email', { optional: false, type: 'email', rules: 'required email', autocomplete: 'email' })),
    el('div', { class: 'question' }, field('mobile', 'Mobile', { optional: false, type: 'tel', rules: 'required mobile', autocomplete: 'tel', hint: 'A UK mobile, like 07123 456789.' })),
    el('div', { class: 'question field' }, el('label', { for: 'g-note' }, 'Anything else? ', el('span', { class: 'optional', text: '(optional)' })), note),
    el('div', { class: 'question' },
      el('div', { class: 'field' },
        el('label', { class: 'check' }, privacy, el('span', {}, 'Read how we use your details in our ', el('a', { href: config.urls.privacy, text: 'privacy notice' }), ', and tick to accept it.')),
        el('p', { class: 'feedback', 'data-error-for': 'privacy_accepted', id: 'error-privacy_accepted', 'aria-live': 'polite', 'data-state': 'hint' })),
      el('div', { class: 'field' }, el('label', { class: 'check' }, marketing, el('span', { text: 'Send me occasional news from Spa 99.' })))),
  ];
}

function renderStep(step) {
  const head = c(`screen_${step}`);
  const body = step === 1 ? screenAbout() : step === 2 ? screenVisits() : screenYou();
  const last = step === 3;
  const primary = el('button', { type: last ? 'submit' : 'button', class: 'btn btn-primary', 'data-primary': '', 'data-working-text': 'Sending' }, last ? 'Send application' : jc('continue').cta, last ? null : ' ', last ? null : arrowIcon());
  const bar = el('div', { class: 'action-bar' }, step > 1 ? el('button', { type: 'button', class: 'btn-quiet', 'data-back': '', text: jc('back').cta }) : null, primary);
  const section = el(last ? 'form' : 'section', { class: 'screen', 'data-reveal': 'hero', novalidate: last ? '' : null, 'aria-label': head.heading },
    el('div', { class: 'screen-head' }, el('h1', { class: 'screen-title', tabindex: '-1', text: head.heading }), head.body ? el('p', { class: 'lead muted', text: head.body }) : null),
    el('div', { class: 'screen-body' }, body), bar);
  if (last) {
    attachValidation(section); // first, so it validates before our submit handler runs
    section.addEventListener('submit', onSubmit);
  }
  return section;
}

function renderSent(reference) {
  const sent = c('sent');
  return el('section', { class: 'screen gold-sent', tabindex: '-1', 'data-reveal': 'hero' },
    el('span', { class: 'mark-glyph mark-glyph--lg', 'aria-hidden': 'true' }),
    el('h1', { class: 'statement', tabindex: '-1', text: sent.heading }),
    el('p', { class: 'lead', text: sent.body }),
    reference ? el('p', { class: 'reference', text: `Reference ${reference}` }) : null,
    el('div', { class: 'actions' }, el('a', { class: 'btn-quiet', href: config.urls.home, text: sent.cta || 'Back to home' })));
}

function renderClosed() {
  const closed = c('closed');
  return el('section', { class: 'screen gold-sent', 'data-reveal': 'hero' },
    el('h1', { class: 'statement', tabindex: '-1', text: closed.heading }), el('p', { class: 'lead', text: closed.body }),
    el('div', { class: 'actions' }, el('a', { class: 'btn btn-primary', href: config.urls.home, text: closed.cta || 'Back to home' })));
}

/* ---------- navigation ---------- */

const slugFor = (step) => (step === SENT_STEP ? config.sentSlug : config.slugs[step] || `screen-${step}`);
const urlFor = (step) => `${config.base}${slugFor(step)}/`;
function stepForSlug(slug) {
  if (slug === config.sentSlug) return SENT_STEP;
  const found = Object.entries(config.slugs).find(([, value]) => value === slug);
  return found ? Number(found[0]) : null;
}

function updateProgress() {
  const p = current === SENT_STEP ? 1 : current / (STEPS.length + 1);
  fill.style.setProperty('--p', String(p));
  if (config.open) wrapper.dataset.step = String(current); else delete wrapper.dataset.step;
  progress.setAttribute('aria-valuenow', String(Math.round(p * 100)));
  progress.setAttribute('aria-valuetext', current === SENT_STEP ? 'Sent' : `${c(`screen_${current}`).heading.replace(/\.$/, '')}, part ${current} of ${STEPS.length}`);
}

function show(step, reference = '') {
  current = step;
  changingVisits = false;
  const node = !config.open ? renderClosed() : step === SENT_STEP ? renderSent(reference || sessionStorage.getItem(SENT) || '') : renderStep(step);
  root.replaceChildren(node);
  updateProgress();
  window.scrollTo(0, 0);
  (node.querySelector('h1') || node).focus?.({ preventScroll: true });
  observeReveals(root);
  settle(node);
}

function go(step, { replace = false, reference = '' } = {}) {
  const prior = history.state?.idx || 0;
  const entry = { gold: true, step, idx: replace ? prior : prior + 1 };
  if (replace) history.replaceState(entry, '', urlFor(step)); else history.pushState(entry, '', urlFor(step));
  show(step, reference);
}

function fail(name, message, focusName = name) {
  const slot = root.querySelector(`[data-error-slot="${name}"]`);
  if (slot) { slot.dataset.state = 'error'; slot.textContent = message; }
  const input = root.querySelector(`input[name="${focusName}"]`);
  input?.focus();
  input?.closest('fieldset')?.querySelector('legend')?.scrollIntoView({ block: 'center', behavior: reducedMotion() ? 'auto' : 'smooth' });
}
function next() {
  if (current === 1) {
    if (!form.industry) { fail('industry', 'Choose the one closest to what you do.'); return; }
    if (isProperty() && !form.property_link) { fail('property_link', 'Choose your link to property.'); return; }
  }
  go(current + 1);
}
function back() {
  if ((history.state?.idx || 0) > 0) history.back(); else go(Math.max(1, current - 1), { replace: true });
}

/* ---------- submit ---------- */

const FIELDS = ['first_name', 'last_name', 'email', 'mobile', 'industry', 'industry_other', 'property_link', 'size_range', 'location', 'company', 'role', 'bml_relationship', 'referred_by', 'note', 'privacy_accepted', 'marketing_opt_in'];
const STEP_OF = { industry: 1, industry_other: 1, property_link: 1, size_range: 1, location: 1, company: 1, role: 1, bml_relationship: 1, referred_by: 1 };

async function onSubmit(event) {
  if (event.defaultPrevented) return; // the validation pass runs first and re-submits once everything is fine
  event.preventDefault();
  const formEl = event.currentTarget;
  const button = formEl.querySelector('[data-primary]');
  setWorking(button);
  const body = {};
  FIELDS.forEach((name) => { if (form[name] !== undefined && form[name] !== '') body[name] = form[name]; });
  // Follow-ups belong to their industry only: anything else is not sent (the server drops it anyway).
  if (!isProperty()) PROPERTY_KEYS.forEach((name) => delete body[name]);
  if (!isOther()) delete body.industry_other;
  body.privacy_accepted = Boolean(form.privacy_accepted);
  body.marketing_opt_in = Boolean(form.marketing_opt_in);
  let result;
  try { result = await postJson('/gold/apply/', body); } catch { result = null; }
  if (result?.ok) {
    sessionStorage.removeItem(STORE);
    const reference = result.data?.reference || '';
    sessionStorage.setItem(SENT, reference);
    go(SENT_STEP, { reference });
    return;
  }
  clearWorking(button);
  if (result?.status === 400 && result.data?.errors) {
    const errors = result.data.errors;
    const early = Object.keys(errors).find((name) => STEP_OF[name]);
    if (early && !errors.first_name && !errors.email) {
      go(STEP_OF[early]);
      if (errors.industry) fail('industry', errors.industry.join(' '));
      else if (errors.property_link) fail('property_link', errors.property_link.join(' '));
      return;
    }
    Object.entries(errors).forEach(([name, messages]) => {
      const slot = root.querySelector(`[data-error-for="${name}"]`);
      const input = root.querySelector(`[name="${name}"]`);
      if (slot) { slot.dataset.state = 'error'; slot.textContent = messages.join(' '); }
      if (input) input.setAttribute('aria-invalid', 'true');
    });
    root.querySelector('[aria-invalid="true"]')?.focus();
  } else if (result?.status === 403) {
    root.replaceChildren(renderClosed());
  } else if (result?.status === 429) {
    showMessage('error', 'That was a lot at once. Please wait a minute and try again.');
  } else {
    showMessage('error', "We couldn't send that just now. Everything you typed is still here. Please try again.");
  }
}

/* ---------- events ---------- */

clearableTiles(root);

root.addEventListener('change', (event) => {
  const input = event.target;
  if (input.dataset?.g) {
    setField(input.dataset.g, input.value);
    if (input.dataset.g === 'industry') {
      journeyAnswers.industry = { options: [input.value], skipped: false };
      saveJourney('industry');
      syncAbout();
      revealFollowUp();
    }
    const slot = root.querySelector(`[data-error-slot="${input.dataset.g}"]`);
    if (slot) { slot.dataset.state = 'hint'; slot.textContent = ''; }
  } else if (input.dataset?.jq) {
    const q = journeyQuestions().find((item) => item.key === input.dataset.jq);
    const picked = q.type === 'multi'
      ? [...root.querySelectorAll(`input[data-jq="${q.key}"]:checked`)].map((i) => i.value)
      : (input.checked ? [input.value] : []);
    journeyAnswers[q.key] = { options: picked, skipped: picked.length === 0 };
    saveJourney(q.key);
  }
});

root.addEventListener('click', (event) => {
  const target = event.target.closest?.('button');
  if (!target) return;
  if (target.hasAttribute('data-primary') && target.type !== 'submit') next();
  else if (target.hasAttribute('data-back')) back();
  else if (target.hasAttribute('data-change-visits')) { changingVisits = true; root.querySelector('.screen-body').replaceChildren(...visitControls()); }
});

window.addEventListener('popstate', (event) => {
  const step = event.state?.step ?? stepForSlug(location.pathname.split('/').filter(Boolean).pop());
  if (step) show(step);
});

/* ---------- start ---------- */

async function boot() {
  loadForm();
  try {
    [options, journey] = await Promise.all([getJson('/gold/options/'), getJson('/journey/state/')]);
  } catch {
    root.replaceChildren(el('p', { class: 'lead' }, 'The application is not available just now. Please write to us and we will help.'));
    return;
  }
  Object.entries(options.prefill || {}).forEach(([name, value]) => { if (form[name] === undefined || form[name] === '') form[name] = value; });
  journey.screens.flatMap((s) => s.questions).forEach((q) => {
    if (q.answer) journeyAnswers[q.key] = { options: q.answer.options || [], text: q.answer.text || undefined, skipped: Boolean(q.answer.skipped) };
  });
  if (!form.industry && journeyAnswers.industry?.options?.length) form.industry = journeyAnswers.industry.options[0];
  if (!form.industry && form.property_link && form.property_link !== 'none') form.industry = 'property';
  if (form.industry && form.industry_other === undefined && journeyAnswers.industry_other?.text) form.industry_other = journeyAnswers.industry_other.text;
  const slug = location.pathname.split('/').filter(Boolean).pop();
  let step = stepForSlug(slug) || 1;
  if (step === SENT_STEP && !sessionStorage.getItem(SENT)) step = 1;
  history.replaceState({ gold: true, step, idx: history.state?.idx || 0 }, '', urlFor(step));
  show(step);
}

boot();
