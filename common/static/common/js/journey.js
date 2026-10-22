/* The guided journey. One screen at a time, drawn from /journey/state/.
 *
 *  - Every tap is acknowledged at once (the selected state is instant) and saved in the background, in order, with quiet retries.
 *  - Every screen has its own URL (/journey/your-time/ ...) and history entry, so refresh and Back land on the same screen
 *    with the answers shown. The current step is also saved on the server so closing and returning resumes.
 *  - Follow-up questions (property link, "Other") appear and disappear live from the questions' own conditions.
 */
import { el, getJson, postJson, postWithRetry, splitLabel } from './api.js';
import { observeReveals } from './reveal.js';
import { arrowIcon as makeArrow, segmentedEl, tileEl } from './choices.js';
import { dismiss, showMessage } from './messages.js';

const config = JSON.parse(document.getElementById('journey-config').textContent);
const copy = config.copy;
const wrapper = document.querySelector('[data-journey]');
const root = document.querySelector('[data-flow-root]');
const progress = document.querySelector('[data-progress]');
const fill = document.querySelector('[data-progress-fill]');

// Layout choices per question (everything else follows its type).
const PREFER_NOT_SAY = new Set(['industry', 'property_link', 'property_size', 'heard_via']);
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
  saveErrorMessage = showMessage('error', copyOf('save_error').body);
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
const saveStep = (step) => enqueue(() => postWithRetry('/journey/step/', { step }));

/* ---------- building screens ---------- */

const isChecked = (q) => (value) => (answers[q.key]?.options || []).includes(value);

function tile(q, option, kind) {
  return tileEl({
    name: q.key, value: option.value, label: option.label, multi: q.type === 'multi', kind,
    checked: isChecked(q)(option.value), image: config.facilityImages[option.value] || {}, dataset: { q: q.key },
  });
}

function segmented(q) {
  return segmentedEl({ name: q.key, options: q.options, labelledby: `l-${q.key}`, isChecked: isChecked(q), dataset: { q: q.key } });
}

function questionBlock(q) {
  const layout = LAYOUT[q.key] || (q.type === 'scale' ? 'segmented' : q.type === 'multi' ? 'tiles-2' : 'tiles-stack');
  const hidden = !visibleKeys.has(q.key);
  const block = el(q.type === 'text' ? 'div' : 'fieldset', {
    class: `question${parentKey(q) ? ' sub-question' : ''}`, dataset: { question: q.key }, hidden, 'data-reveal': parentKey(q) ? '' : null,
  });
  if (parentKey(q)) block.setAttribute('data-reveal', '');

  if (q.type === 'text') {
    const id = `t-${q.key}`;
    const input = el('input', { type: 'text', id, class: 'input', maxlength: '120', autocomplete: 'off', value: answers[q.key]?.text || '', 'data-q': q.key, 'data-text': '' });
    input.value = answers[q.key]?.text || '';
    block.append(el('div', { class: 'field' }, el('label', { for: id }, q.text, ' ', el('span', { class: 'optional', text: '(optional)' })), input));
    return block;
  }

  const title = el('span', { id: `l-${q.key}`, text: q.text });
  const help = q.help ? el('span', { class: 'question-help', text: q.help }) : null;
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

function actionLabel(number) {
  const last = screenNumbers().slice(-1)[0] === number;
  if (last) return { text: copyOf('last').cta, arrow: true };
  return screenAnswered(number) ? { text: copyOf('continue').cta, arrow: true } : { text: copyOf('skip').cta, arrow: false };
}

function updateAction() {
  const button = root.querySelector('[data-primary]');
  if (!button) return;
  const { text, arrow } = actionLabel(current);
  button.textContent = text;
  if (arrow) button.append(' ', arrowIcon());
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
  const bar = el('div', { class: 'action-bar' }, isFirst ? null : el('button', { type: 'button', class: 'btn-quiet', 'data-back': '', text: copyOf('back').cta }), primary);
  const anyAnswers = Object.values(answers).some((a) => a.options.length || a.text);
  const again = isFirst && anyAnswers ? el('p', { class: 'start-again' }, el('button', { type: 'button', class: 'btn-quiet', 'data-restart': '', text: copyOf('start_again').cta })) : null;
  return el('section', { class: 'screen', 'aria-label': head.heading, 'data-reveal': '' },
    el('div', { class: 'screen-head' }, title, head.body ? el('p', { class: 'lead muted', text: head.body }) : null), body, bar, again);
}

/* ---------- result ---------- */

const money = (amount) => (String(amount).endsWith('.00') ? String(amount).slice(0, -3) : String(amount));
const characterOf = (plan) => `${plan.hours === 'daytime' ? 'Daytime' : 'Any time'}, ${plan.visits_per_month == null ? 'unlimited visits' : `${plan.visits_per_month} visits a month`}.`;
const registerUrl = (slug) => `${config.urls.register}?plan=${encodeURIComponent(slug)}`;

function goldMark() { return el('span', { class: 'mark-glyph', 'aria-hidden': 'true' }); }

function renderResult(data) {
  const s = data.suggested;
  if (!s) {
    return el('section', { class: 'result', tabindex: '-1', 'data-reveal': 'hero' },
      el('h1', { class: 'screen-title', tabindex: '-1', text: 'Thank you.' }),
      el('p', { class: 'lead', text: 'Have a look at the memberships and choose the one that suits you.' }),
      el('div', { class: 'result-actions' }, el('a', { class: 'btn btn-primary', href: config.urls.memberships, text: 'See memberships' })));
  }
  const presentation = data.gold?.presentation || 'none';
  const goldPanelCopy = copyOf('gold_panel');
  const goldLineCopy = copyOf('gold_line');
  const ctaText = copyOf('result_cta').cta.replace('{plan}', s.name);

  const main = el('div', { class: 'result-main', 'data-reveal': 'hero' },
    el('p', { class: 'result-label small', text: copyOf('result_label').body }),
    el('h1', { class: 'display result-tier', tabindex: '-1', text: `${s.name}.` }),
    el('p', { class: 'result-price num', text: `£${money(s.price_ex_vat)} a month, ex VAT (£${s.price_inc_vat} inc VAT)` }),
    el('p', { class: 'result-char', text: characterOf(s) }),
    el('div', { class: 'why' }, el('h2', { text: copyOf('why').heading }), el('ul', { class: 'reasons' }, (s.reasons || []).map((r) => el('li', { text: r })))),
    el('div', { class: 'result-actions' },
      el('a', { class: 'btn btn-primary btn-block-phone', href: registerUrl(s.slug) }, ctaText, ' ', arrowIcon()),
      el('button', { type: 'button', class: 'btn-quiet', 'data-change-answers': '', text: copyOf('change_answers').cta })),
    presentation === 'line'
      ? el('p', { class: 'gold-line-note' }, `${goldLineCopy.body} `, el('a', { href: config.urls.goldApply, text: goldLineCopy.cta }))
      : null);

  const others = (data.others || []).length
    ? el('div', { class: 'others', 'data-reveal': '' }, el('h2', { text: copyOf('others').heading }),
      data.others.map((plan) => el('div', { class: 'other-plan' },
        el('div', {}, el('strong', { text: plan.name }), ' ', el('span', { class: 'muted', text: characterOf(plan) }), plan.not_a_fit ? el('p', { class: 'not-fit', text: plan.hours === 'daytime' ? 'Daytime only' : '' }) : null),
        el('span', { class: 'num', text: `£${money(plan.price_ex_vat)}` }),
        el('a', { class: 'btn-quiet', href: registerUrl(plan.slug), text: copyOf('others').cta.replace('{plan}', plan.name) }))))
    : null;

  const grid = el('div', { class: `result-grid${presentation === 'panel' ? ' has-gold' : ''}` }, main);
  if (presentation === 'panel') {
    grid.append(el('div', { class: 'result-gold', 'data-reveal': '' }, el('div', { class: 'gold-panel' },
      goldMark(), el('h2', { text: goldPanelCopy.heading }), el('p', { text: goldPanelCopy.body }),
      el('a', { class: 'btn btn-primary', href: config.urls.goldApply }, goldPanelCopy.cta, ' ', arrowIcon()))));
  }
  if (others) grid.append(others);
  return el('section', { class: 'result', 'aria-label': copyOf('result_label').body }, grid);
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
  progress.setAttribute('aria-valuetext', onResult ? 'Your membership' : `${name}, part ${index + 1} of ${numbers.length}`);
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
  setSurface(onResult);
  let node;
  if (onResult) {
    root.replaceChildren(el('p', { class: 'muted flow-loading', text: 'One moment' }));
    updateProgress();
    try {
      node = renderResult(await getJson('/journey/result/'));
    } catch {
      showMessage('error', 'We could not load your result just now. Please try again.');
      node = el('section', { class: 'result' }, el('p', { class: 'lead' }, 'Please try again, or ', el('a', { href: config.urls.memberships, text: 'see the memberships' }), '.'));
    }
  } else {
    node = renderQuestionScreen(step);
  }
  root.replaceChildren(node);
  syncVisibility();
  window.scrollTo(0, 0); // instant
  (node.querySelector('h1') || node).focus?.({ preventScroll: true });
  observeReveals(root);
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
  const target = index > 0 ? numbers[index - 1] : numbers[0];
  if ((history.state?.idx || 0) > 0) history.back();
  else go(target, { replace: true });
}

function goNext() {
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
  // A follow-up question that just appeared gets its own reveal.
  observeReveals(root);
}

root.addEventListener('change', (event) => {
  const input = event.target.closest?.('input[data-q]');
  if (!input || input.hasAttribute('data-text')) return;
  const q = questionByKey(input.dataset.q);
  const picked = q.type === 'multi'
    ? [...root.querySelectorAll(`input[data-q="${q.key}"]:checked`)].map((i) => i.value)
    : [input.value];
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
  if (target.hasAttribute('data-primary')) goNext();
  else if (target.hasAttribute('data-back')) goBack();
  else if (target.hasAttribute('data-change-answers')) go(screenNumbers()[0] || 1);
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
    root.replaceChildren(el('p', { class: 'lead' }, 'The guided journey is not available just now. You can ', el('a', { href: config.urls.memberships, text: 'see the memberships' }), '.'));
    return;
  }
  answers = {};
  questions().forEach((q) => {
    if (q.answer) answers[q.key] = { options: q.answer.options || [], text: q.answer.text || '', skipped: Boolean(q.answer.skipped) };
  });
  computeVisible();
  computeResultStep();
  const session = state.session;
  const slug = location.pathname.replace(config.base, '').split('/').filter(Boolean)[0];
  let step = stepForSlug(slug);
  const reachable = (s) => s <= Math.max(session.furthest_step || 1, session.current_step || 1) || session.completed;
  if (!step || !reachable(step) || (step > resultStep) || (step !== resultStep && !screenNumbers().includes(step))) {
    step = Math.min(session.current_step || 1, resultStep);
    if (!screenNumbers().includes(step) && step !== resultStep) step = screenNumbers()[0] || 1;
  }
  history.replaceState({ journey: true, step, idx: history.state?.idx || 0 }, '', urlFor(step));
  await show(step);
}

boot();
