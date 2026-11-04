/* New email (docs/features/email-chat-design.md section 2): To (a person from a search, or a typed address), Subject, and the same editor as the reply.
 * Names, addresses and badges from the search are set with textContent. One recipient: no Cc or Bcc this round. An unsent email is kept as a draft keyed `new`. */
import { csrfToken } from './api.js';
import { bindKeyboard, releaseKeyboard } from './office-keyboard.js';
import { h } from './office-dom.js';
import { Editor } from './email-editor.js';
import { clearDraft, loadDraft, saveDraft } from './email-drafts.js';

const SEARCH_MS = 250;
const looksLikeAddress = (text) => /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(text.trim());
const KIND = { lead: 'Lead', registered: 'Registered', gold: 'Gold' };

export class NewEmail {
  constructor(root) {
    this.root = root;
    const data = JSON.parse(root.querySelector('#em-new-data').textContent);
    this.data = data;
    this.urls = data.urls;
    this.staff = root.closest('[data-em-app]')?.dataset.staff || '';
    this.to = null;
    this.options = [];
    this.active = -1;
    this.seq = 0;
    this.sending = false;
    this.ac = new AbortController();
    this.q = (sel) => root.querySelector(sel);
    this.form = this.q('[data-em-new-form]');
    if (!data.can_send || !this.form) return;
    this.input = this.q('[data-to-input]');
    this.list = this.q('[data-to-list]');
    this.chip = this.q('[data-to-chip]');
    this.chipText = this.q('[data-to-chip-text]');
    this.toError = this.q('[data-to-error]');
    this.subject = this.q('[data-subject-input]');
    this.subjectError = this.q('[data-subject-error]');
    this.bodyError = this.q('[data-body-error]');
    this.sendButtons = [...root.querySelectorAll('[data-ed-send]')];
    this.editor = new Editor(this.q('[data-editor]'), { limits: data.limits, onChange: () => this.changed(), onSend: () => this.send(), onFiles: () => this.changed() });
    this.bind();
    this.prefill();
    this.updateSend();
    bindKeyboard(root, { signal: this.ac.signal });
    (this.to ? this.subject : this.input).focus({ preventScroll: true });
  }

  destroy() {
    this.ac.abort();
    clearTimeout(this.timer);
    clearTimeout(this.draftTimer);
    this.editor?.destroy();
    releaseKeyboard();
  }

  // ---------- To ----------

  prefill() {
    const draft = loadDraft(this.staff, 'new');
    const r = this.data.recipient || {};
    if (r.email) this.choose({ email: r.email, name: r.name || '', person: r.person || '' });
    else if (draft?.to?.email) this.choose(draft.to);
    if (r.error) this.showError(this.toError, r.error);
    if (draft) {
      if (draft.subject) this.subject.value = draft.subject;
      if (draft.html) this.editor.setHtml(draft.html);
    }
  }

  choose(person) {
    this.to = person;
    this.input.value = '';
    this.chip.hidden = false;
    this.chipText.textContent = person.name && person.name !== person.email ? `${person.name} (${person.email})` : person.email;
    this.input.hidden = true;
    this.closeList();
    this.showError(this.toError, '');
    this.changed();
  }

  clearTo() {
    this.to = null;
    this.chip.hidden = true;
    this.input.hidden = false;
    this.input.focus();
    this.changed();
  }

  closeList() {
    this.list.hidden = true;
    this.list.replaceChildren();
    this.options = [];
    this.active = -1;
    this.input.setAttribute('aria-expanded', 'false');
    this.input.removeAttribute('aria-activedescendant');
  }

  async search() {
    const text = this.input.value.trim();
    const mine = ++this.seq;
    if (text.length < 2) { this.closeList(); return; }
    let results = [];
    let limited = false;
    try {
      const response = await fetch(`${this.urls.people}?q=${encodeURIComponent(text)}`, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      if (response.ok) results = (await response.json()).results || [];
      else if (response.status === 429) limited = true; // too many searches in a minute: say so, never show an empty list
    } catch { /* the typed address below still works */ }
    if (mine !== this.seq) return;
    this.renderOptions(text, results, limited);
  }

  renderOptions(text, results, limited = false) {
    const rows = results.map((r) => ({ type: 'person', r }));
    if (looksLikeAddress(text) && !results.some((r) => r.email === text.toLowerCase())) rows.push({ type: 'typed', text: text.trim() });
    this.options = rows;
    this.list.replaceChildren();
    if (!rows.length && !limited) { this.closeList(); return; }
    rows.forEach((row, i) => {
      const li = h('li', { class: 'o-em-option', role: 'option', id: `em-opt-${i}`, 'aria-selected': 'false' });
      if (row.type === 'typed') li.append(h('span', { class: 'o-em-opt-main' }, h('span', { class: 'o-em-opt-name', dir: 'auto', text: `Use ${row.text}` })));
      else {
        const { r } = row;
        li.append(h('span', { class: 'o-em-opt-main' }, h('span', { class: 'o-em-opt-name', dir: 'auto', text: r.name || r.email }), r.name ? h('span', { class: 'o-em-opt-addr', dir: 'auto', text: r.email }) : null));
        const badges = h('span', { class: 'o-em-opt-badges' });
        for (const kind of r.kinds || []) if (KIND[kind]) badges.append(h('span', { class: 'o-wa-quiet', text: KIND[kind] }));
        if (r.suppressed) { li.setAttribute('aria-disabled', 'true'); li.classList.add('is-off'); badges.append(h('span', { class: 'o-em-opt-off', text: 'Cannot be emailed' })); }
        li.append(badges);
      }
      li.addEventListener('pointerdown', (event) => event.preventDefault()); // the field keeps focus
      li.addEventListener('click', () => this.pick(i));
      this.list.append(li);
    });
    if (limited) this.list.append(h('li', { class: 'o-em-option is-off', role: 'presentation', text: 'Too many searches just now. Wait a minute, or type the full address.' }));
    this.list.hidden = false;
    this.input.setAttribute('aria-expanded', 'true');
    this.setActive(-1);
  }

  setActive(i) {
    this.active = i;
    [...this.list.children].forEach((li, n) => { if (li.getAttribute('role') === 'option') li.setAttribute('aria-selected', String(n === i)); });
    if (i >= 0) { this.input.setAttribute('aria-activedescendant', `em-opt-${i}`); this.list.children[i].scrollIntoView({ block: 'nearest' }); } else this.input.removeAttribute('aria-activedescendant');
  }

  pick(i) {
    const row = this.options[i];
    if (!row) return;
    if (row.type === 'typed') this.choose({ email: row.text.toLowerCase(), name: '', person: '' });
    else if (!row.r.suppressed) this.choose({ email: row.r.email, name: row.r.name || '', person: row.r.person || '' });
    else return;
    this.subject.focus();
  }

  // ---------- fields, errors, draft ----------

  showError(node, message) {
    node.hidden = !message;
    node.textContent = message || '';
  }

  bind() {
    const { signal } = this.ac;
    this.input.addEventListener('input', () => { clearTimeout(this.timer); this.showError(this.toError, ''); this.timer = setTimeout(() => this.search(), SEARCH_MS); this.changed(); }, { signal });
    this.input.addEventListener('keydown', (event) => {
      if (event.isComposing) return;
      const n = this.options.length;
      if (event.key === 'ArrowDown' && n) { event.preventDefault(); this.setActive((this.active + 1) % n); } else if (event.key === 'ArrowUp' && n) { event.preventDefault(); this.setActive((this.active - 1 + n) % n); } else if (event.key === 'Escape' && n) { event.preventDefault(); this.closeList(); } else if (event.key === 'Enter') {
        event.preventDefault();
        if (this.active >= 0) this.pick(this.active);
        else if (looksLikeAddress(this.input.value)) { this.choose({ email: this.input.value.trim().toLowerCase(), name: '', person: '' }); this.subject.focus(); }
      }
    }, { signal });
    this.input.addEventListener('blur', () => {
      const text = this.input.value.trim();
      if (text && looksLikeAddress(text)) { this.choose({ email: text.toLowerCase(), name: '', person: '' }); } else setTimeout(() => this.closeList(), 120);
    }, { signal });
    this.q('[data-to-clear]').addEventListener('click', () => this.clearTo(), { signal });
    this.subject.addEventListener('input', () => { this.showError(this.subjectError, ''); this.changed(); }, { signal });
    this.subject.addEventListener('keydown', (event) => { if (event.key === 'Enter' && !event.isComposing) { event.preventDefault(); this.editor.focus(); } }, { signal });
    for (const button of this.sendButtons) {
      button.addEventListener('pointerdown', (event) => event.preventDefault(), { signal });
      button.addEventListener('click', () => this.send(), { signal });
    }
  }

  ready() {
    return !!(this.to && this.subject.value.trim() && this.editor.hasContent() && !this.sending);
  }

  updateSend() {
    const ok = this.ready();
    for (const button of this.sendButtons) button.setAttribute('aria-disabled', String(!ok));
  }

  changed() {
    this.updateSend();
    clearTimeout(this.draftTimer);
    this.draftTimer = setTimeout(() => this.saveNow(), 400);
  }

  saveNow() {
    const html = this.editor.hasText() ? this.editor.html() : '';
    const subject = this.subject.value.trim();
    if (!html && !subject && !this.to) clearDraft(this.staff, 'new'); else saveDraft(this.staff, 'new', { html, subject, to: this.to });
  }

  // ---------- send ----------

  async send() {
    if (!this.ready()) return;
    this.sending = true;
    this.updateSend();
    for (const e of [this.toError, this.subjectError, this.bodyError]) this.showError(e, '');
    this.editor.setError('');
    const labels = this.sendButtons.map((b) => [b, b.querySelector('span')]);
    for (const [b, span] of labels) { b.setAttribute('aria-busy', 'true'); if (span) { b.dataset.was = span.textContent; span.textContent = 'Sending'; } }
    const body = new FormData();
    if (this.to.person) body.set('person', this.to.person); else body.set('to', this.to.email);
    body.set('subject', this.subject.value.trim());
    body.set('body_html', this.editor.html());
    const gold = new URLSearchParams(location.search).get('gold') || (/^gold:(.+)$/.exec(this.to.person || '') || [])[1];
    if (gold) body.set('gold', gold);
    for (const file of this.editor.files) body.append('files', file);
    try {
      const response = await fetch(this.urls.create, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrfToken(), Accept: 'application/json', 'X-Requested-With': 'fetch' }, body });
      const data = await response.json().catch(() => null);
      if (response.ok && data?.ok) {
        clearDraft(this.staff, 'new');
        const go = new CustomEvent('em:open-thread', { detail: { url: data.thread_url }, cancelable: true, bubbles: true });
        if (this.root.dispatchEvent(go)) location.assign(data.thread_url);
        return;
      }
      this.refused(data);
    } catch {
      this.editor.setError('No connection. Your email is still here. Try again in a moment.');
    } finally {
      this.sending = false;
      for (const [b, span] of labels) { b.removeAttribute('aria-busy'); if (span) span.textContent = b.dataset.was || 'Send'; }
      this.updateSend();
    }
  }

  refused(data) {
    const code = data?.error;
    if (code === 'bad_address') this.showError(this.toError, 'That email does not look right.');
    else if (code === 'no_subject') this.showError(this.subjectError, 'Add a subject.');
    else if (code === 'empty') this.showError(this.bodyError, 'Write something first.');
    else if (code === 'bad_target') this.showError(this.toError, data.message || 'That person could not be found.');
    else this.showError(this.bodyError, data?.message || 'That could not be sent. Try again.');
  }
}
