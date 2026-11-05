/* Approvals (docs/features/office-2-design.md section 4): Approve, Decline and Back to waiting are sent in the background (the plain form still works without script).
 * Nothing asks "are you sure": undo is free. The row is replaced IN PLACE by an Undo strip of the SAME height: its height is fixed before the swap, because if the strip were shorter the next
 * row would jump under his thumb and the next tap would land on the wrong person. The strip stays until he leaves or reloads (no timer), the tab counts update, and a polite line announces the change.
 * A failure puts nothing in place of the row and says so. The strip's words are filled with textContent into the page's own <template>: no HTML is built from text. */
import { clearWorking } from './buttons.js';
import { toast } from './feedback.js';

const WORDS = { approve: 'approved.', decline: 'declined.', undo: 'back to waiting.' };
const SAVED_NOT = 'That did not save. Please try again.';
const fmt = (n) => Number(n).toLocaleString('en-GB');

/** Sent in the background, so the page never reloads: the row's forms must be made usable again by hand (buttons.js marked them busy on submit). */
function ready(row) {
  row.querySelectorAll('form').forEach((form) => { delete form.dataset.submitting; });
  row.querySelectorAll('button').forEach((button) => { clearWorking(button); button.disabled = false; });
}

export function initApprovals() {
  const card = document.querySelector('[data-approvals]');
  if (!card) return;
  const live = document.querySelector('[data-approvals-live]');
  const busy = new WeakSet();

  const showCounts = (counts) => {
    if (!counts) return;
    ['waiting', 'approved', 'declined'].forEach((status) => {
      const el = document.querySelector(`[data-tab="${status}"] [data-tab-count]`);
      if (el && counts[status] !== undefined) el.textContent = fmt(counts[status]);
    });
  };

  /** Where Undo on the strip goes: back to how the row was (approved or declined), or to waiting for a decision made from Waiting. */
  const reverse = (kind, row, data) => {
    if (kind !== 'undo') return data.row.undo_url;
    return row.dataset.status === 'declined' ? data.row.decline_url : data.row.approve_url;
  };

  function toStrip(row, form, kind, data) {
    const template = document.querySelector('template[data-approval-strip]');
    if (!template) return false;
    const token = form.querySelector('[name="csrfmiddlewaretoken"]')?.value || '';
    const cells = row.querySelectorAll('td').length || 5;
    row.style.boxSizing = 'border-box';
    row.style.transition = 'none';   // without this the pressed scale eases back while we measure, and the height comes out a little short
    row.style.transform = 'none';   // a row that is being pressed is scaled a little: measure it as it lies
    row.style.height = `${row.getBoundingClientRect().height}px`;   // fixed before the swap: the strip keeps the row's exact height
    row.style.transform = '';
    row.style.transition = '';
    const held = document.createDocumentFragment();
    held.append(...row.childNodes);
    row._held = { nodes: held, status: row.dataset.status, press: row.hasAttribute('data-press') };
    const strip = template.content.cloneNode(true);
    strip.querySelector('[data-strip-name]').textContent = data.name;
    strip.querySelector('[data-strip-verb]').textContent = WORDS[kind];
    const undo = strip.querySelector('form');
    undo.action = new URL(reverse(kind, row, data), location.href).href;
    undo.dataset.decision = 'restore';
    undo.querySelector('[name="csrfmiddlewaretoken"]').value = token;
    strip.querySelector('td').colSpan = cells;
    row.replaceChildren(strip);
    row.classList.add('o-approval--strip');
    row.removeAttribute('data-press');
    const list = row.closest('[data-office-list]');
    if (list) list.dataset.left = String((Number(list.dataset.left) || 0) + 1);   // it has left this list: the next page carries on from the right place (shift)
    return true;
  }

  function fromStrip(row) {
    const held = row._held;
    if (!held) return;
    row.replaceChildren(held.nodes);
    ready(row);   // Undo brings back the very buttons that were pressed: without this they stay on "Working..."
    row.classList.remove('o-approval--strip');
    const list = row.closest('[data-office-list]');
    if (list) list.dataset.left = String(Math.max((Number(list.dataset.left) || 0) - 1, 0));
    if (held.press) row.setAttribute('data-press', '');
    row.dataset.status = held.status;
    row.style.height = '';
    row.style.boxSizing = '';
    row._held = null;
  }

  document.addEventListener('submit', async (event) => {
    const form = event.target.closest?.('form[data-decision]');
    if (!form || !card.contains(form)) return;
    event.preventDefault();
    const row = form.closest('[data-approval-row]');
    if (!row || busy.has(row)) return;
    busy.add(row);
    const buttons = [...row.querySelectorAll('button')];
    buttons.forEach((button) => { button.disabled = true; });
    const kind = form.dataset.decision;
    try {
      const response = await fetch(form.action, { method: 'POST', body: new FormData(form), credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch', Accept: 'application/json' } });
      const data = await response.json().catch(() => null);
      if (!response.ok || !data || !data.ok) throw new Error(String(response.status));
      showCounts(data.counts);
      if (kind === 'restore') {
        fromStrip(row);
        if (live) live.textContent = `${data.name} is back.`;
      } else {
        if (!toStrip(row, form, kind, data)) throw new Error('no strip');
        if (live) live.textContent = `${data.name} ${WORDS[kind]}`;
      }
    } catch {
      ready(row);
      toast(SAVED_NOT, { kind: 'error' });
    } finally {
      busy.delete(row);
    }
  });
}
