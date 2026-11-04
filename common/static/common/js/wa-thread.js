/* One WhatsApp chat in the Office (docs/features/whatsapp-design.md sections 3 to 5).
 *
 * Safety rule: no HTML is ever built from message text here. Bubbles are made with createElement and textContent; the only innerHTML is
 * `body_html`, which the server has already escaped and formatted (whatsapp.formatting.render), and a template's `body_html` for the preview.
 * The chat page embeds its data as JSON (#wa-data); polling and sending keep this object in step with the server.
 *
 * Round 2 (docs/features/email-chat-design.md section 4): Reply on a bubble (his phone gets the quoted line as WhatsApp's `> text`, not the tap-to-jump box), a quick
 * emoji row that sends a NORMAL message (Twilio cannot send a reaction, and the screen says so), MP4 video, voice notes (the microphone is released on every exit,
 * including leaving the page) and a neutral bubble for what the Office cannot show. */
import { csrfToken } from './api.js';
import { toast } from './feedback.js';
import { bindKeyboard, releaseKeyboard } from './office-keyboard.js';
import { bytes, dayLabel, dayOf, desktopKeys, fullStamp, h, icon, mb, phone, reduced, timeOf } from './office-dom.js';

// ---------- photos over WhatsApp's 5 MB limit are made smaller here, in the browser ----------
// WhatsApp's image limit cannot be raised, so a bigger photo is drawn to a canvas and saved again as a JPEG (quality 0.9 down to 0.5, long side 2560 px down by a fifth each round)
// until it fits. The server's checks and limit stay as they are: what it receives is an ordinary image/jpeg under the limit. WebP and HEIC are always converted.
const CONVERT_TYPES = new Set(['image/webp', 'image/heic', 'image/heif']);
const MAX_SIDE = 2560;
const QUALITIES = [0.9, 0.8, 0.7, 0.6, 0.5];

/** The extra picture types this browser can read (it cannot be known for sure without a file, so the picker offers them where the engine is known to). */
export function extraImageTypes() {
  const out = [];
  const canvas = document.createElement('canvas');
  if (canvas.toDataURL('image/webp').startsWith('data:image/webp')) out.push('image/webp');
  if (/Apple/.test(navigator.vendor || '') && /iPhone|iPad|Macintosh/.test(navigator.userAgent)) out.push('image/heic', 'image/heif');
  return out;
}

function decodeImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('unreadable')); };
    img.src = url;
  });
}

function jpegName(name) {
  const base = String(name || '').replace(/\.[^.]*$/, '').replace(/[^\w .-]+/g, '').trim().slice(0, 60);
  return `${base || 'photo'}.jpg`;
}

/** A JPEG File under `max` bytes made from `file`. Throws Error('unreadable') when the browser cannot read it, Error('toobig') when no size gets it under the limit. */
export async function shrinkImage(file, max) {
  const img = await decodeImage(file);
  const w0 = img.naturalWidth || img.width;
  const h0 = img.naturalHeight || img.height;
  if (!w0 || !h0) throw new Error('unreadable');
  let scale = Math.min(1, MAX_SIDE / Math.max(w0, h0));
  for (let round = 0; round < 8; round += 1) {
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(w0 * scale));
    canvas.height = Math.max(1, Math.round(h0 * scale));
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#fff';   // a PNG with see-through parts would turn black as a JPEG
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    for (const quality of QUALITIES) {
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality));
      if (blob && blob.size > 0 && blob.size <= max) return new File([blob], jpegName(file.name), { type: 'image/jpeg', lastModified: Date.now() });
    }
    scale *= 0.8;
  }
  throw new Error('toobig');
}

const GROUP_MS = 5 * 60 * 1000;
const POLL_VISIBLE_MS = 4000;
const POLL_HIDDEN_MS = 30000;
const NEAR_BOTTOM = '0px 0px 96px 0px';

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
const QUOTE_WORDS = { image: 'Photo', audio: 'Voice note', video: 'Video', document: 'PDF', file: 'File' };   // what a quote of a message with no text says (as the server's quote_text)
const EMOJI = [['\u{1F44D}', 'thumbs up'], ['\u{1F64F}', 'folded hands'], ['\u{1F642}', 'smiling face'], ['\u{1F44C}', 'OK hand'], ['\u2705', 'check mark']];
const first = (name) => String(name || '').split(' ')[0] || String(name || '');
const clock = (seconds) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
const canPlayOgg = () => { try { return !!document.createElement('audio').canPlayType('audio/ogg; codecs=opus'); } catch { return false; } };

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
    this.quote = null;
    this.rec = null;
    this.ac = new AbortController();
    this.q = (sel) => root.querySelector(sel);
    this.ui = {
      scroll: this.q('[data-scroll]'), msgs: this.q('[data-msgs]'), older: this.q('[data-older]'), start: this.q('[data-start]'),
      jump: this.q('[data-jump]'), jumpCount: this.q('[data-jump-count]'), live: this.q('[data-live]'), wallNote: this.q('[data-wall-note]'),
      win: this.q('[data-win]'), pill: this.q('[data-win-pill]'), offline: this.q('[data-offline]'), input: this.q('[data-input]'),
      send: this.q('[data-send]'), composer: this.q('[data-composer]'), count: this.q('[data-count]'), file: this.q('[data-file]'),
      tray: this.q('[data-tray]'), trayThumb: this.q('[data-tray-thumb]'), trayName: this.q('[data-tray-name]'), traySize: this.q('[data-tray-size]'),
      trayError: this.q('[data-tray-error]'), drop: this.q('[data-drop]'), wall: this.q('[data-wall]'),
      quote: this.q('[data-quote]'), quoteWho: this.q('[data-quote-who]'), quoteText: this.q('[data-quote-text]'), quoteNote: this.q('[data-quote-note]'),
      mic: this.q('[data-mic]'), recPanel: this.q('[data-rec]'),
    };
    for (const m of this.messages) this.byId.set(m.id, m);
    this.layout();
    this.bindObservers();
    this.bindComposer();
    this.bindActs();
    this.bindVoice();
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
    this.cancelRecording(true); // the phone's microphone indicator must not stay on
    releaseKeyboard();
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
        win.replaceChildren(icon('clock'), document.createTextNode(minutes <= 1 ? 'Under a minute left. His reply restarts it.' : `${minutes} minutes left. His reply restarts it.`));
        if (!this.warned) { this.warned = true; this.say(minutes <= 1 ? 'Under a minute left to message freely.' : `${minutes} minutes left to message freely.`); }
      } else {
        win.hidden = false;
        win.className = 'o-wa-win';
        win.replaceChildren(document.createTextNode(`Message freely for ${Math.floor(left / 3600000)}h more. His replies restart this.`));
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
    if (state !== 'open') { this.cancelRecording(); if (this.quote) this.setQuote(null); this.closeActs(); }
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
    // the log is one tab stop: a roving tabindex on the lines (Up and Down move, see bindActs)
    const lines = [...this.ui.msgs.querySelectorAll('.o-wa-line')];
    const keep = lines.find((r) => r.getAttribute('tabindex') === '0') || lines[lines.length - 1];
    lines.forEach((r) => r.setAttribute('tabindex', r === keep ? '0' : '-1'));
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

  /** A card for a file we cannot show inline (or could not play): icon, name, size, download. */
  fileCard(m, iconName, label) {
    const media = m.media;
    return h('a', { class: 'o-wa-file', href: media.url, download: media.filename || '' }, icon(iconName, 'o-icon o-wa-file-icon'),
      h('span', { class: 'o-wa-file-text' }, h('span', { class: 'o-wa-file-name', text: media.filename || label }), h('span', { class: 'o-wa-file-size', text: `${label}${media.size ? `, ${bytes(media.size)}` : ''}` })), icon('download'));
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
    if (m.kind === 'audio' && media) {
      // an older iPhone may not play OGG: a file card, with the download, instead of a player that cannot play
      if (!canPlayOgg() && (media.type || '').includes('ogg')) return this.fileCard(m, 'microphone', 'Voice note');
      return h('audio', { class: 'o-wa-audio', controls: true, preload: 'metadata', src: media.url, 'aria-label': 'Voice note' });
    }
    if (m.kind === 'video' && media) {
      const video = h('video', { class: 'o-wa-video', controls: true, playsinline: true, preload: 'metadata', src: media.url, 'aria-label': 'Video' });
      if (media.width && media.height) video.style.aspectRatio = `${media.width} / ${media.height}`;
      video.addEventListener('error', () => { if (m.progress === undefined) video.replaceWith(this.fileCard(m, 'video', 'Video')); }, { once: true });
      return video;
    }
    if (media) return this.fileCard(m, 'file-pdf', OTHER_WORDS[m.kind] || 'File');
    if (['audio', 'video', 'file'].includes(m.kind)) {
      return h('div', { class: 'o-wa-file o-wa-file--none' }, icon('file-pdf', 'o-icon o-wa-file-icon'),
        h('span', { class: 'o-wa-file-text' }, h('span', { class: 'o-wa-file-name', text: `${OTHER_WORDS[m.kind]}. This type cannot be shown here.` })));
    }
    return null;
  }

  makeRow(m) {
    const li = h('li', { class: `o-wa-line o-wa-line--${m.direction}`, 'data-id': String(m.id), tabindex: '-1' });
    const wrap = h('div', { class: 'o-wa-bw' }, this.makeBubble(m));
    const acts = this.actsNode(m);
    if (acts) wrap.append(acts);
    li.append(wrap);
    const fail = this.failNode(m);
    if (fail) li.append(fail);
    return li;
  }

  makeBubble(m) {
    const bubble = h('div', { class: `o-wa-msg o-wa-msg--${m.direction}` });
    bubble.append(h('span', { class: 'sr-only', 'data-sr': '', text: this.srPrefix(m) }));
    if (m.direction === 'out' && m.author_first_name) bubble.append(h('p', { class: 'o-wa-author', 'data-author': '', text: m.author_first_name, title: m.author || '' }));
    if (m.template) bubble.append(h('p', { class: 'o-wa-tpl-label', text: `Template: ${m.template.label}` }));
    if (m.reply_to) bubble.append(this.quoteNode(m.reply_to));
    const media = this.mediaNode(m);
    if (media) bubble.append(media);
    const other = m.kind === 'other' && !m.media;
    const hasText = !!(m.body_html || m.localText) || other;
    if (hasText) {
      const text = h('div', { class: other ? 'o-wa-text o-wa-other' : 'o-wa-text', dir: 'auto' });
      if (other) text.textContent = 'This message cannot be shown here.'; // not a fault (it may be a reaction): no icon, no warning colour
      else if (m.body_html) text.innerHTML = m.body_html; // server-escaped and formatted, never built here
      else text.textContent = m.localText; // an unsent bubble shows plain text until the server answers
      text.append(h('span', { class: 'o-wa-spacer', 'aria-hidden': 'true' }));
      bubble.append(text);
    }
    bubble.classList.toggle('has-text', hasText);
    bubble.classList.toggle('has-photo', m.kind === 'image' && !!m.media);
    bubble.classList.toggle('has-photo-only', m.kind === 'image' && !!m.media && !hasText);
    bubble.classList.toggle('has-video', m.kind === 'video' && !!m.media);
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
    if (fail) { row.append(fail); row.querySelector('.o-wa-acts')?.remove(); } // nothing to reply to on a message that did not go
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
    bindKeyboard(this.root, { signal: this.ac.signal, onChange: () => { if (this.atBottom) this.scrollToBottom(); } });
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

  /** What goes to Twilio as text: with a quote, `> first line`, a blank line, then what he typed (the server builds the same). The 1600 limit counts this. */
  finalText(body) {
    if (!this.quote || this.rec) return body;
    return body ? `> ${this.quote.text}\n\n${body}` : `> ${this.quote.text}`;
  }

  /** The 1600 rule: silent until 100 from the end, never cut, never maxlength. */
  overBy() {
    const max = this.contact.limits.body;
    return Math.max(0, this.codePoints(this.finalText(this.ui.input.value.trim())) - max);
  }

  updateCount() {
    const { count, input } = this.ui;
    const max = this.contact.limits.body;
    const n = this.codePoints(this.finalText(input.value.trim()));
    if (n >= max - 100) {
      count.hidden = false;
      const over = n - max;
      count.classList.toggle('is-over', over > 0);
      count.textContent = over > 0 ? `Too long by ${over} character${over === 1 ? '' : 's'}.` : `${n} of ${max}`;
    } else count.hidden = true;
  }

  canSend() { return !this.preparing && (this.ui.input.value.trim() || this.file) && !this.overBy(); }

  /** The microphone takes the Send slot while the field is empty, nothing is attached, voice notes are available here and the browser can record. Typing swaps it back at once. */
  voiceReady() { return !!(this.contact.voice?.available && window.MediaRecorder && navigator.mediaDevices?.getUserMedia); }

  updateSend() {
    const { send, input, mic } = this.ui;
    if (!send) return;
    const ok = !!this.canSend();
    send.setAttribute('aria-disabled', ok ? 'false' : 'true');
    send.classList.toggle('is-ready', ok);
    input.placeholder = this.file ? 'Add a caption' : 'Message';
    const showMic = !!mic && this.voiceReady() && !input.value.trim() && !this.file && !this.rec;
    if (mic) mic.hidden = !showMic;
    send.hidden = showMic;
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
    const extra = extraImageTypes();
    if (extra.length) file.accept = `${file.accept},${extra.join(',')}`;
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

  /** A file picked, pasted or dropped. A photo over the limit, a WebP or a HEIC is first made into a smaller JPEG (shrinkImage); the tray and the bubble then show that one. */
  async chooseFile(file) {
    const limits = this.contact.limits;
    const ticket = (this.choosing = (this.choosing || 0) + 1);   // every pick takes a new ticket: a shrink still running for an earlier pick finds it stale and is dropped, even when this one needs no shrink
    if (this.preparing) { this.preparing = false; this.ui.tray.hidden = true; this.updateSend(); }   // the earlier photo's "Making the photo smaller" is over
    const convert = CONVERT_TYPES.has(file.type);
    const isImage = file.type === 'image/jpeg' || file.type === 'image/png' || convert;
    const isPdf = file.type === 'application/pdf';
    const isVideo = file.type === 'video/mp4';
    const error = this.ui.trayError;
    const say = (text) => { error.hidden = false; error.textContent = text; };
    error.hidden = true;
    if (!isImage && !isPdf && !isVideo) { say('Photos, PDFs or MP4 videos only.'); return; }   // an iPhone's own .mov is refused here, as on the server
    if (isVideo && file.size > limits.file_bytes) { say(`That video is too big. Videos can be up to ${mb(limits.file_bytes)}.`); return; }
    if (isPdf && file.size > limits.file_bytes) { say(`That PDF is too big. PDFs can be up to ${mb(limits.file_bytes)}.`); return; }
    if (isImage && (convert || file.size > limits.image_bytes)) {
      this.file = null;
      this.preparing = true;
      this.showTray(file, null, 'Making the photo smaller\u2026');
      this.updateSend();
      try {
        file = await shrinkImage(file, limits.image_bytes);
      } catch (failure) {
        if (ticket !== this.choosing) return;
        this.preparing = false;
        this.ui.tray.hidden = true;
        this.updateSend();
        say(failure.message === 'toobig' ? `That photo could not be made small enough. WhatsApp takes photos up to ${mb(limits.image_bytes)}.` : 'That photo could not be read. Try another one.');
        return;
      }
      if (ticket !== this.choosing) return;   // another file was picked meanwhile
      this.preparing = false;
    }
    this.file = file;
    this.showTray(file, isImage ? file : null, bytes(file.size), isVideo ? 'video' : 'file-pdf');
    this.updateSend();
    this.ui.input.focus({ preventScroll: true });
  }

  /** The tray above the composer: a thumbnail of `image` (or an icon), the name and a line under it. */
  showTray(file, image, line, iconName) {
    const { tray, trayThumb, trayName, traySize } = this.ui;
    trayThumb.replaceChildren();
    if (image) {
      const url = URL.createObjectURL(image);
      (this.urls_to_free = this.urls_to_free || []).push(url);
      trayThumb.append(h('img', { src: url, alt: '' }));
    } else trayThumb.append(icon(iconName || 'file-pdf', 'o-icon o-wa-tray-icon'));
    trayName.textContent = file.name;
    traySize.textContent = line;
    tray.hidden = false;
  }

  clearFile() {
    this.file = null;
    this.preparing = false;
    this.choosing = (this.choosing || 0) + 1;   // a photo still being made smaller is dropped
    this.ui.tray.hidden = true;
    this.ui.trayError.hidden = true;
    this.updateSend();
  }

  // ---------- reply, emoji: the actions on a bubble (open window only) ----------

  /** Who a quote names: "Spa 99" for ours, his first name for his. */
  whoQuoted(direction) { return direction === 'out' ? 'Spa 99' : first(this.contact.name); }

  /** The words a quote of this message shows: its first line, or Photo, Voice note, Video, PDF, File, Message. */
  quoteLabel(m) {
    const line = String(m.body || m.localText || '').split('\n').map((l) => l.replace(/^[\s>]+/, '').replace(/[*_~`]/g, '').trim()).find(Boolean);
    return line ? (line.length > 100 ? `${line.slice(0, 99).trimEnd()}\u2026` : line) : (m.kind === 'template' && m.template ? (m.template.label || m.template.name) : (QUOTE_WORDS[m.kind] || 'Message'));
  }

  /** The quote inside a bubble, both directions. Its text goes through textContent only. */
  quoteNode(r) {
    const who = this.whoQuoted(r.direction);
    const button = h('button', { type: 'button', class: 'o-wa-reply', 'aria-label': `Reply to ${who}: ${r.text}. Go to that message.`, 'data-reply-to': String(r.id) },
      h('span', { class: 'o-wa-reply-who', text: who }), h('span', { class: 'o-wa-reply-text', dir: 'auto', text: r.text }));
    button.addEventListener('click', () => this.jumpTo(r.id));
    return button;
  }

  /** To the original, with one soft fade of an overlay on it; "further back" when it is not loaded. */
  jumpTo(id) {
    const row = this.rows.get(id);
    if (!row) { this.say('That message is further back.'); toast('That message is further back.', { kind: 'info' }); return; }
    row.scrollIntoView({ block: 'center', behavior: reduced() ? 'auto' : 'smooth' });
    const bubble = row.querySelector('.o-wa-msg');
    if (reduced() || !bubble) return;
    bubble.classList.remove('is-jump');
    void bubble.offsetWidth;
    bubble.classList.add('is-jump');
    bubble.addEventListener('animationend', () => bubble.classList.remove('is-jump'), { once: true });
  }

  actsNode(m) {
    if (typeof m.id !== 'number' || m.kind === 'other' || BAD.has(m.status) || m.localFail) return null;
    const box = h('div', { class: 'o-wa-acts', role: 'group', 'aria-label': 'Message actions' });
    box.append(h('button', { type: 'button', class: 'o-wa-act o-wa-act--reply', 'data-act': 'reply', 'aria-label': 'Reply', title: 'Reply', tabindex: '-1' }, icon('reply'), h('span', { class: 'o-wa-act-label', text: 'Reply' })));
    if (m.direction === 'in') {
      box.append(h('button', { type: 'button', class: 'o-wa-act o-wa-act--emoji', 'data-act': 'emoji', 'aria-label': 'Quick reply with an emoji', title: 'Quick reply with an emoji', 'aria-haspopup': 'true', 'aria-expanded': 'false', tabindex: '-1' }, icon('smiley')));
      const panel = h('div', { class: 'o-wa-emojis', role: 'group', 'aria-label': 'Quick reply' });
      const row = h('div', { class: 'o-wa-emoji-row' });
      for (const [glyph, name] of EMOJI) row.append(h('button', { type: 'button', class: 'o-wa-emoji', 'data-act': 'send-emoji', 'data-emoji': glyph, 'aria-label': `Send ${name}`, tabindex: '-1', text: glyph }));
      panel.append(row, h('p', { class: 'o-wa-emoji-note', text: 'Goes as a normal message, not a reaction.' }));
      box.append(panel);
    }
    return box;
  }

  bindActs() {
    const { signal } = this.ac;
    const { msgs, scroll } = this.ui;
    const messageOf = (el) => this.byId.get(Number(el.closest('.o-wa-line')?.dataset.id));
    msgs.addEventListener('click', (event) => {
      const act = event.target.closest('[data-act]');
      if (act) {
        const m = messageOf(act);
        const kind = act.dataset.act;
        if (kind === 'reply' && m) { this.setQuote(m); this.closeActs(); } else if (kind === 'emoji') {
          const row = act.closest('.o-wa-line');
          const on = !row.classList.contains('is-emoji');
          this.closeActs();
          if (on) { row.classList.add('is-emoji'); act.setAttribute('aria-expanded', 'true'); this.flipEmoji(row); }
        } else if (kind === 'send-emoji') { this.closeActs(); this.sendText(act.dataset.emoji, null, { plain: true }); }
        return;
      }
      // a phone: tap the bubble and the actions open under it (not on a link, photo, video or audio control, and not while text is selected)
      if (desktopKeys() || this.state !== 'open') return;
      const bubble = event.target.closest('.o-wa-msg');
      if (!bubble || event.target.closest('a, button, video, audio, img') || String(window.getSelection?.() || '')) { return; }
      const row = bubble.closest('.o-wa-line');
      if (!row.querySelector('.o-wa-acts')) return;
      const on = !row.classList.contains('is-acts');
      this.closeActs();
      if (on) row.classList.add('is-acts');
    }, { signal });
    document.addEventListener('click', (event) => { if (!event.target.closest('.o-wa-line.is-acts, .o-wa-line.is-emoji')) this.closeActs(); }, { signal });
    // the keyboard: one tab stop for the log, Up and Down between messages, Enter opens the actions, R replies, Escape goes back
    scroll.addEventListener('keydown', (event) => {
      if (event.isComposing) return;
      const target = event.target;
      const line = target.closest?.('.o-wa-line');
      if (!line) return;
      if (target.classList.contains('o-wa-line')) {
        const lines = [...msgs.querySelectorAll('.o-wa-line')];
        const at = lines.indexOf(line);
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
          event.preventDefault();
          const next = lines[Math.max(0, Math.min(lines.length - 1, at + (event.key === 'ArrowDown' ? 1 : -1)))];
          lines.forEach((l) => l.setAttribute('tabindex', l === next ? '0' : '-1'));
          next.focus();
        } else if ((event.key === 'r' || event.key === 'R') && this.state === 'open' && line.querySelector('.o-wa-acts') && !event.metaKey && !event.ctrlKey && !event.altKey) {
          event.preventDefault(); this.setQuote(messageOf(line));
        } else if (event.key === 'Enter' && this.state === 'open') {
          const first_ = line.querySelector('.o-wa-act'); if (first_) { event.preventDefault(); line.classList.add('is-keys'); first_.setAttribute('tabindex', '0'); first_.focus(); }
        }
      } else if (event.key === 'Escape') {
        event.preventDefault(); this.closeActs(); line.focus();
      } else if ((event.key === 'ArrowRight' || event.key === 'ArrowLeft') && target.closest('.o-wa-acts')) {
        const buttons = [...line.querySelectorAll('.o-wa-act, .o-wa-emoji')].filter((b) => b.offsetParent !== null);
        const at = buttons.indexOf(target);
        if (at >= 0) { event.preventDefault(); buttons[(at + (event.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length].focus(); }
      }
    }, { signal });
    msgs.addEventListener('focusout', (event) => { const line = event.target.closest?.('.o-wa-line'); if (line && !line.contains(event.relatedTarget)) { line.classList.remove('is-keys'); line.querySelectorAll('.o-wa-act').forEach((b) => b.setAttribute('tabindex', '-1')); } }, { signal });
    this.ui.quote?.querySelector('[data-quote-remove]')?.addEventListener('click', () => { this.setQuote(null); this.ui.input?.focus({ preventScroll: true }); }, { signal });
  }

  closeActs() {
    this.ui.msgs.querySelectorAll('.o-wa-line.is-acts, .o-wa-line.is-emoji').forEach((row) => {
      row.classList.remove('is-acts', 'is-emoji');
      row.querySelector('[data-act="emoji"]')?.setAttribute('aria-expanded', 'false');
    });
  }

  /** The emoji popover opens above its disc, or below when the message is near the top of the pane. */
  flipEmoji(row) {
    const room = row.getBoundingClientRect().top - this.ui.scroll.getBoundingClientRect().top;
    row.classList.toggle('is-below', room < 140);
  }

  setQuote(m) {
    if (!m) this.quote = null;
    else this.quote = { id: m.id, direction: m.direction, kind: m.kind, who: this.whoQuoted(m.direction), text: this.quoteLabel(m) };
    this.renderQuote();
    if (m) this.ui.input?.focus({ preventScroll: true });
    this.updateSend();
  }

  renderQuote() {
    const { quote, quoteWho, quoteText, quoteNote } = this.ui;
    if (!quote) return;
    quote.hidden = !this.quote;
    if (!this.quote) return;
    quoteWho.textContent = `Replying to ${this.quote.who}`;
    quoteText.textContent = this.quote.text;
    quoteNote.textContent = this.rec ? 'A voice note carries no quote on his phone.' : 'On his phone this shows as a quoted line.';
  }

  // ---------- voice notes (docs/features/email-chat-design.md section 4) ----------
  // Tap to start, tap to send: not hold (hold fights text selection and is hard for a long note). The permission prompt only ever follows that tap. Every exit
  // (cancel, send, the limit, a locked phone, leaving the chat or the page) stops the recorder AND every track of the stream, or the phone's microphone indicator stays on.

  bindVoice() {
    const { mic, recPanel } = this.ui;
    if (!mic || !recPanel) return;
    const { signal } = this.ac;
    mic.addEventListener('click', () => this.startRecording(), { signal });
    recPanel.querySelector('[data-rec-cancel]').addEventListener('click', () => this.cancelRecording(), { signal });
    recPanel.querySelector('[data-rec-send]').addEventListener('click', () => this.finishRecording(), { signal });
    // a locked or hidden phone stops the recording; he still chooses Cancel or Send
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden' && this.rec?.mode === 'recording') this.stopRecorder(); }, { signal });
    window.addEventListener('pagehide', () => this.cancelRecording(true), { signal });
  }

  micError(error) {
    const name = error?.name || '';
    const app = navigator.standalone === true;
    let words = 'The microphone could not be started. Try again.';
    if (['NotAllowedError', 'SecurityError', 'PermissionDeniedError'].includes(name)) words = app ? 'Microphone blocked. Allow it in Settings, then try again.' : 'Microphone blocked. Allow it in your browser settings, then try again.';
    else if (['NotFoundError', 'DevicesNotFoundError', 'OverconstrainedError'].includes(name)) words = 'No microphone found.';
    const box = this.ui.trayError;
    box.hidden = false;
    box.textContent = words;
  }

  releaseTracks(rec) {
    rec?.stream?.getTracks().forEach((track) => { try { track.stop(); } catch { /* already stopped */ } });
  }

  async startRecording() {
    if (this.rec || this.state !== 'open' || !this.voiceReady()) return;
    const rec = { mode: 'asking', stream: null, recorder: null, chunks: [], seconds: 0, timer: 0, warned: false, cancelled: false, sendAfter: false, mime: '' };
    this.rec = rec;
    this.ui.trayError.hidden = true;
    this.ui.input.blur();
    this.renderRec();
    let stream = null;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); } catch (error) { if (this.rec === rec) this.rec = null; this.renderRec(); this.micError(error); return; }
    if (!this.alive || this.rec !== rec) { stream.getTracks().forEach((t) => t.stop()); return; } // he left, or cancelled while the phone was asking
    rec.stream = stream;
    let recorder = null;
    try {
      const type = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/webm'].find((t) => MediaRecorder.isTypeSupported?.(t));
      recorder = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
    } catch {
      this.releaseTracks(rec); this.rec = null; this.renderRec();
      this.ui.trayError.hidden = false; this.ui.trayError.textContent = 'Voice notes are not available right now.';
      this.contact = { ...this.contact, voice: { ...(this.contact.voice || {}), available: false } }; this.updateSend();
      return;
    }
    rec.recorder = recorder;
    rec.mime = recorder.mimeType || 'audio/webm';
    recorder.addEventListener('dataavailable', (event) => { if (event.data && event.data.size) rec.chunks.push(event.data); });
    recorder.addEventListener('stop', () => this.recorderStopped(rec));
    recorder.start(1000);
    rec.mode = 'recording';
    rec.startedAt = Date.now();
    rec.max = this.contact.voice?.max_seconds || 300;
    rec.timer = setInterval(() => this.tickRec(rec), 250);
    this.renderRec();
    this.say('Recording'); // once, never each second
    this.ui.recPanel.focus({ preventScroll: true });
  }

  tickRec(rec) {
    if (this.rec !== rec || rec.mode !== 'recording') return;
    rec.seconds = (Date.now() - rec.startedAt) / 1000;
    if (!rec.warned && rec.max - rec.seconds <= 30) { rec.warned = true; this.say(`Stops at ${clock(rec.max)}`); }
    if (rec.seconds >= rec.max) { rec.seconds = rec.max; rec.atLimit = true; this.stopRecorder(); return; }
    this.renderRec();
  }

  /** Stop the recorder (the limit, a hidden page, or Send). The tracks are released when the recorder says it has stopped. */
  stopRecorder() {
    const rec = this.rec;
    if (!rec || rec.mode !== 'recording') return;
    clearInterval(rec.timer);
    rec.seconds = Math.min(rec.max, (Date.now() - rec.startedAt) / 1000);
    rec.mode = 'stopped';
    this.renderRec();
    try { if (rec.recorder.state !== 'inactive') rec.recorder.stop(); else this.recorderStopped(rec); } catch { this.recorderStopped(rec); }
    this.releaseTracks(rec);
  }

  recorderStopped(rec) {
    this.releaseTracks(rec);
    if (rec.cancelled || this.rec !== rec) return;
    rec.blob = new Blob(rec.chunks, { type: rec.mime || 'audio/webm' });
    if (rec.sendAfter) this.sendRecorded();
  }

  /** The send disc: while recording it stops and then sends; when already stopped it sends the held recording. */
  finishRecording() {
    const rec = this.rec;
    if (!rec || rec.mode === 'asking') return;
    if (rec.mode === 'recording') { rec.sendAfter = true; this.stopRecorder(); return; }
    if (rec.blob) this.sendRecorded(); else rec.sendAfter = true;
  }

  sendRecorded() {
    const rec = this.rec;
    if (!rec || !rec.blob) return;
    const reply = this.quote ? { id: this.quote.id, direction: this.quote.direction, kind: this.quote.kind, text: this.quote.text } : null; // a voice note carries no quote on his phone, but the Office still links it
    const { blob, seconds } = rec;
    this.rec = null;
    this.renderRec();
    this.setQuote(null);
    if (!blob.size || seconds < 0.5) { this.ui.trayError.hidden = false; this.ui.trayError.textContent = 'That recording could not be used. Try again.'; return; }
    this.sendVoice(blob, seconds, null, reply);
    this.updateSend();
  }

  cancelRecording(silent = false) {
    const rec = this.rec;
    if (!rec) return;
    rec.cancelled = true;
    clearInterval(rec.timer);
    try { if (rec.recorder && rec.recorder.state !== 'inactive') rec.recorder.stop(); } catch { /* already stopped */ }
    this.releaseTracks(rec);
    this.rec = null;
    if (!silent) { this.renderRec(); this.updateSend(); }
  }

  renderRec() {
    const { composer, recPanel } = this.ui;
    if (!recPanel) return;
    const rec = this.rec;
    if (rec) composer.dataset.recording = rec.mode; else delete composer.dataset.recording;
    recPanel.hidden = !rec;
    this.renderQuote();
    if (!rec) return;
    const q = (sel) => recPanel.querySelector(sel);
    q('[data-rec-ask]').hidden = rec.mode !== 'asking';
    q('[data-rec-live]').hidden = rec.mode === 'asking';
    q('[data-rec-dot]').hidden = rec.mode !== 'recording';
    q('[data-rec-time]').textContent = clock(rec.seconds);
    q('[data-rec-word]').textContent = rec.mode === 'stopped' ? `Stopped at ${clock(rec.seconds)}` : 'Recording';
    const pill = q('[data-rec-pill]');
    pill.hidden = !(rec.mode === 'recording' && rec.warned);
    if (!pill.hidden) pill.textContent = `Stops at ${clock(rec.max)}`;
    q('[data-rec-send]').setAttribute('aria-disabled', String(rec.mode === 'asking'));
  }

  // ---------- sending ----------

  tempMessage(fields) {
    this.tmp += 1;
    return { id: `tmp-${this.tmp}`, direction: 'out', kind: 'text', body: '', body_html: '', status: 'queued', error: null, author: '', author_id: '', author_first_name: '', template: null, media: null, reply_to: null,
      created_at: new Date().toISOString(), sent_at: '', retry_url: '', ...fields };
  }

  /** The quote the message being sent carries: shown in its bubble at once, posted as reply_to. */
  quoteOf() {
    return this.quote && !this.rec ? { id: this.quote.id, direction: this.quote.direction, kind: this.quote.kind, text: this.quote.text } : null;
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
    const reply = this.quoteOf();
    this.ui.input.value = '';
    this.grow();
    this.clearFile();
    this.setQuote(null);
    if (file) this.sendFile(file, text, null, reply); else this.sendText(text, null, { reply });
    this.updateSend();
    if (!phone()) this.ui.input.focus();
  }

  form(extra, reply) {
    const body = new URLSearchParams(extra);
    if (this.gold) body.set('gold', this.gold.id);
    if (reply) body.set('reply_to', String(reply.id));
    return body;
  }

  /** `opts.plain`: an emoji from the quick row goes as it is, with no quote (a quote plus one emoji reads worse on his phone than the emoji). */
  async sendText(text, existing, opts = {}) {
    const reply = existing ? existing.reply_to : (opts.plain ? null : opts.reply || null);
    const temp = existing || this.tempMessage({ localText: text, body: text, reply_to: reply });
    if (!existing) this.addTemp(temp);
    temp.status = 'queued';
    this.sending += 1;
    try {
      const response = await fetch(this.urls.send, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrfToken(), Accept: 'application/json' }, body: this.form({ body: text }, reply) });
      const data = await response.json().catch(() => null);
      if (response.ok && data?.ok) { this.afterSent(temp, data.message, text); return; }
      if (!data) throw new Error('bad answer');
      this.serverRefused(temp, data, opts.plain ? '' : text);
    } catch {
      this.setOffline(true);
      this.failTemp(temp, 'Not sent. Try again.', () => this.sendText(text, temp, opts));
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
    if (data.error === 'voice_unavailable') this.contact = { ...this.contact, voice: { ...(this.contact.voice || {}), available: false } };
    const words = {
      window_closed: 'Not sent. The window has closed.', opted_out: 'Not sent. He replied STOP.', bad_reply: 'That message can no longer be quoted.',
      voice_too_long: 'That voice note is over 5 minutes.', too_big: temp.kind === 'audio' ? 'That voice note is too large to send.' : (data.message || 'That file is too big to send.'), voice_unavailable: 'Voice notes are not available right now.',
      bad_file: temp.kind === 'audio' ? 'That recording could not be used. Try again.' : '',
    };
    const reason = words[data.error] || (data.message ? `Not sent. ${data.message}` : 'Not sent. Try again.');
    const retry = temp.kind === 'audio' && data.error === 'bad_file' ? temp.again : null;   // "Try again" resends the held recording
    this.failTemp(temp, reason, retry);
    if (data.error === 'bad_reply' && this.quote) this.setQuote(null);
    if (text) { try { sessionStorage.setItem(this.draftKey, text); } catch { /* private mode */ } }
    this.applyState();
    if (this.state === 'open' && text && !this.ui.input.value) { this.ui.input.value = text; this.grow(); this.updateSend(); }
  }

  /** One upload with a progress bar (photo, PDF, video, voice note). `url`, the form, and `again` (what "Try again" runs) differ; the rest is the same. */
  upload(temp, url, body, again, caption) {
    this.sending += 1;
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);
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
      if (xhr.status === 413) { this.failTemp(temp, 'That file is too big to send.', null); return; }   // refused before it reached the app (not JSON)
      this.failTemp(temp, 'Not sent. Try again.', again);
    });
    xhr.addEventListener('error', () => { this.sending -= 1; this.setOffline(true); this.failTemp(temp, 'Not sent. Try again.', again); });
    xhr.send(body);
  }

  sendFile(file, caption, existing, reply) {
    const kind = file.type.startsWith('image/') ? 'image' : (file.type.startsWith('video/') ? 'video' : 'document');
    const url = existing ? existing.media.url : URL.createObjectURL(file);
    if (!existing) (this.urls_to_free = this.urls_to_free || []).push(url);
    const quote = existing ? existing.reply_to : reply || null;
    const temp = existing || this.tempMessage({
      kind, localText: caption, body: caption, progress: 0, reply_to: quote,
      media: { url, type: file.type, filename: file.name, size: file.size, width: null, height: null },
    });
    if (!existing) {
      if (kind === 'image') { // read the size so the bubble keeps its shape while it uploads
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
    if (quote) body.set('reply_to', String(quote.id));
    this.upload(temp, this.urls.send_media, body, () => this.sendFile(file, caption, temp, quote), caption);
  }

  /** A recorded voice note: the bubble appears at once with the bar and the queued tick; the server converts it, so it stays "Sending" until it answers. */
  sendVoice(blob, seconds, existing, reply) {
    const url = existing ? existing.media.url : URL.createObjectURL(blob);
    if (!existing) (this.urls_to_free = this.urls_to_free || []).push(url);
    const quote = existing ? existing.reply_to : reply || null;
    const temp = existing || this.tempMessage({
      kind: 'audio', progress: 0, reply_to: quote,
      media: { url, type: blob.type || 'audio/webm', filename: 'voice-note', size: blob.size, width: null, height: null },
    });
    if (!existing) this.addTemp(temp); else { temp.progress = 0; temp.status = 'queued'; this.refreshTemp(temp); }
    const ext = /mp4|aac/.test(blob.type) ? 'm4a' : (/ogg/.test(blob.type) ? 'ogg' : 'webm');
    const body = new FormData();
    body.set('file', blob, `voice-note.${ext}`);
    body.set('duration', String(Math.round(seconds)));
    if (this.gold) body.set('gold', this.gold.id);
    if (quote) body.set('reply_to', String(quote.id));
    const again = () => this.sendVoice(blob, seconds, temp, quote);
    temp.again = again;
    this.upload(temp, this.urls.send_voice, body, again, '');
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
