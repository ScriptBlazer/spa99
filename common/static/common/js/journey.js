/* The guided journey. One screen at a time, drawn from /journey/state/.
 *
 *  - Every tap is acknowledged at once (the selected state is instant) and saved in the background, in order, with quiet retries.
 *  - Every screen has its own URL (/journey/your-time/ ...) and history entry, so refresh and Back land on the same screen
 *    with the answers shown. The current step is also saved on the server so closing and returning resumes.
 *  - Follow-up questions (property link, "Other") appear and disappear live from the questions' own conditions.
 */
import { el, getJson, postJson, postWithRetry } from './api.js';
import { observeReveals } from './reveal.js';
import { arrowIcon as makeArrow, clearableTiles, companyGlyphs, reducedMotion, segmentedEl, settle, tileEl } from './choices.js';
import { dismiss, toast } from './feedback.js';

const config = JSON.parse(document.getElementById('journey-config').textContent);
const copy = config.copy;
const wrapper = document.querySelector('[data-journey]');
const root = document.querySelector('[data-flow-root]');
const progress = document.querySelector('[data-progress]');
const fill = document.querySelector('[data-progress-fill]');

// Layout choices per question (everything else follows its type).
const PREFER_NOT_SAY = new Set(['property_link', 'property_size', 'heard_via']);
const LAYOUT = {
  time: 'tiles-2', frequency: 'segmented', facilities: 'image', company: 'large', industry: 'tiles-4',
  property_link: 'tiles-stack', property_size: 'segmented', property_law: 'segmented', heard_via: 'small',
};

let state = null;
let answers = {}; // question key -> { options: [], text: '', skipped: false }
let visibleKeys = new Set();
let current = 1;
let resultStep = 5;
let saveErrorMessage = null;
let lastSuggestion = config.lastSuggestion || null; // { plan_name, plan_slug, url } once a journey was finished
let pendingNudge = false;

const questions = () => state.screens.flatMap((screen) => screen.questions);
const questionByKey = (key) => questions().find((q) => q.key === key);
const copyOf = (key) => copy[key] || { heading: '', body: '', cta: '' };

/* ---------- conditions and visibility (mirrors journey/conditions.py) ---------- */

function conditionItems(condition) {
  if (!condition) return [];
  return (Array.isArray(condition) ? condition : [condition]).filter(Boolean);
}
function matches(condition, values) {
  return conditionItems(condition).every((item) => {
    const wanted = item.any_of || [];
    return !wanted.length || (values[item.question] || []).some((v) => wanted.includes(v));
  });
}
const parentKey = (q) => (conditionItems(q.condition)[0] || {}).question || null;

function computeVisible() {
  const values = {};
  const visible = new Set();
  questions().forEach((q) => {
    if (!matches(q.condition, values)) return;
    visible.add(q.key);
    const a = answers[q.key];
    if (a && !a.skipped) values[q.key] = a.options;
  });
  visibleKeys = visible;
}
const screenNumbers = () => state.screens.filter((s) => s.questions.some((q) => visibleKeys.has(q.key))).map((s) => s.number);
function computeResultStep() {
  const numbers = screenNumbers();
  resultStep = (numbers.length ? numbers[numbers.length - 1] : 0) + 1;
}

/** A screen's questions with follow-ups placed directly under the question they depend on. */
function arrange(list) {
  const keys = new Set(list.map((q) => q.key));
  const out = [];
  const place = (q) => {
    out.push(q);
    list.filter((child) => parentKey(child) === q.key).forEach(place);
  };
  list.filter((q) => !keys.has(parentKey(q))).forEach(place);
  return out;
}

/* ---------- saving: in order, in the background, with quiet retries ---------- */

let chain = Promise.resolve();
const unsaved = new Set();
const enqueue = (job) => { chain = chain.then(job).catch(() => {}); return chain; };

function payloadFor(key) {
  const a = answers[key] || { options: [], text: '', skipped: false };
  const q = questionByKey(key);
  if (a.skipped) return { question: key, skipped: true };
  if (q.type === 'text') return { question: key, text: a.text };
  return { question: key, options: a.options };
}

function applyServerVisibility(visible) {
  if (!visible) return;
  const changed = questions().some((q) => (q.key in visible) && visible[q.key] !== visibleKeys.has(q.key));
  if (changed) {
    visibleKeys = new Set(Object.keys(visible).filter((k) => visible[k]));
    syncVisibility();
  }
}

function showSaveError() {
  if (saveErrorMessage && saveErrorMessage.isConnected) return;
  saveErrorMessage = toast(copyOf('save_error').body, { kind: 'error' });
}
function clearSaveError() {
  if (saveErrorMessage) { dismiss(saveErrorMessage); saveErrorMessage = null; }
}

function saveAnswer(key) {
  unsaved.delete(key);
  return enqueue(async () => {
    const result = await postWithRetry('/journey/answer/', payloadFor(key));
    if (result.ok) {
      applyServerVisibility(result.data?.visible);
      if (unsaved.size) { const retry = [...unsaved]; retry.forEach((k) => saveAnswer(k)); } else clearSaveError();
    } else if (result.status >= 500 || result.status === 0 || result.status === 429 || result.status === 403) {
      unsaved.add(key);
      showSaveError(); // the journey keeps working; the answers stay on this page
    }
    // A 400 means the server does not know the question any more (for example a follow-up that was hidden): nothing to keep.
  });
}
const screenOfKey = (key) => state.screens.find((sc) => sc.questions.some((q) => q.key === key))?.number || 0;
const saveStep = (step) => enqueue(async () => {
  const reply = await postWithRetry('/journey/step/', { step });
  // A required answer is missing on an earlier screen (a stale page): go back there and say so.
  const missing = reply.status === 400 ? reply.data?.missing : null;
  if (missing?.length && step === current && missing.some((k) => screenOfKey(k) && screenOfKey(k) < step)) bounce(missing);
});

/* ---------- building screens ---------- */

const isChecked = (q) => (value) => (answers[q.key]?.options || []).includes(value);

function tile(q, option, kind) {
  return tileEl({
    name: q.key, value: option.value, label: option.label, multi: q.type === 'multi', kind,
    checked: isChecked(q)(option.value), image: config.facilityImages[option.value] || {}, dataset: { q: q.key },
    glyphs: q.key === 'company' ? companyGlyphs(option.value) : [],
  });
}

function segmented(q) {
  return segmentedEl({ name: q.key, options: q.options, labelledby: `l-${q.key}`, isChecked: isChecked(q), dataset: { q: q.key } });
}

function questionBlock(q) {
  const layout = LAYOUT[q.key] || (q.type === 'scale' ? 'segmented' : q.type === 'multi' ? 'tiles-2' : 'tiles-stack');
  const hidden = !visibleKeys.has(q.key);
  const block = el(q.type === 'text' ? 'div' : 'fieldset', {
    class: `question${parentKey(q) ? ' sub-question' : ''}`, dataset: { question: q.key }, hidden,
  });

  if (q.type === 'text') {
    const id = `t-${q.key}`;
    const input = el('input', { type: 'text', id, class: 'input', maxlength: String(state.session.max_text_length), autocomplete: 'off', value: answers[q.key]?.text || '', 'data-q': q.key, 'data-text': '' });
    input.value = answers[q.key]?.text || '';
    block.append(el('div', { class: 'field' }, el('label', { for: id }, q.text, ' ', el('span', { class: 'optional', text: copyOf('optional').body })), input));
    return block;
  }

  const title = el('span', { id: `l-${q.key}`, text: q.text });
  const needs = (q.min_choices || 0) > 0;
  const helpText = q.help || (needs ? 'Choose at least one.' : '');
  const help = helpText ? el('span', { class: 'question-help', id: `hint-${q.key}`, text: helpText }) : null;
  const legend = el('legend', {}, title);
  if (PREFER_NOT_SAY.has(q.key)) {
    legend.append(' ', el('button', { type: 'button', class: 'btn-quiet prefer-not', 'data-skip': q.key, text: copyOf('prefer_not').cta }));
  }
  block.append(legend);
  if (help) block.append(help);

  let controls;
  if (layout === 'segmented') {
    controls = segmented(q);
  } else {
    const cls = { 'tiles-2': 'tiles tiles--2', 'tiles-4': 'tiles tiles--4', 'tiles-stack': 'tiles tiles--stack', large: 'tiles tiles--1 tiles-company', image: 'tiles tiles--4', small: 'tiles tiles--row' }[layout];
    const kind = layout === 'large' ? 'large' : layout === 'image' ? 'image' : layout === 'small' ? 'small' : '';
    controls = el('div', { class: cls }, q.options.map((option) => tile(q, option, kind)));
  }
  controls.dataset.controls = q.key;
  if (answers[q.key]?.skipped) controls.dataset.skipped = 'true';
  block.append(controls);
  return block;
}

/** Show or hide follow-up questions to match the answers, without rebuilding the screen. */
function syncVisibility() {
  computeVisible();
  computeResultStep();
  root.querySelectorAll('[data-question]').forEach((block) => {
    const show = visibleKeys.has(block.dataset.question);
    if (block.hidden === show) block.hidden = !show;
  });
  updateAction();
  updateProgress();
}

const screenAnswered = (number) => {
  const screen = state.screens.find((s) => s.number === number);
  return screen.questions.some((q) => visibleKeys.has(q.key) && answers[q.key] && (answers[q.key].skipped || answers[q.key].options.length || answers[q.key].text));
};

/** Visible questions on a screen that still need more choices than they have (the "at least one" rule). */
function unmetQuestions(number) {
  const screen = state.screens.find((sc) => sc.number === number);
  return screen.questions.filter((q) => visibleKeys.has(q.key) && (q.min_choices || 0) > 0 && (answers[q.key]?.options.length || 0) < q.min_choices);
}

function actionLabel(number) {
  if (unmetQuestions(number).length) return { text: copyOf('continue').cta, arrow: false, unmet: true };
  const last = screenNumbers().slice(-1)[0] === number;
  if (last) return { text: copyOf('last').cta, arrow: true };
  return screenAnswered(number) ? { text: copyOf('continue').cta, arrow: true } : { text: copyOf('skip').cta, arrow: false };
}

function applyActionState(button, label) {
  if (label.unmet) {
    button.setAttribute('aria-disabled', 'true');
    button.setAttribute('aria-describedby', `hint-${unmetQuestions(current)[0].key}`);
  } else {
    button.removeAttribute('aria-disabled');
    button.removeAttribute('aria-describedby');
    root.querySelectorAll('.question-help[data-state]').forEach((h) => h.removeAttribute('data-state'));
  }
}

function updateAction() {
  const button = root.querySelector('[data-primary]');
  if (!button) return;
  const label = actionLabel(current);
  button.textContent = label.text;
  if (label.arrow) button.append(' ', arrowIcon());
  applyActionState(button, label);
}

/** Pressing the inactive Continue (or arriving without the required answer): say why, never move on. */
function nudge() {
  const unmet = unmetQuestions(current);
  if (!unmet.length) return;
  unmet.forEach((q) => root.querySelector(`#hint-${q.key}`)?.setAttribute('data-state', 'nudge'));
  const live = root.querySelector('[data-live-msg]');
  if (live) {
    live.textContent = '';
    requestAnimationFrame(() => { live.textContent = copyOf('need_one').body || 'Choose at least one to continue.'; });
  }
  const legend = root.querySelector(`[data-question="${unmet[0].key}"] legend`);
  if (legend) {
    const r = legend.getBoundingClientRect();
    if (r.top < 0 || r.bottom > window.innerHeight) legend.scrollIntoView({ block: 'center', behavior: reducedMotion() ? 'auto' : 'smooth' });
  }
}

const arrowIcon = () => makeArrow(config.iconSprite);

function renderQuestionScreen(number) {
  const screen = state.screens.find((s) => s.number === number);
  const head = copyOf(`screen_${number}`);
  const numbers = screenNumbers();
  const isFirst = numbers[0] === number;
  const title = el('h1', { class: 'screen-title', tabindex: '-1', text: head.heading });
  const body = el('div', { class: 'screen-body' }, arrange(screen.questions).map(questionBlock));
  const label = actionLabel(number);
  const primary = el('button', { type: 'button', class: 'btn btn-primary', 'data-primary': '', text: label.text });
  if (label.arrow) primary.append(' ', arrowIcon());
  if (label.unmet) applyActionState(primary, label);
  const bar = el('div', { class: 'action-bar' }, isFirst ? null : el('button', { type: 'button', class: 'btn-quiet', 'data-back': '', text: copyOf('back').cta }), primary);
  const anyAnswers = Object.values(answers).some((a) => a.options.length || a.text);
  const again = isFirst && anyAnswers ? el('p', { class: 'start-again' }, el('button', { type: 'button', class: 'btn-quiet', 'data-restart': '', text: copyOf('start_again').cta })) : null;
  const suggestion = isFirst && lastSuggestion
    ? el('p', { class: 'last-suggestion' }, el('a', { href: lastSuggestion.url || urlFor(resultStep), 'data-last-suggestion': '', text: copyOf('last_suggestion').cta }))
    : null;
  return el('section', { class: 'screen', 'aria-label': head.heading, 'data-reveal': 'hero' },
    el('div', { class: 'screen-head' }, title, head.body ? el('p', { class: 'lead muted', text: head.body }) : null, suggestion),
    body, bar, again, el('p', { class: 'sr-only', 'aria-live': 'polite', 'data-live-msg': '' }));
}

/* ---------- result ---------- */

const registerUrl = (slug) => `${config.urls.register}?plan=${encodeURIComponent(slug)}`;

function goldMark() { return el('span', { class: 'mark-glyph', 'aria-hidden': 'true' }); }

function renderResult(data) {
  const s = data.suggested;
  if (!s) {
    const empty = config.membershipsHidden ? { ...copyOf('result_empty'), url: config.urls.memberships } : (data.copy?.empty || {});
    return el('section', { class: 'result', tabindex: '-1', 'data-reveal': 'hero' },
      el('h1', { class: 'screen-title', tabindex: '-1', text: empty.heading || '' }),
      el('p', { class: 'lead', text: empty.body || '' }),
      el('div', { class: 'result-actions' }, el('a', { class: 'btn btn-primary', href: empty.url || config.urls.memberships, text: empty.cta || '' })));
  }
  const presentation = data.gold?.presentation || 'none';
  const goldPanelCopy = copyOf('gold_panel');
  const goldLineCopy = copyOf('gold_line');
  const ctaText = copyOf('result_cta').cta.replace('{plan}', s.name);

  const main = el('div', { class: 'result-main', 'data-reveal': 'hero' },
    el('p', { class: 'result-label small', text: copyOf('result_label').body }),
    el('h1', { class: 'display result-tier', tabindex: '-1', text: `${s.name}.` }),
    el('p', { class: 'result-price num', text: s.price_line }),
    el('p', { class: 'result-char', text: s.character_line }),
    el('div', { class: 'why' }, el('h2', { text: copyOf('why').heading }), el('ul', { class: 'reasons' }, (s.reasons || []).map((r) => el('li', { text: r })))),
    el('div', { class: 'result-actions' },
      el('a', { class: 'btn btn-primary btn-block-phone', href: registerUrl(s.slug) }, ctaText, ' ', arrowIcon()),
      el('button', { type: 'button', class: 'btn-quiet', 'data-restart': '', text: copyOf('start_again').cta })),
    presentation === 'line'
      ? el('p', { class: 'gold-line-note' }, `${goldLineCopy.body} `, el('a', { href: config.urls.goldApply, text: goldLineCopy.cta }))
      : null);

  const others = (data.others || []).length
    ? el('div', { class: 'others', 'data-reveal': '' }, el('h2', { text: copyOf('others').heading }),
      data.others.map((plan) => el('div', { class: 'other-plan' },
        el('div', {}, el('strong', { text: plan.name }), ' ', el('span', { class: 'muted', text: plan.character_line }), plan.not_a_fit ? el('p', { class: 'not-fit', text: copyOf('not_a_fit').body }) : null),
        el('span', { class: 'num', text: `£${plan.price_whole}` }),
        el('a', { class: 'btn-quiet', href: registerUrl(plan.slug), text: copyOf('others').cta.replace('{plan}', plan.name) }))),
      // he has given his email to get here, so the Memberships page is open to him
      el('p', { class: 'explore-memberships' }, el('a', { class: 'btn-quiet', href: config.urls.membershipsPage, text: copyOf('explore_memberships').cta })))
    : null;

  const grid = el('div', { class: `result-grid${presentation === 'panel' ? ' has-gold' : ''}` }, main);
  if (presentation === 'panel') {
    grid.append(el('div', { class: 'result-gold', 'data-reveal': '' }, el('div', { class: 'gold-panel' },
      goldMark(), el('h2', { text: goldPanelCopy.heading }), el('p', { text: goldPanelCopy.body }),
      config.goldFeeNote ? el('p', { class: 'fee-note', text: config.goldFeeNote }) : null,
      el('a', { class: 'btn btn-primary', href: config.urls.goldApply }, goldPanelCopy.cta, ' ', arrowIcon()))));
  }
  if (others) grid.append(others);
  return el('section', { class: 'result', 'aria-label': copyOf('result_label').body }, grid);
}

/* ---------- the email gate (before the result) ---------- */

/** One field and one consent. Posts to /journey/lead/; the server checks the address and says why when it is wrong. */
function renderGate() {
  const g = config.gate || {};
  const input = el('input', { id: 'lead-email', name: 'email', type: 'email', class: 'input', autocomplete: 'email', inputmode: 'email', 'aria-describedby': 'lead-email-msg' });
  const emailMsg = el('p', { class: 'feedback', id: 'lead-email-msg', 'aria-live': 'polite', 'data-state': 'hint' });
  const consent = el('input', { type: 'checkbox', id: 'lead-consent', name: 'consent', 'aria-describedby': 'lead-consent-msg' });
  const consentMsg = el('p', { class: 'feedback', id: 'lead-consent-msg', 'aria-live': 'polite', 'data-state': 'hint' });
  const primary = el('button', { type: 'submit', class: 'btn btn-primary', 'data-gate-primary': '' }, g.cta || '', ' ', arrowIcon());
  const back = el('button', { type: 'button', class: 'btn-quiet', 'data-back': '', text: copyOf('back').cta });
  const form = el('form', { class: 'screen lead-gate', novalidate: '', 'aria-label': g.heading || '', 'data-reveal': 'hero' },
    el('div', { class: 'screen-head' }, el('h1', { class: 'screen-title', tabindex: '-1', text: g.heading || '' }), g.body ? el('p', { class: 'lead muted', text: g.body }) : null),
    el('div', { class: 'screen-body' },
      el('div', { class: 'question' }, el('div', { class: 'field' }, el('label', { for: 'lead-email' }, g.email_label || 'Email'), input, emailMsg)),
      el('div', { class: 'question' }, el('div', { class: 'field' },
        el('label', { class: 'check' }, consent, el('span', {}, `${g.consent || ''} `, el('a', { href: config.urls.privacy, text: g.privacy_label || 'Privacy' }))), consentMsg)),
      el('div', { class: 'hp', 'aria-hidden': 'true' }, el('label', {}, 'Website ', el('input', { name: 'website', tabindex: '-1', autocomplete: 'off' })))),
    el('div', { class: 'action-bar' }, back, primary));
  const mark = (slot, message) => { slot.textContent = message || ''; slot.dataset.state = message ? 'error' : 'hint'; };
  input.addEventListener('input', () => { mark(emailMsg, ''); input.removeAttribute('aria-invalid'); });
  consent.addEventListener('change', () => mark(consentMsg, ''));
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (primary.disabled) return;
    primary.disabled = true;
    primary.setAttribute('aria-busy', 'true');
    const reply = await postJson(config.urls.lead, { email: input.value, consent: consent.checked, website: form.querySelector('[name=website]').value }).catch(() => null);
    primary.disabled = false;
    primary.removeAttribute('aria-busy');
    if (reply?.ok) {
      state.session.lead_required = false;
      show(resultStep); // same URL: now the result itself
      return;
    }
    const errors = reply?.status === 400 ? reply.data?.errors || {} : null;
    if (errors) {
      mark(emailMsg, errors.email);
      mark(consentMsg, errors.consent);
      if (errors.email) { input.setAttribute('aria-invalid', 'true'); input.focus(); } else consent.focus();
    } else {
      mark(emailMsg, g.error || '');
    }
  });
  return form;
}

/* ---------- navigation ---------- */

const slugFor = (step) => (step === resultStep ? config.resultSlug : config.slugs[step] || `screen-${step}`);
const urlFor = (step) => `${config.base}${slugFor(step)}/`;
function stepForSlug(slug) {
  if (!slug) return null;
  if (slug === config.resultSlug) return resultStep;
  const found = Object.entries(config.slugs).find(([, value]) => value === slug);
  if (found) return Number(found[0]);
  const m = /^screen-(\d+)$/.exec(slug);
  return m ? Number(m[1]) : null;
}

function updateProgress() {
  const numbers = screenNumbers();
  const onResult = current === resultStep;
  const index = numbers.indexOf(current);
  const p = onResult ? 1 : (index + 1) / (numbers.length + 1);
  fill.style.setProperty('--p', String(p));
  progress.setAttribute('aria-valuenow', String(Math.round(p * 100)));
  const name = copyOf(`screen_${current}`).heading.replace(/\.$/, '');
  progress.setAttribute('aria-valuetext', onResult ? copyOf('result_label').body : `${name}, part ${index + 1} of ${numbers.length}`);
}

function setSurface(light) {
  wrapper.classList.toggle('on-light', light);
  wrapper.classList.toggle('on-dark', !light);
  document.body.classList.toggle('journey-light', light);
}

async function show(step) {
  current = step;
  computeVisible();
  computeResultStep();
  if (step > resultStep) current = step = resultStep;
  const onResult = step === resultStep;
  const gated = onResult && Boolean(state.session.lead_required);
  setSurface(onResult && !gated);
  let node;
  if (gated) {
    node = renderGate();
    updateProgress();
  } else if (onResult) {
    root.replaceChildren(el('p', { class: 'muted flow-loading', text: copyOf('result_loading').body }));
    updateProgress();
    try {
      // POST: arriving at the result is what stores the suggestion and marks the journey finished (a GET changes nothing).
      const reply = await postWithRetry('/journey/result/', {});
      if (reply.status === 400 && reply.data?.missing?.length) { bounce(reply.data.missing); return; }
      if (reply.status === 403 && reply.data?.needs_email) { state.session.lead_required = true; show(step); return; }  // gate first
      if (!reply.ok) throw new Error('result');
      if (reply.data?.suggested) lastSuggestion = { plan_name: reply.data.suggested.name, plan_slug: reply.data.suggested.slug, url: urlFor(resultStep) };
      node = renderResult(reply.data);
    } catch {
      const failed = copyOf('result_error');
      toast(failed.heading, { kind: 'error' });
      node = el('section', { class: 'result' }, el('p', { class: 'lead' }, `${failed.body} `, el('a', { href: config.urls.memberships, text: failed.cta }), '.'));
    }
  } else {
    node = renderQuestionScreen(step);
  }
  root.replaceChildren(node);
  syncVisibility();
  window.scrollTo(0, 0); // instant
  (node.querySelector('h1') || node).focus?.({ preventScroll: true });
  observeReveals(root);
  if (!onResult) settle(node);
  if (pendingNudge && !onResult) { pendingNudge = false; nudge(); }
}

/** The server says a required answer is missing (stale page, deep link): take him to that screen and show the hint. */
function bounce(missing) {
  const screen = state.screens.find((sc) => sc.questions.some((q) => missing.includes(q.key)));
  if (!screen) { go(screenNumbers()[0] || 1, { replace: true }); return Promise.resolve(); }
  pendingNudge = true;
  return go(screen.number, { replace: true });
}

function go(step, { replace = false } = {}) {
  const prior = history.state?.idx || 0;
  const entry = { journey: true, step, idx: replace ? prior : prior + 1 };
  if (replace) history.replaceState(entry, '', urlFor(step));
  else history.pushState(entry, '', urlFor(step));
  saveStep(step);
  return show(step);
}

function goBack() {
  const numbers = screenNumbers();
  const index = numbers.indexOf(current);
  const target = index > 0 ? numbers[index - 1] : (current === resultStep ? numbers[numbers.length - 1] : numbers[0]);
  if ((history.state?.idx || 0) > 0) history.back();
  else go(target, { replace: true });
}

function goNext() {
  if (unmetQuestions(current).length) { nudge(); return; }
  const numbers = screenNumbers();
  const index = numbers.indexOf(current);
  const target = index >= 0 && index < numbers.length - 1 ? numbers[index + 1] : resultStep;
  if (!screenAnswered(current)) {
    // "Skip this part": the skips are saved too.
    const screen = state.screens.find((s) => s.number === current);
    screen.questions.filter((q) => visibleKeys.has(q.key) && q.type !== 'text' && !answers[q.key]).forEach((q) => {
      answers[q.key] = { options: [], text: '', skipped: true };
      saveAnswer(q.key);
    });
  }
  go(target);
}

/* ---------- events ---------- */

function setAnswer(key, value) {
  answers[key] = value;
  saveAnswer(key);
  const controls = root.querySelector(`[data-controls="${key}"]`);
  if (controls) { if (value.skipped) controls.dataset.skipped = 'true'; else delete controls.dataset.skipped; }
  syncVisibility();
}

clearableTiles(root);
root.addEventListener('change', (event) => {
  const input = event.target.closest?.('input[data-q]');
  if (!input || input.hasAttribute('data-text')) return;
  const q = questionByKey(input.dataset.q);
  const picked = q.type === 'multi'
    ? [...root.querySelectorAll(`input[data-q="${q.key}"]:checked`)].map((i) => i.value)
    : (input.checked ? [input.value] : []);
  setAnswer(q.key, picked.length ? { options: picked, text: '', skipped: false } : { options: [], text: '', skipped: true });
});

let textTimer = null;
root.addEventListener('input', (event) => {
  const input = event.target.closest?.('input[data-text]');
  if (!input) return;
  clearTimeout(textTimer);
  textTimer = setTimeout(() => {
    const text = input.value.trim().replace(/\s+/g, ' ');
    setAnswer(input.dataset.q, text ? { options: [], text, skipped: false } : { options: [], text: '', skipped: true });
  }, 500);
});

root.addEventListener('click', async (event) => {
  const target = event.target.closest?.('button, a');
  if (!target) return;
  if (target.hasAttribute('data-primary')) { if (target.getAttribute('aria-disabled') === 'true') nudge(); else goNext(); }
  else if (target.hasAttribute('data-last-suggestion')) {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button) return;
    event.preventDefault();
    go(resultStep);
  }
  else if (target.hasAttribute('data-back')) goBack();
  else if (target.dataset.skip) {
    const key = target.dataset.skip;
    root.querySelectorAll(`input[data-q="${key}"]`).forEach((i) => { i.checked = false; });
    setAnswer(key, { options: [], text: '', skipped: true });
  } else if (target.hasAttribute('data-restart')) {
    target.disabled = true;
    const fresh = await postJson('/journey/restart/', {}).catch(() => null);
    if (fresh?.ok) { load(fresh.data, 1); history.replaceState({ journey: true, step: 1, idx: 0 }, '', urlFor(1)); }
    else target.disabled = false;
  }
});

window.addEventListener('popstate', (event) => {
  const step = event.state?.step ?? stepForSlug(location.pathname.split('/').filter(Boolean).pop());
  if (!step) return;
  saveStep(step);
  show(step);
});

/* ---------- start ---------- */

function load(fresh, step) {
  state = fresh;
  lastSuggestion = fresh.last_suggestion || null;
  answers = {};
  questions().forEach((q) => {
    if (q.answer) answers[q.key] = { options: q.answer.options || [], text: q.answer.text || '', skipped: Boolean(q.answer.skipped) };
  });
  computeVisible();
  computeResultStep();
  return show(step);
}

async function boot() {
  const params = new URLSearchParams();
  if (document.referrer) params.set('ref', document.referrer);
  new URLSearchParams(location.search).forEach((value, key) => { if (key.startsWith('utm_')) params.set(key, value); });
  try {
    state = await getJson(`/journey/state/?${params}`);
  } catch {
    const down = copyOf('unavailable');
    root.replaceChildren(el('p', { class: 'lead' }, `${down.body} `, el('a', { href: config.urls.memberships, text: down.cta }), '.'));
    return;
  }
  answers = {};
  questions().forEach((q) => {
    if (q.answer) answers[q.key] = { options: q.answer.options || [], text: q.answer.text || '', skipped: Boolean(q.answer.skipped) };
  });
  lastSuggestion = state.last_suggestion || config.lastSuggestion || null;
  computeVisible();
  computeResultStep();
  const session = state.session;
  const slug = location.pathname.replace(config.base, '').split('/').filter(Boolean)[0];
  let step = stepForSlug(slug);
  const reachable = (s) => s <= Math.max(session.furthest_step || 1, session.current_step || 1) || session.completed;
  if (!step || !reachable(step) || (step > resultStep) || (step !== resultStep && !screenNumbers().includes(step))) {
    step = Math.min(session.resume_step || 1, resultStep);
    if (!screenNumbers().includes(step) && step !== resultStep) step = screenNumbers()[0] || 1;
  }
  history.replaceState({ journey: true, step, idx: history.state?.idx || 0 }, '', urlFor(step));
  await show(step);
}

boot();
