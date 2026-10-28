/* System > Emails > the parts editor of a group send (docs/design/EMAIL-BUILDER-UI.md, docs/features/email-builder.md).
   The email is a list of parts (heading, paragraph, button, image, divider, small print). This module draws the list, keeps it in a hidden
   `blocks` input as JSON on every change, uploads pictures, maps the server's per-part errors onto the cards, and looks after focus,
   announcements and motion. system-emails.js owns the page around it (preview, save bar) and passes in what it shares.
   Sections: helpers, field specs, the builder (state, cards, errors, menu, images, start). */

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const SVG_NS = 'http://www.w3.org/2000/svg';

/** Tiny element builder: attrs (class, text, others as attributes), then children. */
function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === false || value == null) continue;
    if (key === 'class') el.className = value;
    else if (key === 'text') el.textContent = value;
    else el.setAttribute(key, value === true ? '' : value);
  }
  kids.flat().forEach((kid) => { if (kid != null && kid !== false) el.append(kid); });
  return el;
}

function icon(sprite, name) {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('class', 'se-icon');
  svg.setAttribute('width', '14');
  svg.setAttribute('height', '14');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  const use = document.createElementNS(SVG_NS, 'use');
  use.setAttribute('href', `${sprite}#${name}`);
  svg.append(use);
  return svg;
}

const megabytes = (bytes) => `${Math.round((bytes / 1048576) * 10) / 10} MB`;
const sizeText = (bytes) => (bytes >= 1048576 ? megabytes(bytes) : `${Math.max(1, Math.round(bytes / 1024))} KB`);
const IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif'];
const LIST_WORDS = { 'Add at least one part that is not a divider.': 'Add something besides a divider. A heading, paragraph, button, image or small print.' };

/* ---------- field specs: what each part shows (the limits come from the server, as block_types) ---------- */

const SPECS = {
  heading: { label: 'Heading', fields: [{ name: 'text', label: 'Text', control: 'line', place: true }] },
  paragraph: { label: 'Paragraph', fields: [{ name: 'text', label: 'Text', control: 'area', rows: 5, place: true, hint: 'A blank line starts a new paragraph.' }] },
  button: {
    label: 'Button',
    fields: [
      { name: 'label', label: 'Label', control: 'line', hint: 'Short, like Book your visit.' },
      { name: 'url', label: 'Link', control: 'url', hint: 'A full address (https://...) or a page on the site, like /memberships/.' },
    ],
  },
  image: {
    label: 'Image',
    fields: [
      { name: 'image', label: 'Image', control: 'image' },
      { name: 'alt', label: 'Describe the image', control: 'line', hint: "Read aloud to people who can't see it, and shown when images are off." },
      { name: 'url', label: 'Link', control: 'url', optional: true, hint: 'Where a tap on the image goes.' },
    ],
  },
  divider: { label: 'Divider', fields: [], note: 'A thin line between sections.' },
  small_print: { label: 'Small print', fields: [{ name: 'text', label: 'Text', control: 'area', rows: 3, place: true, hint: 'Shown small and grey, for terms or details.' }] },
};

/** deps: { known (Set of placeholder names), drawTokens, insertAt, csrf, onChange(kind) } where kind is 'structure' | 'field' | 'image'. */
export function initBuilder(form, deps) {
  const root = $('[data-se-builder]', form);
  const types = JSON.parse($('#se-block-types').textContent);
  const seed = JSON.parse($('#se-blocks').textContent) || [];
  const seedErrors = JSON.parse($('#se-block-errors').textContent) || {};
  const maxParts = Number(form.dataset.maxParts) || 30;
  const sprite = form.dataset.icons;
  const uploadUrl = form.dataset.imageUrl;
  const maxBytes = Number(form.dataset.imageMax) || 2097152;
  const viewBase = form.dataset.imageBase || '';
  const list = $('[data-se-list]', root);
  const empty = $('[data-se-empty]', root);
  const full = $('[data-se-full]', root);
  const countLabel = $('[data-se-parts-count]', root);
  const summary = $('[data-se-summary]', root);
  const listError = $('[data-se-list-error]', root);
  const addButton = $('[data-se-add]', root);
  const addWrap = $('[data-se-add-wrap]', root);
  const menu = $('[data-se-menu]', root);
  const hidden = $('[data-se-blocks]', root);
  const liveRegion = $('[data-se-parts-live]', root);
  const palette = $('[data-se-palette]', root);
  const subject = $('[data-se-subject]', form);
  const undoBox = $('[data-se-undo]', form);

  let parts = [];
  let counter = 0;
  let attempted = false; // after a save attempt every error shows, not only those of fields already visited
  let listErrors = [];
  let undo = null; // { part, index, label }
  let menuState = null; // { opener, index }
  let target = subject; // the field the Placeholders insert into
  const field = (kind, name) => types[kind]?.[name] || {};

  /* ----- announcements ----- */

  const say = (message) => { liveRegion.textContent = ''; setTimeout(() => { liveRegion.textContent = message; }, 30); };

  /* ----- state ----- */

  const typeLabel = (part) => SPECS[part.type].label;
  const nameOf = (part, index = parts.indexOf(part)) => `${typeLabel(part)} ${index + 1}`;

  function makePart(raw) {
    const kind = SPECS[raw?.type] ? raw.type : null;
    if (!kind) return null;
    const data = {};
    SPECS[kind].fields.forEach((f) => { data[f.name] = typeof raw[f.name] === 'string' ? raw[f.name] : ''; });
    return { key: ++counter, type: kind, data, errors: {}, touched: new Set(), editing: '', up: null, imgError: null, el: null, refs: {} };
  }

  function serialize() {
    return parts.map((part) => {
      const out = { type: part.type };
      Object.keys(types[part.type] || {}).forEach((name) => { out[name] = part.data[name] || ''; });
      return out;
    });
  }

  function sync() { hidden.value = JSON.stringify(serialize()); }

  function changed(kind) {
    sync();
    deps.onChange?.(kind);
  }

  /* ----- one card ----- */

  function counterText(part, f) {
    const max = field(part.type, f.name).max;
    const length = (part.data[f.name] || '').length;
    return { max, length, show: !!max && length >= max * 0.8, over: !!max && length > max };
  }

  function paintCounter(part, f) {
    const node = part.refs[`count-${f.name}`];
    if (!node) return;
    const c = counterText(part, f);
    node.hidden = !c.show;
    node.textContent = `${c.length} / ${c.max}`;
    node.classList.toggle('over', c.over);
  }

  function buildField(part, f) {
    const id = `se-p${part.key}-${f.name}`;
    const row = h('div', { class: 'sys-row se-field', 'data-field': f.name });
    if (f.control === 'image') {
      const host = h('div', { class: 'se-image', 'data-se-image': true });
      part.refs.image = host;
      row.append(h('span', { class: 'sys-label sr', text: 'Image' }), host);
      return row;
    }
    const label = h('label', { for: id }, f.label, f.optional ? h('small', { text: 'Optional' }) : null);
    const wrap = h('div');
    let control;
    if (f.control === 'area') {
      const pre = h('pre', { class: 'se-pre', 'aria-hidden': 'true' });
      control = h('textarea', { id, rows: f.rows, spellcheck: 'true' });
      control.value = part.data[f.name];
      const box = h('div', { class: 'se-editor', style: `--rows: ${f.rows}` }, pre, control);
      wrap.append(box);
      part.refs[`pre-${f.name}`] = pre;
      pre.innerHTML = deps.drawTokens(control.value, deps.known);
    } else {
      control = h('input', { id, type: 'text', autocomplete: 'off', ...(f.control === 'url' ? { inputmode: 'url', spellcheck: 'false', autocapitalize: 'none' } : {}) });
      control.value = part.data[f.name];
      wrap.append(control);
    }
    if (f.place) control.dataset.place = '';
    const errId = `${id}-err`;
    const hintId = `${id}-hint`;
    const errorNode = h('p', { class: 'sys-error', id: errId, hidden: true });
    const hint = f.hint ? h('span', { class: 'sys-muted se-help', id: hintId, text: f.hint }) : null;
    const count = field(part.type, f.name).max ? h('span', { class: 'se-count-n sys-muted mono', hidden: true }) : null;
    control.setAttribute('aria-describedby', [hint && hintId, errId].filter(Boolean).join(' '));
    wrap.append(errorNode, h('div', { class: 'se-meta-row' }, hint, count));
    part.refs[`ctl-${f.name}`] = control;
    part.refs[`err-${f.name}`] = errorNode;
    if (count) part.refs[`count-${f.name}`] = count;

    control.addEventListener('input', () => {
      part.data[f.name] = control.value;
      part.editing = f.name;
      part.errors[f.name] = []; // an error clears on that field's next input
      paintErrors();
      if (f.control === 'area') part.refs[`pre-${f.name}`].innerHTML = deps.drawTokens(control.value, deps.known);
      paintCounter(part, f);
      if (part.type === 'image' && f.name === 'alt') { const img = $('img', part.refs.image); if (img) img.alt = control.value; }
      changed('field');
    });
    control.addEventListener('blur', () => { part.editing = ''; part.touched.add(f.name); paintErrors(); });
    row.append(label, wrap);
    return row;
  }

  function buildPart(part) {
    const spec = SPECS[part.type];
    const li = h('li', { class: 'se-part', tabindex: '-1', 'aria-labelledby': `se-p${part.key}-h`, 'data-key': part.key });
    const num = h('span', { class: 'se-n mono' });
    const name = h('span', { class: 'se-type', text: spec.label });
    const button = (act, glyph) => h('button', { type: 'button', class: 'sys-btn sm se-ic', 'data-act': act }, icon(sprite, glyph));
    const buttons = {
      add: button('add', 'plus'), up: button('up', 'arrow-up'), down: button('down', 'arrow-down'), remove: button('remove', 'trash'),
    };
    buttons.add.setAttribute('aria-haspopup', 'menu');
    buttons.add.setAttribute('aria-expanded', 'false');
    const head = h('div', { class: 'se-part-head' }, h('span', { class: 'se-part-title', id: `se-p${part.key}-h` }, num, name), h('span', { class: 'se-part-tools' }, buttons.add, buttons.up, buttons.down, buttons.remove));
    const cardError = h('p', { class: 'sys-error se-card-error', hidden: true });
    li.append(head, cardError);
    part.refs = { num, name, buttons, cardError };
    part.el = li;
    spec.fields.forEach((f) => li.append(buildField(part, f)));
    if (spec.note) li.append(h('p', { class: 'sys-muted se-note', text: spec.note }));
    if (part.type === 'image') paintImage(part);
    return li;
  }

  function paintCounters(part) { SPECS[part.type].fields.forEach((f) => { if (f.control !== 'image') paintCounter(part, f); }); }

  /* ----- the list chrome: numbers, labels, disabled states, counts ----- */

  function chrome() {
    const total = parts.length;
    const isFull = total >= maxParts;
    parts.forEach((part, i) => {
      const where = nameOf(part, i);
      part.refs.num.textContent = String(i + 1);
      const b = part.refs.buttons;
      b.add.setAttribute('aria-label', `Add a part below ${where}`);
      b.up.setAttribute('aria-label', `Move ${where} up`);
      b.down.setAttribute('aria-label', `Move ${where} down`);
      b.remove.setAttribute('aria-label', `Remove ${where}`);
      b.up.disabled = i === 0;
      b.down.disabled = i === total - 1;
      b.add.disabled = isFull;
    });
    addButton.disabled = isFull;
    list.hidden = !total;
    empty.hidden = !!total;
    full.hidden = !isFull;
    countLabel.hidden = total < 25;
    countLabel.textContent = `${total} of ${maxParts}`;
    countLabel.classList.toggle('full', isFull);
    paintErrors();
  }

  /* ----- errors: from saving and from the preview, by part position ----- */

  const visible = (part, name) => name !== part.editing && (attempted || part.touched.has(name));

  function paintErrors() {
    const bad = [];
    parts.forEach((part, i) => {
      let any = false;
      SPECS[part.type].fields.forEach((f) => {
        const messages = visible(part, f.name) ? part.errors[f.name] || [] : [];
        const message = messages[0] || '';
        if (f.control === 'image') {
          part.imgServer = message;
          paintImageError(part);
        } else {
          const node = part.refs[`err-${f.name}`];
          const control = part.refs[`ctl-${f.name}`];
          node.textContent = message;
          node.hidden = !message;
          if (message) control.setAttribute('aria-invalid', 'true'); else control.removeAttribute('aria-invalid');
        }
        any = any || !!message;
      });
      const whole = (part.errors.type || [])[0] || '';
      part.refs.cardError.textContent = whole;
      part.refs.cardError.hidden = !whole;
      any = any || !!whole;
      part.el.classList.toggle('invalid', any);
      if (any) bad.push({ part, index: i });
    });
    const message = listErrors[0] || '';
    listError.textContent = LIST_WORDS[message] || message;
    listError.hidden = !message || !parts.length;
    summary.replaceChildren();
    if (bad.length) {
      const note = h('p', { class: 'sys-note error se-fixnote' }, `${bad.length} ${bad.length === 1 ? 'part needs' : 'parts need'} a fix. `);
      bad.forEach(({ part, index }, n) => {
        const link = h('a', { href: `#se-p${part.key}`, text: nameOf(part, index) });
        link.addEventListener('click', (event) => { event.preventDefault(); focusPart(part, { firstInvalid: true }); });
        note.append(n ? ', ' : '', link);
      });
      summary.append(note);
    }
  }

  /** Errors as the server shapes them: { "_": [...], "<index>": { field: [...] } }. */
  function applyErrors(errors) {
    const found = errors || {};
    parts.forEach((part, i) => { part.errors = found[String(i)] || {}; });
    listErrors = found._ || [];
    paintErrors();
  }

  /** The visible-or-not problems, as the form's problems dialog lists them. Also makes every error show from now on. */
  function problems() {
    attempted = true;
    paintErrors();
    const items = [];
    if (!parts.length) items.push({ field: 'blocks', label: 'Parts', message: 'Add a part to the email.', control: addButton });
    else if (listErrors.length) items.push({ field: 'blocks', label: 'Parts', message: listError.textContent, control: addButton });
    parts.forEach((part, i) => {
      const spec = SPECS[part.type];
      const base = nameOf(part, i);
      (part.errors.type || []).forEach((message) => items.push({ field: `blocks-${i}`, label: base, message, control: part.el }));
      spec.fields.forEach((f) => {
        (part.errors[f.name] || []).forEach((message) => items.push({
          field: `blocks-${i}-${f.name}`, label: spec.fields.length > 1 ? `${base} · ${f.label}` : base, message, control: controlOf(part, f.name),
        }));
      });
    });
    return items;
  }

  const controlOf = (part, name) => part.refs[`ctl-${name}`] || $('input[type=file], button', part.refs.image) || part.el;

  function focusPart(part, { firstInvalid = false } = {}) {
    let el = part.el;
    if (firstInvalid) {
      const name = SPECS[part.type].fields.map((f) => f.name).find((n) => (part.errors[n] || []).length);
      if (name) el = controlOf(part, name);
    }
    el.focus({ preventScroll: true });
    part.el.scrollIntoView({ block: 'center', behavior: reduced.matches ? 'auto' : 'smooth' });
  }

  /* ----- adding, moving, removing ----- */

  function firstControl(part) {
    const first = SPECS[part.type].fields[0];
    if (!first) return part.el;
    return controlOf(part, first.name);
  }

  function land(el, cls) {
    el.classList.add(cls);
    void el.offsetWidth; // start from the highlighted look, then let it fade
    requestAnimationFrame(() => el.classList.remove(cls));
  }

  function clearUndo() { undo = null; undoBox.hidden = true; }

  function insert(part, index) {
    parts.splice(index, 0, part);
    const li = buildPart(part);
    list.insertBefore(li, list.children[index] || null);
    paintCounters(part);
  }

  function addPart(kind, index) {
    if (parts.length >= maxParts) return;
    const part = makePart({ type: kind });
    clearUndo();
    insert(part, index);
    chrome();
    land(part.el, 'is-new');
    firstControl(part).focus();
    part.el.scrollIntoView({ block: 'nearest', behavior: reduced.matches ? 'auto' : 'smooth' });
    say(`${typeLabel(part)} added, part ${index + 1} of ${parts.length}.`);
    changed('structure');
  }

  function flip(items) {
    if (reduced.matches) return;
    items.forEach(([el, from]) => {
      const dy = from - el.getBoundingClientRect().top;
      if (!dy) return;
      el.style.transition = 'none';
      el.style.transform = `translateY(${dy}px)`;
      void el.offsetWidth;
      el.style.transition = 'transform 180ms cubic-bezier(.2,.8,.2,1), background-color .7s ease-out';
      el.style.transform = '';
      setTimeout(() => { el.style.transition = ''; }, 220);
    });
  }

  function movePart(index, dir, pressed) {
    const j = index + dir;
    if (j < 0 || j >= parts.length) return;
    const a = parts[index];
    const b = parts[j];
    const before = [[a.el, a.el.getBoundingClientRect().top], [b.el, b.el.getBoundingClientRect().top]];
    clearUndo();
    [parts[index], parts[j]] = [b, a];
    const lo = Math.min(index, j);
    const hi = Math.max(index, j);
    list.insertBefore(parts[lo].el, parts[hi].el);
    chrome();
    flip(before);
    land(a.el, 'is-hl');
    const buttons = a.refs.buttons;
    const same = dir < 0 ? buttons.up : buttons.down;
    const other = dir < 0 ? buttons.down : buttons.up;
    (same.disabled ? other : same).focus({ preventScroll: true });
    if (!pressed) a.el.scrollIntoView({ block: 'nearest' });
    say(`${typeLabel(a)} moved to part ${j + 1}.`);
    changed('structure');
  }

  function removePart(index) {
    const part = parts[index];
    const where = nameOf(part, index);
    abortUpload(part);
    clearUndo();
    undo = { part, index, label: typeLabel(part) };
    parts.splice(index, 1);
    part.el.remove();
    if (menuState && part.el.contains(menu)) closeMenu(false);
    chrome();
    const next = parts[Math.max(0, index - 1)];
    (next ? next.el : addButton).focus({ preventScroll: true });
    say(`${typeLabel(part)} removed.`);
    undoBox.firstElementChild.textContent = `${where} removed.`;
    undoBox.hidden = false;
    changed('structure'); // the Undo stays until the next add, move or remove
  }

  function restore() {
    if (!undo || parts.length >= maxParts) return;
    const { part, index, label } = undo;
    undo = null;
    undoBox.hidden = true;
    const at = Math.min(index, parts.length);
    part.up = null;
    parts.splice(at, 0, part);
    list.insertBefore(part.el, list.children[at] || null);
    chrome();
    land(part.el, 'is-new');
    part.el.focus({ preventScroll: true });
    part.el.scrollIntoView({ block: 'nearest', behavior: reduced.matches ? 'auto' : 'smooth' });
    say(`${label} restored, part ${at + 1} of ${parts.length}.`);
    changed('structure');
  }

  $('button', undoBox).addEventListener('click', restore);

  /* ----- the card buttons ----- */

  list.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-act]');
    if (!button || button.disabled) return;
    const li = button.closest('.se-part');
    const index = parts.findIndex((p) => p.el === li);
    if (index < 0) return;
    const act = button.dataset.act;
    if (act === 'up') movePart(index, -1, true);
    else if (act === 'down') movePart(index, 1, true);
    else if (act === 'remove') removePart(index);
    else if (act === 'add') toggleMenu(button, index + 1, li);
  });

  /* ----- the Add part menu ----- */

  const items = () => $$('[role=menuitem]', menu);

  function openMenu(opener, index, anchor) {
    if (parts.length >= maxParts) return;
    closeMenu(false);
    menuState = { opener, index };
    anchor.append(menu);
    menu.hidden = false;
    menu.removeAttribute('data-up');
    const box = menu.getBoundingClientRect();
    const room = window.innerHeight - box.bottom - 64; // the save bar sits at the foot
    if (room < 0 && box.top - box.height > 60) menu.dataset.up = '';
    opener.setAttribute('aria-expanded', 'true');
    items()[0].focus();
  }

  function closeMenu(refocus = true) {
    if (!menuState) return;
    menu.hidden = true;
    menuState.opener.setAttribute('aria-expanded', 'false');
    const { opener } = menuState;
    menuState = null;
    addWrap.append(menu);
    if (refocus && opener.isConnected) opener.focus();
  }

  function toggleMenu(opener, index, anchor) {
    if (menuState?.opener === opener) closeMenu(); else openMenu(opener, index, anchor);
  }

  addButton.addEventListener('click', () => toggleMenu(addButton, parts.length, addWrap));
  addButton.addEventListener('keydown', (event) => { if (event.key === 'ArrowDown' && !menuState) { event.preventDefault(); openMenu(addButton, parts.length, addWrap); } });
  menu.addEventListener('click', (event) => {
    const item = event.target.closest('[role=menuitem]');
    if (!item) return;
    const { index } = menuState;
    closeMenu(false);
    addPart(item.dataset.type, index);
  });
  menu.addEventListener('keydown', (event) => {
    const all = items();
    const at = all.indexOf(document.activeElement);
    const go = (n) => { event.preventDefault(); all[(n + all.length) % all.length].focus(); };
    if (event.key === 'ArrowDown') go(at + 1);
    else if (event.key === 'ArrowUp') go(at - 1);
    else if (event.key === 'Home') go(0);
    else if (event.key === 'End') go(all.length - 1);
    else if (event.key === 'Escape') { event.preventDefault(); closeMenu(); } else if (event.key === 'Tab') closeMenu(false);
  });
  document.addEventListener('click', (event) => {
    if (menuState && !menu.contains(event.target) && !menuState.opener.contains(event.target)) closeMenu(false);
  });

  /* ----- placeholders: into the subject or the text part that last had focus ----- */

  form.addEventListener('focusin', (event) => {
    const el = event.target;
    if (!(el instanceof HTMLElement)) return;
    if (el === subject || el.matches('[data-place]')) { target = el; palette.hidden = false; } else if (el.matches('input, textarea') && el.closest('.se-part')) palette.hidden = true; // a link, label or alt text takes no placeholders
  });
  palette.addEventListener('click', (event) => {
    const button = event.target.closest('[data-insert]');
    if (!button) return;
    deps.insertAt(target?.isConnected ? target : subject, button.dataset.insert);
  });

  /* ----- pictures ----- */

  const abortUpload = (part) => { if (part.up) { part.up.xhr?.abort(); part.up = null; } };

  function problemWith(file) {
    if (!IMAGE_TYPES.includes(file.type)) return 'Use a JPEG, PNG or GIF.';
    if (file.size > maxBytes) return `This file is over ${megabytes(maxBytes)}. Choose a smaller one.`;
    return '';
  }

  function paintImageError(part) {
    const host = part.refs.image;
    if (!host) return;
    let node = $('.se-image-error', host);
    const message = part.imgError?.message || part.imgServer || '';
    if (!message) { node?.remove(); return; }
    if (!node) { node = h('p', { class: 'sys-error se-image-error', role: 'alert' }); host.append(node); }
    node.textContent = message;
    if (part.imgError?.retry && !$('button', node)) {
      const retry = h('button', { type: 'button', class: 'sys-btn sm link', text: 'Try again' });
      retry.addEventListener('click', () => startUpload(part, part.imgError.retry));
      node.append(' ', retry);
    }
  }

  function chooser(part, text, cls) {
    const input = h('input', { type: 'file', accept: IMAGE_TYPES.join(','), 'data-se-file': true });
    input.addEventListener('change', () => { const file = input.files?.[0]; if (file) startUpload(part, file); });
    const label = h('label', { class: cls }, input, h('span', { class: 'se-desk', text: text[0] }), h('span', { class: 'se-touch', text: text[1] }));
    return label;
  }

  function paintImage(part) {
    const host = part.refs.image;
    if (!host) return;
    const had = host.contains(document.activeElement);
    host.replaceChildren();
    let focus = null;
    if (part.up) {
      const bar = h('div', { class: 'se-bar4', 'aria-hidden': 'true' }, h('i'));
      const shown = h('span', { 'aria-hidden': 'true', text: 'Uploading 0%' });
      const status = h('span', { class: 'sr', role: 'status', text: 'Uploading' });
      const cancel = h('button', { type: 'button', class: 'sys-btn sm link', text: 'Cancel' });
      cancel.addEventListener('click', () => { abortUpload(part); paintImage(part); deps.onChange?.('image'); });
      host.append(h('div', { class: 'se-uploading' }, h('p', { class: 'se-file', text: part.up.file.name }), bar, h('div', { class: 'se-up-row' }, shown, status, cancel)));
      part.up.bar = $('i', bar); part.up.shown = shown; part.up.status = status;
      focus = cancel;
    } else if (part.data.image) {
      const src = part.thumb || `${viewBase}${part.data.image}/`;
      const img = h('img', { class: 'se-thumb', src, alt: part.data.alt || '', height: '120' });
      const replace = chooser(part, ['Replace', 'Replace'], 'sys-btn sm');
      const meta = part.file ? `${part.file.name}, ${sizeText(part.file.size)}` : 'Uploaded image';
      host.append(h('div', { class: 'se-done' }, h('div', { class: 'se-thumb-box' }, img), h('div', { class: 'se-done-info' }, h('p', { class: 'sys-muted se-file', text: meta }), replace)));
      focus = $('input', replace);
    } else {
      const zone = h('div', { class: 'se-drop' }, h('p', {}, h('span', { class: 'se-desk', text: 'Drag an image here or ' }), chooser(part, ['Choose a file', 'Choose an image'], 'sys-btn sm')));
      ['dragenter', 'dragover'].forEach((name) => zone.addEventListener(name, (event) => { event.preventDefault(); zone.setAttribute('data-over', ''); }));
      ['dragleave', 'drop'].forEach((name) => zone.addEventListener(name, (event) => { event.preventDefault(); zone.removeAttribute('data-over'); }));
      zone.addEventListener('drop', (event) => { const file = event.dataTransfer?.files?.[0]; if (file) startUpload(part, file); });
      host.append(zone, h('p', { class: 'sys-muted se-help', text: `JPEG, PNG or GIF, up to ${megabytes(maxBytes)}. Shown full width.` }));
      focus = $('input', zone);
    }
    paintImageError(part);
    if (had && focus) focus.focus({ preventScroll: true });
  }

  function startUpload(part, file) {
    abortUpload(part);
    part.touched.add('image');
    part.imgError = null;
    const bad = problemWith(file);
    if (bad) { part.imgError = { message: bad }; paintImage(part); return; }
    const xhr = new XMLHttpRequest();
    part.up = { file, xhr, last: -1 };
    paintImage(part);
    deps.onChange?.('image');
    const finish = () => { part.up = null; };
    xhr.upload.addEventListener('progress', (event) => {
      if (!event.lengthComputable || !part.up) return;
      const percent = Math.min(100, Math.round((event.loaded / event.total) * 100));
      part.up.bar.style.width = `${percent}%`;
      part.up.shown.textContent = `Uploading ${percent}%`;
      if (percent >= part.up.last + 25 || percent === 100) { part.up.last = percent; part.up.status.textContent = `Uploading ${percent}%`; }
    });
    xhr.addEventListener('load', () => {
      let data = null;
      try { data = JSON.parse(xhr.responseText); } catch { data = null; }
      finish();
      if (/\/unlock\//.test(xhr.responseURL || '') || (!data && /html/i.test(xhr.getResponseHeader?.('content-type') || ''))) { // the unlock ran out
        part.imgError = { message: 'System locked. Unlock it in another tab, then try again.', retry: file };
        paintImage(part);
        deps.onChange?.('image');
        deps.locked?.();
        return;
      }
      if (xhr.status === 200 && data?.ok) {
        part.data.image = data.id;
        part.thumb = data.url;
        part.file = { name: file.name, size: file.size };
        part.errors.image = [];
        part.imgError = null;
        paintImage(part);
        say('Image uploaded.');
        changed('image');
      } else {
        part.imgError = { message: data?.message || 'The upload did not finish. Check the connection and try again.', retry: data?.message ? null : file };
        paintImage(part);
        deps.onChange?.('image');
      }
    });
    xhr.addEventListener('error', () => {
      finish();
      part.imgError = { message: 'The upload did not finish. Check the connection and try again.', retry: file };
      paintImage(part);
      deps.onChange?.('image');
    });
    xhr.addEventListener('abort', finish);
    xhr.open('POST', uploadUrl);
    xhr.setRequestHeader('X-CSRFToken', deps.csrf());
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.setRequestHeader('X-Requested-With', 'fetch');
    const body = new FormData();
    body.append('file', file);
    xhr.send(body);
  }

  /* ----- start ----- */

  seed.forEach((raw) => { const part = makePart(raw); if (part) { parts.push(part); list.append(buildPart(part)); } });
  if (!parts.length && !form.dataset.draftId && !Object.keys(seedErrors).length) { // a blank new email starts with one empty paragraph
    const part = makePart({ type: 'paragraph' });
    parts.push(part);
    list.append(buildPart(part));
  }
  parts.forEach(paintCounters);
  chrome();
  if (Object.keys(seedErrors).length) { attempted = true; applyErrors(seedErrors); }
  sync();

  return {
    get count() { return parts.length; },
    get uploading() { return parts.some((p) => p.up); },
    get hasContent() { return parts.some((p) => SPECS[p.type].fields.some((f) => f.control !== 'image' && (p.data[f.name] || '').trim())); },
    json: () => hidden.value,
    applyErrors,
    problems,
    hasErrors: () => parts.some((p) => Object.values(p.errors).some((m) => m?.length)),
  };
}
