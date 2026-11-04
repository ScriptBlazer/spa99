/* One email thread in the Office (docs/features/email-chat-design.md sections 2 and 8).
 *
 * Safety rule: nothing from an email builds HTML in this page. Subjects, names, addresses, file names, previews and his plain text are set with textContent. The only
 * innerHTML is `body_html` of OUR OWN emails, which the server cleaned (common.richtext). His formatted emails live in a sandboxed iframe whose flags are exactly
 * `allow-same-origin allow-popups allow-popups-to-escape-sandbox`: NEVER allow-scripts (with allow-same-origin that would let his mail out of the sandbox altogether).
 * The page script only reads that frame's document to measure it and to fold quoted history; the frame runs no script of its own.
 *
 * The page embeds its data as JSON (#em-data); polling and sending keep this object in step with the server. A frame is loaded when its sheet first opens and is never
 * reloaded by a poll (updates only touch the status row), so his scroll and "Show images" are not lost. */
import { csrfToken } from './api.js';
import { toast } from './feedback.js';
import { bindKeyboard, releaseKeyboard } from './office-keyboard.js';
import { bytes, fullStamp, h, icon, phone, reduced, spokenStamp, timeOf } from './office-dom.js';
import { Editor } from './email-editor.js';
import { clearDraft, loadDraft, saveDraft } from './email-drafts.js';

const POLL_VISIBLE_MS = 15000;
const POLL_HIDDEN_MS = 60000;
const FRAME_FLAGS = 'allow-same-origin allow-popups allow-popups-to-escape-sandbox';
const MIN_FRAME = 80;
const SCALE_FLOOR = 0.6;
const FOLD_AT = 3;

const STATUS = {
  queued: { icon: 'clock', word: 'Sending' },
  sent: { icon: 'tick', word: 'Sent' },
  delivered: { icon: 'ticks', word: 'Delivered' },
  bounced: { icon: 'warning', word: 'Bounced', bad: true },
  failed: { icon: 'warning', word: 'Not sent', bad: true },
};

const first = (name) => String(name || '').split(/[\s@(]/)[0] || '';
function initials(name) {
  const words = String(name || '').split(' (')[0].replace(/[-@.]/g, ' ').split(/\s+/).filter(Boolean);
  if (!words.length || !/\p{L}/u.test(words[0][0])) return '';
  return (words[0][0] + (words.length > 1 ? words[words.length - 1][0] : '')).toUpperCase();
}
const oneLine = (text, n = 140) => String(text || '').replace(/\s+/g, ' ').trim().slice(0, n);

/** Text after `el` inside `root`: a quote at the very end of an email is history, one in the middle is part of what he wrote. */
function textAfter(el, root) {
  for (let node = el; node && node !== root; node = node.parentNode) {
    for (let next = node.nextSibling; next; next = next.nextSibling) if ((next.textContent || '').trim()) return true;
  }
  return false;
}

export class EmailThread {
  constructor(root) {
    this.root = root;
    const data = JSON.parse(root.querySelector('#em-data').textContent);
    this.data = data;
    this.thread = data.thread;
    this.urls = data.urls;
    this.gold = data.gold;
    this.staff = root.closest('[data-em-app]')?.dataset.staff || '';
    this.messages = [...data.chat_messages];
    this.byId = new Map(this.messages.map((m) => [m.id, m]));
    this.sheets = new Map();
    this.frames = new Map();
    this.open = new Map();
    this.touched = new Set();
    this.unfolded = new Set();
    this.lastId = data.last_id || 0;
    this.cursor = data.cursor;
    this.hasOlder = data.has_older;
    this.olderUrl = data.older_url;
    this.unread = data.unread || { count: 0, first_id: null };
    this.alive = true;
    this.polling = false;
    this.sending = false;
    this.tmp = 0;
    this.ac = new AbortController();
    this.q = (sel) => root.querySelector(sel);
    this.ui = {
      scroll: this.q('[data-scroll]'), msgs: this.q('[data-msgs]'), older: this.q('[data-older]'), olderRow: this.q('[data-older-row]'), live: this.q('[data-live]'),
      foot: this.q('[data-foot]'), replyOpen: this.q('[data-reply-open]'), replyText: this.q('[data-reply-open-text]'), composer: this.q('[data-composer]'),
    };
    this.defaults();
    this.layout();
    this.bindEvents();
    this.bindLightbox();
    this.bindComposer();
    this.jumpToStart();
    this.markRead();
    this.schedule();
    bindKeyboard(root, { signal: this.ac.signal });
  }

  destroy() {
    this.alive = false;
    this.ac.abort();
    clearTimeout(this.timer);
    clearTimeout(this.draftTimer);
    for (const state of this.frames.values()) { state.ro?.disconnect(); state.pageRo?.disconnect(); }
    this.editor?.destroy();
    releaseKeyboard();
  }

  say(text) { this.ui.live.textContent = ''; setTimeout(() => { if (this.alive) this.ui.live.textContent = text; }, 30); }

  // ---------- which sheets are open ----------

  isBad(m) { return !!STATUS[m.status]?.bad; }
  isUnread(m) { return m.direction === 'in' && !m.spam && this.unread.first_id && m.id >= this.unread.first_id; }

  /** Open on arrival: the newest, any unread, any bounced or failed. Spam stays collapsed even when newest. */
  defaultOpen(m, newest) {
    if (m.spam) return false;
    return m === newest || this.isUnread(m) || this.isBad(m);
  }

  defaults() {
    const newest = [...this.messages].reverse().find((m) => !m.spam) || null;   // spam never opens, so the thread opens at the newest message that is not spam
    for (const m of this.messages) if (!this.open.has(m.id)) this.open.set(m.id, this.defaultOpen(m, newest));
  }

  // ---------- building a sheet ----------

  senderOf(m) {
    if (m.direction === 'out') return m.author_first_name ? `${m.author_first_name}, Spa 99` : 'Spa 99';
    return m.from_name || m.author || m.from_address || this.thread.name;
  }

  addressOf(m) {
    return m.direction === 'out' ? `To ${this.thread.email}` : (m.from_address || 'Address not shown');
  }

  statusNode(m) {
    const s = STATUS[m.status];
    if (m.direction !== 'out' || !s) return null;
    return h('span', { class: `o-em-status${s.bad ? ' is-bad' : ''}`, 'data-status': m.status }, icon(s.icon), h('span', { text: s.word }));
  }

  makeSheet(m) {
    const mine = m.direction === 'out';
    const name = this.senderOf(m);
    const gold = !mine && (this.thread.labels || []).includes('Gold');
    const disc = h('span', { class: `o-wa-avatar o-wa-avatar--sm o-em-disc${mine ? ' o-em-disc--out' : ''}${gold ? ' o-wa-avatar--gold' : ''}`, 'aria-hidden': 'true', text: initials(mine ? m.author : name) || (mine ? 'S' : name.slice(0, 1).toUpperCase()) });
    const head = h('button', { type: 'button', class: 'o-em-mh', 'aria-expanded': 'true' });
    const side = h('span', { class: 'o-em-side' });
    side.append(h('span', { class: 'o-em-clip', 'data-clip': '', role: 'img', 'aria-label': 'Has a file', hidden: true }, icon('paperclip')));
    if (m.spam) side.append(h('span', { class: 'o-wa-quiet o-em-spam', text: 'Marked as spam' }));
    side.append(h('time', { class: 'o-wa-time', datetime: m.created_at, title: fullStamp(m.created_at), text: timeOf(m.created_at) }));
    head.append(disc, h('span', { class: 'o-em-who' }, h('span', { class: 'o-em-from', dir: 'auto', text: name }), h('span', { class: 'o-em-addr', 'data-addr': '' })), side);
    const art = h('article', { class: `o-em-msg o-em-msg--${m.direction}`, 'data-id': String(m.id), 'aria-label': `From ${first(name) || name}, ${spokenStamp(m.created_at)}` }, head, h('div', { class: 'o-em-open', 'data-open-part': '' }));
    head.addEventListener('click', () => this.toggle(m));
    this.sheets.set(m.id, art);
    this.fill(m, art);
    return art;
  }

  /** Header second row and the opened part. Called on creation and when the status changes (never rebuilds a frame). */
  fill(m, art) {
    const addr = art.querySelector('[data-addr]');
    const open = this.open.get(m.id);
    const status = this.statusNode(m);
    addr.replaceChildren();
    if (open) {
      addr.append(h('span', { class: 'o-em-addr-text', text: this.addressOf(m) }));
      if (status) addr.append(status);
    } else {
      addr.append(h('span', { class: 'o-em-preview', dir: 'auto', text: oneLine(m.body_text) || (m.attachments.length ? 'Attachment' : '') }));
      if (status && STATUS[m.status].bad) addr.append(status);
    }
    art.querySelector('[data-clip]').hidden = open || !m.attachments.length;
    art.classList.toggle('is-collapsed', !open);
    art.querySelector('.o-em-mh').setAttribute('aria-expanded', String(open));
    const part = art.querySelector('[data-open-part]');
    part.hidden = !open;
    if (open && !part.dataset.built) { this.buildBody(m, part); part.dataset.built = '1'; }
    if (open) this.patchFoot(m, part);
    if (open) this.frames.get(m.id)?.show?.();
  }

  buildBody(m, part) {
    const mine = m.direction === 'out';
    if (m.shows_subject && m.subject && m.subject !== this.thread.subject) part.append(h('h2', { class: 'o-em-msubject', dir: 'auto', text: m.subject }));
    if (m.from_other) {
      part.append(h('p', { class: 'o-em-note o-em-note--other' }, icon('warning'),
        h('span', { text: m.from_address ? `Sent from ${m.from_address}, not ${this.thread.email}. Check it is him before sharing anything.` : `The sender's address was not shown, so it may not be ${this.thread.email}. Check it is him before sharing anything.` })));
    }
    if (m.spam) part.append(h('p', { class: 'o-em-note' }, icon('warning'), h('span', { text: 'Flagged as spam. Nobody was notified. Take care with links and files.' })));
    if (mine) {
      const body = h('div', { class: 'o-em-body', dir: 'auto' });
      body.innerHTML = m.body_html; // ours only: the server cleaned it (common.richtext), the one allowed innerHTML
      part.append(body);
    } else if (m.frame_url) this.buildFrame(m, part);
    else this.buildText(m, part);
    if (m.attachments.length) part.append(this.filesNode(m));
    if (m.note) part.append(h('p', { class: 'o-em-filenote', text: m.note }));
    part.append(h('div', { class: 'o-em-foot-slot', 'data-foot-slot': '' }));
  }

  buildText(m, part) {
    const text = h('div', { class: 'o-em-text', dir: 'auto', text: m.body_text });
    part.append(text);
    if (m.body_full && m.body_full !== m.body_text) {
      let full = false;
      const toggle = h('button', { type: 'button', class: 'o-quiet o-em-toggle', text: 'Show earlier text' });
      toggle.addEventListener('click', () => { full = !full; text.textContent = full ? m.body_full : m.body_text; toggle.textContent = full ? 'Hide earlier text' : 'Show earlier text'; });
      part.append(toggle);
    }
  }

  /** The delivery words are in the header; a bounce or a failure also gets its row at the foot of the sheet, open by default. */
  patchFoot(m, part) {
    const slot = part.querySelector('[data-foot-slot]');
    if (!slot) return;
    slot.replaceChildren();
    if (m.direction !== 'out' || !this.isBad(m)) return;
    const reason = m.error?.reason || (m.status === 'bounced' ? 'Bounced. The address did not accept this email.' : 'Not sent. Try again.');
    const row = h('div', { class: 'o-em-fail', role: 'group' }, h('span', { class: 'o-em-fail-text' }, icon('warning'), h('span', { text: reason })));
    if (m.status === 'bounced' && this.thread.page_url) row.append(h('a', { class: 'o-quiet', href: this.thread.page_url, text: 'Check his address' }));
    else if (m.error?.can_retry && m.retry_url) {
      const retry = h('button', { type: 'button', class: 'o-quiet', 'data-retry': '' }, icon('arrow-clockwise'), 'Try again');
      retry.addEventListener('click', () => this.retry(m, retry));
      row.append(retry);
    }
    slot.append(row);
  }

  filesNode(m) {
    const grid = h('div', { class: 'o-em-files' });
    for (const a of m.attachments) {
      const text = h('span', { class: 'o-wa-file-text' }, h('span', { class: 'o-wa-file-name', dir: 'auto', text: a.filename || 'File' }),
        h('span', { class: 'o-wa-file-size', text: `${a.type === 'application/pdf' ? 'PDF' : (String(a.filename || '').split('.').length > 1 ? String(a.filename).split('.').pop().toUpperCase().slice(0, 5) : 'File')}${a.size ? `, ${bytes(a.size)}` : ''}` }));
      if (a.is_image && a.inline) {
        const thumb = h('span', { class: 'o-em-thumb' }, h('img', { src: a.url, alt: '', loading: 'lazy', decoding: 'async' }));
        const card = h('button', { type: 'button', class: 'o-wa-file o-em-file', 'aria-label': `Open ${a.filename || 'picture'}` }, thumb, text);
        card.addEventListener('click', () => this.openLightbox(m, a));
        grid.append(card);
      } else if (a.inline) {
        grid.append(h('a', { class: 'o-wa-file o-em-file', href: a.url, target: '_blank', rel: 'noopener noreferrer' }, icon('file-pdf', 'o-icon o-wa-file-icon'), text));
      } else {
        grid.append(h('a', { class: 'o-wa-file o-em-file', href: a.url, download: a.filename || '', title: 'Downloads, does not open here' }, icon('download', 'o-icon o-wa-file-icon'), text));
      }
    }
    return grid;
  }

  // ---------- his email in the frame ----------

  buildFrame(m, part) {
    const state = { m, iframe: null, src: '', quoted: [], showQuoted: false, scale: 1 };
    this.frames.set(m.id, state);
    const iframe = h('iframe', { class: 'o-em-frame', sandbox: FRAME_FLAGS, title: `Email from ${first(this.senderOf(m)) || 'him'}`, loading: 'lazy', scrolling: 'no' });
    state.iframe = iframe;
    if (m.has_remote_images) {
      const row = h('p', { class: 'o-em-images' }, icon('image'), h('span', { text: 'Outside pictures are hidden.' }));
      const show = h('button', { type: 'button', class: 'o-quiet', text: 'Show images' });
      show.addEventListener('click', () => { row.remove(); this.setFrameSrc(state, m.frame_images_url); });
      row.append(show);
      part.append(row);
    }
    part.append(iframe);
    state.toggleRow = h('p', { class: 'o-em-quotes', hidden: true });
    state.toggle = h('button', { type: 'button', class: 'o-quiet o-em-toggle', text: 'Show earlier text' });
    state.toggle.addEventListener('click', () => this.toggleQuoted(state));
    state.toggleRow.append(state.toggle);
    part.append(state.toggleRow);
    iframe.addEventListener('load', () => { if (state.src && iframe.getAttribute('src') === state.src) this.frameLoaded(state); });
    state.show = () => { if (!state.src) this.setFrameSrc(state, m.frame_url); else this.fit(state); };
    state.show();
    state.pageRo = new ResizeObserver(() => this.fit(state, true));
    state.pageRo.observe(iframe);
  }

  /** Loaded when it first opens (thirty frames at once would be heavy), never again unless staff chose Show images. */
  setFrameSrc(state, url) {
    state.src = url;
    state.iframe.setAttribute('src', url);
  }

  frameLoaded(state) {
    let doc = null;
    try { doc = state.iframe.contentDocument; } catch { doc = null; }
    if (!doc || !doc.documentElement || !doc.body) return;
    state.ro?.disconnect();
    const style = doc.createElement('style');
    style.textContent = 'html.em-fold [data-em-q]{display:none !important}';
    doc.head.append(style);
    this.foldQuotes(state, doc);
    this.fit(state);
    state.ro = new ResizeObserver(() => this.fit(state, true));
    state.ro.observe(doc.body);
  }

  /** Hide every `.quoted` and any outermost blockquote with no text after it. Outlook's quotes carry no marker, so they stay shown. If folding would leave nothing to read, nothing folds. */
  foldQuotes(state, doc) {
    const marks = new Set();
    for (const el of doc.querySelectorAll('.quoted')) if (!el.parentElement.closest('.quoted')) marks.add(el);
    for (const el of doc.querySelectorAll('blockquote')) {
      if (el.parentElement.closest('blockquote, .quoted')) continue;
      if (!textAfter(el, doc.body)) marks.add(el);
    }
    marks.forEach((el) => el.setAttribute('data-em-q', '1'));
    const rest = doc.body.cloneNode(true);
    rest.querySelectorAll('[data-em-q]').forEach((el) => el.remove());
    const readable = rest.textContent.trim() || rest.querySelector('img');
    if (!marks.size || !readable) { marks.forEach((el) => el.removeAttribute('data-em-q')); state.toggleRow.hidden = true; return; }
    state.toggleRow.hidden = false;
    doc.documentElement.classList.toggle('em-fold', !state.showQuoted);
    state.toggle.textContent = state.showQuoted ? 'Hide earlier text' : 'Show earlier text';
  }

  toggleQuoted(state) {
    state.showQuoted = !state.showQuoted;
    let doc = null;
    try { doc = state.iframe.contentDocument; } catch { /* gone */ }
    if (doc?.documentElement) doc.documentElement.classList.toggle('em-fold', !state.showQuoted);
    state.toggle.textContent = state.showQuoted ? 'Hide earlier text' : 'Show earlier text';
    this.fit(state);
  }

  /** Width: a document wider than the frame is scaled down to fit (floor 0.6; below it sideways scroll inside the frame). Height: from the document, never animated. */
  fit(state, fromObserver = false) {
    const { iframe } = state;
    let doc = null;
    try { doc = iframe.contentDocument; } catch { return; }
    if (!doc?.documentElement || !doc.body || !iframe.offsetParent) return;
    if (fromObserver) {
      if (state.busy) return;
      state.busy = true;
      requestAnimationFrame(() => { state.busy = false; });
    }
    const root = doc.documentElement;
    root.style.transform = '';
    root.style.transformOrigin = '';
    root.style.width = '';
    iframe.setAttribute('scrolling', 'no');
    const avail = iframe.clientWidth;
    const need = root.scrollWidth;
    let scale = 1;
    if (avail && need > avail + 1) {
      scale = Math.max(SCALE_FLOOR, avail / need);
      root.style.transformOrigin = '0 0';
      root.style.transform = `scale(${scale})`;
      if (avail / need < SCALE_FLOOR) iframe.setAttribute('scrolling', 'auto'); // small type that scrolls beats type too small to read
    }
    state.scale = scale;
    // the body's own box, not scrollHeight: scrollHeight never drops below the frame's current height, so a folded quote would leave the room it took
    const box = doc.body.getBoundingClientRect();
    const margins = (Number.parseFloat(doc.defaultView.getComputedStyle(doc.body).marginTop) || 0) + (Number.parseFloat(doc.defaultView.getComputedStyle(doc.body).marginBottom) || 0);
    const height = Math.max(MIN_FRAME, Math.ceil(box.height + margins * scale));
    if (iframe.style.height !== `${height}px`) iframe.style.height = `${height}px`;
  }

  // ---------- the list of sheets ----------

  toggle(m) {
    this.touched.add(m.id);
    const was = this.open.get(m.id);
    this.open.set(m.id, !was);
    const art = this.sheets.get(m.id);
    this.fill(m, art);
    if (!reduced() && !was) { const part = art.querySelector('[data-open-part]'); part.classList.remove('is-in'); void part.offsetWidth; part.classList.add('is-in'); }
  }

  /** Order, folds and open or collapsed. Existing sheets are never moved or rebuilt (moving an iframe in the DOM would reload it). */
  layout() {
    const list = this.messages;
    for (const m of list) if (!this.sheets.has(m.id)) this.makeSheet(m);
    this.ui.msgs.querySelectorAll('.o-em-fold').forEach((n) => n.remove());
    const nodes = [];
    let run = [];
    const flush = () => {
      if (run.length >= FOLD_AT) {
        nodes.push(this.foldRow(run));
        run.forEach((id) => { this.sheets.get(id).hidden = true; nodes.push(this.sheets.get(id)); });
      } else run.forEach((id) => { this.sheets.get(id).hidden = false; nodes.push(this.sheets.get(id)); });
      run = [];
    };
    for (const m of list) {
      const collapsed = !this.open.get(m.id) && !this.unfolded.has(m.id);
      if (collapsed) run.push(m.id); else { flush(); this.sheets.get(m.id).hidden = false; nodes.push(this.sheets.get(m.id)); }
    }
    flush();
    const wanted = new Set(nodes);
    for (const child of [...this.ui.msgs.children]) if (!wanted.has(child)) child.remove();
    let cursor = this.ui.msgs.firstElementChild;
    for (const node of nodes) {
      if (node === cursor) { cursor = cursor.nextElementSibling; continue; }
      this.ui.msgs.insertBefore(node, cursor);
    }
    this.ui.olderRow.hidden = !this.hasOlder;
  }

  foldRow(ids) {
    const button = h('button', { type: 'button', class: 'o-quiet o-em-foldbtn', text: `Show ${ids.length} earlier emails` });
    button.addEventListener('click', () => { ids.forEach((id) => this.unfolded.add(id)); this.layout(); this.sheets.get(ids[0])?.querySelector('.o-em-mh')?.focus({ preventScroll: true }); });
    return h('p', { class: 'o-em-fold' }, button);
  }

  /** Where it opens: at the top of the first unread message, or else the top of the newest. Not the bottom: a long email is read from its start. */
  jumpToStart() {
    const { scroll } = this.ui;
    const target = (this.unread.first_id && this.sheets.get(this.unread.first_id)) || this.sheets.get(this.messages[this.messages.length - 1]?.id);
    if (!target || target === this.ui.msgs.querySelector('.o-em-msg:not([hidden])')) { scroll.scrollTop = 0; return; }
    this.scrollToSheet(target, 'start');
  }

  scrollToSheet(sheet, at = 'start') {
    const { scroll } = this.ui;
    if (!sheet) return;
    const top = sheet.getBoundingClientRect().top - scroll.getBoundingClientRect().top + scroll.scrollTop;
    scroll.scrollTop = Math.max(0, top - (at === 'start' ? 4 : 0));
  }

  async loadOlder() {
    if (!this.hasOlder || this.loadingOlder || !this.alive) return;
    this.loadingOlder = true;
    this.ui.older.setAttribute('aria-busy', 'true');
    const { scroll } = this.ui;
    try {
      const response = await fetch(this.olderUrl, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error(String(response.status));
      const data = await response.json();
      const before = scroll.scrollHeight;
      const top = scroll.scrollTop;
      const fresh = data.messages.filter((m) => !this.byId.has(m.id));
      fresh.forEach((m) => { this.byId.set(m.id, m); this.open.set(m.id, this.defaultOpen(m, null)); });
      this.messages = [...fresh, ...this.messages];
      this.hasOlder = data.has_older;
      this.olderUrl = data.older_url;
      this.layout();
      scroll.scrollTop = top + (scroll.scrollHeight - before); // iOS Safari has no overflow-anchor: keep his place by hand
    } catch { toast('Earlier emails could not be loaded. Try again.', { kind: 'error' }); } finally {
      this.loadingOlder = false;
      this.ui.older.removeAttribute('aria-busy');
    }
  }

  // ---------- polling ----------

  schedule() {
    clearTimeout(this.timer);
    if (!this.alive) return;
    this.timer = setTimeout(() => this.poll(), document.visibilityState === 'visible' ? POLL_VISIBLE_MS : POLL_HIDDEN_MS);
  }

  async poll() {
    if (!this.alive) return;
    if (this.polling || this.sending) { this.schedule(); return; }
    this.polling = true;
    try {
      const url = `${this.urls.poll}?after=${this.lastId}&since=${encodeURIComponent(this.cursor)}`; // the cursor's "+00:00" breaks without this
      const response = await fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      if (!response.ok || new URL(response.url).pathname.startsWith('/login')) throw new Error(String(response.status));
      const data = await response.json();
      this.cursor = data.cursor;
      this.thread = { ...this.thread, ...data.thread };
      for (const m of data.updates || []) this.patch(m);
      const fresh = (data.messages || []).filter((m) => !this.byId.has(m.id));
      for (const m of fresh) { this.byId.set(m.id, m); this.messages.push(m); this.open.set(m.id, this.defaultOpen(m, m)); }
      this.lastId = Math.max(this.lastId, data.last_id || 0);
      if (fresh.length) {
        this.layout();
        const theirs = fresh.filter((m) => m.direction === 'in' && !m.spam);
        if (theirs.length) { this.say(`New email from ${first(this.thread.name) || this.thread.name}`); this.markRead(); }
      }
      document.dispatchEvent(new CustomEvent('em:unread', { detail: { total: data.unread_total } }));
    } catch { /* quiet: the next poll tries again */ } finally {
      this.polling = false;
      this.schedule();
    }
  }

  /** A status changed: only the status words and the foot row move. A frame is never touched. */
  patch(m) {
    const old = this.byId.get(m.id);
    if (!old) return;
    Object.assign(old, m);
    if (this.isBad(old) && !this.touched.has(old.id)) this.open.set(old.id, true);
    const art = this.sheets.get(old.id);
    if (!art) return;
    this.fill(old, art);
    this.layout();
  }

  async markRead() {
    if (!this.alive || document.visibilityState !== 'visible' || this.readBusy) return;
    this.readBusy = true;
    try {
      const response = await fetch(this.urls.read, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrfToken(), Accept: 'application/json' } });
      if (response.ok) { const data = await response.json(); document.dispatchEvent(new CustomEvent('em:unread', { detail: { total: data.unread_total, read: this.thread.id } })); }
    } catch { /* tried again on the next poll */ } finally { this.readBusy = false; }
  }

  async retry(m, button) {
    if (button.getAttribute('aria-busy') === 'true') return;
    button.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch(m.retry_url, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrfToken(), Accept: 'application/json' } });
      const data = await response.json().catch(() => null);
      if (data?.ok) { Object.assign(m, data.message); this.fill(m, this.sheets.get(m.id)); } else toast(data?.message || 'That could not be sent again.', { kind: 'error' });
    } catch { toast('No connection. Try again in a moment.', { kind: 'error' }); } finally { button.removeAttribute('aria-busy'); }
  }

  bindEvents() {
    const { signal } = this.ac;
    this.ui.older.addEventListener('click', () => this.loadOlder(), { signal });
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') { this.poll(); this.markRead(); } else this.schedule();
    }, { signal });
    // Back on a phone keeps the list's scroll: go back in history when the list is where he came from
    const back = this.q('[data-em-back]');
    back?.addEventListener('click', (event) => {
      if (!phone() || event.metaKey || event.ctrlKey || event.shiftKey) return;
      try {
        if (history.length > 1 && new URL(document.referrer).pathname === new URL(back.href).pathname) { event.preventDefault(); history.back(); }
      } catch { /* a normal link */ }
    }, { signal });
    this.root.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && this.composing && !this.root.querySelector('dialog[open]')) { event.preventDefault(); this.closeComposer(); }
    }, { signal });
  }

  // ---------- pictures ----------

  bindLightbox() {
    const box = this.q('[data-lightbox]');
    this.lightbox = box;
    const close = () => box.close();
    this.q('[data-lb-close]').addEventListener('click', close, { signal: this.ac.signal });
    box.addEventListener('click', (event) => { if (event.target === box) close(); }, { signal: this.ac.signal });
    box.addEventListener('close', () => { this.lbOpener?.focus({ preventScroll: true }); box.querySelector('[data-lb-img]').removeAttribute('src'); }, { signal: this.ac.signal });
  }

  openLightbox(m, a) {
    const box = this.lightbox;
    this.lbOpener = document.activeElement;
    box.querySelector('[data-lb-img]').src = a.url;
    const dl = box.querySelector('[data-lb-download]');
    dl.href = a.url;
    dl.setAttribute('download', a.filename || 'picture');
    box.querySelector('[data-lb-cap]').textContent = `${this.senderOf(m)}, ${fullStamp(m.created_at)}`;
    box.showModal();
  }

  // ---------- the reply ----------

  get composing() { return this.root.hasAttribute('data-composing'); }

  bindComposer() {
    const { replyOpen, composer } = this.ui;
    if (!composer) return;
    const { signal } = this.ac;
    this.subjectRow = this.q('[data-subject-row]');
    this.subjectInput = this.q('[data-subject-input]');
    this.subjectToggle = this.q('[data-subject-toggle]');
    this.sendButtons = [...this.root.querySelectorAll('[data-ed-send]')];
    this.editor = new Editor(this.q('[data-editor]'), { limits: this.thread.limits, onChange: () => this.changed(), onSend: () => this.send(), onFiles: () => this.changed() });
    replyOpen.addEventListener('click', () => this.openComposer(), { signal });
    this.q('[data-reply-close]').addEventListener('click', () => this.closeComposer(), { signal });
    this.q('[data-reply-close-desk]')?.addEventListener('click', () => this.closeComposer(), { signal });
    this.q('[data-discard]').addEventListener('click', () => this.discard(), { signal });
    this.subjectToggle.addEventListener('click', () => {
      const show = this.subjectRow.hidden;
      this.subjectRow.hidden = !show;
      this.subjectToggle.setAttribute('aria-expanded', String(show));
      if (show) this.subjectInput.focus();
    }, { signal });
    this.subjectInput.addEventListener('input', () => this.changed(), { signal });
    for (const button of this.sendButtons) {
      button.addEventListener('pointerdown', (event) => event.preventDefault(), { signal }); // the keyboard stays
      button.addEventListener('click', () => this.send(), { signal });
    }
    const draft = loadDraft(this.staff, this.thread.id);
    if (draft && (draft.html || draft.subject)) {
      if (draft.html) this.editor.setHtml(draft.html);
      if (draft.subject && draft.subject !== this.data.reply_subject) { this.subjectInput.value = draft.subject; this.subjectRow.hidden = false; this.subjectToggle.setAttribute('aria-expanded', 'true'); }
    }
    this.updateReplyLabel();
    this.updateSend();
  }

  openComposer() {
    this.root.setAttribute('data-composing', '');
    this.ui.composer.hidden = false;
    this.ui.replyOpen.hidden = true;
    this.editor.focus();
    this.say('Reply');
  }

  closeComposer() {
    this.root.removeAttribute('data-composing');
    this.ui.composer.hidden = true;
    this.ui.replyOpen.hidden = false;
    this.saveNow();
    this.updateReplyLabel();
    this.ui.replyOpen.focus({ preventScroll: true });
  }

  subjectValue() {
    const value = this.subjectInput.value.trim();
    return value && value !== String(this.data.reply_subject || '').trim() ? value : '';
  }

  changed() {
    this.updateSend();
    clearTimeout(this.draftTimer);
    this.draftTimer = setTimeout(() => this.saveNow(), 400);
  }

  saveNow() {
    clearTimeout(this.draftTimer);
    if (!this.editor) return;
    const html = this.editor.hasText() ? this.editor.html() : '';
    const subject = this.subjectValue();
    if (!html && !subject) clearDraft(this.staff, this.thread.id); else saveDraft(this.staff, this.thread.id, { html, subject });
    this.updateReplyLabel();
  }

  updateReplyLabel() {
    const text = this.editor?.hasText() ? this.editor.text() : '';
    this.ui.replyText.textContent = text ? `Draft: ${oneLine(text, 40)}${text.length > 40 ? '...' : ''}` : 'Write a reply';
    this.ui.replyOpen.classList.toggle('has-draft', !!text);
  }

  ready() { return !!this.editor?.hasContent() && !this.sending; }

  updateSend() {
    const ok = this.ready();
    for (const button of this.sendButtons) button.setAttribute('aria-disabled', String(!ok));
  }

  async discard() {
    this.editor.clear();
    this.subjectInput.value = this.data.reply_subject || '';
    clearDraft(this.staff, this.thread.id);
    this.updateSend();
    this.updateReplyLabel();
    toast('Draft discarded.');
    if (phone()) this.closeComposer(); else this.editor.focus();
  }

  async send() {
    if (!this.ready()) return;
    this.sending = true;
    this.updateSend();
    this.editor.setError('');
    for (const button of this.sendButtons) { button.dataset.was = button.querySelector('span')?.textContent || 'Send'; button.setAttribute('aria-busy', 'true'); if (button.querySelector('span')) button.querySelector('span').textContent = 'Sending'; }
    const body = new FormData();
    body.set('body_html', this.editor.html());
    const subject = this.subjectValue();
    if (subject) body.set('subject', subject);
    if (this.gold) body.set('gold', this.gold.id);
    for (const file of this.editor.files) body.append('files', file);
    try {
      const response = await fetch(this.urls.send, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrfToken(), Accept: 'application/json' }, body });
      const data = await response.json().catch(() => null);
      if (response.ok && data?.ok) {
        const m = data.message;
        this.editor.clear();
        this.subjectInput.value = this.data.reply_subject || '';
        this.subjectRow.hidden = true;
        this.subjectToggle.setAttribute('aria-expanded', 'false');
        clearDraft(this.staff, this.thread.id);
        this.updateReplyLabel();
        if (!this.byId.has(m.id)) { this.byId.set(m.id, m); this.messages.push(m); this.open.set(m.id, true); this.lastId = Math.max(this.lastId, m.id); }
        this.layout();
        this.closeComposer();
        this.scrollToSheet(this.sheets.get(m.id), 'start');
        if (this.gold && this.gold.status === 'new') { this.gold.status = 'contacted'; toast('Marked Contacted.'); }
      } else {
        this.editor.setError(data?.message || 'That could not be sent. Try again.');
      }
    } catch {
      this.editor.setError('No connection. Your email is still here. Try again in a moment.');
    } finally {
      this.sending = false;
      for (const button of this.sendButtons) { button.removeAttribute('aria-busy'); if (button.querySelector('span')) button.querySelector('span').textContent = button.dataset.was || 'Send'; }
      this.updateSend();
    }
  }
}

