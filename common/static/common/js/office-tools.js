/* Office person tools (docs/features/office-outreach-design.md): the sticky notes board and sheet, the reason chips of the
 * Approach list dialog, and the Mark done / Remove actions on the Approach list page.
 *
 * Everything works as a plain form without this file (the server redirects with a toast). Here a note is added or deleted in the
 * background (an HX-Request post answers with the notes partial, which replaces #person-notes), and a list row fades out before the
 * list is refreshed. A note is deleted at once, with no question (R8); "Restore" on its history line brings it back. If anything fails
 * the plain form is posted instead. */
import { toast, toastsFromDocument } from './feedback.js';
import { clearWorking, setWorking } from './buttons.js';
import { measureClamps } from './office-clamp.js';

const parse = (html) => new DOMParser().parseFromString(html, 'text/html');
const wait = (ms) => new Promise((resolve) => { setTimeout(resolve, ms); });
/** The swap time from the Office tokens (0 under reduced motion), so the fade and the wait always agree. */
const swapMs = () => Number.parseFloat(getComputedStyle(document.body).getPropertyValue('--office-dur-swap')) || 0;
const phone = window.matchMedia('(max-width: 63.99em)');

// ---------- sticky notes ----------

const root = () => document.getElementById('person-notes');
const sheet = () => root()?.querySelector('[data-note-sheet]');

/** Notes use the shared clamp (office-clamp.js): measured again after the board changes and after the sheet opens. */
const measure = () => requestAnimationFrame(() => measureClamps());

function openComposer(scope) {
  const draft = scope?.querySelector('[data-note-draft]');
  if (!draft) return;
  draft.hidden = false;
  draft.querySelector('textarea').focus();
}

function closeComposer(draft) {
  const area = draft.querySelector('textarea');
  area.value = '';
  draft.querySelector('[data-note-counter]').hidden = true;
  draft.querySelector('.o-field-error')?.remove();
  draft.hidden = true;
  draft.closest('.o-notes-board, .o-notesheet')?.querySelector('[data-note-compose]')?.focus({ preventScroll: true });
}

function showError(form, messages) {
  form.querySelector('.o-field-error')?.remove();
  const error = document.createElement('p');
  error.className = 'o-field-error';
  error.setAttribute('role', 'alert');
  error.textContent = messages[0] || 'The note could not be saved.';
  form.querySelector('.o-note-actions').before(error);   // add and edit forms both have the actions row
}

/** Header button (phone): the count in its pill follows the board. */
function syncCount(count) {
  document.querySelectorAll('.o-notes-open').forEach((button) => {
    let pill = button.querySelector('[data-notes-pill]');
    if (!count) { pill?.remove(); return; }
    if (!pill) {
      pill = document.createElement('span');
      pill.className = 'o-notes-pill';
      pill.dataset.notesPill = '';
      button.append(' ', pill);
    }
    pill.innerHTML = `${count}<span class="sr-only"> note${count === 1 ? '' : 's'}</span>`;
  });
}

/** Put the partial the server sent in place of the notes. A sheet that was open stays open; `focus` names what gets focus after. */
function swapNotes(html, { scope, focus }) {
  const next = parse(html).getElementById('person-notes');
  const old = root();
  if (!next || !old) throw new Error('no notes in the answer');
  const sheetWasOpen = sheet()?.open;
  if (sheetWasOpen) sheet().close();
  const fresh = document.importNode(next, true);
  old.replaceWith(fresh);
  syncCount(Number(fresh.dataset.count) || 0);
  if (sheetWasOpen) sheet()?.showModal();
  const place = scope === 'sheet' ? sheet() : fresh.querySelector('[data-notes-board]');
  if (focus === 'newest') place?.querySelector('.o-note[data-note]')?.focus();
  else if (focus.startsWith('note:')) place?.querySelector(`.o-note[data-note="${focus.slice(5)}"] [data-note-edit]`)?.focus({ preventScroll: true });
  else if (focus === 'after-delete') (place?.querySelector('.o-note[data-note]') || place?.querySelector('[data-note-compose]') || place?.querySelector('[data-note-sheet-close]'))?.focus({ preventScroll: true });
  measure();
}

/** The timeline card and the Gold history card, taken from a page document: the "Note deleted" line (and its Restore) follows the board. */
function swapHistory(doc) {
  ['[data-person-timeline]', '[data-gold-history-card]'].forEach((selector) => {
    const fresh = doc.querySelector(selector);
    const old = document.querySelector(selector);
    if (fresh && old) old.replaceWith(document.importNode(fresh, true));
  });
}

async function refreshHistory() {
  if (!document.querySelector('[data-person-timeline], [data-gold-history-card]')) return;
  try {
    const response = await fetch(location.pathname + location.search, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } });
    if (response.ok) swapHistory(parse(await response.text()));
  } catch { /* the history is there on the next load */ }
}

async function post(form) {
  return fetch(form.action, { method: 'POST', body: new FormData(form), credentials: 'same-origin', headers: { 'HX-Request': 'true', 'X-Requested-With': 'fetch' } });
}

async function addNote(form) {
  const button = form.querySelector('button[type="submit"]');
  const scope = form.closest('[data-note-sheet]') ? 'sheet' : 'board';
  setWorking(button);
  try {
    const response = await post(form);
    const html = await response.text();
    if (response.status === 400) {
      showError(form, [...parse(html).querySelectorAll('[data-note-errors] .o-field-error')].map((el) => el.textContent.trim()));
      return;
    }
    if (!response.ok) throw new Error(String(response.status));
    swapNotes(html, { scope, focus: 'newest' });
  } catch {
    clearWorking(button);
    form.submit();   // the plain post: a redirect with a toast
  } finally {
    clearWorking(button);
    delete form.dataset.submitting;
  }
}

async function deleteNote(form) {
  const note = form.closest('.o-note');
  const scope = form.closest('[data-note-sheet]') ? 'sheet' : 'board';
  note.classList.add('is-leaving');
  try {
    const [response] = await Promise.all([post(form), wait(swapMs())]);
    if (!response.ok) throw new Error(String(response.status));
    swapNotes(await response.text(), { scope, focus: 'after-delete' });
    toast('Note deleted.');
    refreshHistory();
  } catch {
    note.classList.remove('is-leaving');
    delete form.dataset.submitting;
    toast('The note could not be deleted. Please try again.', { kind: 'error' });
  }
}

/** "Restore" on a "Note deleted" line: the note comes back on the board, with its own author and date, and the line says "Note restored". */
async function restoreNote(form) {
  const button = form.querySelector('button[type="submit"]');
  setWorking(button);
  try {
    const response = await fetch(form.action, { method: 'POST', body: new FormData(form), credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } });
    if (!response.ok) throw new Error(String(response.status));
    const html = await response.text();
    const doc = parse(html);
    toastsFromDocument(doc);
    swapNotes(html, { scope: 'board', focus: '' });
    swapHistory(doc);
  } catch {
    clearWorking(button);
    delete form.dataset.submitting;
    form.submit();   // the plain post: a redirect with a toast
  }
}

// ---------- edit a note by clicking it (R9) ----------

/** Show the note again in place of its editor; `focusText` puts the focus back on the note's text. */
function closeEdit(note, { focusText = true } = {}) {
  const form = note.querySelector('[data-note-edit-form]');
  if (!form || form.hidden) return;
  const area = form.querySelector('textarea');
  area.value = area.defaultValue;
  form.querySelector('.o-field-error')?.remove();
  form.querySelector('[data-note-counter]').hidden = true;
  form.hidden = true;
  note.classList.remove('is-editing');
  if (focusText) note.querySelector('[data-note-edit]')?.focus({ preventScroll: true });
}

function openEdit(text) {
  const note = text.closest('.o-note');
  const form = note?.querySelector('[data-note-edit-form]');
  if (!form || !form.hidden) return;
  document.querySelectorAll('.o-note.is-editing').forEach((other) => closeEdit(other, { focusText: false }));   // one editor at a time
  note.classList.add('is-editing');
  form.hidden = false;
  const area = form.querySelector('textarea');
  area.focus();
  area.setSelectionRange(area.value.length, area.value.length);
  area.dispatchEvent(new Event('input', { bubbles: true }));   // the counter, for a long note
}

async function saveEdit(form) {
  const note = form.closest('.o-note');
  const area = form.querySelector('textarea');
  if (area.value.trim() === area.defaultValue.trim()) { closeEdit(note); delete form.dataset.submitting; return; }   // no change: nothing is sent
  const id = note.dataset.note;
  const scope = form.closest('[data-note-sheet]') ? 'sheet' : 'board';
  const button = form.querySelector('button[type="submit"]');
  setWorking(button);
  try {
    const response = await post(form);
    const html = await response.text();
    if (response.status === 400) {
      showError(form, [...parse(html).querySelectorAll('[data-note-errors] .o-field-error')].map((el) => el.textContent.trim()));
      return;
    }
    if (!response.ok) throw new Error(String(response.status));
    swapNotes(html, { scope, focus: `note:${id}` });
    toast('Note saved.');
    refreshHistory();
  } catch {
    toast('The note could not be saved. Please try again.', { kind: 'error' });
  } finally {
    clearWorking(button);
    delete form.dataset.submitting;
  }
}

function initNotes() {
  document.addEventListener('click', (event) => {
    const target = event.target;
    if (!target.closest) return;
    if (target.closest('[data-note-sheet-open]')) { sheet()?.showModal(); measure(); return; }
    if (target.closest('[data-note-sheet-close]')) { sheet()?.close(); return; }
    if (target.matches?.('dialog[data-note-sheet]')) { target.close(); return; }   // the backdrop
    const compose = target.closest('[data-note-compose]');
    if (compose) { openComposer(compose.closest('.o-notes-board, .o-notesheet')); return; }
    const edit = target.closest('[data-note-edit]');
    if (edit) {
      if (!window.getSelection()?.isCollapsed && edit.contains(window.getSelection().anchorNode)) return;   // selecting text to copy is not editing
      openEdit(edit);
      return;
    }
    const cancelEdit = target.closest('[data-note-edit-cancel]');
    if (cancelEdit) { closeEdit(cancelEdit.closest('.o-note')); return; }
    const cancel = target.closest('[data-note-cancel]');
    if (cancel) { closeComposer(cancel.closest('[data-note-draft]')); return; }
    const all = target.closest('[data-note-all]');
    if (all) {
      const board = all.closest('[data-notes-board]');
      const open = !board.hasAttribute('data-all');
      board.toggleAttribute('data-all', open);
      all.setAttribute('aria-expanded', String(open));
      all.textContent = open ? 'Show fewer' : all.dataset.allLabel;
      measure();
      return;
    }
  });
  document.addEventListener('keydown', (event) => {
    const text = event.target.closest?.('[data-note-edit]');
    if (text && event.target === text && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); openEdit(text); return; }
    const area = event.target.closest?.('[data-note-input]');
    if (!area) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      if (area.closest('[data-note-edit-form]')) closeEdit(area.closest('.o-note')); else closeComposer(area.closest('[data-note-draft]'));
    }
    else if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) { event.preventDefault(); area.form.requestSubmit(); }
  });
  document.addEventListener('input', (event) => {
    const area = event.target.closest?.('[data-note-input]');
    if (!area) return;
    const counter = area.form.querySelector('[data-note-counter]');
    const length = area.value.length;
    const max = Number(area.dataset.max || area.maxLength);   // the edit box has no maxlength: a long backfilled note must not be cut silently
    counter.hidden = length < 900;
    counter.classList.toggle('is-over', length > max);
    counter.textContent = length > max ? `Note: keep it to ${max} characters (you have ${length})` : `${length} of ${max}`;
    area.form.querySelector('.o-field-error')?.remove();
  });
  phone.addEventListener('change', (event) => { if (!event.matches) sheet()?.close(); measure(); });
  window.addEventListener('resize', measure);
  measure();
}

// ---------- the Approach list dialog: reason chips ----------

function initReasonChips() {
  document.addEventListener('click', (event) => {
    const chip = event.target.closest?.('[data-reason-chip]');
    if (!chip) return;
    const form = chip.closest('form');
    const field = form.querySelector('[data-reason-input]');
    const on = chip.getAttribute('aria-pressed') !== 'true';
    form.querySelectorAll('[data-reason-chip]').forEach((other) => other.setAttribute('aria-pressed', String(other === chip && on)));
    field.value = on ? chip.textContent.trim() : '';
    field.focus({ preventScroll: true });
  });
  document.addEventListener('input', (event) => {
    const field = event.target.closest?.('[data-reason-input]');
    if (!field) return;
    field.form.querySelectorAll('[data-reason-chip]').forEach((chip) => chip.setAttribute('aria-pressed', String(chip.textContent.trim() === field.value)));
  });
}

// ---------- the Approach list page: Mark done and Remove ----------

async function refreshList() {
  const response = await fetch(location.pathname + location.search, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } });
  if (!response.ok) throw new Error(String(response.status));
  const doc = parse(await response.text());
  const rows = doc.querySelector('[data-office-list]');
  const body = document.querySelector('[data-office-list]');
  if (!rows || !body) throw new Error('no list');
  body.replaceChildren(...[...rows.childNodes].map((node) => document.importNode(node, true)));
  doc.querySelectorAll('[data-region]:not([data-office-list])').forEach((next) => {
    document.querySelector(`[data-region="${next.dataset.region}"]`)?.replaceWith(document.importNode(next, true));
  });
}

async function actOnRow(form) {
  const row = form.closest('tr');
  const button = form.querySelector('button');
  row.classList.add('is-leaving');
  button.disabled = true;
  try {
    const [response] = await Promise.all([
      fetch(form.action, { method: 'POST', body: new FormData(form), credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } }),
      wait(swapMs()),
    ]);
    if (!response.ok) throw new Error(String(response.status));
    toastsFromDocument(parse(await response.text()));
    await refreshList();
  } catch {
    row.classList.remove('is-leaving');
    button.disabled = false;
    delete form.dataset.submitting;
    form.submit();
  }
}

/** Mark done, Remove (Approach list) and Move back (Archived leads): the row fades, the list is fetched again, the server's toast shows. */
function initRowActions() {
  document.addEventListener('submit', (event) => {
    const form = event.target.closest?.('form[data-outreach-act], form[data-row-act]');
    if (!form || event.defaultPrevented || !document.querySelector('[data-office-list]')) return;
    event.preventDefault();
    actOnRow(form);
  }, true);
}

export function initTools() {
  document.addEventListener('submit', (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || event.defaultPrevented) return;
    if (form.hasAttribute('data-note-add')) { event.preventDefault(); addNote(form); }
    else if (form.hasAttribute('data-note-edit-form')) { event.preventDefault(); saveEdit(form); }
    else if (form.hasAttribute('data-note-delete')) { event.preventDefault(); deleteNote(form); }
    else if (form.hasAttribute('data-note-restore')) { event.preventDefault(); restoreNote(form); }
  }, true);
  initNotes();
  initReasonChips();
  initRowActions();
}
