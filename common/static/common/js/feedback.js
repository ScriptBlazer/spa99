/* Feedback: the one toast and the one modal for every host (public site, member area, Office, System, Control).
 * Spec: docs/design/FEEDBACK.md. Markup: common/_feedback.html (toast regions, server messages, the shared <dialog>).
 *
 * Toasts:  toast('Saved.')  toast("We couldn't save that. Please try again.", { kind: 'error' })
 *          toast('All music muted.', { action: { label: 'Undo', onClick: () => ... } })
 * Modals:  if (await confirmModal({ title: 'Delete your account?', body: '...', confirmLabel: 'Delete account', tone: 'danger' })) { ... }
 *          await alertModal({ title: 'Your session ended.', body: 'Sign in again.', tone: 'error' })
 *          Markup: <button data-confirm data-confirm-title="..." data-confirm-body="..." data-confirm-label="..." data-confirm-danger>
 *          (data-confirm-message is the old name for data-confirm-body and still works.)
 *
 * Never window.alert/confirm/prompt, not even as a fallback. Without <dialog>.showModal the same markup is shown as a
 * <div role="dialog"> in a fixed overlay. Nothing ever resolves true unless the person chose it.
 */

import { setWorking } from './buttons.js';

const MAX_TOASTS = 3;
const SHAPES = {
  success: '<circle cx="8" cy="8" r="6.25"/><path d="m5.25 8.25 1.9 1.9 3.6-4"/>',
  info: '<circle cx="8" cy="8" r="6.25"/><path d="M8 7.25v3.5M8 5.25h.01"/>',
  warning: '<path d="M8 2.5 14.25 13.25H1.75Z"/><path d="M8 6.5v3M8 11.5h.01"/>',
  error: '<circle cx="8" cy="8" r="6.25"/><path d="M8 4.75v3.5M8 10.75h.01"/>',
};
const PREFIX = { success: 'Done: ', info: 'Note: ', warning: 'Warning: ', error: 'Error: ' };
const CLOSE_SHAPE = '<path d="M2 2l8 8M10 2l-8 8"/>';
const reducedMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

function svg(shape, size, className) {
  const el = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  el.setAttribute('viewBox', `0 0 ${size} ${size}`);
  el.setAttribute('width', String(size));
  el.setAttribute('height', String(size));
  el.setAttribute('fill', 'none');
  el.setAttribute('stroke', 'currentColor');
  el.setAttribute('stroke-width', '1.5');
  el.setAttribute('stroke-linecap', 'round');
  el.setAttribute('stroke-linejoin', 'round');
  el.setAttribute('aria-hidden', 'true');
  el.setAttribute('focusable', 'false');
  if (className) el.setAttribute('class', className);
  el.innerHTML = shape;
  return el;
}

/* ---------- toasts ---------- */

let sequence = 0;

function regions() {
  let section = document.querySelector('.toasts');
  if (!section) {
    section = document.createElement('section');
    section.className = 'toasts';
    section.setAttribute('aria-label', 'Notifications');
    section.innerHTML = '<ol class="toasts-list" role="status" aria-live="polite" data-toasts-polite></ol><ol class="toasts-list" role="alert" aria-live="assertive" data-toasts-assertive></ol>';
    document.body.append(section);
  }
  return { section, polite: section.querySelector('[data-toasts-polite]'), assertive: section.querySelector('[data-toasts-assertive]') };
}

const liveToasts = (section) => [...section.querySelectorAll('.toast:not([data-leaving])')].sort((a, b) => Number(a.dataset.seq) - Number(b.dataset.seq));

function removeNow(element) {
  element._cleanup?.();
  element.remove();
}

export function dismiss(element) {
  if (!element || element.dataset.leaving !== undefined) return;
  element.dataset.leaving = '';
  element._cleanup?.();
  if (reducedMotion()) { element.remove(); return; }
  setTimeout(() => element.remove(), 160);
}

function defaultTimeout(kind, hasAction) {
  if (kind === 'error') return 0;                  // stays until dismissed, or until the cause clears (dismiss)
  if (hasAction || kind === 'warning') return 6000;
  return 4000;
}

/** Timers pause on hover, on focus inside the toast, and while the tab is hidden. */
function startTimer(element, ms) {
  if (!ms) return;
  let left = ms;
  let startedAt = 0;
  let timer = 0;
  const holds = new Set();
  const run = () => {
    if (holds.size || startedAt || element.dataset.leaving !== undefined) return;
    startedAt = performance.now();
    timer = setTimeout(() => dismiss(element), left);
  };
  const pause = () => {
    if (!startedAt) return;
    clearTimeout(timer);
    left -= performance.now() - startedAt;
    startedAt = 0;
  };
  const hold = (reason) => { holds.add(reason); pause(); };
  const release = (reason) => { holds.delete(reason); run(); };
  const mouse = (event) => event.pointerType === 'mouse';
  element.addEventListener('pointerenter', (event) => { if (mouse(event)) hold('hover'); });
  element.addEventListener('pointerleave', (event) => { if (mouse(event)) release('hover'); });
  element.addEventListener('focusin', () => hold('focus'));
  element.addEventListener('focusout', (event) => { if (!element.contains(event.relatedTarget)) release('focus'); });
  const visibility = () => (document.hidden ? hold('hidden') : release('hidden'));
  document.addEventListener('visibilitychange', visibility);
  element._cleanup = () => { clearTimeout(timer); document.removeEventListener('visibilitychange', visibility); };
  if (document.hidden) holds.add('hidden');
  run();
}

export function toast(text, { kind = 'success', action, timeout } = {}) {
  const shown = SHAPES[kind] ? kind : 'info';
  const { section, polite, assertive } = regions();
  const message = String(text ?? '');

  // The same text twice in a row replaces the old one: no duplicates.
  liveToasts(section).filter((old) => old.dataset.text === message && old.dataset.kind === shown).forEach(removeNow);
  // Max three: a fourth removes the oldest non-error toast; if all are errors, the oldest error.
  let live = liveToasts(section);
  while (live.length >= MAX_TOASTS) {
    removeNow(live.find((old) => old.dataset.kind !== 'error') || live[0]);
    live = liveToasts(section);
  }

  const element = document.createElement('li');
  element.className = 'toast';
  element.dataset.kind = shown;
  element.dataset.text = message;
  element.dataset.seq = String((sequence += 1));
  element.style.order = element.dataset.seq; // newest at the bottom, across both live regions

  const icon = document.createElement('span');
  icon.className = 'toast-icon';
  icon.append(svg(SHAPES[shown], 16));
  const body = document.createElement('p');
  body.className = 'toast-text';
  const prefix = document.createElement('span');
  prefix.className = 'visually-hidden';
  prefix.textContent = PREFIX[shown];
  body.append(prefix, message);
  element.append(icon, body);

  if (action?.label) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'toast-action';
    button.textContent = action.label;
    button.addEventListener('click', () => { action.onClick?.(); dismiss(element); });
    element.append(button);
  }
  const close = document.createElement('button');
  close.type = 'button';
  close.className = 'toast-close';
  close.setAttribute('aria-label', 'Dismiss');
  close.append(svg(CLOSE_SHAPE, 12));
  close.addEventListener('click', () => dismiss(element));
  element.append(close);

  (shown === 'error' ? assertive : polite).append(element);
  void element.offsetWidth; // commit the resting-below state so the entrance transitions
  element.dataset.in = '';
  startTimer(element, timeout === undefined ? defaultTimeout(shown, !!action?.label) : timeout);
  return element;
}

/** Posts an undo link from a server message (System): a real form POST, so the server stays the one that undoes. */
export function postUndo(url) {
  if (!url.startsWith('/')) return;
  const form = document.createElement('form');
  form.method = 'post';
  form.action = url;
  const token = document.querySelector('#system-csrf')?.content?.querySelector('input')?.cloneNode()
    || Object.assign(document.createElement('input'), { type: 'hidden', name: 'csrfmiddlewaretoken', value: (document.cookie.match(/(?:^|; )csrftoken=([^;]*)/) || [])[1] || '' });
  const next = Object.assign(document.createElement('input'), { type: 'hidden', name: 'next', value: location.pathname + location.search });
  form.append(token, next);
  document.body.append(form);
  document.dispatchEvent(new CustomEvent('spa99:leaving')); // System: no "unsaved changes" prompt for this one
  form.submit();
}

/** Server messages are rendered as a <template>; they are shown 100ms after load so screen readers announce them. */
function showServerMessages(template = document.querySelector('template[data-server-messages]')) {
  if (!template) return;
  const items = [...template.content.querySelectorAll('li')];
  template.remove();
  if (!items.length) return;
  setTimeout(() => {
    items.forEach((item) => {
      const undo = item.dataset.undo || '';
      toast(item.textContent.trim(), {
        kind: item.dataset.kind || 'info',
        action: undo ? { label: 'Undo', onClick: () => postUndo(undo) } : undefined,
      });
    });
  }, 100);
}

/** Toasts for the messages of a fetched page (Office swaps content without a reload). */
export function toastsFromDocument(doc) {
  doc.querySelector('template[data-server-messages]')?.content.querySelectorAll('li').forEach((item) => {
    toast(item.textContent.trim(), { kind: item.dataset.kind || 'info' });
  });
}

/* ---------- the modal ---------- */

const MODAL_HTML = `<div class="fb-modal-wrap">
  <div data-fb-standard>
    <h2 class="fb-modal-title" id="fb-modal-title"><svg class="fb-modal-icon" data-fb-icon hidden aria-hidden="true" focusable="false"></svg><span data-fb-title></span></h2>
    <div class="fb-modal-details" data-fb-details hidden></div>
    <p class="fb-modal-body" id="fb-modal-body" data-fb-body></p>
    <label class="fb-modal-guard" data-fb-guard hidden><span>Type <b data-fb-word></b> to confirm</span><input type="text" autocomplete="off" spellcheck="false" data-fb-input></label>
    <div class="fb-modal-actions">
      <button type="button" class="fb-btn fb-btn--secondary" data-fb-cancel>Cancel</button>
      <button type="button" class="fb-btn fb-btn--primary" data-fb-ok>Confirm</button>
    </div>
  </div>
  <div class="fb-modal-custom" data-fb-custom hidden></div>
</div>`;

const nativeDialog = () => typeof HTMLDialogElement === 'function' && typeof HTMLDialogElement.prototype.showModal === 'function';

function sharedDialog() {
  let dialog = document.querySelector('dialog.fb-modal[data-fb-modal]');
  if (!dialog) {
    dialog = document.createElement('dialog');
    dialog.className = 'fb-modal';
    dialog.dataset.fbModal = '';
    dialog.setAttribute('aria-labelledby', 'fb-modal-title');
    dialog.setAttribute('aria-describedby', 'fb-modal-body');
    dialog.innerHTML = MODAL_HTML;
    document.body.append(dialog);
  }
  return dialog;
}

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

// A second call while one is open queues; it never replaces the open one.
const waiting = [];
let busy = false;
function enqueue(job, fallback) {
  return new Promise((resolve) => {
    waiting.push({ job, fallback, resolve });
    pump();
  });
}
async function pump() {
  if (busy) return;
  const next = waiting.shift();
  if (!next) return;
  busy = true;
  try { next.resolve(await next.job()); } catch { next.resolve(next.fallback); } finally { busy = false; pump(); }
}

/** Opens the shell (native <dialog> or the overlay fallback). `prepare({ root, finish, signal })` fills it and returns the element to focus. */
function showShell(prepare, cancelValue, opener) {
  return new Promise((resolve) => {
    const native = nativeDialog();
    const template = sharedDialog();
    const control = new AbortController();
    const { signal } = control;
    let root = template;
    let overlay = null;
    const inerted = [];
    if (!native) {
      overlay = document.createElement('div');
      overlay.className = 'fb-overlay';
      root = document.createElement('div');
      root.className = 'fb-modal fb-modal--fallback';
      root.setAttribute('role', 'dialog');
      root.setAttribute('aria-modal', 'true');
      root.innerHTML = template.innerHTML;
      root.querySelectorAll('[id]').forEach((node) => { node.id += '-fallback'; });
      root.setAttribute('aria-labelledby', 'fb-modal-title-fallback');
      root.setAttribute('aria-describedby', 'fb-modal-body-fallback');
      overlay.append(root);
    }
    let finished = false;
    const finish = (value) => {
      if (finished) return;
      finished = true;
      control.abort();
      root.querySelector('[data-fb-custom]')?.replaceChildren();
      if (native) { if (root.open) root.close(); } else {
        overlay.remove();
        inerted.forEach((node) => { node.inert = false; });
      }
      if (opener && opener.isConnected && typeof opener.focus === 'function') opener.focus({ preventScroll: true });
      resolve(value);
    };

    let focusTarget;
    try { focusTarget = prepare({ root, finish, signal, native }); } catch { finish(cancelValue); return; }

    if (native) {
      root.addEventListener('cancel', (event) => { event.preventDefault(); finish(cancelValue); }, { signal }); // Esc
      root.addEventListener('close', () => finish(cancelValue), { signal });                                    // a form button with method=dialog
      let downOnBackdrop = false;
      root.addEventListener('pointerdown', (event) => { downOnBackdrop = event.target === root; }, { signal });
      root.addEventListener('click', (event) => { if (event.target === root && downOnBackdrop) finish(cancelValue); }, { signal });
      try { root.showModal(); } catch { finish(cancelValue); return; }
    } else {
      [...document.body.children].forEach((node) => { if (!node.inert) { node.inert = true; inerted.push(node); } });
      document.body.append(overlay);
      let downOnBackdrop = false;
      overlay.addEventListener('pointerdown', (event) => { downOnBackdrop = event.target === overlay; }, { signal });
      overlay.addEventListener('click', (event) => { if (event.target === overlay && downOnBackdrop) finish(cancelValue); }, { signal });
      root.querySelector('[data-fb-custom]')?.addEventListener('submit', (event) => { event.preventDefault(); finish(cancelValue); }, { signal });
      window.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); finish(cancelValue); return; }
        if (event.key !== 'Tab') return;
        const items = [...root.querySelectorAll(FOCUSABLE)].filter((node) => !node.closest('[hidden]') && node.offsetParent !== null);
        if (!items.length) { event.preventDefault(); return; }
        const first = items[0];
        const last = items[items.length - 1];
        if (event.shiftKey && (document.activeElement === first || !root.contains(document.activeElement))) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && (document.activeElement === last || !root.contains(document.activeElement))) { event.preventDefault(); first.focus(); }
      }, { signal, capture: true });
    }
    (focusTarget || root.querySelector(FOCUSABLE) || root).focus?.();
  });
}

function prepareStandard(root, { title, body, details, icon, okLabel, okTone, cancelLabel, hasCancel, guard }) {
  const q = (selector) => root.querySelector(selector);
  const standard = q('[data-fb-standard]');
  const custom = q('[data-fb-custom]');
  custom.hidden = true;
  custom.replaceChildren();
  standard.hidden = false;
  delete root.dataset.mode;
  root.setAttribute('aria-labelledby', root.classList.contains('fb-modal--fallback') ? 'fb-modal-title-fallback' : 'fb-modal-title');
  root.dataset.tone = okTone;

  q('[data-fb-title]').textContent = title || '';
  const mark = q('[data-fb-icon]');
  if (icon) { mark.setAttribute('viewBox', '0 0 16 16'); mark.setAttribute('stroke-width', '1.5'); mark.setAttribute('fill', 'none'); mark.setAttribute('stroke', 'currentColor'); mark.setAttribute('stroke-linecap', 'round'); mark.setAttribute('stroke-linejoin', 'round'); mark.dataset.kind = icon; mark.innerHTML = SHAPES[icon]; }
  mark.hidden = !icon;

  const detailsBox = q('[data-fb-details]');
  detailsBox.replaceChildren();
  if (details) detailsBox.append(details);
  detailsBox.hidden = !details;

  const bodyEl = q('[data-fb-body]');
  bodyEl.textContent = body || '';
  bodyEl.hidden = !body;
  if (body) root.setAttribute('aria-describedby', bodyEl.id); else root.removeAttribute('aria-describedby');

  const ok = q('[data-fb-ok]');
  const cancel = q('[data-fb-cancel]');
  ok.textContent = okLabel;
  ok.className = `fb-btn fb-btn--${okTone === 'danger' ? 'danger' : 'primary'}`;
  cancel.textContent = cancelLabel;
  cancel.hidden = !hasCancel;

  const guardBox = q('[data-fb-guard]');
  const input = q('[data-fb-input]');
  guardBox.hidden = !guard;
  input.value = '';
  q('[data-fb-word]').textContent = guard || '';
  ok.disabled = !!guard;
  return { ok, cancel, input };
}

/** Resolves true only when the person chooses the confirm button. Esc, backdrop and Cancel resolve false. */
export function confirmModal(options = {}) {
  const {
    title, body = options.message, confirmLabel = 'Confirm', cancelLabel = 'Cancel', details, guard,
    tone = options.danger ? 'danger' : 'neutral',
  } = options;
  const opener = options.opener || document.activeElement;
  return enqueue(() => showShell(({ root, finish, signal }) => {
    const { ok, cancel, input } = prepareStandard(root, {
      title, body, details, icon: '', okLabel: confirmLabel, okTone: tone, cancelLabel, hasCancel: true, guard,
    });
    ok.addEventListener('click', () => finish(true), { signal });
    cancel.addEventListener('click', () => finish(false), { signal });
    if (guard) input.addEventListener('input', () => { ok.disabled = input.value.trim() !== guard; }, { signal });
    return tone === 'danger' || guard ? cancel : ok; // destructive confirms focus Cancel first
  }, false, opener), false);
}

/** One button; resolves when it closes. Tones warning and error show the icon. */
export function alertModal(options = {}) {
  const { title, body = options.message, tone = 'info', closeLabel = 'Close' } = options;
  const opener = options.opener || document.activeElement;
  return enqueue(() => showShell(({ root, finish, signal }) => {
    const { ok } = prepareStandard(root, {
      title, body, icon: tone === 'warning' || tone === 'error' ? tone : '', okLabel: closeLabel, okTone: 'neutral', cancelLabel: '', hasCancel: false,
    });
    ok.addEventListener('click', () => finish(undefined), { signal });
    return ok;
  }, undefined, opener), undefined);
}

/** A small form in the same dialog (Control). `build(form, close)` fills a <form method="dialog">; resolves with whatever
 *  close() was given, or null when it is dismissed. */
export function formModal(build, options = {}) {
  const opener = options.opener || document.activeElement;
  return enqueue(() => showShell(({ root, finish }) => {
    const standard = root.querySelector('[data-fb-standard]');
    const stale = root.querySelector('[data-fb-custom]');
    const custom = document.createElement('form'); // a fresh form each time: no handler from the last dialog survives
    custom.method = 'dialog';
    custom.className = 'fb-modal-custom';
    custom.dataset.fbCustom = '';
    stale.replaceWith(custom);
    standard.hidden = true;
    custom.hidden = false;
    root.dataset.mode = 'form';
    build(custom, (value) => finish(value));
    const heading = custom.querySelector('[id]');
    if (heading) root.setAttribute('aria-labelledby', heading.id);
    root.removeAttribute('aria-describedby');
    return custom.querySelector('[autofocus]') || custom.querySelector(FOCUSABLE);
  }, null, opener), null);
}

/** A note box in the same dialog (Office "Send back for review"). Resolves with the text (may be '') when confirmed, or null when
 *  it is cancelled, closed with Esc or the backdrop. The text is cut to `max` by the box itself. */
export function noteModal(options = {}) {
  const { title, body, label = 'Note', max = 1000, confirmLabel = 'Send', cancelLabel = 'Cancel' } = options;
  const opener = options.opener || document.activeElement;
  return formModal((form, close) => {
    const heading = document.createElement('h2');
    heading.className = 'fb-modal-title';
    heading.id = 'fb-note-title';
    heading.textContent = title || '';
    form.append(heading);
    if (body) { const text = document.createElement('p'); text.className = 'fb-modal-body'; text.textContent = body; form.append(text); }
    const field = document.createElement('label');
    field.className = 'fb-modal-field';
    const name = document.createElement('span');
    name.textContent = label;
    const box = document.createElement('textarea');
    box.className = 'fb-modal-textarea';
    box.rows = 4;
    box.maxLength = max;
    box.setAttribute('autofocus', '');
    const count = document.createElement('span');
    count.className = 'fb-modal-count';
    count.setAttribute('aria-hidden', 'true');
    const paint = () => { count.textContent = `${box.value.length} / ${max}`; };
    box.addEventListener('input', paint);
    paint();
    field.append(name, box, count);
    const actions = document.createElement('div');
    actions.className = 'fb-modal-actions';
    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'fb-btn fb-btn--secondary';
    cancel.textContent = cancelLabel;
    cancel.addEventListener('click', () => close(null));
    const ok = document.createElement('button');
    ok.type = 'submit';
    ok.className = 'fb-btn fb-btn--primary';
    ok.textContent = confirmLabel;
    actions.append(cancel, ok);
    form.append(field, actions);
    form.addEventListener('submit', (event) => { event.preventDefault(); close(box.value.trim()); });
  }, { opener });
}

/** [data-confirm] on a button or link: ask first, then do what it would have done. */
export function initConfirm(root = document) {
  root.addEventListener('click', async (event) => {
    const trigger = event.target.closest?.('[data-confirm]');
    if (!trigger || trigger.dataset.confirmed === 'true') return;
    event.preventDefault();
    const data = trigger.dataset;
    const accepted = await confirmModal({
      title: data.confirmTitle,
      body: data.confirmBody ?? data.confirmMessage,
      confirmLabel: data.confirmLabel || 'Confirm',
      cancelLabel: data.confirmCancel || 'Cancel',
      tone: trigger.hasAttribute('data-confirm-danger') || data.confirmTone === 'danger' ? 'danger' : 'neutral',
      opener: trigger,
    });
    if (!accepted) return;
    trigger.dataset.confirmed = 'true';
    try {
      if (trigger.form) trigger.form.requestSubmit(trigger);
      else if (trigger.href) window.location.assign(trigger.href);
      else setWorking(trigger);
    } finally {
      delete trigger.dataset.confirmed; // used once: the next click always asks again
    }
  });
  // Back button (bfcache) can restore the page as it was: make sure nothing stays pre-confirmed.
  window.addEventListener('pageshow', () => {
    root.querySelectorAll?.('[data-confirmed]').forEach((node) => delete node.dataset.confirmed);
  });
}

/* ---------- start ---------- */

let started = false;
/** Once per page: the regions exist from load, server messages appear, [data-confirm] works. */
export function initFeedback() {
  if (started) return;
  started = true;
  regions();
  showServerMessages();
  initConfirm();
}

window.spa99Feedback = { toast, dismiss, confirmModal, alertModal, formModal, noteModal };
