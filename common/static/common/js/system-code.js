/* System code view: the hidden "rules as code" editor (docs/design/SYSTEM-CODE-VIEW.md, docs/features/system-code-view.md).
   An enhancement only: without JS the toggle stays hidden. Loaded on the six rule pages. Toasts and modals are the shared ones (feedback.js).
   Sections: tokenizer, helpers, panel, editor, review, flow (open, load, review, apply, close), keys. */
import { toast, confirmModal, postUndo } from './feedback.js';

const $ = (selector, root = document) => root.querySelector(selector);
const toggle = $('[data-system-code]');

/* ---------- tokenizer: Python literals only (strings, numbers, True/False/None, comments, keys, punctuation) ---------- */

const KEYWORDS = new Set(['True', 'False', 'None']);
const esc = (text) => text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

function tokenize(line) {
  const out = [];
  const n = line.length;
  let i = 0;
  while (i < n) {
    const ch = line[i];
    if (ch === '#') { out.push(['sc-c', line.slice(i)]); break; }
    if (ch === '"' || ch === "'") {
      let j = i + 1;
      while (j < n && line[j] !== ch) { if (line[j] === '\\') j += 1; j += 1; }
      j = Math.min(j + 1, n);
      out.push([/^\s*:/.test(line.slice(j)) ? 'sc-k' : 'sc-s', line.slice(i, j)]);
      i = j;
    } else if (/[0-9]/.test(ch) || (ch === '-' && /[0-9]/.test(line[i + 1] || ''))) {
      let j = i + 1;
      while (j < n && /[0-9._eE]/.test(line[j])) j += 1;
      out.push(['sc-n', line.slice(i, j)]);
      i = j;
    } else if (/[A-Za-z_]/.test(ch)) {
      let j = i + 1;
      while (j < n && /\w/.test(line[j])) j += 1;
      const word = line.slice(i, j);
      out.push([KEYWORDS.has(word) ? 'sc-kw' : 'sc-nm', word]);
      i = j;
    } else if ('{}[]:,()'.includes(ch)) { out.push(['sc-p', ch]); i += 1; }
    else if (ch === '=') { out.push(['sc-nm', ch]); i += 1; }
    else {
      let j = i + 1;
      while (j < n && !/[#"'0-9A-Za-z_{}[\]:,()=-]/.test(line[j])) j += 1;
      out.push(['', line.slice(i, j)]);
      i = j;
    }
  }
  if (/#\s*read only\s*$/.test(line)) for (const t of out) if (t[0] === 'sc-s' || t[0] === 'sc-n' || t[0] === 'sc-kw') t[0] = 'sc-ro'; // the generated value is not code you change
  return out;
}

const span = (cls, text) => (cls ? `<span class="${cls}">${esc(text)}</span>` : esc(text));

/** One line as HTML. `errCol` (1-based) underlines the token that starts there. */
function lineHtml(line, errCol = 0) {
  const tokens = tokenize(line);
  if (!errCol) return tokens.map(([c, t]) => span(c, t)).join('');
  let html = '';
  let at = 0;
  let marked = false;
  for (const [cls, text] of tokens) {
    const end = at + text.length;
    if (!marked && end > errCol - 1 && text.trim() !== '') {
      const cut = Math.max(0, errCol - 1 - at);
      html += span(cls, text.slice(0, cut)) + `<span class="sc-ul">${span(cls, text.slice(cut))}</span>`;
      marked = true;
    } else html += span(cls, text);
    at = end;
  }
  return html;
}

/* ---------- the view ---------- */

function init(button) {
  const body = document.body;
  const IS_LIVE = (body.dataset.env || '').toLowerCase() === 'live';
  const ENV = (body.dataset.env || 'dev').toUpperCase();
  const base = button.dataset.systemCode.endsWith('/') ? button.dataset.systemCode : `${button.dataset.systemCode}/`;
  const section = base.split('/').filter(Boolean).pop();
  const icons = button.dataset.icons || '';
  const main = $('[data-system-main]');
  const head = $('.sys-head', main);
  const MAX = 128 * 1024;
  const WARN = 96 * 1024;
  const heading = ($('h1', head)?.textContent || 'Rules').trim();
  const nouns = { plans: 'plan', gold: 'rule' };
  const typing = (el) => el && (['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) || el.isContentEditable);
  const modalOpen = () => $('dialog[open]') || $('.fb-overlay');

  const S = {
    open: false, mode: 'read', original: '', version: '', errors: [], errIdx: 0, stale: null, applied: false, tabFocus: false,
    cur: 1, col: 1, preview: null, reviewed: '', busy: false, loaded: false, notice: '', sel: [0, 0],
  };
  let E = {};
  let frame = 0;
  let cw = 8;
  let copyTimer = 0;

  /* ----- small helpers ----- */

  const csrf = () => $('#system-csrf')?.content.querySelector('input')?.value || '';
  const bytes = (text) => new Blob([text]).size;
  const kb = (n) => (n / 1024).toFixed(1);
  const plural = (n, one, many) => (n === 1 ? one : many);
  const lineHeight = () => parseFloat(getComputedStyle(E.pre).lineHeight) || 20;
  const text = () => E.ta.value;
  const dirty = () => S.loaded && text() !== S.original;
  const announce = (message) => { E.alert.textContent = ''; setTimeout(() => { E.alert.textContent = message; }, 30); };
  const el = (tag, cls, label) => { const node = document.createElement(tag); if (cls) node.className = cls; if (label !== undefined) node.textContent = label; return node; };
  const actionButton = (label, cls, onClick) => { const b = el('button', `sys-btn sm ${cls || ''}`.trim(), label); b.type = 'button'; b.addEventListener('click', onClick); return b; };
  const icon = (name, size) => `<svg width="${size}" height="${size}" aria-hidden="true" focusable="false"><use href="${icons}#${name}"></use></svg>`;

  function caretAt(pos = E.ta.selectionStart) {
    const before = text().slice(0, pos);
    return { line: before.split('\n').length, col: pos - before.lastIndexOf('\n') };
  }

  function setCaret(line, col) {
    const lines = text().split('\n');
    let pos = 0;
    for (let i = 0; i < line - 1 && i < lines.length; i += 1) pos += lines[i].length + 1;
    pos += Math.max(0, Math.min(col - 1, (lines[line - 1] || '').length));
    E.ta.setSelectionRange(pos, pos);
  }

  /* ----- the panel ----- */

  // The viewer's own choice (localStorage) wins until the System > Settings default changes: the choice is stored with the
  // default it was made under ("light|dark"), so a new default in Settings applies again. Storage may be blocked: every touch is guarded.
  const THEME_KEY = 'spa99.system.codeTheme';
  const fallback = () => (button.dataset.themeDefault === 'light' ? 'light' : 'dark');
  const theme = () => {
    let saved = null;
    try { saved = localStorage.getItem(THEME_KEY); } catch { /* blocked */ }
    const [value, madeUnder] = (saved || '').split('|');
    if ((value === 'dark' || value === 'light') && madeUnder === fallback()) return value;
    return fallback();
  };
  const storeTheme = (value) => { try { localStorage.setItem(THEME_KEY, `${value}|${fallback()}`); } catch { /* blocked: the choice lasts until reload */ } };

  function buildPanel() {
    const panel = el('section', 'sys-panel sc-panel');
    panel.id = 'sc-panel';
    panel.setAttribute('aria-label', 'Rules as code');
    panel.innerHTML = `
<div class="sc-toolbar">
  <span class="sc-file" title="spa99 / rules / ${section}.py"><span class="sc-file-dir">spa99 / rules / </span><span>${section}.py</span></span>
  <span class="sys-badge sc-badge" data-sc-badge data-state="read">Read only</span>
  <span class="sc-spacer"></span>
  <button type="button" class="sc-theme" data-sc-theme aria-label="Dark theme" aria-pressed="true"></button>
  <span class="sc-actions" data-sc-actions></span>
  <button type="button" class="sc-close" data-sc-close aria-label="Close code view">${icon('x', 12)}</button>
</div>
<div class="sc-stale" role="alert" data-sc-stale hidden><p><b>Changed since you opened it.</b> Someone saved this page after you opened the code.</p><span class="sc-actions"><button type="button" class="sys-btn sm" data-sc-mine>Copy my version</button><button type="button" class="sys-btn sm" data-sc-latest>Load the latest</button></span></div>
<div class="sc-body" data-sc-body>
  <p class="sc-note" data-sc-note>Loading code</p>
  <div class="sc-failed" data-sc-failed hidden><p>Could not load the code.</p><button type="button" class="sys-btn sm" data-sc-retry>Try again</button></div>
  <div class="sc-scroll" data-sc-scroll>
    <div class="sc-sheet" data-sc-sheet>
      <div class="sc-gutter" aria-hidden="true" data-sc-gutter></div>
      <div class="sc-code">
        <pre class="sc-pre" aria-hidden="true" data-sc-pre></pre>
        <textarea class="sc-input" id="sc-input" data-sc-input readonly aria-readonly="true" aria-multiline="true" aria-label="${esc(heading)} rules as code" aria-describedby="sc-status sc-keyhint" spellcheck="false" autocapitalize="off" autocomplete="off" autocorrect="off" wrap="off"></textarea>
      </div>
    </div>
    <span class="sc-measure" data-sc-measure aria-hidden="true">0000000000</span>
  </div>
  <div class="sc-review" data-sc-review tabindex="-1" aria-label="Review of your edits" hidden></div>
</div>
<div class="sc-status" id="sc-status" data-sc-status>
  <span data-sc-left>Ln 1, Col 1</span>
  <button type="button" class="sys-btn sm sc-copy sc-copy-status" data-sc-copy hidden>Copy</button>
  <span data-sc-right></span>
</div>
<span class="sr" id="sc-keyhint">Tab inserts 4 spaces. Ctrl M to move focus with Tab. Ctrl Enter to review.</span>
<p class="sr" role="alert" data-sc-alert></p><p class="sr" aria-live="polite" data-sc-live></p>`;
    const q = (name) => $(`[data-sc-${name}]`, panel);
    E = {
      panel, badge: q('badge'), actions: q('actions'), stale: q('stale'), body: q('body'), note: q('note'), failed: q('failed'), scroll: q('scroll'), sheet: q('sheet'),
      gutter: q('gutter'), pre: q('pre'), ta: q('input'), measure: q('measure'), review: q('review'), status: q('status'), left: q('left'), right: q('right'),
      alert: q('alert'), live: q('live'), btn: {},
    };
    q('close').addEventListener('click', () => close());
    const themeBtn = q('theme');
    const paint = () => { const dark = panel.dataset.theme === 'dark'; themeBtn.setAttribute('aria-pressed', String(dark)); themeBtn.title = dark ? 'Dark theme: on' : 'Dark theme: off'; themeBtn.innerHTML = icon(dark ? 'moon' : 'sun', 16); };
    panel.dataset.theme = theme();
    paint();
    themeBtn.addEventListener('click', () => { const next = panel.dataset.theme === 'dark' ? 'light' : 'dark'; panel.dataset.theme = next; storeTheme(next); paint(); });
    q('retry').addEventListener('click', () => load());
    q('mine').addEventListener('click', () => copy(text(), { quiet: true }));
    q('latest').addEventListener('click', loadLatest);
    q('copy').addEventListener('click', () => copy(text()));
    E.ta.addEventListener('input', onInput);
    E.ta.addEventListener('keydown', onEditorKey);
    E.ta.addEventListener('scroll', () => { E.ta.scrollTop = 0; E.ta.scrollLeft = 0; });
    E.ta.addEventListener('focus', () => { markCurrent(); });
    E.ta.addEventListener('click', () => markCurrent());
    return panel;
  }

  /* ----- rendering the code ----- */

  function renderCode() {
    const lines = text().split('\n');
    const errs = new Map();
    for (const e of S.errors) if (!errs.has(e.line)) errs.set(e.line, e);
    E.sheet.toggleAttribute('data-wide', lines.length > 999);
    E.sheet.toggleAttribute('data-errs', S.errors.length > 0);
    let pre = '';
    let gut = '';
    lines.forEach((line, i) => {
      const n = i + 1;
      const err = errs.get(n);
      const cur = n === S.cur ? ' data-cur' : '';
      pre += `<span class="l"${cur}${err ? ' data-err' : ''}>${lineHtml(line, err ? err.col : 0)}</span>`;
      gut += `<div${cur}${err ? ` data-err title="${esc(err.message)}"` : ''}>${err ? icon('warning-octagon', 12) : ''}${n}</div>`;
    });
    E.pre.innerHTML = pre;
    E.gutter.innerHTML = gut;
    const bad = S.errors.length > 0;
    E.ta.toggleAttribute('aria-invalid', bad);
    if (bad) { E.ta.setAttribute('aria-invalid', 'true'); E.ta.setAttribute('aria-errormessage', 'sc-status'); } else E.ta.removeAttribute('aria-errormessage');
  }

  const schedule = () => { if (!frame) frame = requestAnimationFrame(() => { frame = 0; renderCode(); renderStatus(); }); };

  function markCurrent() {
    const { line, col } = caretAt();
    S.col = col;
    if (line !== S.cur) {
      for (const parent of [E.pre, E.gutter]) {
        parent.children[S.cur - 1]?.removeAttribute('data-cur');
        parent.children[line - 1]?.setAttribute('data-cur', '');
      }
      S.cur = line;
    }
    renderStatus();
  }

  function reveal(center = false, line = S.cur, col = S.col) {
    const sc = E.scroll;
    const lh = lineHeight();
    const top = (line - 1) * lh + 8;
    if (center) sc.scrollTop = Math.max(0, top - sc.clientHeight / 2 + lh / 2);
    else if (top < sc.scrollTop + 8) sc.scrollTop = Math.max(0, top - 8);
    else if (top + lh + 8 > sc.scrollTop + sc.clientHeight) sc.scrollTop = top + lh + 8 - sc.clientHeight;
    const gw = E.gutter.offsetWidth;
    const x = gw + 12 + (col - 1) * cw;
    if (x < sc.scrollLeft + gw + 24) sc.scrollLeft = Math.max(0, x - gw - 48);
    else if (x > sc.scrollLeft + sc.clientWidth - 40) sc.scrollLeft = x - sc.clientWidth + 80;
  }

  /* ----- status strip ----- */

  function renderStatus() {
    if (!E.left) return;
    const size = bytes(text());
    const lines = text().split('\n').length;
    const over = size > MAX;
    E.right.innerHTML = '';
    E.right.append(`${lines} ${plural(lines, 'line', 'lines')} · `);
    const sz = el('span', '', `${kb(size)} / 128 KB`);
    if (over) sz.dataset.bad = ''; else if (size > WARN) sz.dataset.warn = '';
    E.right.append(sz);
    const showErrors = S.mode === 'edit' && S.errors.length > 0;
    E.status.toggleAttribute('data-err', showErrors || !!S.notice);
    E.left.replaceChildren();
    if (showErrors) {
      const e = S.errors[S.errIdx] || S.errors[0];
      if (S.errors.length > 1) E.left.append(`${S.errors.length} problems · `);
      const msg = el('button', 'sc-msg', `Line ${e.line}, column ${e.col}: ${e.message}`);
      msg.type = 'button';
      msg.addEventListener('click', () => gotoError(S.errIdx));
      E.left.append(msg);
      if (S.errors.length > 1) {
        const prev = actionButton('Previous', 'link', () => gotoError(S.errIdx - 1));
        const next = actionButton('Next', 'link', () => gotoError(S.errIdx + 1));
        prev.title = 'Shift F8'; next.title = 'F8';
        E.left.append(' ', prev, next);
      }
    } else if (S.notice) E.left.textContent = S.notice;
    else if (S.mode === 'edit' && over) E.left.textContent = 'Over 128 KB. Shorten it to review.';
    else if (S.mode === 'review') E.left.textContent = 'Nothing is saved until you apply.';
    else E.left.textContent = `Ln ${S.cur}, Col ${S.col}${S.tabFocus ? ' · Tab moves focus' : ''}`;
    syncButtons();
  }

  /* ----- modes and toolbar ----- */

  function setMode(mode) {
    S.mode = mode;
    E.panel.dataset.mode = mode;
    E.badge.dataset.state = mode;
    E.badge.textContent = { read: 'Read only', edit: 'Editing', review: 'Review' }[mode];
    E.ta.readOnly = mode !== 'edit';
    E.ta.setAttribute('aria-readonly', String(mode !== 'edit'));
    E.scroll.hidden = mode === 'review';
    E.review.hidden = mode !== 'review';
    E.actions.replaceChildren();
    E.btn = {};
    const copyBtn = $('[data-sc-copy]', E.panel);
    if (copyBtn) copyBtn.hidden = mode !== 'read';
    if (mode === 'read') {
      E.btn.copy = actionButton('Copy', 'sc-copy', () => copy(text()));
      E.btn.copy.dataset.scCopy = '';
      E.btn.edit = actionButton('Edit', '', startEdit);
      E.actions.append(E.btn.copy, E.btn.edit);
    } else if (mode === 'edit') {
      E.btn.discard = actionButton('Discard', '', discard);
      E.btn.review = actionButton('Review', 'primary', review);
      E.actions.append(E.btn.discard, E.btn.review);
    } else {
      E.btn.back = actionButton('Back to code', '', backToCode);
      E.actions.append(E.btn.back);
      if (S.preview && S.preview.count > 0) {
        const n = S.preview.count;
        E.btn.apply = actionButton(`Apply ${n} ${plural(n, 'change', 'changes')}`, IS_LIVE && S.preview.risky ? 'danger' : 'primary', apply);
        E.actions.append(E.btn.apply);
      }
    }
    renderStatus();
  }

  function syncButtons() {
    if (E.btn.discard) E.btn.discard.hidden = !dirty();
    if (E.btn.review && !S.busy) {
      E.btn.review.disabled = !dirty() || bytes(text()) > MAX || !!S.stale;
      E.btn.review.title = S.stale ? 'Load the latest first' : '';
    }
    if (E.btn.apply && !S.busy) E.btn.apply.disabled = !!S.stale;
  }

  /* ----- copy ----- */

  async function copy(value, { quiet = false } = {}) {
    let done = false;
    try { await navigator.clipboard.writeText(value); done = true; } catch { /* denied: select the text below */ }
    if (!done) {
      if (E.scroll.hidden) backToCode();
      E.ta.focus();
      E.ta.select();
      try { done = document.execCommand('copy'); } catch { done = false; }
      if (!done) { toast('Could not copy. The code is selected, so copy it yourself.', { kind: 'info' }); return; }
    }
    if (quiet) { toast('Your version is copied.', { kind: 'success' }); return; }
    const buttons = [...E.panel.querySelectorAll('[data-sc-copy]')];
    buttons.forEach((b) => { b.dataset.was = b.dataset.was || b.textContent; b.textContent = 'Copied'; });
    E.live.textContent = 'Copied';
    clearTimeout(copyTimer);
    copyTimer = setTimeout(() => { buttons.forEach((b) => { b.textContent = b.dataset.was || 'Copy'; }); E.live.textContent = ''; }, 1500);
  }

  /* ----- editor behaviour ----- */

  function onInput() {
    if (S.errors.length) {
      const lines = text().split('\n');
      if (lines.length !== S.errLineCount) S.errors = []; // lines moved: the markers no longer point at the right place
      else S.errors = S.errors.filter((e) => lines[e.line - 1] === e.text); // a marker clears when its line is edited
      S.errIdx = Math.min(S.errIdx, Math.max(0, S.errors.length - 1));
    }
    if (S.stale === null) S.notice = '';
    const { line, col } = caretAt();
    S.cur = line; S.col = col;
    schedule();
    reveal();
  }

  function insert(value, start = E.ta.selectionStart, end = E.ta.selectionEnd) {
    E.ta.focus();
    E.ta.setSelectionRange(start, end);
    if (!document.execCommand || !document.execCommand('insertText', false, value)) { // keeps the browser's undo where it can
      E.ta.setRangeText(value, start, end, 'end');
      E.ta.dispatchEvent(new Event('input', { bubbles: true }));
    }
  }

  function blockOf(v, s, e) {
    const from = v.lastIndexOf('\n', s - 1) + 1;
    const to = e > s && v[e - 1] === '\n' ? e - 1 : e;
    const next = v.indexOf('\n', to);
    return [from, next === -1 ? v.length : next];
  }

  function indent() {
    const v = text(); const s = E.ta.selectionStart; const e = E.ta.selectionEnd;
    if (s === e) { insert('    '); return; }
    const [from, to] = blockOf(v, s, e);
    const rows = v.slice(from, to).split('\n');
    insert(rows.map((r) => `    ${r}`).join('\n'), from, to);
    E.ta.setSelectionRange(s + 4, e + 4 * rows.length);
  }

  function outdent() {
    const v = text(); const s = E.ta.selectionStart; const e = E.ta.selectionEnd;
    const [from, to] = blockOf(v, s, e);
    let first = 0; let total = 0;
    const rows = v.slice(from, to).split('\n').map((r, i) => {
      const cut = r.startsWith('\t') ? 1 : Math.min(4, (/^ */.exec(r) || [''])[0].length);
      if (i === 0) first = cut;
      total += cut;
      return r.slice(cut);
    });
    if (!total) return;
    insert(rows.join('\n'), from, to);
    E.ta.setSelectionRange(Math.max(from, s - Math.min(first, s - from)), Math.max(from, e - total));
  }

  function newline() {
    const v = text(); const s = E.ta.selectionStart; const e = E.ta.selectionEnd;
    const before = v.slice(v.lastIndexOf('\n', s - 1) + 1, s);
    const pad = /^[ \t]*/.exec(before)[0];
    const opens = '{[('.includes(before.trimEnd().slice(-1)) && before.trim() !== '';
    const closes = { '{': '}', '[': ']', '(': ')' }[before.trimEnd().slice(-1)];
    if (opens && v[e] === closes) { insert(`\n${pad}    \n${pad}`, s, e); E.ta.setSelectionRange(s + 1 + pad.length + 4, s + 1 + pad.length + 4); }
    else insert(`\n${pad}${opens ? '    ' : ''}`, s, e);
  }

  function onEditorKey(event) {
    if (S.mode !== 'edit' || event.isComposing) return;
    if (event.key === 'Tab' && !event.ctrlKey && !event.metaKey && !event.altKey) {
      if (S.tabFocus) return;
      event.preventDefault();
      if (event.shiftKey) outdent(); else indent();
    } else if (event.key === 'Enter' && !event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey) {
      event.preventDefault();
      newline();
    } else if (event.ctrlKey && !event.metaKey && !event.altKey && event.key.toLowerCase() === 'm') {
      event.preventDefault();
      S.tabFocus = !S.tabFocus;
      renderStatus();
      E.live.textContent = S.tabFocus ? 'Tab moves focus' : 'Tab inserts spaces';
    }
  }

  /* ----- errors ----- */

  function gotoError(index) {
    if (!S.errors.length) return;
    S.errIdx = (index + S.errors.length) % S.errors.length;
    const e = S.errors[S.errIdx];
    E.ta.focus({ preventScroll: true });
    setCaret(e.line, e.col);
    S.cur = e.line; S.col = e.col;
    renderCode();
    renderStatus();
    reveal(true, e.line, e.col);
  }

  function showErrors(list, { announceIt = true } = {}) {
    const lines = text().split('\n');
    S.errors = list.map((e) => ({ line: Math.max(1, Math.min(e.line || 1, lines.length)), col: Math.max(1, e.col || 1), message: e.message || 'Check this line.', text: lines[Math.max(1, Math.min(e.line || 1, lines.length)) - 1] }));
    S.errLineCount = lines.length;
    S.errIdx = 0;
    if (S.mode !== 'edit') setMode('edit');
    gotoError(0);
    if (announceIt) {
      const e = S.errors[0];
      const n = S.errors.length;
      announce(`${n} ${plural(n, 'problem', 'problems')}. Nothing was saved. First: line ${e.line}, column ${e.col}, ${e.message}`);
    }
  }

  /* ----- network ----- */

  async function request(path, init) {
    let response;
    try { response = await fetch(path, { credentials: 'same-origin', ...init, headers: { Accept: 'application/json', 'X-Requested-With': 'fetch', ...(init?.headers || {}) } }); }
    catch { return { net: true }; }
    let data = null;
    try { data = await response.json(); } catch { /* not JSON: a lock or an error page */ }
    return { status: response.status, data, redirected: response.redirected };
  }

  const post = (kind, payload) => request(`${base}${kind}/`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() }, body: JSON.stringify(payload) });

  /** Everything that is not a success. Returns true when it handled the answer. */
  function failed(r) {
    if (r.net) { toast('Could not reach System. Your code is still here.', { kind: 'error' }); return true; }
    if (!r.data) { toast('System could not answer, or it has locked. Your code is still here. Unlock System and try again.', { kind: 'error' }); return true; }
    const d = r.data;
    if (r.status === 409 && typeof d.code === 'string') {
      S.stale = { code: d.code, version: d.version };
      if (S.mode === 'review') backToCode(false);
      E.stale.hidden = false;
      S.notice = '';
      renderStatus();
      return true;
    }
    if (r.status === 413) { S.notice = d.message || 'Over 128 KB. Shorten it to review.'; if (S.mode === 'review') backToCode(false); renderStatus(); return true; }
    if (r.status === 429) { S.notice = d.message || 'Too many requests. Please wait a moment.'; renderStatus(); setTimeout(() => { S.notice = ''; renderStatus(); }, 8000); return true; }
    if (r.status === 400 && Array.isArray(d.errors) && d.errors.length) { showErrors(d.errors); return true; }
    toast(d.message || 'That did not work. Nothing was saved.', { kind: 'error' });
    return true;
  }

  /* ----- load ----- */

  async function load({ keepScroll = false } = {}) {
    E.note.hidden = false; E.failed.hidden = true;
    if (!keepScroll) E.scroll.hidden = false;
    S.loaded = false;
    const r = await request(base, {});
    if (r.redirected && !r.data) { location.href = `${body.dataset.systemUnlockUrl}?next=${encodeURIComponent(location.pathname + location.search)}`; return; }
    if (r.net || r.status !== 200 || !r.data || typeof r.data.code !== 'string') {
      E.note.hidden = true; E.failed.hidden = false; E.scroll.hidden = true;
      return;
    }
    E.note.hidden = true; E.scroll.hidden = false;
    S.original = r.data.code; S.version = r.data.version;
    S.loaded = true; S.errors = []; S.stale = null; S.notice = '';
    E.stale.hidden = true;
    E.ta.value = r.data.code;
    if (r.data.title) E.ta.setAttribute('aria-label', `${r.data.title} rules as code`);
    S.cur = 1; S.col = 1;
    cw = E.measure.getBoundingClientRect().width / 10 || cw;
    setMode('read');
    renderCode();
    E.ta.focus({ preventScroll: true });
    E.ta.setSelectionRange(0, 0);
  }

  async function loadLatest() {
    if (!S.stale) return;
    if (dirty()) {
      const ok = await confirmModal({ title: 'Load the latest code?', body: 'Your edits will be lost.', confirmLabel: 'Load the latest', cancelLabel: 'Keep editing', tone: 'danger' });
      if (!ok) return;
    }
    const fresh = S.stale;
    S.stale = null;
    E.stale.hidden = true;
    S.original = fresh.code; S.version = fresh.version;
    E.ta.value = fresh.code;
    S.errors = []; S.notice = '';
    setMode('read');
    renderCode();
    E.ta.focus({ preventScroll: true });
  }

  /* ----- edit, review, apply ----- */

  function startEdit() {
    setMode('edit');
    E.ta.focus({ preventScroll: true });
    E.ta.setSelectionRange(0, 0);
    S.cur = 1; S.col = 1;
    E.scroll.scrollTop = 0; E.scroll.scrollLeft = 0;
    renderCode();
    renderStatus();
  }

  async function discard() {
    if (dirty()) {
      const ok = await confirmModal({ title: 'Discard your edits?', body: 'Your edits will be lost.', confirmLabel: 'Discard', cancelLabel: 'Keep editing', tone: 'danger' });
      if (!ok) return;
    }
    E.ta.value = S.original;
    S.errors = []; S.notice = '';
    setMode('read');
    renderCode();
    E.ta.focus({ preventScroll: true });
  }

  function busy(on, button, label, idle) {
    S.busy = on;
    if (button) { button.disabled = on; button.textContent = on ? label : idle; }
    if (E.btn.back) E.btn.back.disabled = on;
    if (!on) { clearTimeout(S.dim); E.body.removeAttribute('data-busy'); syncButtons(); } else S.dim = setTimeout(() => { if (S.busy) E.body.setAttribute('data-busy', ''); }, 150);
  }

  async function review() {
    if (S.busy || !E.btn.review || E.btn.review.disabled || !dirty()) return;
    S.sel = [E.ta.selectionStart, E.ta.selectionEnd];
    S.notice = '';
    const sent = text();
    busy(true, E.btn.review, 'Checking', 'Review');
    const r = await post('preview', { code: sent, version: S.version });
    busy(false, E.btn.review, 'Checking', 'Review');
    if (r.status === 200 && r.data?.ok) {
      S.preview = r.data; S.reviewed = sent;
      buildReview(r.data);
      setMode('review');
      E.review.focus({ preventScroll: true });
      E.review.scrollTop = 0;
      return;
    }
    failed(r);
  }

  function backToCode(refocus = true) {
    S.preview = null;
    setMode('edit');
    if (refocus) { E.ta.focus({ preventScroll: true }); E.ta.setSelectionRange(S.sel[0], S.sel[1]); markCurrent(); }
  }

  function chips(old, now, label) {
    const box = el('span', 'sc-diff-chip');
    const del = el('span', 'sc-chip del');
    const was = el('span', 'sr', 'was ');
    del.append(was, String(old));
    const arrow = el('span', 'sc-arrow', '→');
    arrow.setAttribute('aria-hidden', 'true');
    const add = el('span', 'sc-chip add');
    add.append(el('span', 'sr', ', now '), String(now));
    box.append(del, arrow, add);
    if (label) box.title = label;
    return box;
  }

  function row(path, field, content, risky) {
    const li = el('li');
    const p = el('span', 'sc-path');
    p.append(path);
    if (field) { p.append(' · ', Object.assign(el('b'), { textContent: field })); }
    const box = el('span', 'sc-chips');
    box.append(...content);
    li.append(p, box);
    if (risky) li.append(el('span', 'sys-badge sc-badge-warn', 'Confirm'));
    return li;
  }

  function changeRows(data, onlyRisky = false) {
    const list = el('ul', 'sc-changes');
    for (const c of data.changes || []) if (!onlyRisky || c.risky) list.append(row(c.row_label, c.field, [chips(c.old_display, c.new_display)], c.risky));
    for (const c of data.creates || []) {
      if (onlyRisky) continue;
      const added = el('span', 'sc-chip add', 'added');
      list.append(row(c.row_label, c.noun ? `new ${c.noun}` : 'new', [added, ...(c.fields || []).map((f) => el('span', 'sc-chip plain', `${f.field}: ${f.display}`))], false));
    }
    for (const d of data.deletes || []) list.append(row(d.row_label, d.noun || 'removed', [el('span', 'sc-chip del', 'removed')], true));
    return list;
  }

  function codeRow(type, oldNo, newNo, code) {
    const r = el('div', 'sc-dr');
    r.dataset.type = type;
    const sign = { add: '+', del: '−', ctx: '', hunk: '' }[type];
    const hidden = { add: `added line ${newNo}`, del: `removed line ${oldNo}` }[type];
    if (type === 'hunk') { r.innerHTML = `<span class="t">${esc(code)}</span>`; return r; }
    r.innerHTML = `<span class="n">${oldNo ?? ''}</span><span class="n">${newNo ?? ''}</span><span class="g" aria-hidden="true">${sign}</span><span class="t">${hidden ? `<span class="sr">${hidden}: </span>` : ''}${lineHtml(code)}</span>`;
    return r;
  }

  function buildReview(data) {
    const box = E.review;
    box.replaceChildren();
    const n = data.count ?? 0;
    const rows = new Set([...(data.changes || []), ...(data.creates || []), ...(data.deletes || [])].map((c) => c.row_label));
    if (!n && !(data.diff_lines || []).length) {
      box.append(el('p', 'sc-none', 'Nothing to change. The code matches what is saved.'));
      return;
    }
    const noun = nouns[section] || 'row';
    const h = el('h2', 'sc-rhead', `${n} ${plural(n, 'change', 'changes')}${nouns[section] || ['hours', 'journey'].includes(section) ? ` in ${rows.size} ${plural(rows.size, noun, `${noun}s`)}` : ''}`);
    h.setAttribute('aria-live', 'polite');
    box.append(h, changeRows(data));
    box.append(Object.assign(el('hr', 'sc-rule'), {}));
    const diff = el('div', 'sc-diff');
    diff.setAttribute('role', 'group');
    diff.setAttribute('aria-label', 'Code changes');
    const lines = data.diff_lines || [];
    for (let i = 0; i < lines.length;) {
      if (lines[i].type !== 'ctx') { const l = lines[i]; diff.append(codeRow(l.type, l.old, l.new, l.text)); i += 1; continue; }
      let j = i;
      while (j < lines.length && lines[j].type === 'ctx') j += 1;
      const run = lines.slice(i, j).map((l) => codeRow('ctx', l.old, l.new, l.text));
      if (run.length > 6) {
        const fold = el('button', 'sc-fold', `Show ${run.length} unchanged lines`);
        fold.type = 'button';
        fold.addEventListener('click', () => { fold.replaceWith(...run); });
        diff.append(fold);
      } else diff.append(...run);
      i = j;
    }
    box.append(diff);
    if (data.diff_truncated) box.append(el('p', 'sc-trunc', 'Diff truncated.'));
  }

  async function apply(confirmed = false) {
    const p = S.preview;
    if (S.busy || !p || S.stale) return;
    if (p.risky && confirmed !== true) {
      const n = p.count;
      const details = changeRows(p, true);
      details.classList.add('sc-compact');
      const ok = await confirmModal({ title: `Apply risky changes on ${ENV}?`, body: 'These go live as soon as you apply.', details, confirmLabel: `Apply ${n} ${plural(n, 'change', 'changes')}`, tone: IS_LIVE ? 'danger' : 'neutral' });
      if (!ok) return;
    }
    const idle = E.btn.apply.textContent;
    busy(true, E.btn.apply, 'Applying', idle);
    const r = await post('apply', { code: S.reviewed, version: S.version, confirm_risky: !!p.risky });
    busy(false, E.btn.apply, 'Applying', idle);
    if (r.status === 200 && r.data?.ok) { applied(r.data); return; }
    if (r.status === 400 && r.data?.needs_confirm && confirmed !== true) { S.preview = { ...p, ...r.data, count: p.count, risky: true }; apply(false); return; }
    failed(r);
  }

  function applied(data) {
    S.preview = null; S.errors = []; S.notice = ''; S.stale = null;
    E.stale.hidden = true;
    if (typeof data.code === 'string') { S.original = data.code; E.ta.value = data.code; } else S.original = S.reviewed;
    if (data.version) S.version = data.version;
    if (data.changed) {
      S.applied = true;
      toast(data.message || 'Saved.', { action: data.undo_url ? { label: data.changed > 1 ? 'Undo all' : 'Undo', onClick: () => postUndo(data.undo_url) } : undefined });
    } else toast(data.message || 'Nothing to change.', { kind: 'info' });
    setMode('read');
    renderCode();
    E.ta.focus({ preventScroll: true });
  }

  /* ----- open and close ----- */

  function draftCount() {
    const bar = $('[data-system-savebar]');
    if (!bar || bar.hidden) return 0;
    return Number(($('[data-system-count]', bar)?.textContent.match(/\d+/) || [1])[0]);
  }

  function setUrl(on) {
    const url = new URL(location.href);
    if (on) url.searchParams.set('view', 'code'); else url.searchParams.delete('view');
    history.replaceState(history.state, '', url);
  }

  async function open({ initial = false } = {}) {
    if (S.open) return;
    if (!initial) {
      const n = draftCount();
      if (n) {
        const ok = await confirmModal({ title: `Open code without your ${n} unsaved ${plural(n, 'change', 'changes')}?`, body: 'The code shows what is saved. Your drafts stay on the page.', confirmLabel: 'Open code', cancelLabel: 'Cancel', opener: button });
        if (!ok) return;
      }
    }
    S.open = true; S.loaded = false;
    button.setAttribute('aria-pressed', 'true');
    main.setAttribute('data-sc-open', '');
    const panel = buildPanel();
    head.after(panel);
    setUrl(true);
    setMode('read');
    renderCode();
    load();
  }

  async function close() {
    if (!S.open) return;
    if (dirty()) {
      const ok = await confirmModal({ title: 'Close without applying?', body: 'Your edits will be lost.', confirmLabel: 'Close', cancelLabel: 'Keep editing', tone: 'danger' });
      if (!ok) return;
    }
    if (S.applied) { // the page body shows the old values: reload it without the code view
      document.dispatchEvent(new CustomEvent('spa99:leaving'));
      const url = new URL(location.href);
      url.searchParams.delete('view');
      location.href = url.toString();
      return;
    }
    S.open = false;
    E.panel.remove();
    E = {};
    main.removeAttribute('data-sc-open');
    button.setAttribute('aria-pressed', 'false');
    setUrl(false);
    button.focus();
  }

  /* ----- keys ----- */

  button.addEventListener('click', () => (S.open ? close() : open()));

  // Cmd/Ctrl+S would save the page drafts hidden behind the code: not while the code is open
  window.addEventListener('keydown', (event) => {
    if (S.open && (event.metaKey || event.ctrlKey) && !event.altKey && event.key.toLowerCase() === 's') { event.preventDefault(); event.stopPropagation(); }
  }, true);

  document.addEventListener('keydown', (event) => {
    if (event.isComposing || event.defaultPrevented) return;
    const plain = !event.metaKey && !event.ctrlKey && !event.altKey;
    if (event.key === '`' && plain && !typing(event.target) && !modalOpen()) { event.preventDefault(); if (S.open) close(); else open(); return; }
    if (!S.open || modalOpen() || !E.panel) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      if (S.mode === 'review') backToCode(); else close();
    } else if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
      event.preventDefault();
      if (S.mode === 'edit') review();
    } else if (event.key === 'F8' && S.mode === 'edit' && S.errors.length) {
      event.preventDefault();
      gotoError(S.errIdx + (event.shiftKey ? -1 : 1));
    }
  });

  document.addEventListener('selectionchange', () => {
    if (S.open && E.ta && document.activeElement === E.ta && S.loaded) { markCurrent(); if (S.mode === 'edit') reveal(); }
  });
  window.addEventListener('beforeunload', (event) => { if (S.open && dirty()) { event.preventDefault(); event.returnValue = ''; } });
  window.matchMedia('(max-width: 48em)').addEventListener('change', () => { if (S.open && E.measure) { cw = E.measure.getBoundingClientRect().width / 10 || cw; } });

  if (new URLSearchParams(location.search).get('view') === 'code') open({ initial: true });
}

if (toggle) init(toggle);
