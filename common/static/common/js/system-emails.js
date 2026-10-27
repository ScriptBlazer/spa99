/* System > Emails behaviour (docs/design/SYSTEM-EMAILS.md). Loaded on the Emails pages only. Every page still works as plain forms where it can;
   this adds the live parts: the token editor and the real-email preview, group counts, sending progress, the invite list check.
   Toasts, the confirm modal and the problems modal are the shared ones (feedback.js, form-problems.js).
   Sections: helpers, token editor, preview, automatic email, group composer (the parts editor is system-email-builder.js), sending progress, invites, overview, start. */
import { toast, confirmModal } from './feedback.js';
import { collectProblems, showProblems } from './form-problems.js';
import { initBuilder } from './system-email-builder.js';

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const IS_LIVE = (document.body.dataset.env || '').toLowerCase() === 'live';
const reduced = matchMedia('(prefers-reduced-motion: reduce)');

/* ---------- helpers ---------- */

const csrf = () => $('#system-csrf')?.content.querySelector('input')?.value || '';
const fmt = (n) => Number(n || 0).toLocaleString('en-GB');
const plural = (n, one, many) => (n === 1 ? one : many);
const esc = (text) => text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const debounce = (fn, ms) => { let timer = 0; const run = (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); }; run.cancel = () => clearTimeout(timer); return run; };
const NETWORK = 'Could not reach System. Your work is still here.';

/** POST (or GET) as a script: JSON back where the endpoint speaks it. Resolves { ok, status, data, response }; a network failure resolves { ok: false, status: 0 }. */
async function call(url, { method = 'POST', body, signal, json = true } = {}) {
  const headers = { 'X-CSRFToken': csrf(), 'X-Requested-With': 'fetch' };
  if (json) headers.Accept = 'application/json';
  try {
    const response = await fetch(url, { method, body: body instanceof FormData || body instanceof URLSearchParams ? body : body ? new URLSearchParams(body) : undefined, credentials: 'same-origin', headers, signal });
    let data = null;
    if (json) { try { data = await response.clone().json(); } catch { data = null; } }
    return { ok: response.ok, status: response.status, data, response };
  } catch (error) {
    if (error.name === 'AbortError') return { ok: false, status: -1, aborted: true };
    return { ok: false, status: 0, data: null };
  }
}

// A toast that survives the next page load (a send ends by opening the detail page).
const flash = (text, kind = 'success') => { try { sessionStorage.setItem('se-flash', JSON.stringify({ text, kind })); } catch { /* blocked */ } };
function showFlash() {
  let item = null;
  try { item = JSON.parse(sessionStorage.getItem('se-flash') || 'null'); sessionStorage.removeItem('se-flash'); } catch { /* blocked */ }
  if (item?.text) setTimeout(() => toast(item.text, { kind: item.kind }), 150);
}

const whenText = (date, time) => {
  if (!date) return '';
  const d = new Date(`${date}T${time || '09:00'}:00`);
  if (Number.isNaN(d.getTime())) return '';
  const day = d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' }).replace(',', '');
  return `${day}, ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
};

/* ---------- token editor: a transparent textarea over an aria-hidden pre (the code view technique, placeholders only) ---------- */

const TOKEN = /\{([A-Za-z_][A-Za-z0-9_]*)\}/g;

function drawTokens(text, known) {
  let html = '';
  let last = 0;
  for (const match of text.matchAll(TOKEN)) {
    html += esc(text.slice(last, match.index));
    html += `<mark class="se-tk${known.has(match[1]) ? '' : ' bad'}">${esc(match[0])}</mark>`;
    last = match.index + match[0].length;
  }
  return `${html}${esc(text.slice(last))}\n `; // the extra line keeps the caret line visible and both layers the same height
}

/** What is wrong with a piece of text, in plain words, and where the first bad placeholder starts. */
function problemsIn(text, known, { needButton = false } = {}) {
  const names = [...text.matchAll(TOKEN)];
  const bad = names.filter((m) => !known.has(m[1]));
  const unique = [...new Set(bad.map((m) => m[1]))];
  let message = '';
  if (unique.length) message = `{${unique[0]}} is not a placeholder for this email. Pick one from the list.${unique.length > 1 ? ` ${unique.length - 1} more below.` : ''}`;
  else if (needButton && text.trim() && !names.some((m) => m[1] === 'button')) message = 'This email needs {button} on a line of its own, so people can use the link.';
  else if (names.filter((m) => m[1] === 'button').length > 1) message = 'Use {button} once.';
  return { message, at: bad.length ? [bad[0].index, bad[0].index + bad[0][0].length] : null };
}

/** Insert text at the caret of an input or textarea (replacing a selection), tell the page it changed, and return focus there. */
function insertAt(field, text, { block = false } = {}) {
  field.focus();
  const start = field.selectionStart ?? field.value.length;
  const end = field.selectionEnd ?? start;
  let put = text;
  if (block) { // {button} sits on a line of its own
    const before = field.value.slice(0, start);
    const after = field.value.slice(end);
    const lead = !before ? '' : before.endsWith('\n\n') ? '' : before.endsWith('\n') ? '\n' : '\n\n';
    const tail = !after ? '' : after.startsWith('\n\n') ? '' : after.startsWith('\n') ? '\n' : '\n\n';
    put = `${lead}${text}${tail}`;
  }
  field.setRangeText(put, start, end, 'end');
  field.dispatchEvent(new Event('input', { bubbles: true }));
  field.focus();
}

/** The placeholder fields shared by the automatic email editor and the group composer.
 *  known: { subject: Set, body: Set }; needButton: the body must hold {button}. Returns hooks the page uses. */
function wordingFields(form, { known, needButton = false, ownPalette = false, onChange = () => {} }) {
  const subject = $('[data-se-subject]', form);
  const body = $('[data-se-body]', form);
  const pre = $('.se-pre', form);
  const live = { subject: $('[data-se-live="subject"]', form), body: $('[data-se-live="body"]', form) };
  const palette = $('[data-se-palette]', form);
  let focused = body || subject;
  let server = {}; // problems the server found while drawing the preview (stray braces, ...), by field
  const state = { subject: { message: '', at: null }, body: { message: '', at: null } };

  const show = (name, el) => {
    const local = state[name].message;
    const message = local || (server[name] || [])[0] || '';
    if (el) { el.setCustomValidity(message); if (message) el.setAttribute('aria-invalid', 'true'); else el.removeAttribute('aria-invalid'); }
    if (live[name]) { live[name].textContent = message; live[name].hidden = !message; }
  };

  function check() {
    if (subject) { state.subject = problemsIn(subject.value, known.subject); show('subject', subject); }
    if (body) {
      state.body = problemsIn(body.value, known.body, { needButton });
      if (pre) pre.innerHTML = drawTokens(body.value, known.body);
      show('body', body);
    }
    syncPalette();
  }

  function syncPalette() {
    if (!palette) return;
    const scope = focused === subject ? 'subject' : 'body';
    let any = false;
    $$('[data-scope]', palette).forEach((button) => {
      const on = button.dataset.scope === 'both' || button.dataset.scope === scope;
      button.toggleAttribute('data-on', on);
      any = any || on;
    });
    const label = $('.se-palette-label, [data-se-palette-label]', palette);
    if (label && subject && body) label.textContent = scope === 'subject' ? 'Placeholders for the subject' : 'Placeholders for the body';
    $('[data-se-palette-none]', palette)?.toggleAttribute('hidden', any);
  }

  [subject, body].filter(Boolean).forEach((field) => {
    field.addEventListener('focus', () => { focused = field; syncPalette(); });
    field.addEventListener('input', () => { field.closest('.sys-row')?.classList.remove('invalid'); check(); onChange(field); });
  });
  if (!ownPalette) palette?.addEventListener('click', (event) => { // the parts editor (ownPalette) inserts into the part that has focus
    const button = event.target.closest('[data-insert]');
    if (!button) return;
    const text = button.dataset.insert;
    insertAt(focused, text, { block: text === '{button}' && focused === body });
  });
  // When the form lists problems and the person closes it, the caret lands on the first bad placeholder.
  let caretTo = null;
  body?.addEventListener('invalid', () => { caretTo = state.body.at; });
  body?.addEventListener('focus', () => { if (caretTo) { const [a, b] = caretTo; caretTo = null; body.setSelectionRange(a, b); } });
  form.addEventListener('reset', () => setTimeout(() => { server = {}; check(); onChange(); }, 0));
  check();

  return {
    subject, body, check,
    setServer(errors) { server = errors || {}; show('subject', subject); show('body', body); },
    get valid() { return !state.subject.message && !state.body.message && !Object.values(server).some((m) => m?.length); },
    get serverErrors() { return server; },
  };
}

/* ---------- preview: the real email in a sandboxed frame ---------- */

function previewPane(root, { url, params, onResult = () => {}, sample, nothing = () => '' }) {
  const wrap = $('[data-se-frame-wrap]', root);
  const frame = $('[data-se-frame]', root);
  const errorBox = $('[data-se-preview-error]', root);
  const note = $('[data-se-preview-note]', root);
  const subjectLine = $('[data-se-subject-line]', root);
  const sampleLine = $('[data-se-sample]', root);
  if (sampleLine && sample) sampleLine.textContent = sample;
  let seq = 0;
  let controller = null;

  function fit() {
    try {
      const doc = frame.contentDocument;
      if (!doc?.documentElement) return;
      frame.style.height = `${Math.max(240, doc.documentElement.scrollHeight)}px`;
    } catch { /* cross-origin: keep the default height */ }
  }
  frame.addEventListener('load', () => {
    try {
      const doc = frame.contentDocument;
      const style = doc.createElement('style');
      style.textContent = 'a{pointer-events:none}'; // a sample link goes nowhere
      doc.head.append(style);
    } catch { /* ignore */ }
    fit();
  });

  async function refresh() {
    const mine = ++seq;
    controller?.abort();
    const none = nothing();
    if (none) { delete wrap.dataset.busy; errorBox.hidden = true; note.textContent = none; note.hidden = false; onResult({}); return; }
    controller = new AbortController();
    wrap.dataset.busy = '';
    const result = await call(url, { body: params(), signal: controller.signal });
    if (mine !== seq || result.aborted) return;
    delete wrap.dataset.busy;
    if (!result.data || (!result.ok && result.status !== 200)) { errorBox.hidden = false; note.hidden = true; return; }
    errorBox.hidden = true;
    const data = result.data;
    if (data.ok) {
      note.hidden = true;
      frame.hidden = false;
      frame.srcdoc = data.html;
      if (subjectLine) subjectLine.textContent = `Subject: ${data.subject}`;
      onResult({});
    } else {
      const first = Object.values(data.errors || {}).flat()[0];
      const empty = root.querySelector('[name=subject]') && !root.querySelector('[name=subject]').value.trim()
        && !(root.querySelector('[name=body]')?.value || '').trim();
      note.textContent = empty ? 'Type a subject and message to see the preview.'
        : first ? 'Fix the wording to see the preview.' : 'The preview is not ready.';
      note.hidden = false;
      onResult(data.errors || {});
    }
  }
  const soon = debounce(refresh, 400);
  $('[data-se-retry]', root)?.addEventListener('click', () => { errorBox.hidden = true; refresh(); });
  return { refresh, soon };
}

/** The Desktop / Phone toggle (buttons with aria-pressed): the frame width and its title. */
function widthToggle(root) {
  const wrap = $('[data-se-frame-wrap]', root);
  const frame = $('[data-se-frame]', root);
  $$('[data-se-width]', root).forEach((button) => button.addEventListener('click', () => {
    const width = button.dataset.seWidth;
    wrap.dataset.width = width;
    frame.title = `Email preview, ${width} width`;
    $$('[data-se-width]', root).forEach((b) => b.setAttribute('aria-pressed', String(b === button)));
    setTimeout(() => frame.dispatchEvent(new Event('load')), 0);
  }));
}

/** Below 64em the Write / Preview switch shows one panel at a time. */
function paneSwitch(form, onPreview = () => {}) {
  $$('[data-se-show]', form).forEach((button) => button.addEventListener('click', () => {
    form.dataset.view = button.dataset.seShow;
    $$('[data-se-show]', form).forEach((b) => b.setAttribute('aria-pressed', String(b === button)));
    if (button.dataset.seShow === 'preview') onPreview();
    window.scrollTo({ top: 0, behavior: reduced.matches ? 'auto' : 'smooth' });
  }));
}

/* ---------- automatic email editor ---------- */

function initEditor(form) {
  const spec = JSON.parse($('#se-spec').textContent);
  const names = (list) => new Set((list || []).map((p) => p.name));
  const known = { subject: names(spec.subject_placeholders), body: new Set([...names(spec.placeholders), ...(spec.has_button ? ['button'] : [])]) };
  const testButton = $('[data-se-test]');
  const testNote = $('[data-se-test-note]', form);
  const sampleValue = spec.placeholders[0]?.sample;
  const reason = 'Fix the placeholders first.';
  let preview;

  const fields = wordingFields(form, {
    known, needButton: spec.button_required,
    onChange: () => { refreshTest(); preview.soon(); },
  });
  const params = () => new URLSearchParams({ subject: fields.subject.value, body: fields.body ? fields.body.value : '' });
  preview = previewPane(form, { url: form.dataset.previewUrl, params, onResult: (errors) => { fields.setServer(errors); refreshTest(); }, sample: sampleValue ? `Sample name in the preview: ${sampleValue}` : '' });
  widthToggle(form);
  paneSwitch(form, () => preview.refresh());

  function refreshTest() {
    if (!testButton) return;
    const blocked = !fields.valid;
    testButton.setAttribute('aria-disabled', String(blocked));
    if (testNote) { testNote.textContent = blocked ? reason : ''; testNote.toggleAttribute('data-bad', blocked); }
  }
  refreshTest();
  preview.refresh();

  testButton?.addEventListener('click', async () => {
    if (testButton.getAttribute('aria-disabled') === 'true') return;
    testButton.setAttribute('aria-disabled', 'true');
    const result = await call(form.dataset.testUrl, { body: params() });
    refreshTest();
    if (result.status === 0) return toast(NETWORK, { kind: 'error' });
    const message = result.data?.message || 'The test could not be sent.';
    if (result.data?.ok) {
      const who = $('[data-system-user]')?.textContent.trim();
      toast(form.dataset.dev ? 'Test printed in the server log.' : who ? `Test sent to ${who}.` : message);
    } else toast(message, { kind: 'error' });
  });

  // Stale (409): the same strip as the code view.
  $('[data-se-copy-mine]')?.addEventListener('click', async (event) => {
    const text = `${fields.subject.value}\n\n${fields.body?.value || ''}`;
    try { await navigator.clipboard.writeText(text); event.currentTarget.textContent = 'Copied'; setTimeout(() => { event.currentTarget.textContent = 'Copy my version'; }, 1500); }
    catch { toast('Could not copy. Select the wording and copy it by hand.', { kind: 'error' }); }
  });
  $('[data-se-load-latest]')?.addEventListener('click', async (event) => {
    const url = event.currentTarget.dataset.seLoadLatest;
    const ok = await confirmModal({ title: 'Load the latest wording?', body: 'Your edits will be lost.', confirmLabel: 'Load the latest', cancelLabel: 'Keep editing', tone: 'danger', opener: event.currentTarget });
    if (ok) { document.dispatchEvent(new CustomEvent('spa99:leaving')); location.href = url; }
  });
}

/* ---------- group composer ---------- */

const KIND_HELP = {
  news: 'Goes only to people who chose to hear news. Includes an unsubscribe link.',
  service: 'Goes to everyone in the group. Only for things they need to know, such as booking opening.',
};

function initComposer(form) {
  const names = new Set(JSON.parse($('#se-placeholders').textContent).map((p) => p.name));
  const known = { subject: names, body: names };
  const bar = $('[data-se-bar]', form);
  const note = $('[data-se-bar-note]', form);
  const send = $('[data-se-send]', form);
  const saveButton = $('[data-se-save-draft]', form);
  const testButton = $('[data-se-test]', form);
  const countBox = $('[data-se-count]', form);
  const nameField = $('[data-se-name]', form);
  const date = $('[data-se-date]', form);
  const time = $('[data-se-time]', form);
  const base = form.dataset.sendBase.endsWith('/') ? form.dataset.sendBase : `${form.dataset.sendBase}/`;
  const allowed = form.dataset.allowed === '1';
  let count = null; // the chosen group's count: null until read, a number once known
  let countError = '';
  let counting = false;
  let dirty = false;
  let typed = false; // something was written (not just a group or kind chosen): switching the starting template then asks first
  let saving = false;

  const radio = (name) => form.querySelector(`input[name="${name}"]:checked`);
  const group = () => radio('group')?.value || '';
  const kind = () => radio('kind')?.value || 'news';
  const later = () => radio('when')?.value === 'later';
  const optionsOf = (key) => {
    const card = $(`.se-group[data-group="${key}"]`, form);
    const out = {};
    $$('select, input', card).forEach((el) => { if (el.name && el.name !== 'group') out[el.name] = el.value; });
    return out;
  };
  // only the chosen group's options are live: the others are neither checked nor sent
  const syncOptions = () => $$('.se-group[data-group]', form).forEach((card) => $$('.se-group-opts select, .se-group-opts input', card).forEach((el) => { el.disabled = card.dataset.group !== group(); }));
  const needs = (key) => $$('select[required]', $(`.se-group[data-group="${key}"]`, form)).some((s) => !s.value);

  const fields = wordingFields(form, {
    known, ownPalette: true, onChange: (field) => {
      dirty = true; typed = true; refreshBar();
      if (field === fields.subject && nameField && !nameField.dataset.touched) nameField.value = fields.subject.value.slice(0, 60);
      preview.soon();
    },
  });
  // The parts of the email (system-email-builder.js): kept as JSON in the hidden `blocks` input, previewed and saved as such.
  const builder = initBuilder(form, {
    known: known.body, drawTokens, insertAt, csrf,
    onChange: () => { dirty = true; typed = true; refreshBar(); preview.soon(); },
  });
  const params = () => new URLSearchParams({ subject: fields.subject.value, blocks: builder.json(), kind: kind(), group: group() });
  const preview = previewPane(form, {
    url: form.dataset.previewUrl, params,
    nothing: () => (builder.count ? '' : 'Add a part to see the preview.'),
    onResult: (errors) => { const { blocks, ...rest } = errors; fields.setServer(rest); builder.applyErrors(blocks || {}); refreshBar(); },
  });
  widthToggle(form);
  paneSwitch(form, () => preview.refresh());
  nameField?.addEventListener('input', () => { nameField.dataset.touched = '1'; dirty = true; typed = true; });
  if (nameField && nameField.value) nameField.dataset.touched = '1';

  /* ----- counts ----- */

  const cardSeq = {};
  async function countCard(key, asChosen) {
    const cardCount = $(`.se-group[data-group="${key}"] [data-se-card-count]`, form);
    if (needs(key)) { cardCount.textContent = '-'; cardCount.removeAttribute('data-zero'); if (asChosen) { count = null; counting = false; countError = ''; paintCount(); } return; }
    const mine = (cardSeq[key] = (cardSeq[key] || 0) + 1);
    if (asChosen) { counting = true; countError = ''; paintCount(); }
    const query = new URLSearchParams({ group: key, kind: kind(), ...optionsOf(key) });
    const result = await call(`${form.dataset.countUrl}?${query}`, { method: 'GET' });
    if (mine !== cardSeq[key] || result.aborted) return;
    if (!result.ok || !result.data) {
      cardCount.textContent = '-';
      if (asChosen) { counting = false; count = null; countError = 'Could not count. Try again in a moment.'; paintCount(); refreshBar(); }
      return;
    }
    const n = result.data.count;
    cardCount.textContent = n == null ? '-' : fmt(n);
    cardCount.toggleAttribute('data-zero', n === 0);
    if (asChosen) {
      counting = false;
      count = n;
      countError = n == null ? Object.values(result.data.errors || {}).flat()[0] || '' : '';
      paintCount();
      refreshBar();
    }
  }
  const countAll = debounce(() => {
    $$('.se-group[data-group]', form).forEach((card) => countCard(card.dataset.group, card.dataset.group === group()));
  }, 250);
  const countChosen = debounce(() => { if (group()) countCard(group(), true); }, 250);

  function paintCount() {
    countBox.replaceChildren();
    if (!group()) return;
    if (counting) { const p = document.createElement('p'); p.dataset.counting = ''; p.textContent = 'Counting'; p.className = 'sys-muted'; countBox.append(p); return; }
    if (countError) { const p = document.createElement('p'); p.className = 'se-live-error'; p.textContent = countError; countBox.append(p); return; }
    if (count === null) { const p = document.createElement('p'); p.className = 'sys-muted'; p.textContent = 'Choose an option for this group to see how many people get it.'; countBox.append(p); return; }
    if (count === 0) { const p = document.createElement('p'); p.className = 'sys-note warn'; p.textContent = 'Nobody in this group can get this. Try another group or kind.'; countBox.append(p); return; }
    const p = document.createElement('p');
    const n = document.createElement('span');
    n.className = 'mono'; n.textContent = fmt(count);
    p.append(n, ` ${plural(count, 'person', 'people')} will get this. ${kind() === 'news' ? 'Anyone who has not opted in to news, or is suppressed, is skipped.' : 'Suppressed addresses are skipped.'}`);
    countBox.append(p);
  }

  /* ----- the bottom bar ----- */

  function whenIso() { return date.value && time.value ? `${date.value}T${time.value}` : ''; }

  function refreshBar() {
    const gate = !allowed;
    let reason = '';
    if (!group()) reason = 'Choose who gets it.';
    else if (counting) reason = 'Counting.';
    else if (countError) reason = countError;
    else if (count === null) reason = 'Choose an option for the group.';
    else if (count === 0) reason = 'Nobody to send to.';
    else if (later() && !whenIso()) reason = 'Choose a date and time.';
    else if (builder.uploading) reason = 'Wait for the image to finish uploading.';
    else if (!builder.count) reason = 'Add a part to the email.';
    else if (!fields.valid) reason = 'Fix the placeholders first.';
    if (gate) reason = 'Off until Amazon approves production sending.';
    const label = later() ? (whenIso() ? `Schedule for ${whenText(date.value, time.value)}` : 'Schedule') : (count ? `Send to ${fmt(count)}` : 'Send');
    send.textContent = label;
    send.setAttribute('aria-disabled', String(!!reason));
    send.dataset.reason = reason;
    note.textContent = reason;
    testButton.setAttribute('aria-disabled', String(!!testReason()));
  }

  /** Why Send me a test is off right now ('' when it is on). */
  function testReason() {
    if (builder.uploading) return 'Wait for the image to finish uploading.';
    if (!builder.count) return 'Add a part to the email.';
    if (!fields.valid) return 'Fix the placeholders first.';
    return '';
  }

  $$('input[name="group"]', form).forEach((r) => r.addEventListener('change', () => { syncOptions(); dirty = true; count = null; countError = ''; countChosen(); paintCount(); refreshBar(); preview.soon(); }));
  $$('.se-group-opts select, .se-group-opts input', form).forEach((el) => el.addEventListener('change', () => { dirty = true; const key = el.closest('.se-group[data-group]').dataset.group; if (key === group()) countChosen(); else countCard(key, false); }));
  $$('input[name="kind"]', form).forEach((r) => r.addEventListener('change', () => { dirty = true; help(); countAll(); refreshBar(); preview.soon(); }));
  $$('input[name="when"]', form).forEach((r) => r.addEventListener('change', () => {
    if (later() && !date.value) { const d = new Date(); d.setDate(d.getDate() + 1); date.value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; }
    dirty = true; refreshBar();
  }));
  [date, time].forEach((el) => el.addEventListener('input', refreshBar));
  const help = () => { $('[data-se-kind-help]', form).textContent = KIND_HELP[kind()] || ''; };
  help();
  syncOptions();
  paintCount();
  countAll();
  refreshBar();
  preview.refresh();

  /* ----- save, test, send ----- */

  const problemList = async () => [...await collectProblems(form), ...builder.problems()];

  const FIELD_LABELS = { name: 'Name', subject: 'Subject', group: 'Who', kind: 'Kind', _: 'Email' };
  /** The server's { field: [messages], blocks: {...}, _: [...] } as dialog rows; the parts' errors also land on their cards. */
  function problemsFrom(errors) {
    const items = [];
    Object.entries(errors).forEach(([key, value]) => {
      if (key === 'blocks') return;
      items.push({ field: key, label: FIELD_LABELS[key] || '', message: [value].flat().join(' '), control: $(`[name="${key}"]`, form) });
    });
    builder.applyErrors(errors.blocks || {});
    return [...items, ...builder.problems()];
  }

  /** Save the draft (a script POST to the form's own address, answered as JSON). Resolves the draft id, or '' when something is wrong. */
  async function saveDraft({ quiet = false } = {}) {
    if (saving) return '';
    if (builder.uploading) { toast('Wait for the image to finish uploading.', { kind: 'error' }); return ''; }
    const found = await problemList();
    if (found.length) { await showProblems(form, found, { opener: saveButton }); return ''; }
    saving = true;
    saveButton.setAttribute('aria-disabled', 'true');
    const data = new FormData(form);
    ['when', 'start'].forEach((name) => data.delete(name));
    let id = '';
    try {
      const response = await fetch(form.action || location.href, { method: 'POST', body: data, credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch', Accept: 'application/json', 'X-CSRFToken': csrf() } });
      let answer = null;
      try { answer = await response.json(); } catch { answer = null; }
      if (answer?.ok && answer.id) id = answer.id;
      else if (answer?.errors) {
        const issues = problemsFrom(answer.errors);
        if (issues.length) await showProblems(form, issues, { opener: saveButton });
        else toast('We could not save the draft. Please try again.', { kind: 'error' });
      } else toast('We could not save the draft. Please try again.', { kind: 'error' });
    } catch { toast(NETWORK, { kind: 'error' }); }
    saving = false;
    saveButton.setAttribute('aria-disabled', 'false');
    if (!id) return '';
    form.dataset.draftId = id;
    form.action = `${base}${id}/edit/`;
    history.replaceState(null, '', form.action);
    if (startBlock) startBlock.hidden = true; // an Edit draft has no Start from
    dirty = false;
    if (!quiet) toast('Saved as a draft.');
    return id;
  }

  /* ----- Start from (a new send only): the server draws the chosen template, so changing it reloads the page ----- */

  const startBlock = $('[data-se-start-block]', form);
  if (startBlock) {
    const startNote = $('[data-se-start-note]', startBlock);
    const startRadios = $$('input[name="start"]', startBlock);
    const current = form.dataset.start || '';
    let wanted = '';
    const go = (key) => { dirty = false; location.href = key ? `${location.pathname}?start=${encodeURIComponent(key)}` : location.pathname; };
    startRadios.forEach((r) => r.addEventListener('change', () => {
      if (!typed) { go(r.value); return; }
      wanted = r.value;
      startNote.hidden = false;
    }));
    $('[data-se-start-replace]', startBlock).addEventListener('click', () => go(wanted));
    $('[data-se-start-keep]', startBlock).addEventListener('click', () => {
      startRadios.forEach((r) => { r.checked = r.value === current; });
      startNote.hidden = true;
      startRadios.find((r) => r.checked)?.focus();
    });
  }

  saveButton.addEventListener('click', () => saveDraft());
  form.addEventListener('submit', (event) => { event.preventDefault(); saveDraft(); });
  document.addEventListener('keydown', (event) => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') { event.preventDefault(); saveDraft(); } });
  window.addEventListener('beforeunload', (event) => { if (dirty && !saving) { event.preventDefault(); event.returnValue = ''; } });

  testButton.addEventListener('click', async () => {
    if (testButton.getAttribute('aria-disabled') === 'true') { note.textContent = testReason(); return; }
    const id = await saveDraft({ quiet: true });
    if (!id) return;
    testButton.setAttribute('aria-disabled', 'true');
    const result = await call(`${base}${id}/test/`);
    refreshBar();
    if (result.status === 0) return toast(NETWORK, { kind: 'error' });
    if (result.data?.ok) toast(form.dataset.dev ? 'Test printed in the server log.' : `Test sent to ${$('[data-system-user]')?.textContent.trim() || 'you'}.`);
    else toast(result.data?.message || 'The test could not be sent.', { kind: 'error' });
  });

  send.addEventListener('click', async () => {
    if (send.getAttribute('aria-disabled') === 'true') { note.textContent = send.dataset.reason; return; }
    const found = await problemList();
    if (found.length) { await showProblems(form, found, { opener: send }); return; }
    const scheduled = later();
    const n = count;
    const subject = fields.subject.value.trim();
    const label = kind() === 'news' ? 'News' : 'Service message';
    const when = whenText(date.value, time.value);
    const ok = await confirmModal({
      title: scheduled ? `Schedule for ${when}?` : `Send to ${fmt(n)} ${plural(n, 'person', 'people')}?`,
      body: `${label}: ${subject}. ${kind() === 'news' ? 'People who are not opted in and suppressed addresses are skipped.' : 'Suppressed addresses are skipped.'} ${scheduled ? 'You can cancel until then.' : 'This cannot be unsent.'}`,
      confirmLabel: scheduled ? `Schedule for ${when}` : `Send to ${fmt(n)}`,
      tone: IS_LIVE ? 'danger' : 'neutral', opener: send,
    });
    if (!ok) return;
    const id = await saveDraft({ quiet: true });
    if (!id) return;
    send.setAttribute('aria-disabled', 'true');
    const body = scheduled ? { scheduled_at: whenIso() } : { expected_count: String(n) };
    const result = await call(`${base}${id}/${scheduled ? 'schedule' : 'send'}/`, { body });
    if (result.status === 0) { refreshBar(); return toast(NETWORK, { kind: 'error' }); }
    if (result.data?.ok) {
      dirty = false;
      flash(scheduled ? `Scheduled for ${when}.` : 'Sending has started.');
      location.href = `${base}${id}/`;
      return;
    }
    toast(result.data?.message || 'It could not be sent.', { kind: 'error' });
    countAll();
    refreshBar();
  });
}

/* ---------- sending progress (a group send and an invite batch) ---------- */

function eta(done, total, startedAt) {
  const elapsed = (Date.now() - new Date(startedAt).getTime()) / 1000;
  if (!startedAt || !done || elapsed < 3) return '';
  const left = (total - done) / (done / elapsed);
  if (!Number.isFinite(left) || left <= 0) return '';
  if (left < 60) return 'Less than a minute left';
  const minutes = Math.round(left / 60);
  return minutes >= 60 ? `About ${Math.round(minutes / 6) / 10} hours left` : `About ${minutes} ${plural(minutes, 'minute', 'minutes')} left`;
}

/** Poll a progress address every 2 s while the tab is visible. paint(data) returns true when finished. */
function poll(url, paint, { every = 2000 } = {}) {
  let failures = 0;
  const tick = async () => {
    if (document.hidden) return schedule();
    const result = await call(url, { method: 'GET' });
    if (result.ok && result.data) { failures = 0; if (await paint(result.data, false)) return; } else failures += 1;
    if (failures >= 3) paint(null, true);
    schedule();
  };
  const schedule = () => setTimeout(tick, every);
  setTimeout(tick, 0); // read it once straight away (the page was drawn some seconds ago), then every 2 s
}

function initSending(box) {
  const panel = $('[data-se-sending]', box);
  if (!panel) return;
  const bar = $('[data-se-bar]', panel);
  const fill = $('i', bar);
  const text = $('[data-se-progress-text]', panel);
  const etaLine = $('[data-se-eta]', panel);
  const live = $('[data-se-announce]', panel);
  const url = box.dataset.progressUrl;
  const batch = box.matches('[data-se-batch]');
  const announced = new Set();
  const say = (message) => { live.textContent = ''; setTimeout(() => { live.textContent = message; }, 30); };
  const milestones = (percent, total, done) => {
    if (!announced.has('start')) { announced.add('start'); say(`Sending started. ${fmt(done)} of ${fmt(total)}.`); return; }
    for (const m of [75, 50, 25]) if (percent >= m && !announced.has(m)) { announced.add(m); say(`${m} percent sent. ${fmt(done)} of ${fmt(total)}.`); break; }
  };

  poll(url, async (data, failed) => {
    if (failed) { if (etaLine) etaLine.textContent = 'Could not refresh. Trying again.'; return false; }
    let total; let done; let finished;
    if (batch) {
      total = data.total; done = data.total - data.queued - data.sending; finished = data.queued + data.sending === 0;
    } else {
      total = data.total; done = data.sent + data.bounced + data.skipped + data.failed; finished = data.finished || data.status !== 'sending';
    }
    const percent = total ? Math.floor((done * 100) / total) : 0;
    fill.style.width = `${percent}%`;
    bar.setAttribute('aria-valuemax', String(total)); bar.setAttribute('aria-valuenow', String(done));
    text.textContent = `${batch ? 'Sending invites' : 'Sending'} ${fmt(done)} of ${fmt(total)}`;
    if (etaLine && !batch) etaLine.textContent = eta(done, total, data.started_at);
    if (finished) {
      say(`Sending finished. ${fmt(done)} of ${fmt(total)}.`);
      flash(batch ? 'Invites sent.' : (data.status === 'sent' ? `Sent to ${fmt(data.sent + data.bounced)}.` : data.status === 'cancelled' ? 'Sending stopped.' : 'Sending stopped early.'), data.status === 'failed' ? 'warning' : 'success');
      setTimeout(() => location.reload(), 600);
      return true;
    }
    milestones(percent, total, done);
    return false;
  });
}

/** Detail pages: sandboxed frames fit their content, the width toggle works. */
function initStaticPreview(root) {
  widthToggle(root);
  const frame = $('[data-se-frame]', root);
  frame.addEventListener('load', () => {
    try {
      const doc = frame.contentDocument;
      const style = doc.createElement('style'); style.textContent = 'a{pointer-events:none}'; doc.head.append(style);
      frame.style.height = `${Math.max(240, doc.documentElement.scrollHeight)}px`;
    } catch { /* keep the default height */ }
  });
  if (frame.contentDocument?.readyState === 'complete') frame.dispatchEvent(new Event('load'));
}

/* ---------- invites ---------- */

function initImport(form) {
  const modes = $$('[data-se-mode]', form);
  const text = $('[data-invites-text]', form);
  const file = $('input[type=file]', form);
  const drop = $('[data-se-drop]', form);
  const dropText = $('[data-se-drop-text]', form);
  const error = $('[data-se-live="list"]', form);
  const mode = () => form.querySelector('input[name="mode"]:checked')?.value || 'paste';
  const sync = () => {
    modes.forEach((el) => { el.hidden = el.dataset.seMode !== mode(); });
    text.disabled = mode() !== 'paste'; file.disabled = mode() !== 'upload';
    error.hidden = true;
  };
  $$('input[name="mode"]', form).forEach((r) => r.addEventListener('change', () => { sync(); (mode() === 'paste' ? text : file).focus?.(); }));
  const named = () => {
    const chosen = file.files?.[0];
    dropText.textContent = chosen ? chosen.name : 'Drop a CSV here or choose a file';
    drop.toggleAttribute('data-has', !!chosen);
  };
  file.addEventListener('change', () => { named(); error.hidden = true; });
  ['dragenter', 'dragover'].forEach((name) => drop.addEventListener(name, (event) => { event.preventDefault(); drop.setAttribute('data-over', ''); }));
  ['dragleave', 'drop'].forEach((name) => drop.addEventListener(name, (event) => { event.preventDefault(); drop.removeAttribute('data-over'); }));
  drop.addEventListener('drop', (event) => { if (event.dataTransfer?.files?.length) { file.files = event.dataTransfer.files; named(); error.hidden = true; } });
  text.addEventListener('input', () => { error.hidden = true; });
  form.addEventListener('submit', (event) => {
    const empty = mode() === 'paste' ? !text.value.trim() : !file.files?.length;
    if (empty) {
      event.preventDefault(); event.stopImmediatePropagation();
      error.textContent = mode() === 'paste' ? 'Paste at least one person: name, email.' : 'Choose a CSV file first.';
      error.hidden = false;
      (mode() === 'paste' ? text : file).focus();
    }
  }, true);
  sync();
}

function initReview(root) {
  const wire = () => {
    const list = $('[data-se-list]', root);
    const chips = $$('[data-filter]', root);
    const rows = $$('[data-system-invite-rows] tbody tr', root);
    const apply = (filter) => {
      chips.forEach((chip) => chip.setAttribute('aria-pressed', String(chip.dataset.filter === filter)));
      rows.forEach((row) => { row.hidden = filter !== 'all' && row.dataset.status !== filter; });
    };
    chips.forEach((chip) => chip.addEventListener('click', () => apply(chip.dataset.filter)));

    async function recheck(row) {
      const input = $('[data-se-fix]', row);
      const value = input.value.trim();
      if (!value) { input.setAttribute('aria-invalid', 'true'); input.focus(); return; }
      const lines = list.value.split(/\r\n|\n|\r/);
      const at = Number(row.dataset.line) - 1;
      const old = input.dataset.old;
      if (lines[at] === undefined) return;
      lines[at] = old && lines[at].includes(old) ? lines[at].replace(old, value) : `${row.cells[0].textContent.trim().replace(/^-$/, '')}, ${value}`.replace(/^, /, '');
      const kept = $$('[data-filter][aria-pressed="true"]', root)[0]?.dataset.filter || 'all';
      input.disabled = true;
      const result = await call(root.dataset.reviewUrl, { body: new URLSearchParams({ text: lines.join('\n') }), json: false });
      if (result.status === 0) { input.disabled = false; return toast(NETWORK, { kind: 'error' }); }
      const doc = new DOMParser().parseFromString(await result.response.text(), 'text/html');
      const fresh = $('[data-se-review-root]', doc);
      if (!fresh) { input.disabled = false; return toast('Could not check the list. Please try again.', { kind: 'error' }); }
      root.innerHTML = fresh.innerHTML;
      wire();
      if ($(`[data-filter="${kept}"]`, root)) apply(kept);
      ($$('[data-se-fix]', root)[0] || $('[data-se-send-invites]', root))?.focus();
    }
    $$('[data-se-fix]', root).forEach((input) => {
      const row = input.closest('tr');
      input.addEventListener('keydown', (event) => { if (event.key === 'Enter') { event.preventDefault(); recheck(row); } });
      input.addEventListener('input', () => input.removeAttribute('aria-invalid'));
    });
    $$('[data-se-recheck]', root).forEach((button) => button.addEventListener('click', () => recheck(button.closest('tr'))));

    const form = $('[data-se-send-form]', root);
    const sendButton = $('[data-se-send-invites]', root);
    sendButton?.addEventListener('click', async () => {
      if (sendButton.getAttribute('aria-disabled') === 'true') return;
      const ok = Number(form.dataset.ok);
      const skipped = Number($('[data-system-invite-report]', root).dataset.total) - ok;
      const yes = await confirmModal({
        title: `Send ${fmt(ok)} ${plural(ok, 'invite', 'invites')}?`,
        body: `${skipped ? `${fmt(skipped)} ${plural(skipped, 'is', 'are')} skipped. ` : ''}Each person gets a personal Register link.`,
        confirmLabel: `Send ${fmt(ok)} ${plural(ok, 'invite', 'invites')}`, tone: IS_LIVE ? 'danger' : 'neutral', opener: sendButton,
      });
      if (yes) form.requestSubmit();
    });
  };
  wire();
}

function initInviteSummary() {
  const rows = $$('[data-system-invite-batches] tbody tr[data-total]');
  const line = $('[data-se-batch-summary]');
  if (!line || !rows.length) return;
  const sum = (key) => rows.reduce((n, row) => n + Number(row.dataset[key] || 0), 0);
  line.textContent = `${fmt(sum('total'))} invited · ${fmt(sum('opened'))} opened · ${fmt(sum('registered'))} registered · ${fmt(sum('bounced'))} bounced`;
}

/* ---------- overview: bounce and complaint rates against Amazon's review lines ---------- */

function initOverview() {
  $$('[data-se-rate]').forEach((tile) => {
    const count = Number(tile.dataset.count);
    const sent = Number(tile.dataset.sent);
    const text = $('[data-se-rate-text]', tile);
    const badge = $('[data-se-badge]', tile);
    const bounce = tile.dataset.seRate === 'bounce';
    if (!sent) { text.textContent = 'No sends this week'; return; }
    const rate = (count / sent) * 100;
    text.textContent = `${rate < 10 ? rate.toFixed(2) : rate.toFixed(1)}% of ${fmt(sent)} sent`;
    const [warn, danger] = bounce ? [2, 5] : [0.05, 0.1];
    if (rate > warn) {
      badge.className = `sys-badge ${rate > danger ? 'danger' : 'warn'}`;
      badge.textContent = rate > danger ? 'Very high' : 'High';
    }
  });
}

/* ---------- lists, tabs ---------- */

function initRows() {
  document.addEventListener('click', (event) => {
    const row = event.target.closest('[data-se-row]');
    if (!row || event.target.closest('a, button, input, select')) return;
    const link = $('a[href]', row);
    if (link && !event.defaultPrevented) link.click();
  });
  $('.se-tabs [aria-current]')?.scrollIntoView({ inline: 'center', block: 'nearest' });
}

/* ---------- start ---------- */

function init() {
  showFlash();
  initRows();
  $$('[data-se-editor]').forEach(initEditor);
  $$('[data-se-composer]').forEach(initComposer);
  $$('[data-se-detail], [data-se-batch]').forEach(initSending);
  $$('[data-se-static-preview]').forEach(initStaticPreview);
  $$('[data-se-import]').forEach(initImport);
  $$('[data-se-review-root]').forEach(initReview);
  initInviteSummary();
  initOverview();
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
