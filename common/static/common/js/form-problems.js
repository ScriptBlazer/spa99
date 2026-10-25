/* Form problems in the shared modal (docs/design/FEEDBACK.md, "Form problems modal"). The rule, for every form with fields:
 * while typing, a problem shows only under the box; on Save / Register / Submit / Sign in with anything wrong, ONE centred
 * dialog lists every problem (field label and short message). Closing it keeps everything filled in and moves to the first
 * problem (focus, then a smooth scroll; instant under reduced motion). Never a page jump alone, never a reset.
 *
 *   <form data-problems>            opt in. Checked on submit before any other handler (so before a risky-change confirm).
 *   <form data-problems="manual">   the page calls collectProblems / showProblems itself (Register, Gold apply).
 *
 * Checked, in page order: the live rules (validate.js, form.spaValidation.problems()), the browser's constraint checks
 * (required, pattern, min ...), and required choices: any element with data-required-group (a fieldset or radiogroup)
 * needs one box or radio checked inside it (data-required-message, data-label).
 * Labels come from data-label, the <label>, the group's <legend> / aria-label, or a table row's data-row-label + aria-label.
 *
 * Server answers on a normal POST (the page re-rendered with errors) open the same dialog once, on load, reading the errors
 * from the DOM: [data-problem] (data-problem-label, data-problem-message, data-problem-field; or its text), the shared
 * field feedback lines ([data-error-for][data-state="error"]) and System's .sys-row.invalid .sys-error. An element outside
 * the form names it with data-problem-form="<form id>". A problem with no field (wrong password) focuses the password.
 * Django empties password boxes on a re-render; everything else it keeps.
 *
 * API: collectProblems(form) -> Promise<[{field, control, label, message}]>, showProblems(scope, problems, { title, opener })
 *      (resolves after the dialog is closed and the first problem is focused), focusFirst(scope, problems),
 *      serverProblems(form), initFormProblems().
 */
import { formModal } from './feedback.js';
import { MESSAGES } from './validate.js';

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const SERVER_SELECTOR = '[data-problem], [data-error-for][data-state="error"], .sys-row.invalid .sys-error';
const SKIP_IN_LABEL = 'select, input, textarea, button, small, .optional, .sr, .sr-only, [data-label-skip]';
const GROUP_MESSAGE = 'Choose one to continue.';

const clean = (text) => (text || '').replace(/\s+/g, ' ').trim().replace(/[:：]$/, '');

function textOf(node) {
  const copy = node.cloneNode(true);
  copy.querySelectorAll(SKIP_IN_LABEL).forEach((item) => item.remove());
  return clean(copy.textContent);
}

const humanise = (name) => clean((name || '').replace(/^.*-/, '').replace(/_/g, ' ')).replace(/^./, (c) => c.toUpperCase());

/** The field's name as a person reads it: data-label, its group's legend, its <label>, aria-label, else the name. */
export function labelOf(control) {
  if (!control) return '';
  const own = control.closest('[data-label]')?.dataset.label;
  if (own) return own;
  const choice = control.type === 'radio' || control.type === 'checkbox';
  const group = control.closest('fieldset, [role="radiogroup"], [role="group"]');
  if (control.type === 'radio' && group) {
    const legend = group.querySelector(':scope > legend');
    const named = (legend && textOf(legend)) || clean(group.getAttribute('aria-label'));
    if (named && !/^(choose|select)\b/i.test(named)) return named;
  }
  const labelled = !choice || control.type === 'checkbox' ? [...(control.labels || [])].map(textOf).find(Boolean) : '';
  const aria = clean(control.getAttribute('aria-label'));
  const row = control.closest('tr[data-row-label]');
  if (row) return [clean(row.dataset.rowLabel), aria || labelled].filter(Boolean).join(' · ');
  if (labelled) return labelled;
  if (aria) return aria;
  const field = control.closest('.field, .sys-row');
  const fromField = field && [...field.querySelectorAll('label')].map(textOf).find(Boolean);
  return fromField || humanise(control.name || control.id);
}

function controlNamed(scope, name) {
  if (!name || name === '__all__') return null;
  const found = scope.elements?.[name] || scope.querySelector?.(`[name="${CSS.escape(name)}"]`) || document.getElementById(name);
  if (!found) return null;
  return found instanceof RadioNodeList ? (found.value ? scope.querySelector(`[name="${CSS.escape(name)}"]:checked`) : found[0]) : found;
}

/** Where focus goes for a problem: the box named (or its data-focus-target), else the password, else the first empty box. */
function targetOf(scope, item) {
  const control = item.control || controlNamed(scope, item.field);
  if (control) {
    const alias = control.dataset?.focusTarget;
    return (alias && (scope.querySelector?.(alias) || document.querySelector(alias))) || control;
  }
  const boxes = [...(scope.querySelectorAll?.('input, select, textarea') || [])].filter((el) => !['hidden', 'checkbox', 'radio', 'submit', 'button'].includes(el.type) && !el.disabled && !el.closest('[hidden]'));
  return boxes.find((el) => el.type === 'password') || boxes.find((el) => !el.value) || boxes[0] || null;
}

const inOrder = (a, b) => {
  const pa = a.target; const pb = b.target;
  if (!pa || !pb || pa === pb) return 0;
  return pa.compareDocumentPosition(pb) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;
};

/** Mark a box (aria-invalid) and, if the form has a feedback line for it, say it there too. Cleared as soon as he edits it. */
function markInline(scope, item) {
  const control = item.control || controlNamed(scope, item.field);
  if (!control?.setAttribute || !item.message) return;
  const form = control.form || scope;
  const shown = form.spaValidation?.showError?.(control.name, item.message);
  if (!shown) {
    const slot = form.querySelector?.(`[data-error-for="${CSS.escape(control.name || '')}"]`);
    if (slot && slot.dataset.state !== 'error') { slot.textContent = item.message; slot.dataset.state = 'error'; }
  }
  const boxes = control.type === 'radio' ? [...(scope.querySelectorAll?.(`[name="${CSS.escape(control.name)}"]`) || [control])] : [control];
  boxes.forEach((box) => box.setAttribute('aria-invalid', 'true'));
  const clear = () => boxes.forEach((box) => box.removeAttribute('aria-invalid'));
  boxes[0].addEventListener('input', clear, { once: true });
  boxes[0].addEventListener('change', clear, { once: true });
}

/** A required choice (data-required-group) with nothing picked: show its own message line if the markup has one. */
function groupSlot(group) {
  return group.closest('fieldset, .field')?.querySelector('[data-group-error]') || group.parentElement?.querySelector('[data-group-error]') || null;
}

function inputsOf(group) { return [...group.querySelectorAll('input[type="radio"], input[type="checkbox"]')]; }

/** Every problem on a form, in page order. Shows the live ones under their boxes; moves nothing. */
export async function collectProblems(form) {
  const items = [];
  const seen = new Set();
  const add = (item) => {
    const key = item.control?.type === 'radio' || !item.control ? item.field || item.message : item.control;
    if (seen.has(key)) return false;
    seen.add(key);
    items.push({ ...item, target: targetOf(form, item) });
    return true;
  };

  const live = (await form.spaValidation?.problems?.()) || [];
  live.forEach(({ field, name, message }) => add({ field: name, control: field, label: labelOf(field), message }));

  [...form.elements].forEach((el) => {
    if (!el.willValidate || !el.name || el.type === 'hidden' || el.checkValidity()) return;
    // One calm wording for an empty required box on every host (the browser's own varies with its language).
    const message = el.validity.valueMissing ? (el.dataset.requiredMessage || MESSAGES.required || 'This field is required.') : el.validationMessage;
    if (!message) return;
    if (add({ field: el.name, control: el, label: labelOf(el), message })) markInline(form, { control: el, message }); // the live rules already worded (and showed) theirs
  });

  document.querySelectorAll('[data-required-group]').forEach((group) => {
    const boxes = inputsOf(group);
    if (!boxes.length || boxes[0].form !== form || boxes.some((box) => box.checked) || boxes.every((box) => box.disabled)) return;
    const message = group.dataset.requiredMessage || GROUP_MESSAGE;
    const slot = groupSlot(group);
    if (slot) { slot.textContent = message; slot.hidden = false; if (slot.dataset.state !== undefined) slot.dataset.state = 'error'; }
    const clear = () => { if (slot) slot.hidden = true; };
    group.addEventListener('change', clear, { once: true });
    add({ field: boxes[0].name, control: boxes[0], label: group.dataset.label || labelOf(boxes[0]), message });
  });

  return items.sort(inOrder);
}

/** Reveal a box that sits in a closed "More" row or <details> so it can be focused. */
function reveal(target) {
  target.closest('details:not([open])')?.setAttribute('open', '');
  const sub = target.closest('tr.sys-sub:not([data-open])');
  if (sub?.id) document.querySelector(`[aria-controls="${CSS.escape(sub.id)}"]`)?.click();
}

/** After the dialog: first problem focused, then scrolled to the middle (smooth; instant if he asked for less motion). */
export function focusFirst(scope, problems) {
  const target = problems.map((item) => item.target || targetOf(scope, item)).find(Boolean);
  if (!target) return;
  reveal(target);
  target.focus({ preventScroll: true });
  const box = target.closest('.field, .sys-row, tr, fieldset, .plan-picker') || target;
  box.scrollIntoView({ block: 'center', behavior: reduceMotion.matches ? 'auto' : 'smooth' });
}

/** The shared dialog with the list. Resolves once it is closed and the first problem is focused. `scope` is the form (or
 *  the element that holds the fields). problems: [{ field | control, label, message }]. */
export async function showProblems(scope, problems, { title, opener } = {}) {
  if (!problems?.length) return;
  const many = problems.length > 1;
  await formModal((dialog, close) => {
    const heading = document.createElement('h2');
    heading.className = 'fb-modal-title';
    heading.id = 'fb-problems-title';
    heading.textContent = title || (many ? 'A few things to check' : 'One thing to check');
    const list = document.createElement('ul');
    list.className = 'fb-problems';
    problems.forEach((item) => {
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
  }, { opener: opener || document.activeElement });
  focusFirst(scope, problems);
}

/** What the server drew on a re-rendered form: [{ field, label, message }] (see the header for the markup). */
export function serverProblems(form) {
  const scopes = [form, ...(form.id ? document.querySelectorAll(`[data-problem-form="${CSS.escape(form.id)}"]`) : [])];
  const nodes = [...new Set(scopes.flatMap((scope) => [...(scope.matches?.(SERVER_SELECTOR) ? [scope] : []), ...scope.querySelectorAll(SERVER_SELECTOR)]))];
  const items = [];
  nodes.forEach((node) => {
    if (node.closest('[hidden]')) return;
    const data = node.dataset;
    const field = data.problemField || data.errorFor || node.closest('.sys-row')?.dataset.systemField || '';
    const control = controlNamed(form, field);
    const message = (data.problemMessage ?? node.textContent).replace(/\s+/g, ' ').trim();
    if (!message) return;
    const label = data.problemLabel ?? (control ? labelOf(control) : '');
    if (items.some((item) => item.field === field && item.message === message && item.label === label)) return;
    items.push({ field, control, label, message });
  });
  return items;
}

/* ---------- start ---------- */

const mode = (form) => form.getAttribute('data-problems');
const wants = (form) => form instanceof HTMLFormElement && mode(form) !== null && mode(form) !== 'manual';
const later = () => new Promise((resolve) => { setTimeout(resolve, 0); });

async function onSubmit(event) {
  const form = event.target;
  if (!wants(form)) return;
  form.noValidate = true; // our dialog replaces the browser's bubbles
  if (form.dataset.problemsOk === 'true' || form.dataset.validated === 'true') return; // our own (or validate.js's) re-submit
  event.preventDefault();
  event.stopImmediatePropagation();
  if (form.dataset.problemsBusy === 'true') return;
  form.dataset.problemsBusy = 'true';
  const submitter = event.submitter && event.submitter.form === form ? event.submitter : undefined;
  try {
    const problems = await collectProblems(form);
    if (problems.length) { await showProblems(form, problems, { opener: submitter }); return; }
    form.dataset.problemsOk = 'true';
    if (form.spaValidation) form.dataset.validated = 'true'; // already checked: validate.js need not do it twice
    await later(); // a real click or Enter is still being dispatched: requestSubmit() is ignored until it ends
    try { form.requestSubmit(submitter); } finally { delete form.dataset.problemsOk; delete form.dataset.validated; }
  } finally {
    delete form.dataset.problemsBusy;
  }
}

/** A [data-confirm] button (delete my account) asks only once the form itself is in order. */
async function onConfirmClick(event) {
  const trigger = event.target.closest?.('[data-confirm]');
  const form = trigger?.form;
  if (!trigger || !wants(form) || trigger.dataset.problemsChecked === 'true') return;
  event.preventDefault();
  event.stopImmediatePropagation();
  const problems = await collectProblems(form);
  if (problems.length) { await showProblems(form, problems, { opener: trigger }); return; }
  trigger.dataset.problemsChecked = 'true';
  try { trigger.click(); } finally { delete trigger.dataset.problemsChecked; }
}

let started = false;
/** Once per page. Safe to call from every entry file; the listeners sit on the document, so forms built later work too. */
export function initFormProblems() {
  if (started) return;
  started = true;
  document.querySelectorAll('form[data-problems]').forEach((form) => { form.noValidate = true; });
  document.addEventListener('submit', onSubmit, true);
  document.addEventListener('click', onConfirmClick, true);
  window.addEventListener('pageshow', () => {
    document.querySelectorAll('form[data-problems]').forEach((form) => { delete form.dataset.problemsBusy; delete form.dataset.problemsOk; });
  });
  // A server re-render with errors: the same dialog, once, for the first form that has any.
  setTimeout(() => {
    for (const form of document.querySelectorAll('form[data-problems]')) {
      const items = serverProblems(form);
      if (!items.length) continue;
      showProblems(form, items, { opener: form.querySelector('button[type="submit"]') });
      break;
    }
  }, 0);
}
