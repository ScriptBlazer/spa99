/* The rich text editor of the reply and of New email (docs/features/email-chat-design.md section 3). A small contenteditable with a toolbar, no library.
 *
 * What it makes is cleaned twice more: `html()` below builds a NEW tree from the editor with only the tags and colours the server allows, and the server cleans
 * it again to its own allow-list. Paste is plain text (Word and Outlook bring fonts and sizes that the server would strip, and staff would then see something
 * other than what he gets). Colours are the brief's four and nothing else; a highlight always writes `background-color` AND `color` on one span, never `mark`
 * (Outlook's Word engine ignores it and browsers paint it yellow). Enter is a new line, Cmd or Ctrl+Enter sends. */
import { bytes, h, icon, mb } from './office-dom.js';

const TEXT = '#492e21';   // espresso: the editor's own text, and the text of a highlight
const COLORS = { gold: '#8a5a2e', red: '#8b1e1e', soft: '#745f4f' };   // --office-gold-text, --color-danger, --color-text-muted (every one is in the server's allow-list)
const HIGHLIGHT_BG = '#f6e1c8';   // --office-wa-out
const SAFE_LINK = /^(https?:|mailto:)/i;
const BLOCKS = new Set(['P', 'DIV', 'UL', 'OL', 'LI', 'BLOCKQUOTE', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'PRE', 'TABLE', 'TR']);

/** 'rgb(138, 90, 46)' or '#8A5A2E' or '#abc' to '#8a5a2e'; '' when it is not a plain colour. */
export function toHex(value) {
  const text = String(value || '').trim().toLowerCase();
  let m = /^#([0-9a-f]{6})$/.exec(text);
  if (m) return `#${m[1]}`;
  m = /^#([0-9a-f])([0-9a-f])([0-9a-f])$/.exec(text);
  if (m) return `#${m[1]}${m[1]}${m[2]}${m[2]}${m[3]}${m[3]}`;
  m = /^rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)(?:[\s,/]+([\d.]+%?))?\s*\)$/.exec(text);
  if (m) {
    if (m[4] !== undefined && Number.parseFloat(m[4]) === 0) return '';   // fully transparent
    return `#${[m[1], m[2], m[3]].map((n) => Number(n).toString(16).padStart(2, '0')).join('')}`;
  }
  return '';
}

/** A link address staff typed: a bare domain gains https://, an address gains mailto:, and only http, https and mailto get through ('' otherwise). */
export function safeHref(value) {
  let text = String(value || '').trim();
  if (!text) return '';
  if (!/^[a-z][a-z0-9+.-]*:/i.test(text)) text = /^[^\s@/]+@[^\s@/]+\.[^\s@/]+$/.test(text) ? `mailto:${text}` : `https://${text}`;
  return SAFE_LINK.test(text) ? text : '';
}

/* ---------- the clean copy: only what the server's allow-list keeps ---------- */

/** Which of the span's colours survive. Highlight is one choice: both properties together. Anything else becomes plain text. */
function spanLook(node) {
  const color = toHex(node.style?.color || node.getAttribute?.('color'));
  const bg = toHex(node.style?.backgroundColor);
  if (bg === HIGHLIGHT_BG) return { bg: HIGHLIGHT_BG, color: TEXT };
  if (Object.values(COLORS).includes(color)) return { color };
  return null;
}

/** Copy `from`'s children into `to`, keeping only safe tags. `to` is a node we made; nothing from `from` is ever adopted as is. */
function copyInto(from, to) {
  for (const child of from.childNodes) {
    if (child.nodeType === Node.TEXT_NODE) { to.append(document.createTextNode(child.nodeValue)); continue; }
    if (child.nodeType !== Node.ELEMENT_NODE) continue;
    const tag = child.tagName;
    if (['SCRIPT', 'STYLE', 'TEMPLATE', 'IFRAME', 'OBJECT', 'NOSCRIPT'].includes(tag)) continue;
    let target = null;
    if (tag === 'B' || tag === 'STRONG') target = document.createElement('strong');
    else if (tag === 'I' || tag === 'EM') target = document.createElement('em');
    else if (tag === 'U') target = document.createElement('u');
    else if (tag === 'S' || tag === 'STRIKE' || tag === 'DEL') target = document.createElement('s');
    else if (tag === 'BR') { to.append(document.createElement('br')); continue; }
    else if (tag === 'UL' || tag === 'OL' || tag === 'LI' || tag === 'BLOCKQUOTE') target = document.createElement(tag.toLowerCase());
    else if (tag === 'P' || tag === 'DIV') target = to.closest?.('li') || to.nodeName === 'LI' ? null : document.createElement('p');
    else if (tag === 'A') {
      const href = safeHref(child.getAttribute('href'));
      if (href) { target = document.createElement('a'); target.setAttribute('href', href); }
    } else if (tag === 'SPAN' || tag === 'FONT') {
      // browsers write bold, italic and the like as styles on a span when asked to; carry them over as real tags
      let wrap = to;
      const css = child.style || {};
      const add = (name) => { const el = document.createElement(name); wrap.append(el); wrap = el; };
      if (/^(bold|[6-9]00)$/.test(css.fontWeight || '')) add('strong');
      if (css.fontStyle === 'italic') add('em');
      if ((css.textDecorationLine || css.textDecoration || '').includes('underline')) add('u');
      if ((css.textDecorationLine || css.textDecoration || '').includes('line-through')) add('s');
      const look = spanLook(child);
      if (look) {
        const span = document.createElement('span');
        span.setAttribute('style', `${look.bg ? `background-color: ${look.bg}; ` : ''}color: ${look.color};`);
        wrap.append(span);
        wrap = span;
      }
      copyInto(child, wrap);
      continue;
    }
    if (target === null) { if (BLOCKS.has(tag) && to.lastChild && to.lastChild.nodeName !== 'BR') to.append(document.createElement('br')); copyInto(child, to); continue; }
    copyInto(child, target);
    to.append(target);
  }
}

/** The clean copy of an editor's content: top-level loose text and inline runs are gathered into paragraphs. */
export function cleanTree(from) {
  const staging = document.createElement('div');
  copyInto(from, staging);
  const out = document.createElement('div');
  let run = null;
  for (const node of [...staging.childNodes]) {
    const block = node.nodeType === Node.ELEMENT_NODE && ['P', 'UL', 'OL', 'BLOCKQUOTE'].includes(node.nodeName);
    if (block) { run = null; out.append(node); continue; }
    if (!run) { run = document.createElement('p'); out.append(run); }
    run.append(node);
  }
  for (const p of [...out.querySelectorAll('p')]) if (!p.textContent.trim() && !p.querySelector('br')) p.append(document.createElement('br'));
  // trailing empty paragraphs are just the cursor's room
  while (out.lastElementChild && out.lastElementChild.nodeName === 'P' && !out.lastElementChild.textContent.trim() && out.children.length > 1) out.lastElementChild.remove();
  return out;
}

export class Editor {
  /** `root` is the [data-editor] block. Options: limits {file_bytes, send_bytes, files}, onChange(), onSend(), onFiles() (the tray changed). */
  constructor(root, { limits = {}, onChange = () => {}, onSend = () => {}, onFiles = () => {} } = {}) {
    this.root = root;
    this.limits = { file_bytes: 10 * 1024 * 1024, send_bytes: 9 * 1024 * 1024, files: 20, ...limits };
    this.onChange = onChange;
    this.onSend = onSend;
    this.onFiles = onFiles;
    this.files = [];
    this.urls = [];
    this.range = null;
    this.ac = new AbortController();
    const q = (sel) => root.querySelector(sel);
    this.ed = q('[data-ed-editable]');
    this.tools = q('[data-ed-tools]');
    this.tray = q('[data-ed-tray]');
    this.error = q('[data-ed-error]');
    this.input = q('[data-ed-file]');
    this.colors = q('[data-ed-colors]');
    this.more = q('[data-ed-more]');
    this.dialog = q('[data-ed-link]');
    this.ensureParagraph();
    this.bindEditor();
    this.bindTools();
    this.bindFiles();
    this.bindLink();
    this.refresh();
  }

  destroy() {
    this.ac.abort();
    for (const url of this.urls) URL.revokeObjectURL(url);
    this.urls = [];
  }

  // ---------- content ----------

  /** The email's HTML (a new, clean tree: see cleanTree). */
  html() { return cleanTree(this.ed).innerHTML; }

  /** What he would read as plain text. */
  text() { return (this.ed.innerText || '').replace(/ /g, ' ').trim(); }

  hasText() { return this.text().length > 0; }
  hasContent() { return this.hasText() || this.files.length > 0; }

  /** Fill from a draft: rebuilt through the same clean copy, so nothing but allowed tags can ever enter. */
  setHtml(html) {
    const parsed = new DOMParser().parseFromString(`<body>${html || ''}</body>`, 'text/html').body;
    const clean = cleanTree(parsed);
    this.ed.replaceChildren(...clean.childNodes);
    this.ensureParagraph();
    this.refresh();
  }

  /** An empty field holds one empty paragraph, so what he types goes in a paragraph from the first key (a bare text node makes list and quote buttons build invalid markup). */
  ensureParagraph() {
    if (!this.ed.firstChild) { const p = document.createElement('p'); p.append(document.createElement('br')); this.ed.append(p); }
  }

  clear() {
    this.ed.replaceChildren();
    this.ensureParagraph();
    this.clearFiles();
    this.setError('');
    this.refresh();
  }

  focus() { this.ed.focus({ preventScroll: true }); }

  setError(message) {
    this.error.hidden = !message;
    this.error.textContent = message || '';
  }

  refresh() {
    this.ed.toggleAttribute('data-empty', !this.ed.textContent.trim() && !this.ed.querySelector('li, blockquote'));   // the placeholder shows only on an empty field
    this.syncMarks();
    this.onChange();
  }

  // ---------- the field ----------

  bindEditor() {
    const { signal } = this.ac;
    const ed = this.ed;
    try { document.execCommand('defaultParagraphSeparator', false, 'p'); } catch { /* the browser keeps its own */ }
    ed.addEventListener('input', () => this.refresh(), { signal });
    ed.addEventListener('blur', () => this.saveRange(), { signal });
    document.addEventListener('selectionchange', () => { if (this.inside()) { this.saveRange(); this.syncMarks(); } }, { signal });
    ed.addEventListener('keydown', (event) => {
      if (event.isComposing || event.keyCode === 229) return;
      const mod = event.metaKey || event.ctrlKey;
      const key = event.key.toLowerCase();
      if (mod && event.key === 'Enter') { event.preventDefault(); this.onSend(); return; }
      if (!mod || event.altKey) return;
      if (event.shiftKey && key === 'x') { event.preventDefault(); this.command('strike'); } else if (event.shiftKey && (key === '8' || key === '*')) { event.preventDefault(); this.command('bullets'); } else if (event.shiftKey && (key === '7' || key === '&')) { event.preventDefault(); this.command('numbers'); } else if (!event.shiftKey && key === 'k') { event.preventDefault(); this.command('link'); }
    }, { signal });
    ed.addEventListener('paste', (event) => {
      const files = [...(event.clipboardData?.files || [])];
      if (files.length) { event.preventDefault(); this.addFiles(files); return; }
      event.preventDefault();
      const text = (event.clipboardData?.getData('text/plain') || '').replace(/\r\n?/g, '\n');
      this.insertPlain(text);
    }, { signal });
    // a link he types is only a link when he makes it one: dropped text and files never run anything
    const zone = ed.closest('.o-em-composer, .o-em-new') || ed;
    let depth = 0;
    const dragging = (event) => [...(event.dataTransfer?.types || [])].includes('Files');
    zone.addEventListener('dragenter', (event) => { if (dragging(event)) { depth += 1; zone.classList.add('is-drop'); } }, { signal });
    zone.addEventListener('dragleave', () => { depth = Math.max(0, depth - 1); if (!depth) zone.classList.remove('is-drop'); }, { signal });
    zone.addEventListener('dragover', (event) => { if (dragging(event)) event.preventDefault(); }, { signal });
    zone.addEventListener('drop', (event) => {
      depth = 0; zone.classList.remove('is-drop');
      if (!dragging(event)) return;
      event.preventDefault();
      this.addFiles([...event.dataTransfer.files]);
    }, { signal });
  }

  /** Plain text in, line breaks kept (each line a paragraph). */
  insertPlain(text) {
    this.restore();
    const lines = text.split('\n');
    lines.forEach((line, i) => {
      if (line) document.execCommand('insertText', false, line);
      if (i < lines.length - 1) document.execCommand('insertParagraph');
    });
    this.refresh();
  }

  inside() {
    const sel = window.getSelection();
    return !!sel && sel.rangeCount > 0 && this.ed.contains(sel.anchorNode);
  }

  saveRange() {
    const sel = window.getSelection();
    if (sel && sel.rangeCount && this.ed.contains(sel.anchorNode)) this.range = sel.getRangeAt(0).cloneRange();
  }

  /** Put the cursor back where it was before a button or the link dialog took focus. */
  restore() {
    if (this.inside() && document.activeElement === this.ed) return;
    this.ed.focus({ preventScroll: true });
    if (this.range) { const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(this.range); }
  }

  // ---------- commands ----------

  /** execCommand with or without CSS output: colours want spans, everything else wants tags. */
  exec(name, value, css = false) {
    this.restore();
    try { document.execCommand('styleWithCSS', false, css); } catch { /* old browser */ }
    document.execCommand(name, false, value);
    this.saveRange();
  }

  command(name) {
    if (name === 'bold') this.exec('bold');
    else if (name === 'italic') this.exec('italic');
    else if (name === 'underline') this.exec('underline');
    else if (name === 'strike') this.exec('strikeThrough');
    else if (name === 'bullets') this.exec('insertUnorderedList');
    else if (name === 'numbers') this.exec('insertOrderedList');
    else if (name === 'quote') this.toggleQuote();
    else if (name === 'highlight') this.toggleHighlight();
    else if (name === 'link') { this.openLink(); return; }
    else if (name === 'attach') { this.input.click(); return; }
    else if (name === 'color') { this.toggleColors(); return; }
    this.fixHighlights();
    this.refresh();
    if (!this.mobileMode()) this.ed.focus({ preventScroll: true });
  }

  mobileMode() { return window.matchMedia('(max-width: 63.99em)').matches; }

  toggleQuote() {
    this.restore();
    const sel = window.getSelection();
    const node = sel.anchorNode && (sel.anchorNode.nodeType === 1 ? sel.anchorNode : sel.anchorNode.parentElement);
    const quote = node?.closest('blockquote');
    if (quote && this.ed.contains(quote)) {
      const parent = quote.parentNode;
      while (quote.firstChild) parent.insertBefore(quote.firstChild, quote);
      quote.remove();
    } else this.exec('formatBlock', 'blockquote');
  }

  atHighlight() {
    const node = this.anchorElement();
    for (let el = node; el && el !== this.ed; el = el.parentElement) {
      if (el.tagName === 'SPAN' && toHex(el.style.backgroundColor) === HIGHLIGHT_BG) return true;
    }
    return false;
  }

  toggleHighlight() {
    const on = this.atHighlight();
    this.exec('hiliteColor', on ? 'transparent' : HIGHLIGHT_BG, true);
    if (!on) this.fixHighlights();
  }

  /** A highlight is a pale wash, so its text is always espresso: set both properties on the span, whatever the browser wrote. */
  fixHighlights() {
    for (const span of this.ed.querySelectorAll('span[style]')) {
      const bg = toHex(span.style.backgroundColor);
      if (bg === HIGHLIGHT_BG) span.style.color = TEXT;
      else if (span.style.backgroundColor) span.style.removeProperty('background-color');
    }
  }

  chooseColor(name) {
    this.exec('foreColor', name === 'default' ? TEXT : COLORS[name], true);
    this.fixHighlights();
    this.closeColors();
    this.refresh();
    if (!this.mobileMode()) this.ed.focus({ preventScroll: true });
  }

  toggleColors() {
    const open = this.colors.hidden;
    this.saveRange();
    this.colors.hidden = !open;
    this.tools.dataset.colors = open ? 'open' : '';
    const button = this.tools.querySelector('[data-cmd="color"]');
    button.setAttribute('aria-expanded', String(open));
    if (open) {
      this.positionColors(button);
      this.colors.querySelector('button')?.focus({ preventScroll: true });
    }
  }

  positionColors(button) {
    const left = button.offsetLeft + button.offsetWidth / 2;
    this.colors.style.setProperty('--sw-x', `${left}px`);
  }

  closeColors() {
    if (this.colors.hidden) return;
    this.colors.hidden = true;
    this.tools.dataset.colors = '';
    const button = this.tools.querySelector('[data-cmd="color"]');
    button.setAttribute('aria-expanded', 'false');
  }

  anchorElement() {
    const sel = window.getSelection();
    const node = sel?.anchorNode;
    if (!node || !this.ed.contains(node)) return null;
    return node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
  }

  /** aria-pressed from what the cursor is in. */
  syncMarks() {
    const states = {};
    const el = this.anchorElement();
    if (el) {
      const q = (name) => { try { return document.queryCommandState(name); } catch { return false; } };
      states.bold = q('bold'); states.italic = q('italic'); states.underline = q('underline'); states.strike = q('strikeThrough');
      states.bullets = q('insertUnorderedList'); states.numbers = q('insertOrderedList');
      states.quote = !!el.closest('blockquote');
      states.link = !!el.closest('a');
      states.highlight = this.atHighlight();
      let color = '';
      try { color = toHex(document.queryCommandValue('foreColor')); } catch { /* none */ }
      states.color = !!color && color !== TEXT;
    }
    for (const button of this.tools.querySelectorAll('[aria-pressed]')) button.setAttribute('aria-pressed', String(!!states[button.dataset.cmd]));
  }

  // ---------- the toolbar ----------

  bindTools() {
    const { signal } = this.ac;
    const tools = this.tools;
    // every button keeps the selection and the keyboard: nothing takes focus on a press
    tools.addEventListener('pointerdown', (event) => { if (event.target.closest('.o-em-tool, .o-em-sw, .o-em-send')) event.preventDefault(); }, { signal });
    tools.addEventListener('click', (event) => {
      const sw = event.target.closest('[data-color]');
      if (sw) { this.chooseColor(sw.dataset.color); return; }
      const more = event.target.closest('[data-ed-more]');
      if (more) {
        const open = tools.dataset.more !== 'open';
        tools.dataset.more = open ? 'open' : '';
        more.setAttribute('aria-expanded', String(open));
        this.closeColors();
        return;
      }
      const button = event.target.closest('[data-cmd]');
      if (!button) return;
      if (button.dataset.cmd !== 'color') this.closeColors();
      this.command(button.dataset.cmd);
    }, { signal });
    // roving tabindex: one stop for the toolbar, arrows and Home and End inside it
    tools.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !this.colors.hidden) { event.preventDefault(); this.closeColors(); tools.querySelector('[data-cmd="color"]')?.focus(); return; }
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      const list = [...tools.querySelectorAll('.o-em-tool')].filter((b) => b.offsetParent !== null && !b.closest('[hidden]'));
      const at = list.indexOf(document.activeElement);
      if (at < 0) return;
      event.preventDefault();
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? list.length - 1 : (at + (event.key === 'ArrowRight' ? 1 : -1) + list.length) % list.length;
      list.forEach((b, i) => b.setAttribute('tabindex', i === next ? '0' : '-1'));
      list[next].focus();
    }, { signal });
    tools.addEventListener('focusin', (event) => {
      const button = event.target.closest('.o-em-tool');
      if (!button) return;
      tools.querySelectorAll('.o-em-tool').forEach((b) => b.setAttribute('tabindex', b === button ? '0' : '-1'));
    }, { signal });
    document.addEventListener('pointerdown', (event) => { if (!this.colors.hidden && !event.target.closest('[data-ed-colors], [data-cmd="color"]')) this.closeColors(); }, { signal });
  }

  // ---------- link ----------

  bindLink() {
    const { signal } = this.ac;
    const dialog = this.dialog;
    const form = dialog.querySelector('form');
    const text = dialog.querySelector('[data-link-text]');
    const href = dialog.querySelector('[data-link-href]');
    const error = dialog.querySelector('[data-link-error]');
    const remove = dialog.querySelector('[data-link-remove]');
    this.linkEls = { text, href, error, remove };
    dialog.querySelector('[data-link-cancel]').addEventListener('click', () => dialog.close(), { signal });
    let down = false;
    dialog.addEventListener('pointerdown', (event) => { down = event.target === dialog; }, { signal });
    dialog.addEventListener('click', (event) => { if (event.target === dialog && down) dialog.close(); }, { signal });
    dialog.addEventListener('close', () => { if (this.mobileMode()) this.ed.focus({ preventScroll: true }); else this.ed.focus(); }, { signal });
    href.addEventListener('input', () => { error.hidden = true; href.removeAttribute('aria-invalid'); }, { signal });
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      const address = safeHref(href.value);
      if (!address) {
        error.hidden = false; error.textContent = 'Links start with https:// or mailto:'; href.setAttribute('aria-invalid', 'true'); href.focus();
        return;
      }
      dialog.close();
      this.applyLink(text.value.trim(), address);
    }, { signal });
    remove.addEventListener('click', () => { dialog.close(); this.restore(); this.exec('unlink'); this.refresh(); }, { signal });
  }

  openLink() {
    this.saveRange();
    const { text, href, error, remove } = this.linkEls;
    const link = this.anchorElement()?.closest('a');
    const selected = this.range && !this.range.collapsed ? this.range.toString() : '';
    text.value = link ? link.textContent : selected;
    href.value = link ? link.getAttribute('href') || '' : '';
    error.hidden = true;
    href.removeAttribute('aria-invalid');
    remove.hidden = !link;
    this.dialog.querySelector('#em-link-h').textContent = link ? 'Edit the link' : 'Add a link';
    this.dialog.showModal();
    (selected ? href : text).focus();
  }

  applyLink(label, address) {
    this.restore();
    const link = this.anchorElement()?.closest('a');
    if (link) {
      link.setAttribute('href', address);
      if (label && label !== link.textContent) link.textContent = label;
    } else {
      const a = document.createElement('a');
      a.setAttribute('href', address);
      a.textContent = label || address;
      const sel = window.getSelection();
      if (!sel.rangeCount) { this.ed.append(a); } else {
        const range = sel.getRangeAt(0);
        if (!range.collapsed && label === range.toString()) { try { range.surroundContents(a); } catch { range.deleteContents(); range.insertNode(a); } } else { range.deleteContents(); range.insertNode(a); }
        range.setStartAfter(a); range.collapse(true);
        sel.removeAllRanges(); sel.addRange(range);
      }
    }
    this.refresh();
  }

  // ---------- files ----------

  bindFiles() {
    const { signal } = this.ac;
    this.input.addEventListener('change', () => { this.addFiles([...this.input.files]); this.input.value = ''; }, { signal });
  }

  totalBytes() { return this.files.reduce((n, f) => n + f.size, 0); }

  addFiles(list) {
    this.setError('');
    for (const file of list) {
      if (this.files.length >= this.limits.files) { this.setError(`Up to ${this.limits.files} files.`); break; }
      if (file.size > this.limits.file_bytes) { this.setError(`Files up to ${mb(this.limits.file_bytes)} each.`); continue; }
      if (this.totalBytes() + file.size > this.limits.send_bytes) { this.setError(`Up to ${mb(this.limits.send_bytes)} of files an email.`); continue; }
      this.files.push(file);
    }
    this.renderTray();
    this.refresh();
    this.onFiles();
  }

  removeFile(file) {
    this.files = this.files.filter((f) => f !== file);
    this.setError('');
    this.renderTray();
    this.refresh();
    this.onFiles();
  }

  clearFiles() {
    this.files = [];
    for (const url of this.urls) URL.revokeObjectURL(url);
    this.urls = [];
    this.renderTray();
  }

  renderTray() {
    const nodes = this.files.map((file) => {
      const thumb = h('span', { class: 'o-em-chip-thumb' });
      if (file.type === 'image/jpeg' || file.type === 'image/png' || file.type === 'image/gif' || file.type === 'image/webp') {
        const url = URL.createObjectURL(file);
        this.urls.push(url);
        thumb.append(h('img', { src: url, alt: '' }));
      } else thumb.append(icon(file.type === 'application/pdf' ? 'file-pdf' : 'paperclip'));
      const remove = h('button', { type: 'button', class: 'o-em-chip-x', 'aria-label': `Remove ${file.name}` }, icon('x'));
      remove.addEventListener('click', () => { this.removeFile(file); this.ed.focus({ preventScroll: true }); });
      return h('span', { class: 'o-em-chip o-em-chip--file' }, thumb,
        h('span', { class: 'o-em-chip-main' }, h('span', { class: 'o-em-chip-text', dir: 'auto', text: file.name }), h('span', { class: 'o-em-chip-size', text: bytes(file.size) })), remove);
    });
    this.tray.replaceChildren(...nodes);
    this.tray.hidden = nodes.length === 0;
  }
}

