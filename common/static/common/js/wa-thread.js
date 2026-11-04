/* One WhatsApp chat in the Office (docs/features/whatsapp-design.md sections 3 to 5).
 *
 * Safety rule: no HTML is ever built from message text here. Bubbles are made with createElement and textContent; the only innerHTML is
 * `body_html`, which the server has already escaped and formatted (whatsapp.formatting.render), and a template's `body_html` for the preview.
 * The chat page embeds its data as JSON (#wa-data); polling and sending keep this object in step with the server. */
import { csrfToken } from './api.js';
import { toast } from './feedback.js';

const LONDON = 'Europe/London';
const TIME = new Intl.DateTimeFormat('en-GB', { timeZone: LONDON, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
const DAYKEY = new Intl.DateTimeFormat('en-CA', { timeZone: LONDON, year: 'numeric', month: '2-digit', day: '2-digit' });
const WEEKDAY = new Intl.DateTimeFormat('en-GB', { timeZone: LONDON, weekday: 'long' });
const FULLDAY = new Intl.DateTimeFormat('en-GB', { timeZone: LONDON, day: 'numeric', month: 'short', year: 'numeric' });
const GROUP_MS = 5 * 60 * 1000;
const POLL_VISIBLE_MS = 4000;
const POLL_HIDDEN_MS = 30000;
const NEAR_BOTTOM = '0px 0px 96px 0px';
const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const desktopKeys = () => window.matchMedia('(hover: hover) and (pointer: fine)').matches;
const phone = () => window.matchMedia('(max-width: 63.99em)').matches;

const SVG = 'http://www.w3.org/2000/svg';
export function icon(name, cls = 'o-icon') {
  const svg = document.createElementNS(SVG, 'svg');
  svg.setAttribute('class', cls);
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  const use = document.createElementNS(SVG, 'use');
  use.setAttribute('href', `#i-${name}`);
  svg.append(use);
  return svg;
}

/** createElement with attributes and children; strings become text nodes (never HTML). */
function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children) if (child !== null && child !== undefined && child !== false) node.append(child);
  return node;
}

const dayOf = (iso) => DAYKEY.format(new Date(iso));
const timeOf = (iso) => TIME.format(new Date(iso));
function dayLabel(iso) {
  const key = dayOf(iso);
  const today = DAYKEY.format(new Date());
  const toNum = (k) => Date.UTC(...k.split('-').map((n, i) => (i === 1 ? Number(n) - 1 : Number(n))));
  const days = Math.round((toNum(today) - toNum(key)) / 86400000);
  if (days <= 0) return 'Today';
  if (days === 1) return 'Yesterday';
  if (days < 7) return WEEKDAY.format(new Date(iso));
  return FULLDAY.format(new Date(iso));
}
const fullStamp = (iso) => `${FULLDAY.format(new Date(iso))}, ${timeOf(iso)}`;
function bytes(n) {
  if (!n) return '';
  if (n < 1024 * 1024) return `${Math.max(1, Math.round(n / 1024))} KB`;
  return `${(n / 1024 / 1024).toFixed(1).replace(/\.0$/, '')} MB`;
}
const mb = (n) => `${Math.round(n / 1024 / 1024)} MB`;

const STATUS = {
  queued: { icon: 'clock', word: 'Sending' },
  sent: { icon: 'tick', word: 'Sent' },
  delivered: { icon: 'ticks', word: 'Delivered' },
  read: { icon: 'ticks', word: 'Read' },
  failed: { icon: 'warning', word: 'Not sent' },
  undelivered: { icon: 'warning', word: 'Not sent' },
};
const BAD = new Set(['failed', 'undelivered']);

const OTHER_WORDS = { audio: 'Voice note', video: 'Video', file: 'File', other: 'Message' };

export class Thread {
  constructor(root) {
    this.root = root;
    const data = JSON.parse(root.querySelector('#wa-data').textContent);
    this.data = data;
    this.contact = data.contact;
    this.urls = data.urls;
    this.configured = data.configured;
    this.gold = data.gold;
    this.messages = [...data.messages];
    this.byId = new Map();
    this.rows = new Map();
    this.lastId = data.last_id || 0;
    this.cursor = data.cursor;
    this.hasOlder = data.has_older;
    this.olderUrl = data.older_url;
    this.unread = data.unread || { count: 0, first_id: null };
    this.templates = data.templates || [];
    this.atBottom = true;
    this.pending = 0;
    this.sending = 0;
    this.tmp = 0;
    this.file = null;
    this.polling = false;
    this.offline = false;
    this.alive = true;
    this.warned = false;
    this.ac = new AbortController();
    this.q = (sel) => root.querySelector(sel);
    this.ui = {
      scroll: this.q('[data-scroll]'), msgs: this.q('[data-msgs]'), older: this.q('[data-older]'), start: this.q('[data-start]'),
      jump: this.q('[data-jump]'), jumpCount: this.q('[data-jump-count]'), live: this.q('[data-live]'), wallNote: this.q('[data-wall-note]'),
      win: this.q('[data-win]'), pill: this.q('[data-win-pill]'), offline: this.q('[data-offline]'), input: this.q('[data-input]'),
      send: this.q('[data-send]'), composer: this.q('[data-composer]'), count: this.q('[data-count]'), file: this.q('[data-file]'),
      tray: this.q('[data-tray]'), trayThumb: this.q('[data-tray-thumb]'), trayName: this.q('[data-tray-name]'), traySize: this.q('[data-tray-size]'),
      trayError: this.q('[data-tray-error]'), drop: this.q('[data-drop]'), wall: this.q('[data-wall]'),
    };
    for (const m of this.messages) this.byId.set(m.id, m);
    this.layout();
    this.bindObservers();
    this.bindComposer();
    this.bindLightbox();
    this.bindTemplates();
    this.bindViewport();
    this.bindEvents();
    this.applyState();
    this.restoreDraft();
    this.jumpToStart();
    this.markRead();
    this.schedule();
    this.clock = setInterval(() => this.applyState(), 30000);
    if (data.open_picker && this.state === 'empty') this.openPicker();
  }

  destroy() {
    this.alive = false;
    this.ac.abort();
    clearTimeout(this.timer);
    clearInterval(this.clock);
    this.io?.forEach((io) => io.disconnect());
    document.body.removeAttribute('data-keyboard');
    for (const url of this.urls_to_free || []) URL.revokeObjectURL(url);
  }

  // ---------- state: which of the composer's slots is shown ----------

  windowEnds() { return this.contact.window.ends_at ? new Date(this.contact.window.ends_at).getTime() : 0; }

  computeState() {
    if (!this.configured) return 'unconfigured';
    if (!this.contact.can_send) return 'viewonly';
    const w = this.contact.window.state;
    if (this.contact.opted_out || w === 'opted_out') return 'opted_out';
    if (w === 'open') return this.windowEnds() > Date.now() ? 'open' : 'closed';
    return w;
  }

  applyState() {
    const state = this.computeState();
    const was = this.state;
    this.state = state;
    this.root.dataset.state = state;
    this.root.querySelectorAll('[data-slot]').forEach((slot) => { slot.hidden = slot.dataset.slot !== state; });
    // the line above the composer (open window only) and the desktop pill
    const left = this.windowEnds() - Date.now();
    const { win, pill } = this.ui;
    if (state === 'open') {
      const minutes = Math.max(0, Math.ceil(left / 60000));
      if (left < 3600000) {
        win.hidden = false;
        win.className = 'o-wa-win o-wa-win--soon';
        win.replaceChildren(icon('clock'), document.createTextNode(minutes <= 1 ? 'Window closes in under a minute' : `Window closes in ${minutes} minutes`));
        if (!this.warned) { this.warned = true; this.say(minutes <= 1 ? 'The window closes in under a minute.' : `The window closes in ${minutes} minutes.`); }
      } else {
        win.hidden = false;
        win.className = 'o-wa-win';
        win.replaceChildren(document.createTextNode(`Window closes in ${Math.floor(left / 3600000)}h`));
      }
      pill.textContent = `Open, ${left < 3600000 ? `${minutes}m` : `${Math.floor(left / 3600000)}h`} left`;
    } else {
      win.hidden = true;
      pill.textContent = state === 'closed' || state === 'template_waiting' ? 'Closed' : (state === 'opted_out' ? 'Opted out' : '');
    }
    pill.hidden = !pill.textContent;
    const note = this.ui.wallNote;
    if (!this.messages.length) { note.hidden = false; note.textContent = 'No messages yet.'; } else note.hidden = true;
    if (state !== was && state === 'open' && was) this.ui.input?.focus({ preventScroll: true });
    this.updateSend();
  }

  say(text) { this.ui.live.textContent = ''; setTimeout(() => { if (this.alive) this.ui.live.textContent = text; }, 30); }

  // ---------- building the message list ----------

  /** Rebuild the order of dividers and bubbles from `this.messages`. Existing bubbles are moved, not rebuilt, so photos never reload. */
  layout() {
    const msgs = this.messages;
    const authors = new Set(msgs.filter((m) => m.direction === 'out' && m.author_id).map((m) => m.author_id));
    const multi = authors.size > 1;
    const nodes = [];
    let prev = null;
    for (const m of msgs) {
      const iso = m.created_at;
      const newDay = !prev || dayOf(prev.created_at) !== dayOf(iso);
      if (newDay) nodes.push(this.dayNode(iso));
      const unreadHere = this.unread.first_id && m.id === this.unread.first_id;
      if (unreadHere) nodes.push(this.unreadNode());
      const sameSender = prev && prev.direction === m.direction && (m.direction === 'in' || prev.author_id === m.author_id);
      const first = !prev || newDay || unreadHere || !sameSender || new Date(iso) - new Date(prev.created_at) > GROUP_MS;
      let row = this.rows.get(m.id);
      if (!row) { row = this.makeRow(m); this.rows.set(m.id, row); }
      row.classList.toggle('is-first', first);
      const author = row.querySelector('[data-author]');
      if (author) author.hidden = !(first && multi);
      nodes.push(row);
      prev = m;
    }
    this.ui.msgs.replaceChildren(...nodes);
    this.ui.start.hidden = this.hasOlder || !msgs.length;
  }

  dayNode(iso) { return h('li', { class: 'o-wa-day', 'aria-hidden': 'true' }, h('span', { text: dayLabel(iso) })); }

  unreadNode() {
    this.unreadEl = h('li', { class: 'o-wa-unread', 'data-unread-divider': '' }, h('span', { text: `${this.unread.count} unread message${this.unread.count === 1 ? '' : 's'}` }));
    return this.unreadEl;
  }

  srPrefix(m) {
    const when = timeOf(m.created_at);
    if (m.direction === 'in') return `${this.contact.name}, ${when}: `;
    const status = STATUS[m.status];
    return `You, ${when}${status ? `, ${status.word.toLowerCase()}` : ''}: `;
  }

  metaNode(m) {
    const meta = h('span', { class: 'o-wa-meta', title: `${fullStamp(m.created_at)}${m.direction === 'out' && STATUS[m.status] ? `, ${STATUS[m.status].word}` : ''}` },
      h('time', { datetime: m.created_at, text: timeOf(m.created_at) }));
    if (m.direction === 'out' && STATUS[m.status]) {
      const s = STATUS[m.status];
      meta.append(h('span', { class: `o-wa-tick o-wa-tick--${m.status}`, role: 'img', 'aria-label': s.word }, icon(s.icon)));
    }
    return meta;
  }

  failNode(m) {
    if (!BAD.has(m.status) && !m.localFail) return null;
    const reason = (m.error && m.error.reason) || 'Not sent. Try again.';
    const box = h('div', { class: 'o-wa-fail', role: 'group' }, h('span', { class: 'o-wa-fail-text' }, icon('warning'), h('span', { text: reason })));
    if ((m.error && m.error.can_retry) || m.retry) {
      const button = h('button', { type: 'button', class: 'o-quiet', 'data-retry': '' }, icon('arrow-clockwise'), 'Try again');
      button.addEventListener('click', () => this.retry(m, button));
      box.append(button);
    }
    return box;
  }

  /** The file or media part of a bubble. */
  mediaNode(m) {
    const media = m.media;
    if (m.kind === 'image' && media) {
      const img = h('img', { alt: '', loading: 'lazy', decoding: 'async', src: media.url });
      if (media.width && media.height) { img.width = media.width; img.height = media.height; }
      const ratio = media.width && media.height ? `${media.width} / ${media.height}` : '4 / 3';
      const button = h('button', { type: 'button', class: 'o-wa-photo', 'aria-label': 'Open photo', style: `aspect-ratio: ${ratio}` }, img);
      button.addEventListener('click', () => this.openLightbox(m));
      return button;
    }
    if (m.kind === 'document' && media) {
      const name = media.filename || 'Document';
      return h('a', { class: 'o-wa-file', href: media.url, target: '_blank', rel: 'noopener noreferrer' },
        icon('file-pdf', 'o-icon o-wa-file-icon'), h('span', { class: 'o-wa-file-text' }, h('span', { class: 'o-wa-file-name', text: name }),
          h('span', { class: 'o-wa-file-size', text: `PDF${media.size ? `, ${bytes(media.size)}` : ''}` })), icon('download'));
    }
    if (m.kind === 'audio' && media) return h('audio', { class: 'o-wa-audio', controls: true, preload: 'none', src: media.url, 'aria-label': 'Voice note' });
    if (m.kind === 'video' && media) return h('video', { class: 'o-wa-video', controls: true, preload: 'metadata', playsinline: true, src: media.url, 'aria-label': 'Video' });
    if (media) {
      return h('a', { class: 'o-wa-file', href: media.url, download: media.filename || '' }, icon('file-pdf', 'o-icon o-wa-file-icon'),
        h('span', { class: 'o-wa-file-text' }, h('span', { class: 'o-wa-file-name', text: media.filename || OTHER_WORDS[m.kind] || 'File' }), h('span', { class: 'o-wa-file-size', text: bytes(media.size) || 'Download' })), icon('download'));
    }
    if (['audio', 'video', 'file', 'other'].includes(m.kind)) {
      return h('div', { class: 'o-wa-file o-wa-file--none' }, icon('file-pdf', 'o-icon o-wa-file-icon'),
        h('span', { class: 'o-wa-file-text' }, h('span', { class: 'o-wa-file-name', text: m.kind === 'other' ? 'This type of message cannot be shown here.' : `${OTHER_WORDS[m.kind]}. This type cannot be shown here.` })));
    }
    return null;
  }

  makeRow(m) {
    const li = h('li', { class: `o-wa-line o-wa-line--${m.direction}`, 'data-id': String(m.id) });
    li.append(this.makeBubble(m));
    const fail = this.failNode(m);
    if (fail) li.append(fail);
    return li;
  }

  makeBubble(m) {
    const bubble = h('div', { class: `o-wa-msg o-wa-msg--${m.direction}` });
    bubble.append(h('span', { class: 'sr-only', 'data-sr': '', text: this.srPrefix(m) }));
    if (m.direction === 'out' && m.author_first_name) bubble.append(h('p', { class: 'o-wa-author', 'data-author': '', text: m.author_first_name, title: m.author || '' }));
    if (m.template) bubble.append(h('p', { class: 'o-wa-tpl-label', text: `Template: ${m.template.label}` }));
    const media = this.mediaNode(m);
    if (media) bubble.append(media);
    const hasText = !!(m.body_html || m.localText);
    if (hasText) {
      const text = h('div', { class: 'o-wa-text', dir: 'auto' });
      if (m.body_html) text.innerHTML = m.body_html; // server-escaped and formatted, never built here
      else text.textContent = m.localText; // an unsent bubble shows plain text until the server answers
      text.append(h('span', { class: 'o-wa-spacer', 'aria-hidden': 'true' }));
      bubble.append(text);
    }
    bubble.classList.toggle('has-text', hasText);
    bubble.classList.toggle('has-photo', m.kind === 'image' && !!m.media);
    bubble.classList.toggle('has-photo-only', m.kind === 'image' && !!m.media && !hasText);
    if (m.progress !== undefined) {
      bubble.classList.add('is-uploading');
      bubble.append(h('span', { class: 'o-wa-progress', 'data-progress': '' }, h('span')));
    }
    bubble.append(this.metaNode(m));
    return bubble;
  }

  /** Tick, error and sr text changed: update in place. */
  patchRow(m) {
    const row = this.rows.get(m.id);
    if (!row) return;
    const bubble = row.querySelector('.o-wa-msg');
    bubble.querySelector('[data-sr]').textContent = this.srPrefix(m);
    bubble.querySelector('.o-wa-meta').replaceWith(this.metaNode(m));
    row.querySelector('.o-wa-fail')?.remove();
    const fail = this.failNode(m);
    if (fail) row.append(fail);
  }

  // ---------- scrolling, observers ----------

  bindObservers() {
    const { scroll } = this.ui;
    this.io = [];
    const watch = (selector, margin, fn) => {
      const target = this.q(selector);
      const io = new IntersectionObserver(([entry]) => fn(entry), { root: scroll, rootMargin: margin });
      io.observe(target);
      this.io.push(io);
    };
    watch('[data-bottom-sentinel]', '0px 0px 100% 0px', (e) => { this.far = !e.isIntersecting; this.syncJump(); });
    watch('[data-bottom-sentinel]', NEAR_BOTTOM, (e) => {
      this.atBottom = e.isIntersecting;
      if (this.atBottom) { this.pending = 0; this.syncJump(); this.markRead(); }
    });
    watch('[data-top-sentinel]', '100% 0px 0px 0px', (e) => { if (e.isIntersecting) this.loadOlder(); });
    this.ui.jump.addEventListener('click', () => { this.scrollToBottom(); this.pending = 0; this.syncJump(); });
  }

  syncJump() {
    const show = this.far || this.pending > 0;
    this.ui.jump.hidden = !show;
    this.ui.jumpCount.hidden = !this.pending;
    this.ui.jumpCount.textContent = this.pending > 99 ? '99+' : String(this.pending || '');
    if (this.pending) this.ui.jumpCount.setAttribute('aria-label', `${this.pending} new`);
  }

  scrollToBottom() {
    const { scroll } = this.ui;
    scroll.scrollTop = scroll.scrollHeight;
  }

  /** Opening: unread divider a third of the way down, otherwise the newest message. */
  jumpToStart() {
    const { scroll } = this.ui;
    if (this.unreadEl) {
      const delta = this.unreadEl.getBoundingClientRect().top - scroll.getBoundingClientRect().top;
      scroll.scrollTop += delta - scroll.clientHeight / 3;
    } else this.scrollToBottom();
    requestAnimationFrame(() => { if (!this.unreadEl) this.scrollToBottom(); });
  }

  async loadOlder() {
    if (!this.hasOlder || this.loadingOlder || !this.alive) return;
    this.loadingOlder = true;
    this.ui.older.hidden = false;
    const { scroll } = this.ui;
    try {
      const response = await fetch(this.olderUrl, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error(String(response.status));
      const data = await response.json();
      const before = scroll.scrollHeight;
      const top = scroll.scrollTop;
      const fresh = data.messages.filter((m) => !this.byId.has(m.id));
      fresh.forEach((m) => this.byId.set(m.id, m));
      this.messages = [...fresh, ...this.messages];
      this.hasOlder = data.has_older;
      this.olderUrl = data.older_url;
      this.layout();
      scroll.scrollTop = top + (scroll.scrollHeight - before); // iOS Safari has no overflow-anchor: keep his place by hand
    } catch { /* the next time the top comes into view tries again */ } finally {
      this.loadingOlder = false;
      this.ui.older.hidden = true;
    }
  }

  // ---------- polling ----------

  schedule() {
    clearTimeout(this.timer);
    if (!this.alive) return;
    const wait = document.visibilityState === 'visible' ? POLL_VISIBLE_MS : POLL_HIDDEN_MS;
    this.timer = setTimeout(() => this.poll(), this.offline ? Math.min(wait * 2, 15000) : wait);
  }

  async poll() {
    if (!this.alive) return;
    if (this.polling || this.sending > 0) { this.schedule(); return; }
    this.polling = true;
    try {
      const url = `${this.urls.poll}?after=${this.lastId}&since=${encodeURIComponent(this.cursor)}`;
      const response = await fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      if (!response.ok || new URL(response.url).pathname.startsWith('/login')) throw new Error(String(response.status));
      const data = await response.json();
      this.setOffline(false);
      this.cursor = data.cursor;
      this.contact = { ...this.contact, ...data.contact };
      let touched = false;
      for (const m of data.updates || []) {
        const old = this.byId.get(m.id);
        if (!old) continue;
        Object.assign(old, m);
        this.patchRow(old);
      }
      const incoming = [];
      for (const m of data.messages || []) {
        if (this.byId.has(m.id)) continue;
        this.byId.set(m.id, m);
        this.messages.push(m);
        incoming.push(m);
        touched = true;
      }
      this.lastId = Math.max(this.lastId, data.last_id || 0);
      if (touched) this.afterAppend(incoming);
      this.applyState();
      document.dispatchEvent(new CustomEvent('wa:unread', { detail: { total: data.unread_total } }));
    } catch {
      this.setOffline(true);
    } finally {
      this.polling = false;
      this.schedule();
    }
  }

  setOffline(on) {
    if (this.offline === on) return;
    this.offline = on;
    this.ui.offline.hidden = !on;
  }

  /** New messages are in `this.messages`: lay out and decide whether to follow them. */
  afterAppend(added, own = false) {
    const follow = own || this.atBottom;
    this.layout();
    for (const m of added) {
      const row = this.rows.get(m.id);
      if (!row || reduced()) continue;
      if (m.direction === 'in') row.classList.add('is-new');
      else row.classList.add('is-new-own');
      row.addEventListener('animationend', () => row.classList.remove('is-new', 'is-new-own'), { once: true });
    }
    const theirs = added.filter((m) => m.direction === 'in');
    if (follow) { this.scrollToBottom(); if (theirs.length) this.markRead(); } else if (theirs.length) { this.pending += theirs.length; this.syncJump(); }
    if (theirs.length) {
      const first = theirs[theirs.length - 1];
      const plain = first.kind === 'text' || first.kind === 'template' ? this.plain(first.body) : OTHER_WORDS[first.kind] || 'a message';
      this.say(`New message from ${this.contact.name}${plain ? `: ${plain}` : ''}`);
    }
  }

  plain(body) { return String(body || '').split('\n').find((l) => l.trim())?.slice(0, 80) || ''; }

  async markRead() {
    if (!this.alive || document.visibilityState !== 'visible' || this.readBusy) return;
    if (this.markedAt && Date.now() - this.markedAt < 1500) return;
    this.readBusy = true;
    this.markedAt = Date.now();
    try {
      const response = await fetch(this.urls.read, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrfToken(), Accept: 'application/json' } });
      if (response.ok) { const data = await response.json(); document.dispatchEvent(new CustomEvent('wa:unread', { detail: { total: data.unread_total, read: this.contact.id } })); }
    } catch { /* it is tried again on the next message */ } finally { this.readBusy = false; }
  }

  bindEvents() {
    const { signal } = this.ac;
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') { this.poll(); if (this.atBottom) this.markRead(); }
      else this.schedule();
    }, { signal });
    window.addEventListener('online', () => this.poll(), { signal });
    window.addEventListener('offline', () => this.setOffline(true), { signal });
    this.root.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && event.target === this.ui.input && !this.ui.input.value && desktopKeys()) document.dispatchEvent(new CustomEvent('wa:back-to-list'));
    });
  }

  // ---------- phone keyboard ----------

  bindViewport() {
    const vv = window.visualViewport;
    if (!vv) return;
    const { signal } = this.ac;
    this.fullH = window.innerHeight;
    const apply = () => {
      if (!phone()) { this.root.style.removeProperty('--wa-vh'); this.root.style.removeProperty('--wa-top'); document.body.removeAttribute('data-keyboard'); this.root.removeAttribute('data-keyboard'); return; }
      if (!this.root.contains(document.activeElement) || document.activeElement === document.body) this.fullH = Math.max(window.innerHeight, vv.height);
      const keyboard = this.fullH - vv.height > 120;
      const was = this.root.hasAttribute('data-keyboard');
      this.root.style.setProperty('--wa-vh', `${Math.round(vv.height)}px`);
      this.root.style.setProperty('--wa-top', `${Math.round(vv.offsetTop)}px`);
      this.root.toggleAttribute('data-keyboard', keyboard);
      document.body.toggleAttribute('data-keyboard', keyboard);
      if (keyboard !== was && this.atBottom) this.scrollToBottom();
    };
    vv.addEventListener('resize', apply, { signal });
    vv.addEventListener('scroll', apply, { signal });
    window.addEventListener('orientationchange', () => setTimeout(apply, 300), { signal });
    apply();
  }

  // ---------- composer ----------

  get draftKey() { return `wa-draft:${this.contact.id}`; }

  restoreDraft() {
    try { const text = sessionStorage.getItem(this.draftKey); if (text && this.ui.input) { this.ui.input.value = text; this.grow(); this.updateSend(); } } catch { /* private mode */ }
  }

  saveDraft() {
    try { if (this.ui.input.value) sessionStorage.setItem(this.draftKey, this.ui.input.value); else sessionStorage.removeItem(this.draftKey); } catch { /* private mode */ }
  }

  grow() {
    const input = this.ui.input;
    if (CSS.supports('field-sizing', 'content')) return;
    input.style.height = 'auto';
    input.style.height = `${input.scrollHeight}px`;
  }

  /** The field grew or shrank: the wall changed height, so keep the newest message in view if it was. */
  keepBottom() { if (this.atBottom) requestAnimationFrame(() => this.scrollToBottom()); }

  codePoints(text) { return [...text].length; }

  /** The 1600 rule: silent until 100 from the end, never cut, never maxlength. */
  overBy() {
    const max = this.contact.limits.body;
    return Math.max(0, this.codePoints(this.ui.input.value.trim()) - max);
  }

  updateCount() {
    const { count, input } = this.ui;
    const max = this.contact.limits.body;
    const n = this.codePoints(input.value.trim());
    if (n >= max - 100) {
      count.hidden = false;
      const over = n - max;
      count.classList.toggle('is-over', over > 0);
      count.textContent = over > 0 ? `Too long by ${over} character${over === 1 ? '' : 's'}.` : `${n} of ${max}`;
    } else count.hidden = true;
  }

  canSend() { return (this.ui.input.value.trim() || this.file) && !this.overBy(); }

  updateSend() {
    const { send, input } = this.ui;
    if (!send) return;
    const ok = !!this.canSend();
    send.setAttribute('aria-disabled', ok ? 'false' : 'true');
    send.classList.toggle('is-ready', ok);
    input.placeholder = this.file ? 'Add a caption' : 'Message';
    this.updateCount();
  }

  bindComposer() {
    const { input, send, composer, file, scroll, wall } = this.ui;
    const { signal } = this.ac;
    if (!composer) return;
    input.addEventListener('input', () => { this.grow(); this.saveDraft(); this.updateSend(); this.keepBottom(); });
    input.addEventListener('focus', () => { composer.classList.add('is-focus'); });
    input.addEventListener('blur', () => composer.classList.remove('is-focus'));
    input.addEventListener('keydown', (event) => {
      if (event.isComposing || event.keyCode === 229) return;
      if (event.key === 'Enter') {
        const meta = event.metaKey || event.ctrlKey;
        if (meta || (desktopKeys() && !event.shiftKey)) { event.preventDefault(); this.submit(); }
      }
      if ((event.metaKey || event.ctrlKey) && !event.altKey && ['b', 'i'].includes(event.key.toLowerCase())) {
        event.preventDefault();
        this.wrap(event.key.toLowerCase() === 'b' ? '*' : '_');
      }
    });
    send.addEventListener('pointerdown', (event) => event.preventDefault()); // tapping it must not close the keyboard
    composer.addEventListener('submit', (event) => { event.preventDefault(); this.submit(); });
    this.q('[data-attach]').addEventListener('click', () => file.click());
    file.addEventListener('change', () => { if (file.files[0]) this.chooseFile(file.files[0]); file.value = ''; });
    this.q('[data-tray-remove]').addEventListener('click', () => this.clearFile());
    input.addEventListener('paste', (event) => {
      const pasted = [...(event.clipboardData?.files || [])][0];
      if (pasted) { event.preventDefault(); this.chooseFile(pasted); }
    });
    // desktop drag and drop onto the wall
    let depth = 0;
    const dragging = (event) => [...(event.dataTransfer?.types || [])].includes('Files');
    wall.addEventListener('dragenter', (event) => { if (this.state === 'open' && dragging(event)) { depth += 1; this.ui.drop.hidden = false; } }, { signal });
    wall.addEventListener('dragleave', () => { depth = Math.max(0, depth - 1); if (!depth) this.ui.drop.hidden = true; }, { signal });
    wall.addEventListener('dragover', (event) => { if (this.state === 'open' && dragging(event)) event.preventDefault(); }, { signal });
    wall.addEventListener('drop', (event) => {
      depth = 0; this.ui.drop.hidden = true;
      if (this.state !== 'open' || !dragging(event)) return;
      event.preventDefault();
      if (event.dataTransfer.files[0]) this.chooseFile(event.dataTransfer.files[0]);
    }, { signal });
    void scroll;
  }

  wrap(mark) {
    const input = this.ui.input;
    const { selectionStart: a, selectionEnd: b, value } = input;
    input.value = `${value.slice(0, a)}${mark}${value.slice(a, b)}${mark}${value.slice(b)}`;
    input.setSelectionRange(a + 1, b + 1);
    input.dispatchEvent(new Event('input'));
  }

  chooseFile(file) {
    const limits = this.contact.limits;
    const isImage = file.type === 'image/jpeg' || file.type === 'image/png';
    const isPdf = file.type === 'application/pdf';
    const error = this.ui.trayError;
    error.hidden = true;
    if (!isImage && !isPdf) { error.hidden = false; error.textContent = 'Photos or PDFs only.'; return; }
    if (file.size > (isImage ? limits.image_bytes : limits.file_bytes)) { error.hidden = false; error.textContent = `Photos up to ${mb(limits.image_bytes)}, PDFs up to ${mb(limits.file_bytes)}.`; return; }
    this.file = file;
    const { tray, trayThumb, trayName, traySize } = this.ui;
    trayThumb.replaceChildren();
    if (isImage) {
      const url = URL.createObjectURL(file);
      (this.urls_to_free = this.urls_to_free || []).push(url);
      trayThumb.append(h('img', { src: url, alt: '' }));
    } else trayThumb.append(icon('file-pdf', 'o-icon o-wa-tray-icon'));
    trayName.textContent = file.name;
    traySize.textContent = bytes(file.size);
    tray.hidden = false;
    this.updateSend();
    this.ui.input.focus({ preventScroll: true });
  }

  clearFile() {
    this.file = null;
    this.ui.tray.hidden = true;
    this.ui.trayError.hidden = true;
    this.updateSend();
  }

  // ---------- sending ----------

  tempMessage(fields) {
    this.tmp += 1;
    return { id: `tmp-${this.tmp}`, direction: 'out', kind: 'text', body: '', body_html: '', status: 'queued', error: null, author: '', author_id: '', author_first_name: '', template: null, media: null,
      created_at: new Date().toISOString(), sent_at: '', retry_url: '', ...fields };
  }

  addTemp(m) {
    this.byId.set(m.id, m);
    this.messages.push(m);
    this.afterAppend([m], true);
  }

  swapTemp(temp, real) {
    const row = this.rows.get(temp.id);
    this.byId.delete(temp.id);
    this.rows.delete(temp.id);
    this.messages = this.messages.filter((m) => m !== temp);
    row?.remove();
    if (!this.byId.has(real.id)) {
      this.byId.set(real.id, real);
      this.messages.push(real);
      this.messages.sort((a, b) => (typeof a.id === 'number' && typeof b.id === 'number' ? a.id - b.id : 0));
    }
    this.lastId = Math.max(this.lastId, real.id);
    this.layout();
    const fresh = this.rows.get(real.id);
    if (fresh && !reduced()) { fresh.classList.add('is-swap'); fresh.addEventListener('animationend', () => fresh.classList.remove('is-swap'), { once: true }); }
    this.scrollToBottom();
  }

  failTemp(temp, reason, retry) {
    temp.status = 'failed';
    temp.localFail = true;
    temp.error = { reason, can_retry: false };
    temp.retry = retry || null;
    delete temp.progress;
    const old = this.rows.get(temp.id);
    const next = this.makeRow(temp);
    old?.replaceWith(next);
    this.rows.set(temp.id, next);
    this.layout();
    if (this.atBottom) this.scrollToBottom();
  }

  submit() {
    if (this.state !== 'open') return;
    if (!this.canSend()) {
      if (this.overBy()) this.ui.count.focus?.();
      return;
    }
    const text = this.ui.input.value.trim();
    const file = this.file;
    this.ui.input.value = '';
    this.grow();
    this.clearFile();
    if (file) this.sendFile(file, text); else this.sendText(text);
    this.updateSend();
    if (!phone()) this.ui.input.focus();
  }

  form(extra) {
    const body = new URLSearchParams(extra);
    if (this.gold) body.set('gold', this.gold.id);
    return body;
  }

  async sendText(text, existing) {
    const temp = existing || this.tempMessage({ localText: text, body: text });
    if (!existing) this.addTemp(temp);
    temp.status = 'queued';
    this.sending += 1;
    try {
      const response = await fetch(this.urls.send, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrfToken(), Accept: 'application/json' }, body: this.form({ body: text }) });
      const data = await response.json().catch(() => null);
      if (response.ok && data?.ok) { this.afterSent(temp, data.message, text); return; }
      if (!data) throw new Error('bad answer');
      this.serverRefused(temp, data, text);
    } catch {
      this.setOffline(true);
      this.failTemp(temp, 'Not sent. Try again.', () => this.sendText(text, temp));
    } finally { this.sending -= 1; }
  }

  afterSent(temp, message, text) {
    try { sessionStorage.removeItem(this.draftKey); } catch { /* private mode */ }
    void text;
    this.swapTemp(temp, message);
    if (this.gold && this.gold.status === 'new') { this.gold.status = 'contacted'; toast('Marked Contacted.'); }
    this.contact = { ...this.contact, window: { ...this.contact.window } };
  }

  serverRefused(temp, data, text) {
    if (data.error === 'window_closed') this.contact = { ...this.contact, window: { ...this.contact.window, state: 'closed', open: false } };
    if (data.error === 'opted_out') this.contact = { ...this.contact, opted_out: true };
    const words = { window_closed: 'Not sent. The window has closed.', opted_out: 'Not sent. He replied STOP.' };
    const reason = words[data.error] || (data.message ? `Not sent. ${data.message}` : 'Not sent. Try again.');
    this.failTemp(temp, reason, null);
    if (text) { try { sessionStorage.setItem(this.draftKey, text); } catch { /* private mode */ } }
    this.applyState();
    if (this.state === 'open' && text && !this.ui.input.value) { this.ui.input.value = text; this.grow(); this.updateSend(); }
  }

  sendFile(file, caption, existing) {
    const isImage = file.type.startsWith('image/');
    const url = URL.createObjectURL(file);
    (this.urls_to_free = this.urls_to_free || []).push(url);
    const temp = existing || this.tempMessage({
      kind: isImage ? 'image' : 'document', localText: caption, body: caption, progress: 0,
      media: { url, type: file.type, filename: file.name, size: file.size, width: null, height: null },
    });
    if (!existing) {
      if (isImage) { // read the size so the bubble keeps its shape while it uploads
        const probe = new Image();
        probe.onload = () => { temp.media.width = probe.naturalWidth; temp.media.height = probe.naturalHeight; };
        probe.src = url;
      }
      this.addTemp(temp);
    } else { temp.progress = 0; temp.status = 'queued'; this.refreshTemp(temp); }
    const body = new FormData();
    body.set('file', file);
    body.set('body', caption);
    if (this.gold) body.set('gold', this.gold.id);
    this.sending += 1;
    const xhr = new XMLHttpRequest();
    xhr.open('POST', this.urls.send_media);
    xhr.setRequestHeader('X-CSRFToken', csrfToken());
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.upload.addEventListener('progress', (event) => {
      if (!event.lengthComputable) return;
      const bar = this.rows.get(temp.id)?.querySelector('.o-wa-progress span');
      if (bar) bar.style.transform = `scaleX(${event.loaded / event.total})`;
    });
    xhr.addEventListener('load', () => {
      this.sending -= 1;
      let data = null;
      try { data = JSON.parse(xhr.responseText); } catch { /* not JSON */ }
      if (xhr.status >= 200 && xhr.status < 300 && data?.ok) { this.afterSent(temp, data.message, caption); return; }
      if (data) { this.serverRefused(temp, data, caption); return; }
      this.failTemp(temp, 'Not sent. Try again.', () => this.sendFile(file, caption, temp));
    });
    xhr.addEventListener('error', () => { this.sending -= 1; this.setOffline(true); this.failTemp(temp, 'Not sent. Try again.', () => this.sendFile(file, caption, temp)); });
    xhr.send(body);
  }

  refreshTemp(temp) {
    const old = this.rows.get(temp.id);
    const next = this.makeRow(temp);
    old?.replaceWith(next);
    this.rows.set(temp.id, next);
  }

  async retry(m, button) {
    if (m.retry) { delete m.localFail; delete m.error; m.retry(); return; }
    if (!m.retry_url && !(m.error && m.error.can_retry)) return;
    if (button.getAttribute('aria-busy') === 'true' || m.retrying) return; // a double click sends once (the server also refuses the second)
    m.retrying = true;
    button.setAttribute('aria-busy', 'true');
    try {
      const url = `${this.urls.send.replace(/send\/$/, '')}retry/${m.id}/`;
      const response = await fetch(m.retry_url || url, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrfToken(), Accept: 'application/json' } });
      const data = await response.json().catch(() => null);
      if (data?.ok) { Object.assign(m, data.message); this.patchRow(m); } else toast(data?.message || 'That could not be sent again.', { kind: 'error' });
    } catch { toast('No connection. Try again in a moment.', { kind: 'error' }); } finally { m.retrying = false; button.removeAttribute('aria-busy'); }
  }

  // ---------- lightbox ----------

  bindLightbox() {
    const box = this.q('[data-lightbox]');
    this.lightbox = box;
    const close = () => box.close();
    this.q('[data-lb-close]').addEventListener('click', close);
    box.addEventListener('click', (event) => { if (event.target === box) close(); });
    box.addEventListener('close', () => { this.lbOpener?.focus({ preventScroll: true }); box.querySelector('[data-lb-img]').removeAttribute('src'); });
  }

  openLightbox(m) {
    const box = this.lightbox;
    this.lbOpener = document.activeElement;
    box.querySelector('[data-lb-img]').src = m.media.url;
    const dl = box.querySelector('[data-lb-download]');
    dl.href = m.media.url;
    dl.setAttribute('download', m.media.filename || 'photo');
    const who = m.direction === 'in' ? this.contact.name : (m.author_first_name || 'You');
    box.querySelector('[data-lb-cap]').textContent = `${who}, ${fullStamp(m.created_at)}`;
    box.showModal();
  }

  // ---------- template picker ----------

  bindTemplates() {
    const dialog = this.q('[data-tpl]');
    this.tpl = { dialog, chosen: null, values: {} };
    this.root.querySelectorAll('[data-tpl-open]').forEach((b) => b.addEventListener('click', () => this.openPicker()));
    this.q('[data-tpl-close]').addEventListener('click', () => dialog.close());
    let down = false;
    dialog.addEventListener('pointerdown', (e) => { down = e.target === dialog; });
    dialog.addEventListener('click', (e) => { if (e.target === dialog && down) dialog.close(); });
    dialog.addEventListener('close', () => this.tplOpener?.focus?.({ preventScroll: true }));
    this.q('[data-tpl-send]').addEventListener('click', () => this.sendTemplate());
  }

  openPicker() {
    const { dialog } = this.tpl;
    this.tplOpener = document.activeElement;
    this.buildPicker();
    if (!dialog.open) dialog.showModal();
  }

  tplFirstLine(t) {
    const labels = Object.fromEntries(t.variables.map((v) => [v.key, v.label]));
    const line = (t.body || '').split('\n').find((l) => l.trim()) || '';
    return line.replace(/\{\{\s*(\w+)\s*\}\}/g, (_, k) => `[${labels[k] || k}]`).replace(/[*_~`]/g, '');
  }

  buildPicker() {
    const list = this.q('[data-tpl-list]');
    const empty = this.q('[data-tpl-empty]');
    list.replaceChildren();
    this.q('[data-tpl-fields]').replaceChildren();
    this.q('[data-tpl-prev]').hidden = true;
    this.q('[data-tpl-error]').hidden = true;
    empty.hidden = this.templates.length > 0;
    this.q('[data-tpl-right]').hidden = this.templates.length === 0;
    this.tpl.chosen = null;
    this.tpl.values = {};
    for (const t of this.templates) {
      const item = h('button', { type: 'button', class: 'o-wa-tpl-item', role: 'radio', 'aria-checked': 'false', 'data-id': t.id },
        h('span', { class: 'o-wa-tpl-name', text: t.label }), h('span', { class: 'o-wa-tpl-line', text: this.tplFirstLine(t) }), icon('check', 'o-icon o-wa-tpl-check'));
      item.addEventListener('click', () => this.chooseTemplate(t));
      list.append(item);
    }
    if (this.templates.length === 1) this.chooseTemplate(this.templates[0]);
  }

  chooseTemplate(t) {
    this.tpl.chosen = t;
    this.q('[data-tpl-list]').querySelectorAll('.o-wa-tpl-item').forEach((i) => i.setAttribute('aria-checked', String(i.dataset.id === t.id)));
    const fields = this.q('[data-tpl-fields]');
    fields.replaceChildren();
    this.tpl.values = {};
    for (const v of t.variables) {
      this.tpl.values[v.key] = v.prefill || '';
      const input = h('input', { class: 'fb-modal-input', type: 'text', maxlength: '200', autocomplete: 'off', 'data-key': v.key, 'aria-required': 'true', value: v.prefill || '' });
      input.addEventListener('input', () => { this.tpl.values[v.key] = input.value; input.removeAttribute('aria-invalid'); this.renderPreview(); });
      fields.append(h('label', { class: 'fb-modal-field' }, h('span', { text: v.label }), input));
    }
    const prev = this.q('[data-tpl-prev]');
    prev.hidden = false;
    this.q('[data-tpl-prev-label]').textContent = `Template: ${t.label}`;
    this.q('[data-tpl-preview]').innerHTML = t.body_html; // server-formatted, with <span data-var> placeholders
    this.renderPreview();
    fields.querySelector('input')?.focus({ preventScroll: true });
  }

  renderPreview() {
    const t = this.tpl.chosen;
    if (!t) return;
    this.q('[data-tpl-preview]').querySelectorAll('[data-var]').forEach((span) => {
      const value = (this.tpl.values[span.dataset.var] || '').trim();
      span.textContent = value || `[${span.dataset.label || span.dataset.var}]`;
      span.classList.toggle('is-empty', !value);
    });
    const ready = t.variables.every((v) => (this.tpl.values[v.key] || '').trim());
    this.q('[data-tpl-send]').disabled = !ready;
  }

  async sendTemplate() {
    const t = this.tpl.chosen;
    const button = this.q('[data-tpl-send]');
    const error = this.q('[data-tpl-error]');
    if (!t || button.disabled) return;
    error.hidden = true;
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    const prior = button.textContent;
    button.textContent = 'Sending';
    const body = this.form({ template: t.id });
    for (const v of t.variables) body.set(`var_${v.key}`, (this.tpl.values[v.key] || '').trim());
    try {
      const response = await fetch(this.urls.send_template, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrfToken(), Accept: 'application/json' }, body });
      const data = await response.json().catch(() => null);
      if (response.ok && data?.ok) {
        this.tpl.dialog.close();
        this.sending += 1;
        const m = data.message;
        if (!this.byId.has(m.id)) { this.byId.set(m.id, m); this.messages.push(m); this.lastId = Math.max(this.lastId, m.id); this.afterAppend([m], true); }
        this.sending -= 1;
        this.contact = { ...this.contact, window: { ...this.contact.window, state: this.contact.window.state === 'empty' ? 'template_waiting' : this.contact.window.state } };
        this.applyState();
        toast(this.gold && this.gold.status === 'new' ? 'Marked Contacted.' : 'Template sent.');
        if (this.gold) this.gold.status = 'contacted';
      } else {
        error.hidden = false;
        error.textContent = data?.message || 'That could not be sent. Try again.';
        for (const key of data?.missing || []) this.q(`[data-tpl-fields] [data-key="${key}"]`)?.setAttribute('aria-invalid', 'true');
        button.disabled = false;
      }
    } catch {
      error.hidden = false;
      error.textContent = 'No connection. Try again in a moment.';
      button.disabled = false;
    } finally {
      button.removeAttribute('aria-busy');
      button.textContent = prior;
      this.renderPreview();
    }
  }
}
